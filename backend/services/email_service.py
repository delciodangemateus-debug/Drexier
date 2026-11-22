import asyncio
import base64
import email
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import html
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
import urllib.parse
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import httpx

from backend.database import connect
from backend.services.billing_service import get_last_successful_payment_at
from backend.services.agent import (
    UNKNOWN_REPLY,
    draft_reply,
    check_business_availability,
    detect_message_language,
    effective_agent_instructions,
)

load_dotenv()

logger = logging.getLogger("drexier.email_service")
BUSINESS_TIMEZONE = ZoneInfo("Europe/Lisbon")
# Cache em memória e deduplicação de mensagens recebidas (Anti-Loop & Anti-Ping-Pong)
_PROCESSED_MESSAGE_IDS = set()
_IN_FLIGHT_MESSAGES: Set[Tuple[str, str, str]] = set()
_GOOGLE_SYNC_LOCKS: Dict[str, asyncio.Lock] = {}

LOOP_ACKNOWLEDGMENT_PATTERNS = [
    r"^(obrigad[oa]|obrigad[oa]!|muito obrigad[oa]|valeu|ok|ok!|de acordo|perfeito|combinado|agradecido|obg|obg!|muito obrigado!)$",
    r"^(thanks|thank you|thank you!|great thanks|ok thanks|understood|noted)$",
    r"(resposta autom[aá]tica|auto-?reply|automatic reply|out of office|aus[eê]ncia tempor[aá]ria|agradecemos o seu contacto)"
]

# Constantes de OAuth Google
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

def get_email_config() -> Dict[str, Any]:
    """Recupera as variáveis de ambiente necessárias para integrações de e-mail."""
    load_dotenv(override=False)

    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    google_redirect_uri = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/api/email/oauth/google/callback"
    ).strip()

    return {
        "google": {
            "client_id": google_client_id,
            "client_secret": google_client_secret,
            "redirect_uri": google_redirect_uri,
            "configured": bool(google_client_id and google_client_secret),
        },
    }


def _parse_utc_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if not value:
        return None
    raw_value = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def get_email_response_cutoff(integration: Dict[str, Any]) -> Optional[datetime]:
    """Define o primeiro instante em que a IA pode responder após um pagamento confirmado."""
    payment_at = _parse_utc_datetime(integration.get("last_successful_payment_at"))
    if payment_at is None:
        return None
    connected_at = _parse_utc_datetime(integration.get("created_at"))
    return max(payment_at, connected_at) if connected_at else payment_at


# ===============================================================================
# GOOGLE OAUTH2 (GMAIL)
# ==============================================================================

def build_google_auth_url(state: str) -> str:
    """Gera o link oficial do Google para conceder permissões de leitura e envio de e-mails."""
    config = get_email_config()["google"]
    if not config["client_id"]:
        raise ValueError("GOOGLE_CLIENT_ID não configurado no ficheiro .env")

    params = {
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def exchange_google_code(code: str) -> Dict[str, Any]:
    """Troca o authorization code pelo access_token e refresh_token da Google."""
    config = get_email_config()["google"]
    payload = {
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": config["redirect_uri"],
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(GOOGLE_TOKEN_URL, data=payload)
        data = res.json()
        if res.status_code != 200:
            err = data.get("error_description") or data.get("error") or "Erro na autorização com Google"
            raise ValueError(f"Falha Google OAuth: {err}")
        return data


def _decrypt_integration(row: Optional[Any]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    d = dict(row)
    from backend.services.token_crypto import decrypt_token
    if "access_token" in d and d["access_token"]:
        d["access_token"] = decrypt_token(d["access_token"])
    if "refresh_token" in d and d["refresh_token"]:
        d["refresh_token"] = decrypt_token(d["refresh_token"])
    return d


async def refresh_google_token_if_needed(integration: dict) -> str:
    """Renova o token da Google se expirado ou prestes a expirar."""
    from backend.services.token_crypto import encrypt_token, decrypt_token
    access_token = decrypt_token(integration.get("access_token", ""))
    refresh_token = decrypt_token(integration.get("refresh_token", ""))
    expires_at = integration.get("token_expires_at")

    now = time.time()
    try:
        expires_timestamp = float(expires_at) if expires_at else None
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Data de expiração do token Google inválida; reconecte a conta Gmail.") from exc
    # Se ainda tem validade (com margem de 60s), usa o atual
    if expires_timestamp and expires_timestamp > (now + 60) and access_token:
        return access_token

    if not refresh_token:
        if expires_timestamp and expires_timestamp <= now:
            raise RuntimeError("Token Google expirado e sem refresh token; reconecte a conta Gmail.")
        return access_token

    config = get_email_config()["google"]
    payload = {
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(GOOGLE_TOKEN_URL, data=payload)
        if res.status_code == 200:
            data = res.json()
            new_access_token = data.get("access_token")
            if not new_access_token:
                raise RuntimeError("Google não retornou um access token válido.")
            expires_in = data.get("expires_in", 3600)
            new_expires_at = str(now + expires_in)
            with connect() as c:
                c.execute(
                    "UPDATE email_integrations SET access_token=?, token_expires_at=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (encrypt_token(new_access_token), new_expires_at, integration["id"])
                )
            return new_access_token
        else:
            logger.warning("Falha ao renovar token Google (HTTP %s).", res.status_code)
            raise RuntimeError(
                "Não foi possível renovar a autorização Gmail. Reconecte a conta Google."
            )


async def fetch_google_user_profile(access_token: str) -> Tuple[str, str]:
    """Obtém o endereço de e-mail e nome da conta Google conectada."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.get(GOOGLE_USERINFO_URL, headers=headers)
        if res.status_code == 200:
            data = res.json()
            return data.get("email", ""), data.get("name", "")
        # Fallback via Gmail profile
        res_gmail = await client.get(f"{GMAIL_API_BASE}/profile", headers=headers)
        if res_gmail.status_code == 200:
            data = res_gmail.json()
            return data.get("emailAddress", ""), ""
    return "", ""


# Envio de e-mails Gmail
# ENVIO DE E-MAILS (GMAIL)
# ==============================================================================
# ENVIO DE E-MAILS (GMAIL) E BOTÃO DE MARCAÇÃO
# ==============================================================================

def get_public_base_url() -> str:
    """Retorna a URL pública base da aplicação para links de ação nos e-mails."""
    base = os.getenv("PUBLIC_URL") or os.getenv("APP_URL")
    if not base:
        if os.getenv("APP_ENV") == "production" or os.getenv("ENVIRONMENT") == "production":
            logger.critical("[Security SEC-04] PUBLIC_URL ou APP_URL não definida em produção! Links de agendamento podem quebrar.")
        base = "http://localhost:8000"
    return base.rstrip("/")


def build_booking_action_url(user_id: int, contact_id: int, email: str, name: str = "") -> str:
    """Gera a URL com token seguro para aceder diretamente ao campo de opções de marcação."""
    from backend.auth import create_booking_token
    token = create_booking_token(user_id, contact_id, email, name)
    return f"{get_public_base_url()}/booking?token={token}"


def build_booking_token(user_id: int, contact_id: int, email: str, name: str = "") -> str:
    """Gera apenas o token JWT de agendamento."""
    from backend.auth import create_booking_token
    return create_booking_token(user_id, contact_id, email, name)


def _build_option_confirm_links_html(
    options: List[Dict[str, Any]],
    token: str,
    base_url: str,
    sender_email: str = "",
    subject: str = "",
) -> str:
    """
    Gera cards HTML clicáveis — um por opção.
    Sem emojis e sem menções ao Gmail.
    O cliente seleciona a opção via resposta de e-mail (mailto:),
    sem ser transferido para nenhum link ou página web externa.
    """
    cards = []
    reply_to = sender_email or ""
    reply_subject = f"Re: {subject}" if subject and not subject.lower().startswith("re:") else (subject or "Marcação")

    for idx, opt in enumerate(options):
        reply_body = f"Seleciono a {opt['label']}"
        mailto_url = f"mailto:{reply_to}?subject={urllib.parse.quote(reply_subject)}&body={urllib.parse.quote(reply_body)}" if reply_to else ""
        # Link de fallback direto caso o cliente use cliente web sem suporte a mailto
        params = urllib.parse.urlencode({
            "token": token,
            "slot_id": opt["id"],
            "slot_label": opt["label"],
            "scheduled_at": opt["iso"],
        })
        fallback_confirm_url = f"{base_url}/api/booking/confirm?{params}"
        action_href = mailto_url if mailto_url else fallback_confirm_url

        cards.append(
            f'<tr><td style="padding:0 0 10px 0;">'
            f'<a href="{html.escape(action_href)}" style="'
            f'display:block;text-decoration:none;'
            f'border:2px solid #2563eb;border-radius:10px;'
            f'padding:14px 18px;background:#f0f9ff;'
            f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;">'
            f'<div style="font-size:12px;font-weight:700;color:#2563eb;'
            f'text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">'
            f'Opção {idx + 1} — Clique para selecionar</div>'
            f'<div style="font-size:15px;color:#111827;">'
            f'Dia <strong style="color:#1d4ed8;">{html.escape(opt["date"])}</strong>'
            f'&nbsp;&nbsp;às <strong style="color:#1d4ed8;">{html.escape(opt["time"])}</strong>'
            f'</div>'
            f'</a>'
            f'</td></tr>'
        )

    return (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:20px 0 8px 0;">'
        '<tr><td style="padding:0 0 8px 0;">'
        '<p style="margin:0 0 4px 0;font-size:14px;font-weight:700;color:#1e293b;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;">'
        'Selecione a sua data disponível para efectuar a marcação:</p>'
        '<p style="margin:0;font-size:12px;color:#64748b;'
        'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,sans-serif;">'
        'Clique na opção pretendida para responder ou responda a este e-mail indicando a opção (ex: "Opção 1"):</p>'
        '</td></tr>'
        + "".join(cards)
        + "</table>"
    )


def _build_option_confirm_links_plaintext(
    options: List[Dict[str, Any]],
    token: str,
    base_url: str,
) -> str:
    """Versão texto puro dos links de confirmação por opção (sem emojis e sem menções ao Gmail)."""
    lines = [
        "\n\nSelecione a sua data disponível para efectuar a marcação:\n"
        "Basta responder a este e-mail indicando o número da opção (ex: 'Opção 1'):\n"
    ]
    for idx, opt in enumerate(options):
        params = urllib.parse.urlencode({
            "token": token,
            "slot_id": opt["id"],
            "slot_label": opt["label"],
            "scheduled_at": opt["iso"],
        })
        confirm_url = f"{base_url}/api/booking/confirm?{params}"
        lines.append(f"- Opção {idx + 1}: Dia {opt['date']} às {opt['time']} (Responda 'Opção {idx + 1}'):\n{confirm_url}\n")
    return "\n".join(lines)


def create_mime_message(
    sender: str,
    to: str,
    subject: str,
    body_text: str,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    booking_url: Optional[str] = None,
    # Opções de marcação com seleção direta no Gmail
    booking_token: Optional[str] = None,
    booking_options: Optional[List[Dict[str, Any]]] = None,
    booking_business_name: str = "",
    booking_customer_name: str = "",
) -> MIMEMultipart:
    """
    Cria mensagem MIME multipart/alternative com:
      1. text/plain — fallback universal; inclui opções de resposta no Gmail
      2. text/html  — email HTML com cards clicáveis por opção no Gmail

    Quando booking_token + booking_options estão disponíveis:
      - Mostra cards/botões individuais por opção de horário NO PRÓPRIO EMAIL
      - O cliente clica para responder diretamente no Gmail (sem ser transferido para link externo)
      - O botão com link externo é REMOVIDO

    Quando apenas booking_url está disponível (outros emails, lembretes, etc.):
      - Comportamento de fallback: mostra o botão com o link
    """
    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = to
    # SEC-15: Sanitização de novas linhas para impedir Email Header Injection
    clean_subject = re.sub(r"[\r\n]+", " ", subject).strip() if subject else ""
    msg["Subject"] = clean_subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    has_options = bool(booking_token and booking_options)
    base_url = get_public_base_url()

    # ── 1. Parte texto puro ──────────────────────────────────────────────────
    plain_text = body_text
    if has_options:
        plain_text += _build_option_confirm_links_plaintext(
            booking_options, booking_token, base_url
        )
    elif booking_url and booking_url not in plain_text:
        plain_text += (
            f"\n\n----------------------------------------\n"
            f"📅 Para escolher o seu horário de marcação, aceda a:\n"
            f"{booking_url}\n"
            f"----------------------------------------"
        )
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))

    # ── 2. Parte HTML ────────────────────────────────────────────────────────
    if has_options:
        # Cards clicáveis por opção — seleção direta no próprio Gmail
        booking_block_html = _build_option_confirm_links_html(
            booking_options, booking_token, base_url, sender_email=sender, subject=subject
        )
    elif booking_url:
        # Fallback: botão oficial (com espaçamento padrão preservado para testes)
        booking_block_html = (
            f'<div style="margin: 28px 0 16px 0; text-align: left;">'
            f'<a href="{html.escape(booking_url)}" target="_blank" style="'
            f'background-color: #2563eb; color: #ffffff; padding: 13px 26px; '
            f'text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 15px; '
            f'display: inline-block; '
            f'font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif; '
            f'box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.2);">'
            f'📅 Escolher Horário de Marcação'
            f'</a></div>'
        )
    else:
        booking_block_html = ""

    html_content = (
        "<div style=\"font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
        "Helvetica, Arial, sans-serif; font-size: 15px; color: #222; line-height: 1.6;\">"
        + f"<p style=\"white-space: pre-line; margin: 0 0 16px 0;\">{html.escape(body_text)}</p>"
        + booking_block_html
        + "</div>"
    )
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    return msg


async def send_email(
    integration: dict,
    to_email: str,
    subject: str,
    body_text: str,
    thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    booking_url: Optional[str] = None,
    include_booking_options: bool = False,
) -> Dict[str, Any]:
    """
    Envia uma mensagem oficial pelo Google Gmail conectado.

    As opções para escolher horários só são entregues quando o cliente perguntar
    sobre marcações/agendamentos/disponibilidade (include_booking_options=True),
    e não em todas as mensagens.
    """
    provider = integration.get("provider")
    sender_email = integration.get("email_address")
    sender_name = integration.get("display_name")
    from_header = f"{sender_name} <{sender_email}>" if sender_name else sender_email

    if provider != "google":
        raise ValueError(f"Provedor de email desconhecido: {provider}")

    opt_token: Optional[str] = None
    opt_options: Optional[List[Dict[str, Any]]] = None

    # As opções para escolher só são entregues quando interpretado pela IA (include_booking_options=True)
    if include_booking_options and not booking_url and to_email:
        try:
            with connect() as c:
                uid = integration.get("user_id")
                if uid:
                    row = c.execute(
                        "SELECT id, user_id, name FROM contacts WHERE user_id = ? AND contact_key = ?",
                        (uid, to_email),
                    ).fetchone()
                else:
                    row = c.execute(
                        "SELECT id, user_id, name FROM contacts WHERE contact_key = ? ORDER BY id DESC LIMIT 1",
                        (to_email,),
                    ).fetchone()
                if row:
                    _uid = row["user_id"]
                    _cid = row["id"]
                    _cname = row["name"] or ""
                    opt_token = build_booking_token(_uid, _cid, to_email, _cname)
                    info_rows = c.execute(
                        "SELECT kind, title, content FROM business_info WHERE user_id=?", (_uid,)
                    ).fetchall()
                    opt_options = generate_booking_options(info_rows)
        except Exception as _exc:
            logger.debug(f"[Email Opções] Erro a preparar cards de horário: {_exc}")

    google_token = await refresh_google_token_if_needed(integration)
    mime_msg = create_mime_message(
        from_header, to_email, subject, body_text, in_reply_to, references,
        booking_url=booking_url,          # fallback apenas se não houver opções
        booking_token=opt_token,
        booking_options=opt_options,
    )
    raw_base64 = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")

    payload: Dict[str, Any] = {"raw": raw_base64}
    if thread_id:
        payload["threadId"] = thread_id

    headers = {
        "Authorization": f"Bearer {google_token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(f"{GMAIL_API_BASE}/messages/send", headers=headers, json=payload)
        if res.status_code not in (200, 201):
            logger.error(f"Erro Gmail send: {res.text}")
            raise ValueError(f"Falha ao enviar e-mail via Gmail: {res.text}")
        return res.json()


# ==============================================================================
# BLOQUEIO DE CABEÇALHOS, LIMPEZA E SINCRONIZAÇÃO (IA DREXIER)
# ==============================================================================

_EMAIL_INLINE_HEADER_PATTERN = re.compile(
    r"(?:^|\s*)(?:de|from)\s*[:：]?\s*[^,\n|]+[,\s|]+(?:para|to)\s*[:：]?\s*[^,\n|]+[,\s|]+(?:data|date|sent|enviad)\s*[:：]?\s*(?:\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{4}-\d{2}-\d{2}|[A-Za-z]{3,9},\s*\d{1,2}|\d{1,2}\s+de\s+[A-Za-zçã]+|\S+)(?:\s*(?:às|as|at)?\s*\d{1,2}(?:[:h]\d{0,2}|h\b))?[.,;\s]*",
    re.IGNORECASE,
)

_EMAIL_HEADER_LINE_PATTERN = re.compile(
    r"^\s*(?:[-*_#>\s]*)(?:"
    r"(?:de|from|para|to|cc|bcc|assunto|subject|data|date|sent|hora|time|enviad[oa]s?(\s+em|\s+a|\s+no\s+dia)?|recebid[oa]s?(\s+em|\s+a|\s+no\s+dia)?)\s*[:：]|"
    r"(?:data\s+de\s+envio|data\s+do\s+envio|data\s+do\s+e-?mail|data\s+da\s+mensagem|date\s+sent|sent\s+date|sent\s+on)\s*[:：]|"
    r"(?:\d{1,2}\s*[/-]\s*\d{1,2}(?:\s*[/-]\s*\d{2,4})?|\d{4}-\d{2}-\d{2})\s*(?:[àa]s|as|at)?\s*\d{1,2}(?::\d{2})?\s*$|"
    r"(?:de|from)\s+[^<\n]+<[^@\n]+@[^>\n]+>|"
    r"(?:para|to)\s+[^<\n]+<[^@\n]+@[^>\n]+>|"
    r"(?:data|date|sent)\s*[:：]?\s*(?:\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{4}-\d{2}-\d{2}|[A-Za-z]{3,9},\s*\d{1,2}|\d{1,2}\s+de\s+[A-Za-zçã]+)|"
    r"(?:de|from)\s*[:：]?\s*[^,\n|]+[,\s|]+(?:para|to)\s*[:：]?\s*[^,\n|]+[,\s|]+(?:data|date|sent|enviad).*|"
    r"(?:data|hora)\s+do\s+e-?mail\s*[:：]?|"
    r"[-_]{2,}\s*(?:mensagem\s+original|original\s+message|forwarded\s+message|mensagem\s+encaminhada)\s*[-_]{2,}"
    r")",
    re.IGNORECASE,
)

_EMAIL_SENT_METADATA_PATTERN = re.compile(
    r"\b(?:"
    r"enviei|envio|enviad[oa]s?(\s+em|\s+a|\s+no\s+dia)?|recebid[oa]s?(\s+em|\s+a|\s+no\s+dia)?|"
    r"data\s*[:：]|date\s*[:：]|sent\s*[:：]|"
    r"data\s+de\s+envio|data\s+do\s+envio|data\s+do\s+e-?mail|data\s+da\s+mensagem|"
    r"date\s+sent|sent\s+date|sent\s+on|"
    r"hora\s+de\s+envio|hora\s+do\s+envio|hora\s+do\s+e-?mail|"
    r"(?:de|from)\s*[:：]?\s*[^,\n|]+[,\s|]+(?:para|to)\s*[:：]?\s*[^,\n|]+[,\s|]+(?:data|date|sent|enviad)"
    r")\b",
    re.IGNORECASE,
)

_EMAIL_QUOTE_START_PATTERN = re.compile(
    r"^(?:>+\s*)?"
    r"(?:"
    r".*?\b(?:escreveu|wrote|schrieb|a\s+écrit|escribió)\s*[:：]?\s*$"
    r"|"
    r"(?:em|no\s+dia|a|às|on|le|am)\s+[^,\n]+(?:<.+@.+>|\(.+@.+\)).+?[:：]\s*$"
    r"|"
    r"[-_]{2,}\s*(?:mensagem\s+original|original\s+message|forwarded\s+message|mensagem\s+encaminhada|mensagem\s+reencaminhada)\s*[-_]{2,}"
    r"|"
    r"\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}.+?<.+@.+>[:：]\s*$"
    r"|"
    r"_{10,}"
    r")",
    re.IGNORECASE,
)

_EMAIL_QUOTE_LINE_PATTERN = re.compile(
    r"(?:^(?:on\s+.+\s+wrote:|em\s+.+\s+escreveu:|no\s+dia\s+.+escreveu:|a\s+.+escreveu:|às\s+.+escreveu:|.+<.+@.+>\s+escreveu.*:)|"
    r"\b(?:escreveu|wrote|schrieb|a écrit|escribió)\b.*:\s*$|"
    r"^\s*[-_]{3,}.*[-_]{3,}\s*$)",
    re.IGNORECASE,
)

def strip_email_headers(text: str) -> str:
    """Bloqueia e remove completamente quaisquer linhas ou trechos de cabeçalho, data de envio e citações de mensagens anteriores."""
    if not text:
        return ""
    cleaned = _EMAIL_INLINE_HEADER_PATTERN.sub("", str(text))
    lines = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Se encontrou o início de citação (ex: "em sex., 20 de nov ... escreveu :"), corta tudo dali para baixo
        if (
            _EMAIL_QUOTE_START_PATTERN.match(stripped)
            or _EMAIL_QUOTE_LINE_PATTERN.match(stripped)
            or any(pat.search(stripped) for pat in QUOTE_HEADER_PATTERNS)
            or _EMAIL_QUOTE_MARKER_PATTERN.match(stripped)
        ):
            break
        if _EMAIL_HEADER_LINE_PATTERN.match(stripped):
            continue
        if stripped.startswith(">"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()

QUOTE_HEADER_PATTERNS = [
    re.compile(r"\b(?:escreveu|wrote|schrieb|a écrit|escribió)\b.*:\s*$", re.IGNORECASE),
    re.compile(r"^.*<.+@.+>\s+escreveu.*:\s*$", re.IGNORECASE),
    re.compile(r"^On\s+.+wrote:\s*$", re.IGNORECASE),
    re.compile(r"^Em\s+.+escreveu:\s*$", re.IGNORECASE),
    re.compile(r"^No\s+dia\s+.+escreveu:\s*$", re.IGNORECASE),
    re.compile(r"^A\s+.+escreveu:\s*$", re.IGNORECASE),
    re.compile(r"^Às\s+.+escreveu:\s*$", re.IGNORECASE),
    re.compile(r"^-+\s*(?:original message|mensagem original|forwarded message|mensagem reencaminhada|mensagem encaminhada)\s*-+", re.IGNORECASE),
    re.compile(r"^\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}\s*(?:GMT.*)?\s*<.+@.+>:\s*$", re.IGNORECASE),
]

_STATED_NAME_PATTERNS = [
    re.compile(r"\b(?:o\s+)?meu\s+nome\s+[eé]\s+([A-Za-zÀ-ÿ]{2,}(?:\s+[A-Za-zÀ-ÿ]{2,}){0,3})\b", re.IGNORECASE),
    re.compile(r"\b(?:chamo\s*-?\s*me|me\s+chamo)\s+([A-Za-zÀ-ÿ]{2,}(?:\s+[A-Za-zÀ-ÿ]{2,}){0,3})\b", re.IGNORECASE),
    re.compile(r"\bsou\s+(?:o\s+|a\s+)?([A-Za-zÀ-ÿ]{2,}(?:\s+[A-Za-zÀ-ÿ]{2,}){0,3})\b", re.IGNORECASE),
    re.compile(r"\baqui\s+[eé]\s+(?:o\s+|a\s+)?([A-Za-zÀ-ÿ]{2,}(?:\s+[A-Za-zÀ-ÿ]{2,}){0,3})\b", re.IGNORECASE),
    re.compile(r"\bnome(?:\s+(?:para|de|da)\s+(?:marca[çc][aã]o|agendamento|reserva|registo|registro))?\s*[:：]\s*([A-Za-zÀ-ÿ]{2,}(?:\s+[A-Za-zÀ-ÿ]{2,}){0,3})\b", re.IGNORECASE),
    re.compile(r"\bmy\s+name\s+is\s+([A-Za-zÀ-ÿ]{2,}(?:\s+[A-Za-zÀ-ÿ]{2,}){0,3})\b", re.IGNORECASE),
    re.compile(r"\b(?:i\s+am|i'm)\s+([A-Za-zÀ-ÿ]{2,}(?:\s+[A-Za-zÀ-ÿ]{2,}){0,3})\b", re.IGNORECASE),
    re.compile(r"\bname\s*[:：]\s*([A-Za-zÀ-ÿ]{2,}(?:\s+[A-Za-zÀ-ÿ]{2,}){0,3})\b", re.IGNORECASE),
    re.compile(r"\b(?:me\s+llamo|mi\s+nombre\s+es)\s+([A-Za-zÀ-ÿ]{2,}(?:\s+[A-Za-zÀ-ÿ]{2,}){0,3})\b", re.IGNORECASE),
    re.compile(r"\b(?:je\s+m'appelle|mon\s+nom\s+est)\s+([A-Za-zÀ-ÿ]{2,}(?:\s+[A-Za-zÀ-ÿ]{2,}){0,3})\b", re.IGNORECASE),
    re.compile(r"\b(?:ich\s+hei[ßs]e|mein\s+name\s+ist)\s+([A-Za-zÀ-ÿ]{2,}(?:\s+[A-Za-zÀ-ÿ]{2,}){0,3})\b", re.IGNORECASE),
    re.compile(r"\b(?:mi\s+chiamo|il\s+mio\s+nome\s+[eè])\s+([A-Za-zÀ-ÿ]{2,}(?:\s+[A-Za-zÀ-ÿ]{2,}){0,3})\b", re.IGNORECASE),
]

_SIGN_OFF_NAME_PATTERN = re.compile(
    r"(?:atenciosamente|com\s+os\s+melhores\s+cumprimentos|cumprimentos|obrigad[oa]|abra[çc]o|grato|grata|best\s+regards|regards|sincerely|cordialmente|saludos|cordialement|mit\s+freundlichen\s+gr[üu][ßs]en)\s*[,.]?\s*\n\s*([A-Za-zÀ-ÿ]{2,}(?:\s+[A-Za-zÀ-ÿ]{2,}){0,3})\s*$",
    re.IGNORECASE,
)

def extract_stated_name_from_text(text: str) -> Optional[str]:
    """Extrai o nome do cliente apenas se ele tiver escrito o seu nome no corpo da mensagem.
    
    Nunca extrai de cabeçalhos de envio de email.
    """
    cleaned = strip_email_headers(text)
    if not cleaned:
        return None
    for pattern in _STATED_NAME_PATTERNS:
        m = pattern.search(cleaned)
        if m:
            candidate = m.group(1).strip().strip(".,:;!?-")
            if candidate and len(candidate.split()) <= 4:
                if candidate.lower() not in ("sim", "nao", "não", "yes", "no", "ok", "consulta", "marcação"):
                    return candidate.title() if candidate.islower() else candidate
    m_sign = _SIGN_OFF_NAME_PATTERN.search(cleaned)
    if m_sign:
        candidate = m_sign.group(1).strip().strip(".,:;!?-")
        if candidate and len(candidate.split()) <= 4:
            if candidate.lower() not in ("sim", "nao", "não", "yes", "no", "ok", "consulta", "marcação"):
                return candidate.title() if candidate.islower() else candidate

    words = cleaned.strip().split()
    if 1 <= len(words) <= 3 and all(w.isalpha() for w in words):
        lowered = cleaned.lower().strip()
        excluded_words = {
            "sim", "nao", "não", "yes", "no", "ok", "okay", "certo", "obrigado", "obrigada",
            "bom", "boa", "dia", "tarde", "noite", "olá", "ola", "oi", "hello", "hi",
            "quarta", "quinta", "sexta", "sabado", "sábado", "domingo", "segunda",
            "amanha", "amanhã", "hoje", "marcação", "agendamento", "consulta", "visita"
        }
        if not any(w.lower() in excluded_words for w in words):
            return cleaned.strip().title() if cleaned.islower() else cleaned.strip()

    return None

CONFIRMATION_COMMANDS = {
    "pt": {
        "yes": "sim",
        "no": "não",
        "question": "Deseja prosseguir e confirmar a marcação?",
        "instruction": "Para responder, utilize os seguintes comandos obrigatórios: responda \"sim\" para confirmar a marcação ou \"não\" para não prosseguir.",
    },
    "en": {
        "yes": "yes",
        "no": "no",
        "question": "Do you want to proceed and confirm this booking?",
        "instruction": "To reply, please use the mandatory commands: reply \"yes\" to confirm the booking or \"no\" to not proceed.",
    },
    "es": {
        "yes": "sí",
        "no": "no",
        "question": "¿Desea proceder y confirmar la reserva?",
        "instruction": "Para responder, por favor utilice los comandos obligatorios: responda \"sí\" para confirmar la reserva o \"no\" para no continuar.",
    },
    "fr": {
        "yes": "oui",
        "no": "non",
        "question": "Souhaitez-vous procéder et confirmer la réservation ?",
        "instruction": "Pour répondre, veuillez utiliser les commandes obligatoires : répondez \"oui\" pour confirmer la réservation ou \"non\" pour ne pas continuer.",
    },
    "de": {
        "yes": "ja",
        "no": "nein",
        "question": "Möchten Sie fortfahren und die Buchung bestätigen?",
        "instruction": "Zur Antwort verwenden Sie bitte die verbindlichen Befehle: antworten Sie mit \"ja\", um die Buchung zu bestätigen, oder \"nein\", um nicht fortzufahren.",
    },
    "it": {
        "yes": "sì",
        "no": "no",
        "question": "Desidera procedere e confermare la prenotazione?",
        "instruction": "Per rispondere, si prega di utilizzare i comandi obbligatori: risponda \"sì\" per confermare la prenotazione o \"no\" per non procedere.",
    },
}

def _safe_invalidate_dashboard_cache(user_id: int):
    try:
        from backend.main import invalidate_dashboard_cache
        invalidate_dashboard_cache(user_id)
    except Exception:
        pass


def clean_email_body(body: str) -> str:
    """Limpa assinaturas, citações antigas e cabeçalhos de envio de email.
    
    Bloqueia completamente qualquer cabeçalho de envio (De, Para, Data, Assunto, data de envio).
    """
    if not body:
        return ""
    cleaned = _EMAIL_INLINE_HEADER_PATTERN.sub("", str(body))
    clean_lines = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Se encontrou início de citação / histórico de resposta anterior (ex: "em sex., 20 de nov ... escreveu :"), interrompe imediatamente
        if (
            _EMAIL_QUOTE_START_PATTERN.match(stripped)
            or _EMAIL_QUOTE_LINE_PATTERN.match(stripped)
            or any(pat.search(stripped) for pat in QUOTE_HEADER_PATTERNS)
            or _EMAIL_QUOTE_MARKER_PATTERN.match(stripped)
        ):
            break
        # Cabeçalhos e datas de envio de e-mail são SEMPRE descartados
        if _EMAIL_HEADER_LINE_PATTERN.match(stripped):
            continue
        if stripped.startswith(">"):
            continue
        clean_lines.append(line)
    result = "\n".join(clean_lines).strip()
    return result


def parse_sender_info(raw_from: str) -> Tuple[str, str]:
    """Extrai endereço de email e nome do remetente a partir do cabeçalho From."""
    name, email_addr = email.utils.parseaddr(raw_from)
    # Se o nome estiver codificado (ex: RFC 2047)
    if name:
        decoded_parts = decode_header(name)
        pieces = []
        for content, encoding in decoded_parts:
            if isinstance(content, bytes):
                pieces.append(content.decode(encoding or "utf-8", errors="replace"))
            else:
                pieces.append(str(content))
        name = "".join(pieces).strip()
    return email_addr.lower().strip(), name.strip()


def extract_gmail_body(payload: dict) -> str:
    """Extrai texto do corpo de mensagens do Gmail, inclusive em estruturas multipart aninhadas."""
    if not payload:
        return ""
    mime_type = payload.get("mimeType", "")
    data_str = payload.get("body", {}).get("data", "")
    if data_str and mime_type == "text/plain":
        try:
            return base64.urlsafe_b64decode(data_str + "==").decode("utf-8", errors="replace")
        except Exception:
            pass

    parts = payload.get("parts", [])
    # 1. Tenta encontrar text/plain primeiro
    for part in parts:
        if part.get("mimeType") == "text/plain":
            p_data = part.get("body", {}).get("data", "")
            if p_data:
                try:
                    return base64.urlsafe_b64decode(p_data + "==").decode("utf-8", errors="replace")
                except Exception:
                    pass
        elif "parts" in part:
            sub = extract_gmail_body(part)
            if sub:
                return sub

    # 2. Se não encontrou text/plain, tenta text/html e limpa tags
    for part in parts:
        if part.get("mimeType") == "text/html":
            p_data = part.get("body", {}).get("data", "")
            if p_data:
                try:
                    html_raw = base64.urlsafe_b64decode(p_data + "==").decode("utf-8", errors="replace")
                    clean = re.sub(r"<[^>]+>", " ", html_raw)
                    return html.unescape(clean)
                except Exception:
                    pass

    # Fallback se a raiz tiver data
    if data_str:
        try:
            raw = base64.urlsafe_b64decode(data_str + "==").decode("utf-8", errors="replace")
            if "html" in mime_type:
                return html.unescape(re.sub(r"<[^>]+>", " ", raw))
            return raw
        except Exception:
            pass

    return ""


# ==============================================================================
# FILTRO INTELIGENTE ANTI-SPAM / ANTI-PUBLICIDADE & DETEÇÃO DE CLIENTES REAIS
# ==============================================================================

IGNORED_SENDER_PATTERNS = [
    r"no-?reply", r"donotreply", r"do-not-reply", r"notification", r"newsletter",
    r"promo", r"marketing", r"alerts?", r"billing", r"security", r"accounts?",
    r"mailer-daemon", r"postmaster", r"bounce", r"system@", r"support-ticket",
    r"automated", r"updates?@", r"news@"
]

IGNORED_DOMAINS = [
    "facebookmail.com", "instagram.com", "twitter.com", "x.com", "linkedin.com",
    "pinterest.com", "tiktok.com", "google.com", "accounts.google.com",
    "appleid.apple.com", "accountprotection.microsoft.com", "github.com",
    "notifications.", "email.aliexpress.com", "mercadolivre.", "uber.com",
    "spotify.com", "netflix.com", "cloudflare.com"
]

IGNORED_SUBJECT_OR_BODY_PATTERNS = [
    r"c[oó]digo\s+de\s+(verifica[çc][aã]o|seguran[çc]a|acesso)",
    r"verification\s+code",
    r"security\s+code",
    r"one-time\s+password",
    r"\bOTP\b",
    r"login\s+detectado",
    r"in[ií]cio\s+de\s+sess[aã]o",
    r"novo\s+acesso",
    r"new\s+sign-in",
    r"redefinir\s+(a\s+)?senha",
    r"password\s+reset",
    r"recupera[çc][aã]o\s+de\s+conta",
    r"confirme\s+o\s+seu\s+(endere[çc]o\s+de\s+)?e-?mail",
    r"confirm\s+your\s+email",
    r"fatura\s+dispon[ií]vel",
    r"extrato\s+(mensal|banc[aá]rio)",
    r"comprovativo\s+de\s+pagamento",
    r"recibo\s+da\s+transa[çc][aã]o",
    r"atualiza[çc][aã]o\s+(dos?\s+)?termos",
    r"pol[ií]tica\s+de\s+privacidade\s+atualizada",
    r"unsubscribe",
    r"descadastre-se",
    r"cancelar\s+subscri[çc][aã]o",
    r"desconto\s+exclusivo",
    r"black\s+friday",
    r"cup[oõ]es?\s+de\s+desconto",
    r"oferta\s+especial"
]

def is_genuine_customer_inquiry(
    sender_email: str,
    customer_name: str,
    subject: str,
    body: str,
    headers_map: Optional[Dict[str, str]] = None,
    label_ids: Optional[List[str]] = None
) -> Tuple[bool, str]:
    """
    Filtro rígido anti-spam, anti-publicidade e anti-notificação.
    Garante que a IA NÃO gasta tokens respondendo anúncios, atualizações, redes sociais
    ou códigos de verificação, focando estritamente em clientes humanos reais que fizeram perguntas.
    """
    sender_email = sender_email.lower().strip()
    subject_clean = (subject or "").strip()
    body_clean = (body or "").strip()
    combined_text = f"{subject_clean}\n{body_clean}".lower()
    headers_map = headers_map or {}
    label_ids = [lbl.upper() for lbl in (label_ids or [])]

    # 1. Filtro por Categorias/Labels do Gmail (ignora spam e promoções; atualizações podem conter mensagens legítimas de formulários/clientes)
    forbidden_labels = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "SPAM", "TRASH"}
    found_forbidden = forbidden_labels.intersection(label_ids)
    if found_forbidden:
        return False, f"Categoria de publicidade ou spam ({', '.join(found_forbidden)})"

    # 2. Cabeçalhos de envio automatizado ou marketing
    if headers_map.get("list-unsubscribe"):
        return False, "Newsletter ou marketing comercial (List-Unsubscribe)"
    precedence = headers_map.get("precedence", "").lower()
    if precedence in ("bulk", "list", "junk"):
        return False, f"Envio em massa ({precedence})"
    auto_submitted = headers_map.get("auto-submitted", "").lower()
    if auto_submitted and auto_submitted != "no":
        return False, f"E-mail automático gerado por sistema ({auto_submitted})"
    if headers_map.get("x-autoreply") or headers_map.get("x-autorespond"):
        return False, "Resposta automática de ausência (X-Autoreply)"

    # 3. Remetentes conhecidos por marketing, alertas ou bots
    for pat in IGNORED_SENDER_PATTERNS:
        if re.search(pat, sender_email, re.IGNORECASE):
            return False, f"Remetente automatizado ({pat})"

    domain = sender_email.split("@")[-1] if "@" in sender_email else ""
    for ign_dom in IGNORED_DOMAINS:
        if ign_dom in domain:
            return False, f"Plataforma institucional de notificações ({ign_dom})"

    # 4. Padrões de assunto e corpo (códigos, 2FA, faturas, promoções)
    for pat in IGNORED_SUBJECT_OR_BODY_PATTERNS:
        if re.search(pat, combined_text, re.IGNORECASE):
            return False, f"Conteúdo de publicidade, código de segurança ou notificação ({pat})"

    # 5. Validação de mensagem legível de cliente
    if len(body_clean) < 3 and len(subject_clean) < 3:
        return False, "Mensagem vazia ou sem texto inteligível"

    human_indicators = [
        r"\b(ol[aá]|oi|bom dia|boa tarde|boa noite|prezados?|caros?)\b",
        r"\?",
        r"\b(gostaria|queria|quanto|pre[çc]o|valor|or[çc]amento|hor[aá]rio|dispon[ií]vel|marcar|marca[çc][aã]o|agendar|agendamento|reserva|vaga)\b",
        r"\b(como funciona|voc[eê]s?|fazem|trabalham|atendem|servi[çc]os?|produtos?|ajuda|informa[çc][aã]o|d[uú]vida|reclama[çc][aã]o|problema|encomenda|comprar)\b"
    ]
    has_human_intent = any(re.search(ind, combined_text, re.IGNORECASE) for ind in human_indicators)
    if not has_human_intent and len(body_clean) < 15 and "?" not in combined_text:
        return False, "E-mail sem pergunta ou saudação de cliente identificável"

    return True, "Mensagem válida de cliente"


def detect_booking_or_purchase_intent(incoming_content: str, subject: str) -> Optional[Dict[str, str]]:
    """
    Identifica automaticamente se a mensagem do cliente contém intenção de marcação,
    agendamento, reserva ou compra/encomenda que necessita de validação do proprietário.
    Aceita linguagem natural portuguesa sem exigir formatos rígidos de data/hora.
    """
    text = f"{subject}\n{incoming_content}".lower()

    booking_patterns = [
        # Verbos de marcação/agendamento (núcleo semântico)
        r"\b(marcar|marca[çc][aã]o|agendar|agendamento|reservar?|reserva|combinar|visita)\b",
        r"\b(disponibilidade\s+(para|no|na|em)|vaga\s+(para|no|na|em)|hor[aá]rio\s+(para|dispon[ií]vel))\b",
        # Combinações naturais com dias ou horas
        r"\b(segunda|ter[çc]a|quarta|quinta|sexta|s[aá]bado|domingo)(-feira)?\b.*(\b[aà]s\s+\d{1,2}(h|:\d{2})?|\bmanh[aã]|\btarde|\bnoite)",
        r"\b(\d{1,2}[/-]\d{1,2}|\d{1,2}\s+de\s+[a-z]+)\b.*(\b[aà]s\s+\d{1,2}|\bhor[aá]rio)",
        r"\b(amanhã|amanha|hoje|próxima?\s+semana|semana\s+que\s+vem)\b.*(\b[aà]s\s+\d{1,2}|\bconsulta|\batendimento|\bsess[aã]o|\breuni[aã]o|\bvisita)",
        r"\b(?:dia|no dia)?\s*\d{1,2}\b.*(\b[aà]s\s+\d{1,2}|\bhor[aá]rio|\bpelas?\s+\d{1,2}|\bhoras?\b)",
        r"\b(?:[aà]s|pelas?)\s*\d{1,2}(?::\d{2}|h\d{0,2})?\b.*(\bdia\s+\d{1,2}|\bno\s+dia|\bsegunda|\bter[çc]a|\bquarta|\bquinta|\bsexta|\bs[aá]bado|\bdomingo|\bamanh[aã])",
        r"(\b[aà]s\s+\d{1,2}|\bpelas?\s+\d{1,2}).*(\bsegunda|\bter[çc]a|\bquarta|\bquinta|\bsexta|\bs[aá]bado|\bdomingo)",
        r"\b(?:pode\s+ser|prefiro|gostaria|quero|pretendo)\b.*(\b\d{1,2}[h:]|\b[aà]s\s+\d{1,2}|\bamanh[aã]|\bsegunda|\bter[çc]a|\bquarta|\bquinta|\bsexta|\bs[aá]bado|\bdomingo|\bdia\s+\d{1,2})",
        # Seleção de opção de marcação oferecida anteriormente no Gmail
        r"\b(op[cç][aã]o\s*\d+|seleciono\s+(a\s+)?op[cç][aã]o|escolho\s+(a\s+)?op[cç][aã]o|fico\s+com\s+(a\s+)?op[cç][aã]o)\b",
    ]

    purchase_patterns = [
        r"\b(comprar|compra|adquirir|encomendar?|encomenda)\b",
        r"\b(fechar\s+(o\s+)?pedido|fechar\s+(o\s+)?or[çc]amento|quero\s+contratar|quero\s+o\s+produto|quero\s+comprar|quero\s+adquirir)\b",
        r"\b(confirmar\s+(o\s+)?pedido|confirmo\s+(o\s+)?pedido|confirmo|confirmar\s+(a\s+)?compra|confirmo\s+(a\s+)?compra|pode\s+fechar)\b",
    ]

    for pat in booking_patterns:
        if re.search(pat, text, re.IGNORECASE):
            return {"type": "booking", "details": incoming_content[:300].strip()}

    for pat in purchase_patterns:
        if re.search(pat, text, re.IGNORECASE):
            return {"type": "purchase", "details": incoming_content[:300].strip()}

    return None


BOOKING_INQUIRY_PATTERNS = [
    r"\b(marcar|marca[çc][aã]o|marca[çc][oõ]es|agendar|agendamento|agendamentos|reservar?|reserva|reservas)\b",
    r"\b(?:hor[aá]rios?|datas?|vagas?)\s+dispon[ií]ve(?:l|is)\b",
    r"\bdisponibilidade\s+(?:de\s+)?(?:hor[aá]rios?|datas?|marca[çc][aã]o|agendamento|vagas?)\b",
    r"\b(quando\s+(?:posso|podemos|t[eê]m|h[aá])\s+(?:marcar|agendar|ir|passar))\b",
    r"\b(tem\s+vaga|h[aá]\s+vaga|tem\s+hor[aá]rio|h[aá]\s+hor[aá]rio)\b",
    r"\b(marcar\s+hora|agendar\s+hora|marcar\s+um\s+dia|agendar\s+um\s+dia|marcar\s+atendimento)\b",
    r"\b(consulta|sess[aã]o|visita|atendimento)\b.*(marcar|agendar|quando|hor[aá]rio|vaga)",
    r"(marcar|agendar|quando|hor[aá]rio|vaga).*(consulta|sess[aã]o|visita|atendimento)",
    r"\b(book|booking|appointment|schedule)\b",
]

def is_booking_inquiry(
    incoming_content: str,
    subject: str = "",
    reply_text: Optional[str] = None,
    intent: Optional[Dict[str, str]] = None,
    waiting_for_schedule: bool = False,
    has_specific_schedule: bool = False,
) -> bool:
    """
    Determina segundo a interpretação da IA se a mensagem do cliente é uma pergunta
    ou pedido sobre marcações, agendamentos ou disponibilidade de horários.
    As opções de escolha de data só são entregues nestas mensagens, não em todas.
    """
    if has_specific_schedule:
        return False

    if waiting_for_schedule:
        return True

    if intent and intent.get("type") == "booking":
        return True

    combined = f"{subject or ''}\n{incoming_content or ''}".lower()
    for pat in BOOKING_INQUIRY_PATTERNS:
        if re.search(pat, combined, re.IGNORECASE):
            return True

    if reply_text:
        rt = reply_text.lower()
        if any(w in rt for w in (
            "horários disponíveis", "horarios disponiveis",
            "para efetuar a marcação", "para efectuar a marcação",
            "agendar um horário", "agendar um horario",
            "marcar uma consulta", "marcar um atendimento"
        )):
            return True

    return False


_EXPLICIT_NEGATIVE_PATTERN = re.compile(
    r"\b(?:n[ãa]o\s+(?:confirmo|quero|posso|d[áa]|pretendo|consigo|vou|interessa|aceito)|"
    r"nao\s+(?:confirmo|quero|posso|da|pretendo|consigo|vou)|"
    r"n[ãa]o\s*,\s*(?:obrigad[oa]|prefiro|desisto|cancelo)|"
    r"cancelo|cancelar|cancele|cancelamento|desistir|desisti|desisto|"
    r"prefiro\s+outro|recusar|recuso|nope|not\s+now|not\s+interested|"
    r"don'?t\s+confirm|non|nein)\b",
    re.IGNORECASE,
)

_POSITIVE_CONFIRMATION_PATTERN = re.compile(
    r"\b(?:sim|s[ií]m|confirmo|confirmado|confirmada|confirmar|confirma|confirme|confirmem|"
    r"quero\s+(?:prosseguir|continuar|confirmar|fechar)|"
    r"pode\s+(?:confirmar|marcar|agendar|seguir|ser|avan[cç]ar|fechar|registar|registrar)|"
    r"prosseguir|continuar|avan[cç]ar|combinad[oa]|de\s+acordo|"
    r"concordo|aceito|est[áa]\s+(?:bem|combinad[oa]|fechad[oa]|cert[oa]|perfeit[oa]|marcad[oa]|agendad[oa]|o?timo|ótimo)|"
    r"esta\s+(?:bem|combinad[oa]|fechad[oa]|cert[oa]|perfeit[oa]|marcad[oa]|agendad[oa]|o?timo|ótimo)|"
    r"por\s+mim\s+(?:tudo\s+bem|est[áa]\s+(?:bem|o?timo|ótimo|perfeito|fechado)|pode\s+ser)|"
    r"tudo\s+(?:bem|certo|ok|perfeito)|ok|okay|claro|"
    r"claro\s+que\s+sim|com\s+certeza|sem\s+d[úu]vida|isso\s+mesmo|isso|exato|correto|certo|"
    r"fechado|vamos\s+l[áa]|vamos|segue|seguir|top|perfeito|obrigad[oa]|valeu|obg|"
    r"yes|yeah|confirmed|confirm|go\s+ahead|sure|all\s+good|sounds\s+good|oui|ja|s[ií])\b",
    re.IGNORECASE,
)


def detect_client_confirmation(content: str) -> Optional[str]:
    """Deteta a resposta do cliente aos comandos obrigatórios de confirmação da marcação.

    Reconhece comandos afirmativos ("sim", "yes", "sí", "oui", "ja") e negativos ("não", "no", "non", "nein").
    """
    positive_cmds = {"sim", "sím", "yes", "yeah", "oui", "ja", "si", "sí", "da"}
    negative_cmds = {"nao", "não", "no", "nope", "cancel", "non", "nein"}

    # --- camada 1: texto limpo ---
    text = clean_email_body(content or "").strip()

    if not text:
        for raw_line in (content or "").splitlines():
            stripped_line = raw_line.strip()
            if stripped_line and not stripped_line.startswith(">"):
                text = stripped_line
                break
    if not text:
        return None

    clean_punct = re.sub(r"[^\w\s]", "", text.lower()).strip()
    if clean_punct in negative_cmds:
        return "negative"
    if clean_punct in positive_cmds:
        return "positive"
    if _EXPLICIT_NEGATIVE_PATTERN.search(text):
        return "negative"
    if _POSITIVE_CONFIRMATION_PATTERN.search(text):
        return "positive"

    # --- camada 3: verifica o raw original para garantir que o comando não escapa ---
    raw_text = (content or "").strip()
    raw_clean_punct = re.sub(r"[^\w\s]", "", raw_text.lower()).strip()
    if raw_clean_punct in negative_cmds:
        return "negative"
    if raw_clean_punct in positive_cmds:
        return "positive"
    if _EXPLICIT_NEGATIVE_PATTERN.search(raw_text):
        return "negative"
    if _POSITIVE_CONFIRMATION_PATTERN.search(raw_text):
        return "positive"

    return None


_BOOKING_CUE_PATTERN = re.compile(
    r"\b(marcar|marca[çc][aã]o|agendar|agendamento|reservar?|reserva|consulta|visita|"
    r"encontro|reuni[aã]o|sess[aã]o|hor[aá]rio|data e hora|escolhidas|pretendo|"
    r"gostaria|quero|desejo)\b",
    re.IGNORECASE,
)

_SCHEDULE_TIME_CUE_PATTERN = re.compile(
    r"\b(?:\d{1,2}\s*(?:h|:|horas?)|\d{1,2}:\d{2}|manh[ãa]|tarde|noite|almo[çc]o)\b",
    re.IGNORECASE,
)

_SCHEDULE_DATE_CUE_PATTERN = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|20\d{2}-\d{1,2}-\d{1,2}|"
    r"\d{1,2}\s+de\s+[a-zçã]+|dia\s+\d{1,2}|"
    r"\d{1,2}\b(?=\s*(?:às|as|pelas?)\s*\d{1,2}\s*(?:h|:))|"
    r"amanh[ãa]|hoje|depois\s+de\s+amanh[ãa]|daqui\s+a|"
    r"segunda|ter[çc]a|quarta|quinta|sexta|s[aá]bado|domingo)\b",
    re.IGNORECASE,
)

_EMAIL_SENT_METADATA_PATTERN = re.compile(
    r"\b(?:enviei|envio|enviado|enviada|data\s+de\s+envio|data\s+do\s+e-?mail|"
    r"recebid[oa]\s+em|enviad[oa]\s+em)\b",
    re.IGNORECASE,
)

_EMAIL_QUOTE_MARKER_PATTERN = re.compile(
    r"^(?:on\s+.+\s+wrote:|em\s+.+\s+escreveu:|no\s+dia\s+.+escreveu:|a\s+.+escreveu:|às\s+.+escreveu:|.+<.+@.+>\s+escreveu.*:|-+\s*(?:original message|mensagem original|forwarded message|mensagem encaminhada)\s*-+|\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}.+<.+@.+>:)",
    re.IGNORECASE,
)

_EMAIL_SIGNATURE_PATTERN = re.compile(
    r"^\s*(?:enviado\s+do\s+meu|sent\s+from\s+my|obter\s+o\s+outlook|get\s+outlook)\b.*",
    re.IGNORECASE,
)


def _client_schedule_fragment(message: str) -> str:
    """Isola a frase onde o cliente escolhe a marcação, ignorando metadados do e-mail.

    A data/hora do envio da mensagem (cabeçalhos, citações, "enviei este e-mail às
    Xh", etc.) nunca deve ser usada como data/hora da marcação.
    """
    if not message:
        return ""

    cleaned = strip_email_headers(clean_email_body(str(message)))
    if not cleaned:
        return ""

    segments = re.split(r"(?<=[.;!?\n])|,", cleaned)
    kept_segments = []
    for segment in segments:
        candidate = segment.strip()
        if not candidate:
            continue
        if (
            _EMAIL_SENT_METADATA_PATTERN.search(candidate)
            or _EMAIL_HEADER_LINE_PATTERN.match(candidate)
            or _EMAIL_QUOTE_START_PATTERN.match(candidate)
            or _EMAIL_QUOTE_LINE_PATTERN.match(candidate)
        ):
            continue
        if _EMAIL_SIGNATURE_PATTERN.search(candidate):
            continue
        kept_segments.append(candidate)

    if not kept_segments:
        return ""

    last_cue_index = None
    for index, candidate in enumerate(kept_segments):
        if _BOOKING_CUE_PATTERN.search(candidate):
            last_cue_index = index
    if last_cue_index is not None:
        cue = _BOOKING_CUE_PATTERN.search(kept_segments[last_cue_index])
        candidate = " ".join(
            [kept_segments[last_cue_index][cue.start():]] + kept_segments[last_cue_index + 1:]
        ).strip()
        if (
            _SCHEDULE_TIME_CUE_PATTERN.search(candidate)
            and _SCHEDULE_DATE_CUE_PATTERN.search(candidate)
        ):
            return candidate

    for candidate in reversed(kept_segments):
        if (
            _SCHEDULE_TIME_CUE_PATTERN.search(candidate)
            and _SCHEDULE_DATE_CUE_PATTERN.search(candidate)
        ):
            return candidate

    return "\n".join(kept_segments).strip()


def format_booking_datetime(value: Any) -> str:
    """Formata a data/hora registada (UTC) no fuso e formato usados nos avisos."""
    parsed = _parse_utc_datetime(value)
    if parsed is None:
        return ""
    return parsed.astimezone(BUSINESS_TIMEZONE).strftime("%d/%m/%Y às %H:%M")


def _extract_schedule_time(message: str) -> Optional[Tuple[int, int]]:
    """Extrai apenas a hora escolhida pelo cliente, ignorando metadados do e-mail."""
    clean_msg = re.sub(r"\bop[cç][aã]o\s*\d+\s*:\s*", "", message, flags=re.IGNORECASE)
    text = _client_schedule_fragment(clean_msg).casefold()

    hour: Optional[int] = None
    minute: int = 0

    time_match = re.search(
        r"\b(?:(?:às|as|pelas?)\s*)?(\d{1,2})\s*(?:h|:)\s*(\d{2})?\b",
        text,
    )
    if time_match:
        h = int(time_match.group(1))
        m = int(time_match.group(2) or 0)
        if 0 <= h <= 23 and 0 <= m <= 59:
            hour, minute = h, m
    else:
        hours_word_match = re.search(r"\b(\d{1,2})\s*(?:horas?|hrs?)\b", text)
        if hours_word_match:
            h = int(hours_word_match.group(1))
            if 0 <= h <= 23:
                hour, minute = h, 0
        else:
            alt_time = re.search(r"\b(?:às|as|pelas?)\s*(\d{1,2})\b", text)
            if alt_time:
                h = int(alt_time.group(1))
                if 0 <= h <= 23:
                    hour, minute = h, 0

    if hour is None:
        if re.search(r"\b(de|pela)\s+manh[aã]\b", text):
            hour, minute = 9, 0
        elif re.search(r"\bao\s+almo[çc]o\b|\bna\s+hora\s+do\s+almo[çc]o\b", text):
            hour, minute = 12, 30
        elif re.search(r"\b([àa]|pela|de)\s+tarde\b", text):
            hour, minute = 15, 0
        elif re.search(r"\b(ao\s+)?(fim|final)\s+da\s+tarde\b", text):
            hour, minute = 17, 30
        elif re.search(r"\b([àa]|pela|de)\s+noite\b", text):
            hour, minute = 20, 0

    if hour is None:
        return None

    if hour < 12 and re.search(r"\b(da|à)\s+tarde\b", text):
        hour += 12

    return hour, minute


def extract_scheduled_at(message: str, now: Optional[datetime] = None) -> Optional[str]:
    """
    Extrai a data e a hora da marcação escritas pelo cliente e retorna um
    timestamp ISO em UTC. A data/hora em que o e-mail foi enviado ou recebido
    nunca é usada: apenas a frase da mensagem onde o cliente escolhe a marcação.
    Retorna None se a data ou a hora não forem especificadas pelo cliente no corpo,
    ou se forem no passado. Suporta qualquer data futura (marcações atemporais).
    """
    from datetime import timedelta
    local_now = (now or datetime.now(BUSINESS_TIMEZONE)).astimezone(BUSINESS_TIMEZONE)
    clean_msg = re.sub(r"\bop[cç][aã]o\s*\d+\s*:\s*", "", message, flags=re.IGNORECASE)
    text = _client_schedule_fragment(clean_msg).casefold()
    if not text:
        return None

    # ── 1. Extrair hora a partir do texto limpo do cliente ───────────────────
    schedule_time = _extract_schedule_time(text)
    if schedule_time is None:
        return None
    hour, minute = schedule_time

    # ── 2. Extrair data (qualquer data futura pretendida) ────────────────────
    scheduled_date = None
    month_names = {
        "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4,
        "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
        "outubro": 10, "novembro": 11, "dezembro": 12,
        "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
        "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
    }

    try:
        iso_match = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", text)
        numeric_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", text)
        months_pattern = "|".join(re.escape(m) for m in month_names.keys())
        month_match = re.search(
            rf"\b(?:dia\s+)?(\d{{1,2}})\s+(?:de\s+)?({months_pattern})\b(?:\s+(?:de\s+)?(\d{{4}}))?",
            text,
        )
        day_match = re.search(
            r"\bdia\s+(\d{1,2})(?:\s*(?:º|°))?\b|"
            r"\b(\d{1,2})\b(?=\s*(?:às|as|pelas?)\s*\d{1,2}\s*(?:h|:))",
            text,
        )
        relative_days = re.search(r"\bdaqui\s+a?\s+(\d+)\s+(dias?|semanas?|m[eê]ses?|anos?)\b", text)
        next_week = re.search(r"\bpr[oó]xima\s+semana\b|\bsemana\s+que\s+vem\b", text)

        if iso_match:
            scheduled_date = datetime(
                int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
            ).date()
        elif numeric_match:
            day = int(numeric_match.group(1))
            month = int(numeric_match.group(2))
            yr_raw = numeric_match.group(3)
            year = int(yr_raw) if yr_raw else local_now.year
            if yr_raw and len(yr_raw) == 2:
                year = 2000 + year
            if month > 12 and day <= 12:
                day, month = month, day
            scheduled_date = datetime(year, month, day).date()
            if not yr_raw and scheduled_date < local_now.date():
                scheduled_date = scheduled_date.replace(year=year + 1)
        elif month_match:
            day = int(month_match.group(1))
            month = month_names.get(month_match.group(2))
            if month is None:
                return None
            year = int(month_match.group(3) or local_now.year)
            scheduled_date = datetime(year, month, day).date()
            if not month_match.group(3) and scheduled_date < local_now.date():
                scheduled_date = scheduled_date.replace(year=year + 1)
        elif day_match:
            day = int(day_match.group(1) or day_match.group(2))
            year, month = local_now.year, local_now.month
            scheduled_date = datetime(year, month, day).date()
            if scheduled_date < local_now.date():
                if month == 12:
                    year, month = year + 1, 1
                else:
                    month += 1
                scheduled_date = datetime(year, month, day).date()
        elif relative_days:
            qty = int(relative_days.group(1))
            unit = relative_days.group(2).lower()
            if "m" in unit and ("mês" in unit or "mes" in unit):
                delta = timedelta(days=qty * 30)
            elif "ano" in unit:
                delta = timedelta(days=qty * 365)
            elif "semana" in unit:
                delta = timedelta(weeks=qty)
            else:
                delta = timedelta(days=qty)
            scheduled_date = (local_now + delta).date()
        elif re.search(r"\bdepois\s+de\s+amanhã\b|\bdepois\s+de\s+amanha\b", text):
            scheduled_date = local_now.date() + timedelta(days=2)
        elif "amanhã" in text or "amanha" in text:
            scheduled_date = local_now.date() + timedelta(days=1)
        elif re.search(r"\bpr[oó]ximo\s+m[eê]s\b|\bm[eê]s\s+que\s+vem\b", text):
            y = local_now.year + 1 if local_now.month == 12 else local_now.year
            m = 1 if local_now.month == 12 else local_now.month + 1
            scheduled_date = datetime(y, m, min(local_now.day, 28)).date()
        elif re.search(r"\bhoje\b", text):
            scheduled_date = local_now.date()
        else:
            prefixed_next = bool(re.search(r"\bpr[oó]xim[ao]\b|\bque\s+vem\b", text))
            weekdays = (
                (("segunda",), 0), (("terça", "terca"), 1), (("quarta",), 2),
                (("quinta",), 3), (("sexta",), 4), (("sábado", "sabado"), 5),
                (("domingo",), 6),
            )
            for names, weekday in weekdays:
                if any(re.search(rf"\b{re.escape(n)}(?:\s*-?\s*feira)?\b", text) for n in names):
                    days_ahead = (weekday - local_now.weekday()) % 7
                    if prefixed_next:
                        days_ahead += 7
                    elif days_ahead == 0:
                        days_ahead = 7
                    scheduled_date = local_now.date() + timedelta(days=days_ahead)
                    break
            if scheduled_date is None and next_week:
                days_ahead = (0 - local_now.weekday()) % 7 + 7
                scheduled_date = local_now.date() + timedelta(days=days_ahead)
    except ValueError:
        return None

    if scheduled_date is None:
        return None

    local_scheduled = datetime(
        scheduled_date.year, scheduled_date.month, scheduled_date.day,
        hour, minute, tzinfo=BUSINESS_TIMEZONE,
    )
    # A data/hora em que a mensagem é enviada nunca é uma marcação.
    # Exige margem futura de pelo menos 45 minutos para evitar interpretar
    # metadados ou hora de envio do email como agendamento pretendido.
    if local_scheduled <= local_now + timedelta(minutes=45):
        return None
    return local_scheduled.astimezone(timezone.utc).isoformat()


def capture_scheduled_request(
    conn,
    user_id: int,
    contact_id: int,
    incoming_content: str,
    subject: str,
    intent: Optional[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    """Save a request as awaiting its date/time or pending with the supplied schedule."""
    waiting = conn.execute(
        """SELECT id, request_type, details FROM conversion_requests
           WHERE user_id = ? AND contact_id = ? AND status = 'awaiting_schedule'
           ORDER BY id DESC LIMIT 1""",
        (user_id, contact_id),
    ).fetchone()
    request_type = intent["type"] if intent else (waiting["request_type"] if waiting else None)
    if not request_type:
        return None

    clean_incoming = clean_email_body(incoming_content)
    clean_subject = (subject or "").strip()
    schedule_text = (
        f"{clean_subject}\n{clean_incoming}" if clean_subject else clean_incoming
    )
    scheduled_at = extract_scheduled_at(schedule_text)
    if not scheduled_at and waiting:
        schedule_text = f"{waiting['details'] or ''}\n{schedule_text}"
        scheduled_at = extract_scheduled_at(schedule_text)

    if not scheduled_at:
        # Apenas reutiliza data anterior se não for uma consulta ou intenção de nova marcação
        # (onde as opções de escolha de data devem ser apresentadas de raiz).
        if not is_booking_inquiry(incoming_content, subject):
            previous = conn.execute(
                """SELECT id, request_type, details, scheduled_at, status
                   FROM conversion_requests
                   WHERE user_id = ? AND contact_id = ? AND scheduled_at IS NOT NULL
                     AND status IN ('pending', 'awaiting_client_confirmation')
                   ORDER BY id DESC LIMIT 1""",
                (user_id, contact_id),
            ).fetchone()
            if previous and (not request_type or previous["request_type"] == request_type):
                return {
                    "id": previous["id"],
                    "request_type": previous["request_type"],
                    "status": previous["status"],
                    "scheduled_at": previous["scheduled_at"],
                    "details": previous["details"],
                }

    # Compras de produtos/pedidos não necessitam de agendamento de data/hora
    is_purchase = (request_type == "purchase")

    if not waiting and intent:
        if scheduled_at:
            existing = conn.execute(
                """SELECT id, request_type, details, status FROM conversion_requests
                   WHERE user_id = ? AND contact_id = ? AND request_type = ?
                     AND scheduled_at = ? AND status IN ('pending', 'awaiting_client_confirmation')
                   ORDER BY id DESC LIMIT 1""",
                (user_id, contact_id, request_type, scheduled_at),
            ).fetchone()
        elif is_purchase:
            existing = conn.execute(
                """SELECT id, request_type, details FROM conversion_requests
                   WHERE user_id = ? AND contact_id = ? AND request_type = ?
                     AND status = 'pending'
                   ORDER BY id DESC LIMIT 1""",
                (user_id, contact_id, request_type),
            ).fetchone()
        else:
            existing = None

        if existing:
            return {
                "id": existing["id"],
                "request_type": existing["request_type"],
                "status": existing["status"],
                "scheduled_at": scheduled_at,
                "details": existing["details"],
            }

    if waiting:
        details = waiting["details"] or ""
        if scheduled_at:
            details = f"{details}\nData e hora escolhidas pelo cliente: {incoming_content[:200]}".strip()
        else:
            details = f"{details}\nInformação adicional do cliente: {incoming_content[:200]}".strip()
        new_status = "pending" if (scheduled_at or is_purchase) else "awaiting_schedule"
        conn.execute(
            """UPDATE conversion_requests SET details = ?, scheduled_at = ?, status = ?
               WHERE id = ? AND user_id = ?""",
            (
                details,
                scheduled_at,
                new_status,
                waiting["id"],
                user_id,
            ),
        )
        return {
            "id": waiting["id"],
            "request_type": request_type,
            "status": new_status,
            "scheduled_at": scheduled_at,
            "details": details,
        }

    details = f"Assunto: {subject}\n{incoming_content[:400]}".strip()
    new_status = "pending" if (scheduled_at or is_purchase) else "awaiting_schedule"
    cursor = conn.execute(
        """INSERT INTO conversion_requests
           (user_id, contact_id, request_type, details, status, scheduled_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            contact_id,
            request_type,
            details,
            new_status,
            scheduled_at,
        ),
    )
    return {
        "id": cursor.lastrowid,
        "request_type": request_type,
        "status": new_status,
        "scheduled_at": scheduled_at,
        "details": details,
    }


def ensure_date_time_question(
    reply: str,
    need_date: bool = True,
    need_time: bool = True,
    force: bool = False,
) -> str:
    """Keep the reply focused on collecting only the schedule fields still missing."""
    has_date = re.search(r"\b(data|dia)\b", reply, re.IGNORECASE)
    has_time = re.search(r"\b(hora|horário|horario)\b", reply, re.IGNORECASE)
    if not force and (not need_date or has_date) and (not need_time or has_time):
        return reply

    if need_date and need_time:
        if not reply or not reply.strip():
            return (
                "Para registar o seu pedido, qual é a data e a hora que prefere? "
                "Por favor, indique o dia, mês e horário."
            )
        question = (
            "Para registar a sua marcação, qual é a data e a hora que prefere? "
            "Por favor, indique o dia e o horário da sua preferência."
        )
    elif need_date:
        question = (
            "Para registar a sua marcação, qual é a data que prefere? "
            "Por favor, indique o dia e o mês."
        )
    else:
        question = (
            "Para registar a sua marcação, qual é a hora que prefere? "
            "Por favor, indique o horário desejado."
        )

    if not reply or not reply.strip():
        return question
    return f"{reply.strip()}\n\n{question}"


async def sync_google_emails(user_dict: dict, integration: dict) -> List[Dict[str, Any]]:
    """Serializa sincronizações da mesma conta neste processo."""
    lock_key = str(integration.get("id") or integration.get("user_id"))
    lock = _GOOGLE_SYNC_LOCKS.setdefault(lock_key, asyncio.Lock())
    async with lock:
        return await _sync_google_emails(user_dict, integration)


async def _sync_google_emails(user_dict: dict, integration: dict) -> List[Dict[str, Any]]:
    """
    Sincroniza e-mails não lidos da caixa de entrada do Gmail,
    filtrando rigorosamente apenas mensagens principais de clientes reais.
    """
    token = await refresh_google_token_if_needed(integration)
    headers = {"Authorization": f"Bearer {token}"}
    my_email = (integration.get("email_address") or "").lower().strip()

    cutoff_at = get_email_response_cutoff(integration)
    if cutoff_at is None:
        logger.warning("Sincronização Gmail bloqueada: não há data de pagamento confirmado válida.")
        return []
    cutoff_ts = int(cutoff_at.timestamp() * 1000)

    processed_items = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        async def mark_message_read(message_id: str) -> None:
            response = await client.post(
                f"{GMAIL_API_BASE}/messages/{message_id}/modify",
                headers=headers,
                json={"removeLabelIds": ["UNREAD"]},
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Falha ao atualizar estado da mensagem Gmail (HTTP {response.status_code})."
                )

        # Busca mensagens não lidas da caixa de entrada, ignorando spam e promoções
        query = "label:INBOX is:unread -category:promotions -category:social -label:spam -label:trash"
        list_url = f"{GMAIL_API_BASE}/messages?q={urllib.parse.quote(query)}&maxResults=15"
        res = await client.get(list_url, headers=headers)
        if res.status_code != 200:
            logger.warning("Falha ao listar mensagens do Gmail (HTTP %s).", res.status_code)
            raise RuntimeError(
                f"Falha ao consultar a caixa Gmail (HTTP {res.status_code})."
            )

        messages_list = res.json().get("messages", [])
        for m in messages_list:
            msg_id = m.get("id")
            thread_id = m.get("threadId")

            # Deduplicação imediata contra repetição por eventual lag do índice Gmail ou concorrência
            processed_key = (
                "google",
                str(integration.get("id") or integration.get("email_address")),
                str(msg_id),
            )
            if processed_key in _PROCESSED_MESSAGE_IDS or processed_key in _IN_FLIGHT_MESSAGES:
                await mark_message_read(str(msg_id))
                continue

            with connect() as c:
                previously_processed = c.execute(
                    """SELECT id FROM processed_email_messages
                       WHERE user_id = ? AND provider = 'google' AND provider_message_id = ?""",
                    (user_dict["id"], str(msg_id)),
                ).fetchone()
            if previously_processed:
                _PROCESSED_MESSAGE_IDS.add(processed_key)
                await mark_message_read(str(msg_id))
                continue

            msg_res = await client.get(f"{GMAIL_API_BASE}/messages/{msg_id}?format=full", headers=headers)
            if msg_res.status_code != 200:
                if msg_res.status_code == 404:
                    continue
                raise RuntimeError(
                    f"Falha ao obter mensagem Gmail (HTTP {msg_res.status_code})."
                )

            msg_data = msg_res.json()
            label_ids = msg_data.get("labelIds", [])

            # Ignora rascunhos ou emails enviados pelo próprio sistema/utilizador para evitar auto-looping
            if "SENT" in label_ids or "DRAFT" in label_ids:
                logger.info(f"[Anti-Loop] Mensagem Gmail {msg_id} possui label SENT/DRAFT. Marcando como lida.")
                _PROCESSED_MESSAGE_IDS.add(processed_key)
                with connect() as c:
                    c.execute(
                        """INSERT OR IGNORE INTO processed_email_messages (user_id, provider, provider_message_id)
                           VALUES (?, 'google', ?)""",
                        (user_dict["id"], str(msg_id)),
                    )
                await mark_message_read(str(msg_id))
                continue

            # Filtro por data de recebimento: após pagamento e ligação da integração
            if cutoff_ts is not None:
                try:
                    internal_date = msg_data.get("internalDate")
                    if internal_date is None or int(internal_date) < cutoff_ts:
                        if internal_date is not None:
                            await mark_message_read(str(msg_id))
                            logger.info(f"E-mail Gmail {msg_id} anterior ao início da cobertura paga ignorado.")
                        continue
                except (TypeError, ValueError):
                    logger.warning(f"Data de recebimento inválida no e-mail Gmail {msg_id}; mensagem mantida sem resposta.")
                    continue

            payload = msg_data.get("payload", {})
            headers_list = payload.get("headers", [])

            headers_map = {h["name"].lower(): h["value"] for h in headers_list if "name" in h and "value" in h}
            raw_from = headers_map.get("from", "")
            subject = headers_map.get("subject", "Sem assunto")
            message_id_header = headers_map.get("message-id", "")

            sender_email, customer_name = parse_sender_info(raw_from)
            sender_lower = (sender_email or "").lower().strip()

            # Ignora se for enviado pelo próprio endereço oficial integrado (evita loop infinito com si mesmo)
            if not sender_lower or sender_lower == my_email:
                logger.info(f"[Anti-Loop] Mensagem Gmail {msg_id} enviada pelo próprio endereço ({sender_lower}). Marcando como lida.")
                _PROCESSED_MESSAGE_IDS.add(processed_key)
                with connect() as c:
                    c.execute(
                        """INSERT OR IGNORE INTO processed_email_messages (user_id, provider, provider_message_id)
                           VALUES (?, 'google', ?)""",
                        (user_dict["id"], str(msg_id)),
                    )
                await mark_message_read(str(msg_id))
                continue

            # Ignora respostas automáticas do servidor (auto-reply / out-of-office / bounce)
            auto_submitted = headers_map.get("auto-submitted", "").lower()
            x_autoreply = headers_map.get("x-autoreply", "").lower()
            if auto_submitted in ("auto-replied", "auto-generated") or x_autoreply == "yes":
                logger.info(f"[Anti-Loop] Mensagem Gmail {msg_id} é auto-resposta do servidor ({auto_submitted}). Ignorando.")
                _PROCESSED_MESSAGE_IDS.add(processed_key)
                with connect() as c:
                    c.execute(
                        """INSERT OR IGNORE INTO processed_email_messages (user_id, provider, provider_message_id)
                           VALUES (?, 'google', ?)""",
                        (user_dict["id"], str(msg_id)),
                    )
                await mark_message_read(str(msg_id))
                continue

            # Deduplicação pelo header RFC Message-ID
            if message_id_header:
                with connect() as c:
                    prev_hdr = c.execute(
                        """SELECT id FROM processed_email_messages
                           WHERE user_id = ? AND provider = 'google' AND provider_message_id = ?""",
                        (user_dict["id"], str(message_id_header)),
                    ).fetchone()
                if prev_hdr:
                    logger.info(f"[Anti-Duplicação] Message-ID {message_id_header} já processado anteriormente. Ignorando.")
                    _PROCESSED_MESSAGE_IDS.add(processed_key)
                    await mark_message_read(str(msg_id))
                    continue

            extracted_body = extract_gmail_body(payload)
            body_text = clean_email_body(extracted_body) or "(Email sem corpo de texto legível)"

            # FILTRO RÍGIDO ANTI-SPAM / ANÚNCIOS / CÓDIGOS
            is_valid, reject_reason = is_genuine_customer_inquiry(
                sender_email=sender_email,
                customer_name=customer_name,
                subject=subject,
                body=body_text,
                headers_map=headers_map,
                label_ids=label_ids
            )

            if not is_valid:
                logger.info(f"[Filtro Anti-Spam] E-mail de {sender_email} ('{subject}') ignorado: {reject_reason}")
                _PROCESSED_MESSAGE_IDS.add(processed_key)
                with connect() as c:
                    c.execute(
                        """INSERT OR IGNORE INTO processed_email_messages (user_id, provider, provider_message_id)
                           VALUES (?, 'google', ?)""",
                        (user_dict["id"], str(msg_id)),
                    )
                # Remove unread para não verificar repetidamente
                await mark_message_read(str(msg_id))
                continue

            # Registra como em processamento para evitar corridas com outras sincronizações
            _IN_FLIGHT_MESSAGES.add(processed_key)
            try:
                # Processa e responde com a IA
                reply_text = await process_and_reply_email(
                    user_dict=user_dict,
                    integration=integration,
                    customer_email=sender_email,
                    customer_name=customer_name,
                    subject=subject,
                    incoming_content=body_text,
                    thread_id=thread_id,
                    message_id_header=message_id_header,
                )

                with connect() as c:
                    c.execute(
                        """INSERT OR IGNORE INTO processed_email_messages
                           (user_id, provider, provider_message_id)
                           VALUES (?, 'google', ?)""",
                        (user_dict["id"], str(msg_id)),
                    )
                    if message_id_header:
                        c.execute(
                            """INSERT OR IGNORE INTO processed_email_messages
                               (user_id, provider, provider_message_id)
                               VALUES (?, 'google', ?)""",
                            (user_dict["id"], str(message_id_header)),
                        )
                _PROCESSED_MESSAGE_IDS.add(processed_key)
                if message_id_header:
                    _PROCESSED_MESSAGE_IDS.add((
                        "google",
                        str(integration.get("id") or integration.get("email_address")),
                        str(message_id_header),
                    ))
                # Remove a label UNREAD do Gmail para não responder repetidamente
                await mark_message_read(str(msg_id))

                processed_items.append({
                    "message_id": msg_id,
                    "from": sender_email,
                    "subject": subject,
                    "reply": reply_text
                })
            finally:
                _IN_FLIGHT_MESSAGES.discard(processed_key)

    return processed_items


async def process_and_reply_email(
    user_dict: dict,
    integration: dict,
    customer_email: str,
    customer_name: str,
    subject: str,
    incoming_content: str,
    thread_id: Optional[str] = None,
    message_id_header: Optional[str] = None,
) -> str:
    """
    Registra cliente e mensagem recebida, gera resposta via IA Drexier
    e envia e-mail de retorno oficial.
    """
    user_id = user_dict["id"]

    # ── BLOQUEIO DE CABEÇALHOS E CITAÇÕES: Foca estritamente no que o cliente digitou ──
    # Descarta cabeçalhos e citações antigas (ex: "em sex., 20 de nov ... escreveu :")
    clean_body = clean_email_body(incoming_content)
    if clean_body:
        incoming_content = clean_body

    # Extrai o nome apenas do texto escrito pelo cliente no corpo da mensagem.
    # Nunca usa o nome do cabeçalho "From:" do email como nome de registo de marcação.
    stated_name_from_text = extract_stated_name_from_text(incoming_content)
    # O nome de registo da marcação é o nome que o cliente escreveu no corpo.
    # O customer_name vindo do cabeçalho pode ser usado só para saudação de contacto.
    booking_customer_name = stated_name_from_text or customer_name or ""

    with connect() as c:
        # Localiza ou cria o contacto pelo e-mail
        contact = c.execute(
            "SELECT id, name FROM contacts WHERE user_id = ? AND contact_key = ?",
            (user_id, customer_email)
        ).fetchone()

        full_current_content = f"Assunto: {subject}\n\n{incoming_content}"
        recent_msgs = []

        if contact:
            cid = contact["id"]
            # SISTEMA DE DETECÇÃO ANTI-DUPLICAÇÃO E ANTI-LOOP
            # Se a mensagem mais recente do cliente for idêntica e já houver resposta do agente logo a seguir,
            # significa que esta mensagem exata já foi respondida com sucesso. NUNCA responde novamente!
            recent_msgs = c.execute(
                "SELECT id, sender, content FROM messages WHERE contact_id = ? AND user_id = ? ORDER BY id DESC LIMIT 2",
                (cid, user_id)
            ).fetchall()
            if len(recent_msgs) >= 2:
                if (
                    recent_msgs[0]["sender"] == "agent"
                    and recent_msgs[1]["sender"] == "customer"
                    and recent_msgs[1]["content"] == full_current_content
                ):
                    logger.info(
                        f"[Anti-Duplicação] Mensagem de {customer_email} com o mesmo conteúdo já foi respondida anteriormente pelo agente. Ignorando envio repetido."
                    )
                    return recent_msgs[0]["content"]

            new_name = stated_name_from_text or customer_name or contact["name"] or ""
            c.execute(
                "UPDATE contacts SET name = ?, last_message_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_name, cid)
            )
        else:
            cur = c.execute(
                "INSERT INTO contacts(user_id, name, contact_key, last_message_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (user_id, customer_name or "", customer_email)
            )
            cid = cur.lastrowid

        # Salva mensagem recebida do cliente (se a tentativa anterior falhou antes do envio do agente, reutiliza o registro em vez de duplicar)
        if not (recent_msgs and recent_msgs[0]["sender"] == "customer" and recent_msgs[0]["content"] == full_current_content):
            c.execute(
                "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'customer', ?)",
                (user_id, cid, full_current_content)
            )

        # URL com botão oficial para acesso direto ao campo de opções de marcação
        booking_url = build_booking_action_url(user_id, cid, customer_email, booking_customer_name or customer_name or "")

        # No modo totalmente automático o cliente confirma a marcação antes de ela
        # entrar no quadro "Marcações da Semana". Nenhum outro modo usa este fluxo.
        pending_confirmation = c.execute(
            """SELECT r.id, r.request_type, r.details, r.scheduled_at
               FROM conversion_requests r
               WHERE r.user_id = ? AND r.contact_id = ?
                 AND r.status = 'awaiting_client_confirmation'
               ORDER BY r.id DESC LIMIT 1""",
            (user_id, cid),
        ).fetchone()

        # Loop guard: Se for apenas confirmação breve ("obrigado", "ok") e a IA já respondeu antes
        last_agent_msg = c.execute(
            "SELECT id, content FROM messages WHERE contact_id = ? AND user_id = ? AND sender = 'agent' ORDER BY id DESC LIMIT 1",
            (cid, user_id)
        ).fetchone()
        clean_stripped = incoming_content.strip().lower()
        if (
            last_agent_msg
            and not pending_confirmation
            and any(re.search(pat, clean_stripped, re.IGNORECASE) for pat in LOOP_ACKNOWLEDGMENT_PATTERNS)
        ):
            logger.info(f"[Anti-Loop] Agradecimento ou confirmação breve de {customer_email} recebido após resposta da IA. Não requer nova resposta automática.")
            return "(Agradecimento registado - ciclo de atendimento concluído)"

        mandatory = {}
        try:
            mandatory = json.loads(user_dict.get("mandatory_responses") or "{}")
        except Exception:
            pass

        # Nível de Automação do Agente ('full', 'semi', 'disabled')
        automation_level = mandatory.get("automation_level", "semi")
        auto_reply = bool(integration.get("auto_reply_enabled", 1)) and automation_level != "disabled"

        # Histórico recente de mensagens desse cliente
        history_rows = c.execute(
            "SELECT sender, content FROM messages WHERE contact_id = ? AND user_id = ? AND id != last_insert_rowid() ORDER BY id DESC LIMIT 10",
            (cid, user_id)
        ).fetchall()
        history = [{"sender": r["sender"], "content": r["content"]} for r in reversed(history_rows)]

        # Base de conhecimento do negócio
        info = c.execute(
            "SELECT kind, title, content, metadata FROM business_info WHERE user_id = ? AND kind NOT IN ('subscription', 'assinatura', 'ai_report')",
            (user_id,)
        ).fetchall()

        # Um pedido que já está a aguardar resposta do cliente deve ser sempre
        # concluído, mesmo que o nível de automação tenha mudado entretanto.
        # Caso contrário o cliente fica preso num ciclo interminável de perguntas.
        if pending_confirmation:
            language = detect_message_language(incoming_content)
            confirmation_details = pending_confirmation["details"] or ""
            confirmation_scheduled_at = pending_confirmation["scheduled_at"]

            # ── BLINDAGEM 1-MENSAGEM-POR-TURNO ────────────────────────────────────
            # Usa recent_msgs (lido ANTES da inserção da nova mensagem customer)
            # para verificar se esta mensagem já foi respondida antes pelo agente.
            if (
                len(recent_msgs) >= 2
                and recent_msgs[0]["sender"] == "agent"
                and recent_msgs[1]["sender"] == "customer"
                and recent_msgs[1]["content"] == full_current_content
            ):
                logger.info(
                    f"[Blindagem 1-msg] Mensagem de {customer_email} já foi respondida. "
                    "Ignorando reenvio duplicado."
                )
                return recent_msgs[0]["content"]
            # ─────────────────────────────────────────────────────────────────

            # O cliente pode responder "Sim, mas quinta às 16h" ou apenas "às 16h".
            # Nesses casos a marcação registada é atualizada antes da decisão, para
            # que a confirmação use sempre a data/hora mais recente pedida por ele.
            clean_incoming = clean_email_body(incoming_content)
            new_schedule = extract_scheduled_at(clean_incoming)
            if new_schedule and new_schedule != confirmation_scheduled_at:
                confirmation_scheduled_at = new_schedule
                confirmation_details = (
                    f"{confirmation_details}\nData e hora escolhidas pelo cliente: {incoming_content[:200]}"
                ).strip()
                c.execute(
                    """UPDATE conversion_requests SET details = ?, scheduled_at = ?
                       WHERE id = ? AND user_id = ?""",
                    (confirmation_details, confirmation_scheduled_at, pending_confirmation["id"], user_id),
                )
            elif not new_schedule and confirmation_scheduled_at:
                only_time = _extract_schedule_time(clean_incoming)
                if only_time:
                    previous = _parse_utc_datetime(confirmation_scheduled_at)
                    if previous is not None:
                        adjusted = previous.astimezone(BUSINESS_TIMEZONE).replace(
                            hour=only_time[0], minute=only_time[1]
                        )
                        if adjusted > datetime.now(BUSINESS_TIMEZONE):
                            updated_at = adjusted.astimezone(timezone.utc).isoformat()
                            if updated_at != confirmation_scheduled_at:
                                confirmation_scheduled_at = updated_at
                                confirmation_details = (
                                    f"{confirmation_details}\nHora escolhida pelo cliente: {incoming_content[:200]}"
                                ).strip()
                                c.execute(
                                    """UPDATE conversion_requests SET details = ?, scheduled_at = ?
                                       WHERE id = ? AND user_id = ?""",
                                    (confirmation_details, confirmation_scheduled_at, pending_confirmation["id"], user_id),
                                )

            decision = detect_client_confirmation(incoming_content)

            # ── ANTI-LOOP DE CONFIRMAÇÃO ──────────────────────────────────────
            # Se a decisão for ambígua (None) mas a marcação já tem data/hora
            # definida e o cliente está a responder a uma pergunta de confirmação,
            # trata-se como positivo (evita reperguntar indefinidamente).
            if decision is None and confirmation_scheduled_at:
                # Verifica se há pelo menos uma palavra curta não-negativa
                raw_stripped = (clean_email_body(incoming_content) or incoming_content).strip()
                raw_lower = re.sub(r"[^\w\s]", "", raw_stripped.lower()).strip()
                # Palavras absolutamente neutras ou muito curtas são positivas neste contexto
                _NEUTRAL_BUT_POSITIVE = {"ok", "okay", "certo", "bom", "sim", "s", "yes", "y"}
                if raw_lower in _NEUTRAL_BUT_POSITIVE or len(raw_lower) <= 3:
                    decision = "positive"
                    logger.info(
                        f"[Anti-Loop] Resposta curta/neutra '{raw_lower}' de {customer_email} "
                        "tratada como confirmação positiva (marcação já tem data/hora)."
                    )
            # ─────────────────────────────────────────────────────────────────

            if decision == "positive":
                reply_text = _build_request_status_reply(
                    customer_name=booking_customer_name,
                    business_name=user_dict.get("name") or "nosso negócio",
                    details=confirmation_details,
                    confirmed=True,
                    language=language,
                    request_type="booking",
                    scheduled_at=confirmation_scheduled_at,
                )
                claimed_status, final_status = "validating", "confirmed"
            elif decision == "negative":
                display_name = customer_name.strip() if customer_name and "@" not in customer_name else ""
                greeting = f"Olá, {display_name}." if display_name else "Olá."
                if language == "en":
                    greeting = f"Hello, {display_name}." if display_name else "Hello."
                    body = (
                        "Understood. The booking was not confirmed. "
                        "If you wish, we can arrange another date and time."
                    )
                    closing = f"Kind regards,\n{user_dict.get('name') or 'nosso negócio'}"
                else:
                    body = (
                        "Compreendido. A marcação não foi confirmada. "
                        "Se desejar, podemos agendar outra data e hora."
                    )
                    closing = f"Com os melhores cumprimentos,\n{user_dict.get('name') or 'nosso negócio'}"
                reply_text = f"{greeting}\n\n{body}\n\n{closing}"
                claimed_status, final_status = "validating", "treated"
            else:
                # Decisão ambígua sem data definida: repergunta UMA vez.
                # Mas se já existe uma mensagem do agente a fazer esta pergunta
                # (mesmo texto), não a envia de novo → anti-loop absoluto.
                _conf_question = _build_booking_confirmation_question(
                    customer_name=booking_customer_name,
                    business_name=user_dict.get("name") or "nosso negócio",
                    details=confirmation_details,
                    scheduled_at=confirmation_scheduled_at,
                    language=language,
                )
                previous_agent_content = (last_agent_msg["content"] or "") if last_agent_msg else ""
                if (
                    "Deseja prosseguir e confirmar" in previous_agent_content
                    or "Do you want to proceed and confirm" in previous_agent_content
                ):
                    # Já foi perguntado antes — se o cliente não confirma nem
                    # nega, encerra silenciosamente sem enviar nova mensagem
                    logger.info(
                        f"[Anti-Loop] Pergunta de confirmação já enviada a {customer_email}. "
                        "Cliente não respondeu de forma reconhecida. Aguardando."
                    )
                    return "(Aguardando resposta do cliente - pergunta de confirmação já enviada)"
                reply_text = _conf_question
                claimed_status, final_status = None, "awaiting_client_confirmation"

            if claimed_status:
                claimed = c.execute(
                    """UPDATE conversion_requests SET status = ?
                       WHERE id = ? AND user_id = ? AND status = 'awaiting_client_confirmation'""",
                    (claimed_status, pending_confirmation["id"], user_id),
                )
                if not claimed.rowcount:
                    raise ValueError("Esta marcação já não está a aguardar confirmação do cliente.")

            reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
            if auto_reply:
                try:
                    await send_email(
                        integration=integration,
                        to_email=customer_email,
                        subject=reply_subject,
                        body_text=reply_text,
                        thread_id=thread_id,
                        in_reply_to=message_id_header,
                        references=message_id_header,
                    )
                except Exception as e_send:
                    if claimed_status:
                        c.execute(
                            """UPDATE conversion_requests SET status = 'awaiting_client_confirmation'
                               WHERE id = ? AND user_id = ? AND status = ?""",
                            (pending_confirmation["id"], user_id, claimed_status),
                        )
                    logger.error(f"Erro ao enviar resposta de confirmação automática: {e_send}")
                    raise
            if claimed_status:
                # Dois UPDATEs simples em vez de COALESCE para compatibilidade
                # máxima com o adaptador Supabase (evita split incorreto da vírgula
                # dentro de COALESCE ao tokenizar o SET).
                c.execute(
                    """UPDATE conversion_requests SET status = ?, resolved_at = CURRENT_TIMESTAMP
                       WHERE id = ? AND user_id = ? AND status = ?""",
                    (final_status, pending_confirmation["id"], user_id, claimed_status),
                )
                if confirmation_scheduled_at:
                    c.execute(
                        "UPDATE conversion_requests SET scheduled_at = ? WHERE id = ? AND user_id = ?",
                        (confirmation_scheduled_at, pending_confirmation["id"], user_id),
                    )
                _safe_invalidate_dashboard_cache(user_id)
            if auto_reply:
                c.execute(
                    "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'agent', ?)",
                    (user_id, cid, reply_text),
                )
                c.execute("UPDATE contacts SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?", (cid,))
            if decision == "positive":
                return "(Marcação confirmada pelo cliente - Nível Totalmente Automático)"
            if decision == "negative":
                return "(Marcação não confirmada pelo cliente - Nível Totalmente Automático)"
            return "(Confirmação da marcação solicitada ao cliente - Nível Totalmente Automático)"

        if not auto_reply or automation_level == "disabled":
            logger.info(
                f"[Auto-Reply Desativado] Mensagem de {customer_email} registada com sucesso. Nível de automação desativado."
            )
            return "(Resposta automática desativada pelo utilizador - Nível Desativado)"

        # ── SELEÇÃO DIRETA DE OPÇÃO DE MARCAÇÃO PELO CLIENTE NO GMAIL ────────
        # O cliente escolheu uma das opções (respondeu 'Opção 1', 'Opção 2', clicou para responder no Gmail, etc.)
        # Sem ser transferido para link externo! A marcação é gravada imediatamente no sistema.
        available_booking_options = generate_booking_options(info)
        chosen_opt = extract_booking_option_choice(incoming_content, available_booking_options)
        if chosen_opt:
            chosen_slot_label = chosen_opt["label"]
            chosen_scheduled_at = chosen_opt["iso"]
            chosen_date_str = f"Dia {chosen_opt['date']} às {chosen_opt['time']}"
            details_text = (
                f"Opção de marcação escolhida pelo cliente: {chosen_slot_label}\n"
                f"Data e hora escolhidas pelo cliente: {chosen_date_str}"
            )
            final_customer_name = stated_name_from_text or customer_name or "Cliente"

            existing_req = c.execute(
                """SELECT id, status FROM conversion_requests
                   WHERE user_id = ? AND contact_id = ?
                     AND status IN ('pending', 'validating', 'awaiting_schedule', 'awaiting_client_confirmation')
                   ORDER BY id DESC LIMIT 1""",
                (user_id, cid),
            ).fetchone()

            if automation_level == "full":
                # NÍVEL TOTALMENTE AUTOMÁTICO:
                # Entra imediatamente no card de Marcações da Semana (status='confirmed')
                if existing_req:
                    c.execute(
                        """UPDATE conversion_requests
                           SET status = 'confirmed', scheduled_at = ?, resolved_at = CURRENT_TIMESTAMP, details = ?
                           WHERE id = ? AND user_id = ?""",
                        (chosen_scheduled_at, details_text, existing_req["id"], user_id),
                    )
                else:
                    c.execute(
                        """INSERT INTO conversion_requests
                           (user_id, contact_id, request_type, details, status, scheduled_at, resolved_at)
                           VALUES (?, ?, 'booking', ?, 'confirmed', ?, CURRENT_TIMESTAMP)""",
                        (user_id, cid, details_text, chosen_scheduled_at),
                    )
                _safe_invalidate_dashboard_cache(user_id)

                reply_text = _build_request_status_reply(
                    customer_name=final_customer_name,
                    business_name=user_dict.get("name") or "nosso negócio",
                    details=details_text,
                    confirmed=True,
                    language=detect_message_language(incoming_content),
                    request_type="booking",
                    scheduled_at=chosen_scheduled_at,
                )

                reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
                try:
                    await send_email(
                        integration=integration,
                        to_email=customer_email,
                        subject=reply_subject,
                        body_text=reply_text,
                        thread_id=thread_id,
                        in_reply_to=message_id_header,
                        references=message_id_header,
                    )
                except Exception as e_send:
                    logger.error(f"Erro ao enviar confirmação de marcação automática: {e_send}")

                c.execute(
                    "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'agent', ?)",
                    (user_id, cid, reply_text),
                )
                c.execute("UPDATE contacts SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?", (cid,))
                return "(Marcação confirmada automaticamente no quadro de Marcações da Semana - Nível Totalmente Automático)"

            else:
                # NÍVEL SEMI-AUTOMÁTICO:
                # Aparece no card de Esperando Validação (status='pending') até ser validado pelo proprietário!
                if existing_req:
                    c.execute(
                        """UPDATE conversion_requests
                           SET status = 'pending', scheduled_at = ?, details = ?
                           WHERE id = ? AND user_id = ?""",
                        (chosen_scheduled_at, details_text, existing_req["id"], user_id),
                    )
                else:
                    c.execute(
                        """INSERT INTO conversion_requests
                           (user_id, contact_id, request_type, details, status, scheduled_at)
                           VALUES (?, ?, 'booking', ?, 'pending', ?)""",
                        (user_id, cid, details_text, chosen_scheduled_at),
                    )
                _safe_invalidate_dashboard_cache(user_id)

                lang = detect_message_language(incoming_content)
                greeting = f"Olá, {final_customer_name}." if final_customer_name and "@" not in final_customer_name else "Olá."
                biz_name = user_dict.get("name") or "nosso negócio"
                if lang == "en":
                    greeting = f"Hello, {final_customer_name}." if final_customer_name and "@" not in final_customer_name else "Hello."
                    body_msg = (
                        f"We have received your booking choice for {chosen_date_str}.\n\n"
                        f"Your request is currently awaiting validation by our team. "
                        f"We will contact you shortly once it is confirmed."
                    )
                    closing = f"Kind regards,\n{biz_name}"
                else:
                    body_msg = (
                        f"Recebemos a sua escolha para {chosen_date_str}.\n\n"
                        f"O seu pedido de marcação aguarda validação da nossa equipa. "
                        f"Entraremos em contacto brevemente assim que a marcação for confirmada."
                    )
                    closing = f"Com os melhores cumprimentos,\n{biz_name}"
                reply_text = f"{greeting}\n\n{body_msg}\n\n{closing}"

                reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
                try:
                    await send_email(
                        integration=integration,
                        to_email=customer_email,
                        subject=reply_subject,
                        body_text=reply_text,
                        thread_id=thread_id,
                        in_reply_to=message_id_header,
                        references=message_id_header,
                    )
                except Exception as e_send:
                    logger.error(f"Erro ao enviar aviso de validação pendente: {e_send}")

                c.execute(
                    "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'agent', ?)",
                    (user_id, cid, reply_text),
                )
                c.execute("UPDATE contacts SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?", (cid,))
                return "(Pedido de marcação registado e aguardando validação no card - Nível Semi-Automático)"

        # A marcação só avança para validação quando o cliente fornece data e hora.
        intent = detect_booking_or_purchase_intent(incoming_content, subject)
        if intent is None:
            # Respostas como "quinta às 16h" ou "20/11 às 15h" podem vir sem verbo
            # de agendamento. Se já existir um pedido em aberto, tratamos a data
            # informada como continuação desse pedido.
            unresolved_request = c.execute(
                """SELECT 1 FROM conversion_requests
                   WHERE user_id = ? AND contact_id = ?
                     AND status IN ('awaiting_schedule', 'pending', 'awaiting_client_confirmation')
                   LIMIT 1""",
                (user_id, cid),
            ).fetchone()
            if unresolved_request and extract_scheduled_at(
                f"{subject or ''}\n{clean_email_body(incoming_content)}"
            ):
                intent = {"type": "booking", "details": incoming_content[:300].strip()}
        scheduled_request = capture_scheduled_request(
            c, user_id, cid, incoming_content, subject, intent
        )
        waiting_for_schedule = bool(
            scheduled_request and scheduled_request["status"] == "awaiting_schedule"
        )
        if scheduled_request and not waiting_for_schedule:
            intent = {"type": scheduled_request["request_type"], "details": scheduled_request["details"]}
        else:
            intent = None

        known_schedule_text = "\n".join(
            part for part in (
                (scheduled_request or {}).get("details"),
                incoming_content,
                subject,
            ) if part
        )
        known_schedule_fragment = _client_schedule_fragment(known_schedule_text)
        need_date = not bool(_SCHEDULE_DATE_CUE_PATTERN.search(known_schedule_fragment))
        need_time = _extract_schedule_time(known_schedule_text) is None
        has_specific_schedule = bool(not need_date or not need_time)

        # Verifica previamente se é intenção ou pergunta sobre marcações
        inquiry_intent = is_booking_inquiry(
            incoming_content=incoming_content,
            subject=subject,
            intent=intent,
            waiting_for_schedule=waiting_for_schedule,
            has_specific_schedule=has_specific_schedule,
        )

        reply_instructions = effective_agent_instructions(user_dict)
        if inquiry_intent and not has_specific_schedule:
            reply_instructions += (
                "\n\nCONTEXTO OPERACIONAL: O cliente demonstrou intenção de marcação. "
                "O e-mail já apresenta automaticamente as opções de datas disponíveis para o cliente escolher. "
                "NUNCA pergunte 'qual dia pretendido e o horário de sua preferência', 'aguardamos o seu retorno' "
                "nem peça para o cliente informar data ou horário. "
                "Apenas escreva: 'Selecione a sua data disponível para efectuar a marcação (data e horário).' "
                "(ou esclareça dúvidas pontuais do cliente e conclua com 'Selecione a sua data disponível para efectuar a marcação (data e horário).')."
            )
        elif waiting_for_schedule:
            missing_parts = []
            if need_date:
                missing_parts.append("a data")
            if need_time:
                missing_parts.append("a hora")
            missing_text = " e ".join(missing_parts) if missing_parts else "novos dados"
            reply_instructions += (
                "\n\nCONTEXTO OPERACIONAL: Há um pedido anterior do cliente aguardando data e hora "
                "do agendamento. Responda à mensagem atual do cliente, usando o histórico para "
                f"entender o pedido. O cliente já indicou: {known_schedule_fragment or 'nenhum dado'} . "
                f"Pergunte somente {missing_text}, sem repetir o que o cliente já informou. "
                "Não diga que o pedido foi confirmado nem que aguarda validação da equipe."
            )
        if intent:
            if automation_level == "full":
                # Nível Totalmente Automático: verifica disponibilidade nos dados registrados na aba Negócio
                availability_context = (
                    f"{scheduled_request['details']}\n{incoming_content}"
                    if scheduled_request else incoming_content
                )
                avail = check_business_availability(
                    availability_context,
                    subject,
                    info,
                    user_dict.get("business_type") or "Serviços",
                )
                if avail["available"]:
                    booking_awaits_client = (
                        intent["type"] == "booking"
                        and bool((scheduled_request or {}).get("scheduled_at"))
                    )
                    if booking_awaits_client:
                        reply_text = _build_booking_confirmation_question(
                            customer_name=booking_customer_name,
                            business_name=user_dict.get("name") or "nosso negócio",
                            details=scheduled_request["details"],
                            scheduled_at=scheduled_request["scheduled_at"],
                            language=detect_message_language(incoming_content),
                        )
                        final_status = "awaiting_client_confirmation"
                    else:
                        reply_text = _build_request_status_reply(
                            customer_name=booking_customer_name,
                            business_name=user_dict.get("name") or "nosso negócio",
                            details=incoming_content,
                            confirmed=True,
                            language=detect_message_language(incoming_content),
                            request_type=intent["type"],
                            scheduled_at=(scheduled_request or {}).get("scheduled_at"),
                        )
                        final_status = "confirmed"
                    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
                    try:
                        await send_email(
                            integration=integration,
                            to_email=customer_email,
                            subject=reply_subject,
                            body_text=reply_text,
                            thread_id=thread_id,
                            in_reply_to=message_id_header,
                            references=message_id_header,
                            include_booking_options=True,
                        )
                    except Exception as e_send:
                        logger.error(f"Erro ao enviar confirmação automática de e-mail: {e_send}")
                        raise
                    if scheduled_request:
                        if final_status == "confirmed":
                            c.execute(
                                """UPDATE conversion_requests SET status='confirmed', resolved_at=CURRENT_TIMESTAMP
                                   WHERE id=? AND user_id=?""",
                                (scheduled_request["id"], user_id),
                            )
                            if (scheduled_request or {}).get("scheduled_at"):
                                c.execute(
                                    "UPDATE conversion_requests SET scheduled_at = ? WHERE id = ? AND user_id = ?",
                                    ((scheduled_request or {}).get("scheduled_at"), scheduled_request["id"], user_id),
                                )
                        else:
                            c.execute(
                                """UPDATE conversion_requests SET status='awaiting_client_confirmation'
                                   WHERE id=? AND user_id=?""",
                                (scheduled_request["id"], user_id),
                            )
                            if (scheduled_request or {}).get("scheduled_at"):
                                c.execute(
                                    "UPDATE conversion_requests SET scheduled_at = ? WHERE id = ? AND user_id = ?",
                                    ((scheduled_request or {}).get("scheduled_at"), scheduled_request["id"], user_id),
                                )
                        _safe_invalidate_dashboard_cache(user_id)
                    else:
                        c.execute(
                            """INSERT INTO conversion_requests
                               (user_id, contact_id, request_type, details, status, scheduled_at, resolved_at)
                               VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                            (
                                user_id, cid, intent["type"],
                                f"Assunto: {subject}\n{incoming_content[:400]}",
                                final_status,
                                extract_scheduled_at(incoming_content),
                            ),
                        )
                    c.execute(
                        "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'agent', ?)",
                        (user_id, cid, reply_text)
                    )
                    c.execute("UPDATE contacts SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?", (cid,))
                    if booking_awaits_client:
                        return "(Confirmação da marcação solicitada ao cliente - Nível Totalmente Automático)"
                    return f"(Marcação de {intent['type']} validada e confirmada automaticamente - Nível Totalmente Automático)"
                else:
                    reply_text = _build_request_status_reply(
                        customer_name=customer_name,
                        business_name=user_dict.get("name") or "nosso negócio",
                        details=incoming_content,
                        confirmed=False,
                        language=detect_message_language(incoming_content),
                        note=avail["reason"],
                        request_type=intent["type"],
                        scheduled_at=(scheduled_request or {}).get("scheduled_at"),
                    )
                    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
                    try:
                        await send_email(
                            integration=integration,
                            to_email=customer_email,
                            subject=reply_subject,
                            body_text=reply_text,
                            thread_id=thread_id,
                            in_reply_to=message_id_header,
                            references=message_id_header,
                            include_booking_options=True,
                        )
                    except Exception as e_send:
                        logger.error(f"Erro ao enviar alternativa: {e_send}")
                        raise
                    if scheduled_request:
                        c.execute(
                            """UPDATE conversion_requests SET status='treated', resolved_at=CURRENT_TIMESTAMP
                               WHERE id=? AND user_id=?""",
                            (scheduled_request["id"], user_id),
                        )
                    else:
                        c.execute(
                            """INSERT INTO conversion_requests
                               (user_id, contact_id, request_type, details, status, scheduled_at, resolved_at)
                               VALUES (?, ?, ?, ?, 'treated', ?, CURRENT_TIMESTAMP)""",
                            (
                                user_id, cid, intent["type"],
                                f"Assunto: {subject}\n{incoming_content[:400]}",
                                extract_scheduled_at(incoming_content),
                            ),
                        )
                    c.execute(
                        "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'agent', ?)",
                        (user_id, cid, reply_text)
                    )
                    c.execute("UPDATE contacts SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?", (cid,))
                    return f"(Pedido de {intent['type']} tratado automaticamente por indisponibilidade)"
            else:
                # Nível Semi: a IA responde mas não valida de forma automática a marcação final, aguardando validação do usuário
                has_pending = c.execute(
                    "SELECT id FROM conversion_requests WHERE user_id = ? AND contact_id = ? AND status = 'pending'",
                    (user_id, cid)
                ).fetchone()
                if not has_pending:
                    c.execute(
                        """INSERT INTO conversion_requests
                           (user_id, contact_id, request_type, details, status, scheduled_at)
                           VALUES (?, ?, ?, ?, 'pending', ?)""",
                        (
                            user_id, cid, intent["type"],
                            f"Assunto: {subject}\n{incoming_content[:400]}",
                            extract_scheduled_at(incoming_content),
                        )
                    )
                    logger.info(f"[Validação Pendente - Semi] Intenção de {intent['type']} de {customer_email} registada na Dashboard para validação.")
                if not waiting_for_schedule:
                    # No modo totalmente automático NUNCA dizer que aguarda validação
                    if automation_level == "full":
                        reply_instructions += (
                            "\n\nCONTEXTO OPERACIONAL: Você tem autonomia máxima. "
                            "Responda à mensagem atual confirmando o agendamento diretamente. "
                            "NUNCA diga que aguarda validação da equipe."
                        )
                    else:
                        reply_instructions += (
                            "\n\nCONTEXTO OPERACIONAL: O pedido do cliente está registrado e aguarda "
                            "validação do proprietário. Responda à mensagem atual confirmando apenas o "
                            "recebimento e que aguarda validação. Não diga que já foi confirmado, "
                            "reservado ou concluído."
                        )

    # Gerar resposta com a IA Drexier (Gemini ou fallback)
    try:
        reply_text = await draft_reply(
            message=incoming_content,
            info_rows=info,
            instructions=reply_instructions,
            language=user_dict.get("language") or "Português",
            history=history,
            business_name=user_dict.get("name") or integration.get("display_name") or "nosso negócio",
            business_type=user_dict.get("business_type") or "Serviços",
            business_description=user_dict.get("business_description") or "",
            mandatory_responses=mandatory,
        )
    except Exception as e:
        logger.error(f"Erro ao gerar resposta com a IA: {e}")
        reply_text = (
            "At the moment, I do not have this information registered. Is there anything else I can help you with?"
            if detect_message_language(incoming_content) == "en"
            else UNKNOWN_REPLY
        )

    # Determina segundo a interpretação da IA se esta mensagem é uma consulta sobre marcações
    should_include_options = is_booking_inquiry(
        incoming_content=incoming_content,
        subject=subject,
        reply_text=reply_text,
        intent=intent,
        waiting_for_schedule=waiting_for_schedule,
        has_specific_schedule=has_specific_schedule,
    )

    if should_include_options and not has_specific_schedule:
        # Quando o cliente mostra intenção de marcação, o e-mail já apresenta as opções disponíveis.
        # NUNCA pergunte data/horário de preferência nem 'aguardamos o seu retorno'.
        reply_text = re.sub(
            r"(?i)\b(?:por\s+favor,?\s*)?(?:informe|indique|diga)[^\.\n]*?(?:dia|data|hor[áa]rio)[^\.\n]*?(?:prefer[êe]ncia|pretendid[oa])[^\.\n]*?[\.\?!]?",
            "",
            reply_text,
        )
        reply_text = re.sub(
            r"(?i)\b(?:por\s+favor,?\s*)?aguardamos\s+o\s+seu\s+retorno[^\.\n]*?[\.\?!]?",
            "",
            reply_text,
        )
        reply_text = re.sub(
            r"(?i)\b(?:para\s+registar[^\.\n]*?)?qual\s+[ée]\s+(?:a\s+)?data\s+e\s+(?:a\s+)?hora[^\.\n]*?[\.\?!]?",
            "",
            reply_text,
        )
        reply_text = re.sub(
            r"(?i)\b(?:por\s+favor,?\s*)?indique\s+o\s+dia\s+e\s+o\s+hor[áa]rio[^\.\n]*?[\.\?!]?",
            "",
            reply_text,
        )
        reply_text = re.sub(
            r"(?i)\b(?:por\s+favor,?\s*)?indique\s+o\s+hor[áa]rio\s+desejado[^\.\n]*?[\.\?!]?",
            "",
            reply_text,
        )
        reply_text = re.sub(r"\n{3,}", "\n\n", reply_text).strip()

        # Se o texto ficou vazio ou continha apenas saudação/marcação, define diretamente
        cleaned_check = re.sub(r"(?i)^(?:ol[áa]|bom\s+dia|boa\s+tarde|boa\s+noite)[^\.\n]*?[\.\?!,\s]*", "", reply_text).strip()
        if not cleaned_check or not reply_text:
            greeting = f"Olá, {booking_customer_name}." if booking_customer_name else "Olá."
            reply_text = f"{greeting}\n\nSelecione a sua data disponível para efectuar a marcação (data e horário)."
        elif "selecione a sua data disponível" not in reply_text.lower():
            reply_text = f"{reply_text}\n\nSelecione a sua data disponível para efectuar a marcação (data e horário)."
    elif waiting_for_schedule and (not scheduled_request or scheduled_request.get("request_type") != "purchase"):
        reply_text = ensure_date_time_question(
            reply_text,
            need_date=need_date,
            need_time=need_time,
        )

    # Envia o e-mail de resposta de volta ao cliente pelo provedor configurado
    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    send_kwargs = {
        "integration": integration,
        "to_email": customer_email,
        "subject": reply_subject,
        "body_text": reply_text,
        "thread_id": thread_id,
        "in_reply_to": message_id_header,
        "references": message_id_header,
    }
    if should_include_options and not has_specific_schedule:
        send_kwargs["include_booking_options"] = True
    try:
        await send_email(**send_kwargs)
        logger.info(f"Resposta enviada com sucesso por e-mail para {customer_email}")
    except Exception as e:
        logger.exception(f"Erro ao enviar resposta por e-mail para {customer_email}: {e}")
        raise

    # Só registra a resposta como enviada depois da confirmação do provedor.
    with connect() as c:
        c.execute(
            "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'agent', ?)",
            (user_id, cid, reply_text)
        )
        c.execute("UPDATE contacts SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?", (cid,))

        if thread_id:
            c.execute(
                """INSERT INTO email_threads (user_id, contact_id, provider, thread_id, last_message_id, subject, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(user_id, thread_id) DO UPDATE SET
                       last_message_id = excluded.last_message_id,
                       subject = excluded.subject,
                       updated_at = CURRENT_TIMESTAMP""",
                (user_id, cid, integration["provider"], str(thread_id), message_id_header or "", reply_subject)
            )

    return reply_text


async def sync_emails_for_user(user_id: int) -> List[Dict[str, Any]]:
    """Dispara a sincronização de e-mails para um utilizador específico."""
    with connect() as c:
        user = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        integration = c.execute(
            "SELECT * FROM email_integrations WHERE user_id = ? AND status = 'connected' AND provider = 'google'",
            (user_id,)
        ).fetchone()

    if not user or not integration:
        return []

    user_dict = dict(user)
    integration_dict = dict(integration)
    payment_at = get_last_successful_payment_at(user_id)
    if not payment_at:
        # Fallback: tenta reconciliar com a Stripe para utilizadores com assinatura ativa mas sem
        # data de pagamento persistida localmente. Apenas quando a Stripe esta configurada.
        # A reconciliacao em get_user_subscription_status() persiste os dados automaticamente.
        try:
            from backend.services.billing_service import (
                get_user_subscription_status as _get_sub_status,
                is_stripe_configured as _stripe_ok,
            )
            if _stripe_ok():
                # A reconciliacao Stripe e feita internamente e persiste last_successful_payment_at
                _get_sub_status(user_id)
                # Tentar novamente depois da reconciliacao Stripe
                payment_at = get_last_successful_payment_at(user_id)
                if payment_at:
                    logger.info(
                        f"[Sync Fallback] Pagamento recuperado via reconciliacao Stripe para user {user_id}: {payment_at}"
                    )
                else:
                    # Assinatura ativa na Stripe mas sem data de fatura disponivel.
                    # Usa created_at como cutoff APENAS se existir um stripe_subscription_id real
                    # (garante que e uma assinatura confirmada pela API da Stripe, nao apenas local).
                    sub_check = _get_sub_status(user_id)
                    stripe_sub_id = sub_check.get("stripe_subscription_id") or ""
                    if sub_check.get("has_active_subscription") and stripe_sub_id.startswith("sub_"):
                        payment_at = integration_dict.get("created_at") or "2020-01-01T00:00:00+00:00"
                        logger.info(
                            f"[Sync Fallback] Assinatura Stripe {stripe_sub_id} ativa sem data de fatura. "
                            f"Usando created_at como cutoff para user {user_id}: {payment_at}"
                        )
        except Exception as _fe:
            logger.warning(f"[Sync Fallback] Erro ao reconciliar com Stripe para user {user_id}: {_fe}")
    integration_dict["last_successful_payment_at"] = payment_at
    if get_email_response_cutoff(integration_dict) is None:
        logger.info(f"[SaaS Paywall] Sincronizacao de e-mail bloqueada para user {user_id}: aguarda pagamento confirmado.")
        return []
    provider = integration_dict.get("provider")

    if provider != "google":
        logger.warning("Sincronização bloqueada para provedor de e-mail não suportado.")
        return []

    processed = await sync_google_emails(user_dict, integration_dict)

    with connect() as c:
        c.execute(
            "UPDATE email_integrations SET last_sync_at = CURRENT_TIMESTAMP WHERE id = ?",
            (integration_dict["id"],)
        )

    return processed


def _extract_booking_summary(
    details: str,
    request_type: str = "booking",
    scheduled_at: Any = None,
) -> dict:
    """Resume o pedido usando sempre a data/hora registada como fonte oficial.

    Os metadados do e-mail (data de envio, cabeçalhos e citações) nunca são
    usados para descrever a marcação.
    """
    import re as _re

    raw = (details or "").strip()
    schedule_source = _client_schedule_fragment(raw) or raw

    date_str = format_booking_datetime(scheduled_at) if scheduled_at else ""
    if not date_str:
        m = _re.search(
            r"Data e hora escolhidas pelo cliente\s*[:：]\s*(.+?)(?:\n|$)",
            schedule_source, _re.IGNORECASE,
        )
        if m:
            date_str = m.group(1).strip()

    if not date_str:
        m = _re.search(
            r"\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s+(?:às\s+)?(\d{1,2})[hH:]?(\d{0,2})\b",
            schedule_source,
        )
        if m:
            minutes = m.group(3) or "00"
            date_str = f"{m.group(1)} às {m.group(2)}:{minutes}"

    if not date_str:
        weekdays_pt = r"(?:segunda|terça|quarta|quinta|sexta|sábado|domingo)(?:\s*[-–]?\s*feira)?"
        m = _re.search(
            rf"({weekdays_pt})\s+(?:às?|at|às)?\s*(\d{{1,2}})\s*(?:h(?:oras?)?|:00)?",
            schedule_source, _re.IGNORECASE,
        )
        if m:
            date_str = f"{m.group(1).capitalize()} às {m.group(2)}h"

    purpose = ""
    keywords_map = [
        (r"\b(porsche|porsch[eé]|ferrari|lamborghini|bmw|mercedes|audi|toyota|volkswagen|vw|ford|renault|peugeot|opel|nissan|hyundai|kia|honda|mazda|volvo|fiat|jeep|land rover|range rover)\b", lambda m: f"compra de {m.group(1).capitalize()}"),
        (r"\b(consultoria|consulta|consult[ao])\b", lambda _: "consultoria"),
        (r"\b(test[- ]?drive|test drive)\b", lambda _: "test drive"),
        (r"\b(visit[ao]|visitar)\b", lambda _: "visita ao estabelecimento"),
        (r"\b(reuni[aã]o|reuniao)\b", lambda _: "reunião"),
        (r"\b(revisão|revisao|manut[eê]n[çc][aã]o|manutenção)\b", lambda _: "revisão / manutenção"),
        (r"\b(financiamento|crédito|credito)\b", lambda _: "pedido de financiamento"),
        (r"\b(seguro)\b", lambda _: "contratação de seguro"),
        (r"\b(informa[çc][oõ][eo][sn]?|informações)\b", lambda _: "pedido de informações"),
    ]

    for pattern, label_fn in keywords_map:
        m = _re.search(pattern, schedule_source, _re.IGNORECASE)
        if m:
            purpose = label_fn(m)
            break

    if not purpose:
        purpose = "compra" if request_type == "purchase" else "marcação"

    return {"date_str": date_str, "purpose": purpose}


def _build_request_status_reply(
    customer_name: str,
    business_name: str,
    details: str,
    confirmed: bool,
    language: str = "pt",
    note: str = "",
    request_type: str = "booking",
    scheduled_at: Any = None,
) -> str:
    """Mensagem transacional baseada na data/hora da marcação efetivamente registada.
    
    Quando confirmada, inclui sempre o nome registado e a hora da marcação.
    """
    name = customer_name.strip() if customer_name and "@" not in customer_name else ""
    extra_note = (note or "").strip()
    summary = _extract_booking_summary(details or "", request_type, scheduled_at)
    date_str = summary["date_str"]
    purpose = summary["purpose"]

    lang_cmds = CONFIRMATION_COMMANDS.get(language, CONFIRMATION_COMMANDS["pt"])

    if language == "en":
        greeting = f"Hello, {name}." if name else "Hello."
        if confirmed:
            if date_str:
                if purpose and purpose not in ("booking", "appointment", "marcação", "agendamento"):
                    body = (
                        f"Your booking request has been confirmed successfully.\n"
                        f"Registered name: {name or 'not provided'}.\n"
                        f"Date and time: {date_str}.\n"
                        f"Purpose: {purpose}."
                    )
                else:
                    body = (
                        f"Your appointment has been confirmed successfully.\n"
                        f"Registered name: {name or 'not provided'}.\n"
                        f"Date and time: {date_str}."
                    )
            else:
                body = (
                    f"Your request has been confirmed successfully.\n"
                    f"Registered name: {name or 'not provided'}."
                )
        else:
            body = (
                f"Unfortunately, we were unable to confirm your booking for "
                f"{purpose} on {date_str}."
                if date_str else f"Unfortunately, we were unable to confirm your request for {purpose}."
            )
        lines = [greeting, body]
        if extra_note:
            lines.append(f"Note: {extra_note}")
        lines.append(f"Kind regards,\n{business_name}")
        return "\n\n".join(lines)

    greeting = f"Olá, {name}." if name else "Olá."
    if confirmed:
        if date_str:
            if purpose and purpose not in ("marcação", "agendamento", "booking"):
                body = (
                    f"O seu pedido foi confirmado.\n"
                    f"O seu pedido foi confirmado com sucesso.\n"
                    f"Nome registado: {name or 'não indicado'}.\n"
                    f"Data e hora: {date_str}.\n"
                    f"Serviço: {purpose}."
                )
            else:
                body = (
                    f"O seu pedido foi confirmado.\n"
                    f"O seu agendamento foi confirmado para {date_str}.\n"
                    f"O seu agendamento foi confirmado com sucesso.\n"
                    f"Nome registado: {name or 'não indicado'}.\n"
                    f"Data e hora: {date_str}."
                )
        else:
            body = (
                f"O seu pedido foi confirmado.\n"
                f"O seu pedido foi confirmado com sucesso.\n"
                f"Nome registado: {name or 'não indicado'}."
            )
    else:
        body = (
            f"Infelizmente não nos foi possível confirmar a sua marcação para "
            f"{purpose} em {date_str}."
            if date_str else f"Infelizmente não nos foi possível confirmar o seu pedido de {purpose}."
        )

    lines = [greeting, body]
    if extra_note:
        lines.append(f"Nota: {extra_note}")
    lines.append(f"Com os melhores cumprimentos,\n{business_name}")
    return "\n\n".join(lines)


def _build_booking_confirmation_question(
    customer_name: str,
    business_name: str,
    details: str,
    scheduled_at: Any,
    language: str = "pt",
) -> str:
    """Pede ao cliente autorização explícita antes de validar a marcação (modo totalmente automático).
    
    Inclui os dois comandos obrigatórios ("sim"/"não" ou equivalente no idioma do cliente).
    """
    name = customer_name.strip() if customer_name and "@" not in customer_name else ""
    summary = _extract_booking_summary(details or "", "booking", scheduled_at)
    date_str = summary["date_str"]
    purpose = summary["purpose"]

    lang_cmds = CONFIRMATION_COMMANDS.get(language, CONFIRMATION_COMMANDS["pt"])
    yes_cmd = lang_cmds["yes"]
    no_cmd = lang_cmds["no"]
    instruction = lang_cmds["instruction"]

    if language == "en":
        greeting = f"Hello, {name}." if name else "Hello."
        body = (
            f"We have availability for your {purpose} booking on {date_str}.\n\n"
            f"{lang_cmds['question']}\n\n"
            f"{instruction}"
        )
        return f"{greeting}\n\n{body}\n\nKind regards,\n{business_name}"

    if language == "es":
        greeting = f"Hola, {name}." if name else "Hola."
        body = (
            f"Tenemos disponibilidad para su reserva de {purpose} en {date_str}.\n\n"
            f"{lang_cmds['question']}\n\n"
            f"{instruction}"
        )
        return f"{greeting}\n\n{body}\n\nSaludos cordiales,\n{business_name}"

    if language == "fr":
        greeting = f"Bonjour, {name}." if name else "Bonjour."
        body = (
            f"Nous avons de la disponibilité pour votre réservation de {purpose} le {date_str}.\n\n"
            f"{lang_cmds['question']}\n\n"
            f"{instruction}"
        )
        return f"{greeting}\n\n{body}\n\nCordialement,\n{business_name}"

    if language == "de":
        greeting = f"Guten Tag, {name}." if name else "Guten Tag."
        body = (
            f"Wir haben Verfügbarkeit für Ihre {purpose}-Buchung am {date_str}.\n\n"
            f"{lang_cmds['question']}\n\n"
            f"{instruction}"
        )
        return f"{greeting}\n\n{body}\n\nMit freundlichen Grüßen,\n{business_name}"

    if language == "it":
        greeting = f"Salve, {name}." if name else "Salve."
        body = (
            f"Abbiamo disponibilità per la sua prenotazione di {purpose} il {date_str}.\n\n"
            f"{lang_cmds['question']}\n\n"
            f"{instruction}"
        )
        return f"{greeting}\n\n{body}\n\nCordiali saluti,\n{business_name}"

    # Padrão: português
    greeting = f"Olá, {name}." if name else "Olá."
    purpose_part = "" if purpose == "marcação" else f" de {purpose}"
    body = (
        f"Temos disponibilidade para a sua marcação{purpose_part} em {date_str}.\n\n"
        f"{lang_cmds['question']}\n\n"
        f"{instruction}"
    )
    return f"{greeting}\n\n{body}\n\nCom os melhores cumprimentos,\n{business_name}"


async def process_confirmation_action(
    user_id: int,
    request_id: int,
    action: str,  # 'confirm' or 'reject'
    custom_note: str = ""
) -> Dict[str, Any]:
    """
    Gera uma mensagem transacional determinística e envia um e-mail oficial ao cliente
    confirmando ou recusando o pedido com base nos dados fornecidos pelo proprietário.
    """
    with connect() as c:
        req = c.execute(
            """SELECT r.id, r.request_type, r.details, r.contact_id, ct.name, ct.contact_key,
                      r.scheduled_at, r.status
               FROM conversion_requests r
               JOIN contacts ct ON ct.id = r.contact_id
               WHERE r.id = ? AND r.user_id = ?""",
            (request_id, user_id)
        ).fetchone()
        if not req:
            raise ValueError("Pedido de confirmação não encontrado.")
        if req["status"] in ("confirmed", "confirmed_manual"):
            return {
                "ok": True,
                "action": action,
                "status": req["status"],
                "already_confirmed": True,
            }
        if req["status"] != "pending":
            raise ValueError("Este pedido não está pendente ou já está a ser validado.")
        resolved_scheduled_at = req["scheduled_at"]
        if (
            action in ("confirm", "confirm_manual")
            and not resolved_scheduled_at
            and req["request_type"] == "booking"
        ):
            resolved_scheduled_at = extract_scheduled_at(req["details"] or "")
            if not resolved_scheduled_at:
                raise ValueError(
                    "Ainda falta registar a data e a hora escolhidas pelo cliente antes de validar este pedido."
                )
            c.execute(
                "UPDATE conversion_requests SET scheduled_at = ? WHERE id = ? AND user_id = ?",
                (resolved_scheduled_at, request_id, user_id),
            )

        user = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        integration = c.execute(
            "SELECT * FROM email_integrations WHERE user_id = ? AND status = 'connected' AND provider = 'google'",
            (user_id,)
        ).fetchone()
        email_thread = c.execute(
            """SELECT subject, thread_id, last_message_id FROM email_threads
               WHERE contact_id = ? AND user_id = ? ORDER BY updated_at DESC LIMIT 1""",
            (req["contact_id"], user_id)
        ).fetchone()

        if "@" not in req["contact_key"]:
            raise ValueError("Este cliente não tem um endereço de e-mail para receber a confirmação.")
        if not integration:
            raise ValueError("Nenhuma conta de e-mail conectada para envio da confirmação.")

        # Histórico recente
        history_rows = c.execute(
            "SELECT sender, content FROM messages WHERE contact_id = ? AND user_id = ? ORDER BY id DESC LIMIT 8",
            (req["contact_id"], user_id)
        ).fetchall()
        history = [{"sender": r["sender"], "content": r["content"]} for r in reversed(history_rows)]


    user_dict = dict(user)
    integration_dict = dict(integration) if integration else {}
    business_name = user_dict.get("name") or integration_dict.get("display_name") or "nosso negócio"
    customer_name = req["name"] or req["contact_key"]
    customer_email = req["contact_key"]

    channel_name = "e-mail"
    sender_role = "agent"

    if action == "confirm":
        new_status = "confirmed"
        subject = f"Confirmação de Agendamento - {business_name}"
        latest_customer_message = next(
            (row["content"] for row in reversed(history) if row["sender"] == "customer"),
            "",
        )
        language = (
            detect_message_language(latest_customer_message)
            if latest_customer_message
            else ("en" if (user_dict.get("language") or "").lower().startswith("en") else "pt")
        )
        reply_text = _build_request_status_reply(
            customer_name=customer_name,
            business_name=business_name,
            details=req["details"] or "",
            confirmed=True,
            language=language,
            note=custom_note,
            request_type=req["request_type"] or "booking",
            scheduled_at=resolved_scheduled_at,
        )
    elif action == "confirm_manual":
        # Validação Manual: proprietário escreveu a sua própria mensagem de validação
        reply_text = (custom_note or "").strip()
        if not reply_text:
            raise ValueError("Por favor, escreva a mensagem de validação antes de enviar.")
        new_status = "confirmed"
        subject = f"Confirmação de Agendamento - {business_name}"
        sender_role = "owner"
    elif action in ("treated", "resolve"):
        # Tratado sem marcação (produto ou vaga indisponível)
        new_status = "treated"
        with connect() as c:
            updated = c.execute(
                """UPDATE conversion_requests SET status = 'treated', resolved_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND user_id = ? AND status = 'pending'""",
                (request_id, user_id)
            )
            if not updated.rowcount:
                raise ValueError("Este pedido não está mais pendente para ser tratado.")
        return {
            "ok": True,
            "action": action,
            "status": "treated",
            "customer_email": customer_email,
            "detail": "Pedido marcado como tratado (sem marcação realizada por indisponibilidade)."
        }
    else:
        new_status = "treated"
        subject = f"Atualização sobre a sua solicitação - {business_name}"
        latest_customer_message = next(
            (row["content"] for row in reversed(history) if row["sender"] == "customer"),
            "",
        )
        language = (
            detect_message_language(latest_customer_message)
            if latest_customer_message
            else ("en" if (user_dict.get("language") or "").lower().startswith("en") else "pt")
        )
        reply_text = _build_request_status_reply(
            customer_name=customer_name,
            business_name=business_name,
            details=req["details"] or "",
            confirmed=False,
            language=language,
            note=custom_note,
            request_type=req["request_type"] or "booking",
            scheduled_at=resolved_scheduled_at,
        )

    thread_id = email_thread["thread_id"] if email_thread else None
    last_message_id = email_thread["last_message_id"] if email_thread else None
    if email_thread and email_thread["subject"]:
        subject = email_thread["subject"]
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

    with connect() as c:
        claimed = c.execute(
            """UPDATE conversion_requests SET status = 'validating'
               WHERE id = ? AND user_id = ? AND status = 'pending'""",
            (request_id, user_id),
        )
        if not claimed.rowcount:
            current = c.execute(
                "SELECT status FROM conversion_requests WHERE id = ? AND user_id = ?",
                (request_id, user_id),
            ).fetchone()
            if current and current["status"] in ("confirmed", "confirmed_manual"):
                return {
                    "ok": True,
                    "action": action,
                    "status": current["status"],
                    "already_confirmed": True,
                }
            raise ValueError("Este pedido não está pendente ou já está a ser validado.")

    # Envia a resposta oficial pelo Gmail conectado.
    try:
        await send_email(
            integration=integration_dict,
            to_email=customer_email,
            subject=subject,
            body_text=reply_text,
            thread_id=thread_id,
            in_reply_to=last_message_id,
            references=last_message_id,
        )
    except Exception as e:
        with connect() as c:
            c.execute(
                """UPDATE conversion_requests SET status = 'pending'
                   WHERE id = ? AND user_id = ? AND status = 'validating'""",
                (request_id, user_id),
            )
        logger.error(f"Erro ao enviar confirmação ({channel_name}): {e}")
        raise RuntimeError(f"Mensagem gerada, mas falha no envio: {str(e)}")

    # Só confirma o pedido no histórico depois de o canal aceitar a mensagem.
    with connect() as c:
        updated = c.execute(
            """UPDATE conversion_requests SET status = ?, resolved_at = CURRENT_TIMESTAMP
               WHERE id = ? AND user_id = ? AND status = 'validating'""",
            (new_status, request_id, user_id),
        )
        if not updated.rowcount:
            raise RuntimeError("A mensagem foi enviada, mas o estado do pedido mudou inesperadamente.")
        c.execute(
            "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, ?, ?)",
            (user_id, req["contact_id"], sender_role, reply_text)
        )
        c.execute("UPDATE contacts SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?", (req["contact_id"],))
        _safe_invalidate_dashboard_cache(user_id)

    return {
        "ok": True,
        "action": action,
        "status": new_status,
        "reply_text": reply_text,
        "customer_email": customer_email
    }


async def send_ai_booking_reminder(user_id: int, request_id: int) -> Dict[str, Any]:
    """Generate and send a contextual reminder for a future scheduled request."""
    with connect() as c:
        req = c.execute(
            """SELECT r.id, r.request_type, r.details, r.status, r.scheduled_at,
                      ct.id AS contact_id, ct.name, ct.contact_key
               FROM conversion_requests r
               JOIN contacts ct ON ct.id = r.contact_id
               WHERE r.id = ? AND r.user_id = ?""",
            (request_id, user_id),
        ).fetchone()
        if not req or not req["scheduled_at"]:
            raise ValueError("Este pedido ainda não tem data e hora registadas.")
        if req["status"] not in ("confirmed", "confirmed_manual"):
            raise ValueError("Só é possível enviar lembretes para marcações já validadas.")

        scheduled_at = _parse_utc_datetime(req["scheduled_at"])
        if scheduled_at is None or scheduled_at <= datetime.now(timezone.utc):
            raise ValueError("Só é possível lembrar o cliente sobre uma marcação futura.")

        user = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        email_integration = c.execute(
            "SELECT * FROM email_integrations WHERE user_id = ? AND status = 'connected' AND provider = 'google'",
            (user_id,),
        ).fetchone()
        email_thread = c.execute(
            """SELECT subject, thread_id, last_message_id FROM email_threads
               WHERE contact_id = ? AND user_id = ? ORDER BY updated_at DESC LIMIT 1""",
            (req["contact_id"], user_id),
        ).fetchone()
        history_rows = c.execute(
            """SELECT sender, content FROM messages
               WHERE contact_id = ? AND user_id = ? ORDER BY id DESC LIMIT 10""",
            (req["contact_id"], user_id),
        ).fetchall()

    customer_key = req["contact_key"]
    if "@" not in customer_key:
        raise ValueError("Este cliente não tem um endereço de e-mail para receber o lembrete.")
    if not email_integration:
        raise ValueError("Não há e-mail conectado para enviar o lembrete deste cliente.")

    local_scheduled = scheduled_at.astimezone(BUSINESS_TIMEZONE)
    days_remaining = (local_scheduled.date() - datetime.now(BUSINESS_TIMEZONE).date()).days
    date_text = local_scheduled.strftime("%d/%m/%Y às %H:%M")
    if days_remaining == 0:
        countdown = "hoje"
    elif days_remaining == 1:
        countdown = "amanhã (falta 1 dia)"
    else:
        countdown = f"daqui a {days_remaining} dias (faltam {days_remaining} dias)"
    user_dict = dict(user) if user else {}
    business_name = user_dict.get("name") or "nosso negócio"
    contact_name = req["name"] or customer_key
    latest_customer_message = next(
        (row["content"] for row in reversed(history_rows) if row["sender"] == "customer"),
        "",
    )
    language = (
        detect_message_language(latest_customer_message)
        if latest_customer_message
        else ("en" if (user_dict.get("language") or "").lower().startswith("en") else "pt")
    )
    request_details = _client_schedule_fragment((req["details"] or "").strip())
    booking_time = f"Data e hora da marcação: {date_text}"
    if language == "en":
        reply_text = (
            f"Hello, {contact_name}.\n\n"
            f"This is a reminder that your {req['request_type']} is scheduled for "
            f"{date_text} ({countdown}).\n\n"
            f"Appointment date and time: {date_text}"
        )
        if request_details:
            reply_text += f"\n\nRequest details: {request_details}"
        reply_text += f"\n\nRegards,\n{business_name}"
    else:
        reply_text = (
            f"Olá, {contact_name}.\n\n"
            f"Este é um lembrete de que o seu pedido ({req['request_type']}) está marcado "
            f"para {date_text} ({countdown}).\n\n"
            f"{booking_time}"
        )
        if request_details:
            reply_text += f"\n\nDetalhes do pedido: {request_details}"
        reply_text += f"\n\nCom os melhores cumprimentos,\n{business_name}"

    integration_dict = dict(email_integration)
    subject = email_thread["subject"] if email_thread and email_thread["subject"] else "Lembrete da sua marcação"
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    last_message_id = email_thread["last_message_id"] if email_thread else None
    await send_email(
        integration=integration_dict,
        to_email=customer_key,
        subject=subject,
        body_text=reply_text,
        thread_id=email_thread["thread_id"] if email_thread else None,
        in_reply_to=last_message_id,
        references=last_message_id,
    )

    with connect() as c:
        c.execute(
            "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'agent', ?)",
            (user_id, req["contact_id"], reply_text),
        )
        c.execute(
            "UPDATE contacts SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?",
            (req["contact_id"],),
        )

    return {
        "ok": True,
        "channel": "email",
        "reply_text": reply_text,
        "scheduled_at": scheduled_at.isoformat(),
        "days_remaining": days_remaining,
    }


async def send_owner_reply(user_id: int, contact_id: int, message_text: str) -> Dict[str, Any]:
    """
    Envia uma resposta oficial escrita manualmente pelo proprietário via Gmail.
    """
    message_text = message_text.strip()
    if not message_text:
        raise ValueError("A mensagem não pode estar vazia.")

    with connect() as c:
        contact = c.execute(
            "SELECT id, name, contact_key FROM contacts WHERE id = ? AND user_id = ?",
            (contact_id, user_id)
        ).fetchone()
        if not contact:
            raise ValueError("Cliente não encontrado.")

        email_integration = c.execute(
            "SELECT * FROM email_integrations WHERE user_id = ? AND status = 'connected' AND provider = 'google'",
            (user_id,)
        ).fetchone()

        thread = c.execute(
            "SELECT subject, thread_id, last_message_id FROM email_threads WHERE contact_id = ? AND user_id = ? ORDER BY updated_at DESC LIMIT 1",
            (contact_id, user_id)
        ).fetchone()

    if "@" not in contact["contact_key"]:
        raise ValueError("Este cliente não tem um endereço de e-mail para receber a resposta.")

    if not email_integration:
        raise ValueError("Nenhuma conta de e-mail conectada para envio. Conecte o e-mail em Configurações.")

    customer_email = contact["contact_key"]
    subject = thread["subject"] if thread and thread["subject"] else "Mensagem de Atendimento"
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    thread_id = thread["thread_id"] if thread else None
    last_msg_id = thread["last_message_id"] if thread else None

    # Envia e-mail oficial
    integration_dict = dict(email_integration)
    await send_email(
        integration=integration_dict,
        to_email=customer_email,
        subject=subject,
        body_text=message_text,
        thread_id=thread_id,
        in_reply_to=last_msg_id,
        references=last_msg_id,
    )

    # Registra no histórico como sender = 'owner'
    with connect() as c:
        cur = c.execute(
            "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'owner', ?)",
            (user_id, contact_id, message_text)
        )
        msg_id = cur.lastrowid
        c.execute("UPDATE contacts SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?", (contact_id,))

    return {"ok": True, "channel": "email", "message_id": msg_id, "content": message_text}


def generate_booking_options(info_rows=None, base_dt: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """
    Gera opções de marcações disponíveis para apresentação em opções no portal/campo de marcações.
    Exemplo solicitado: Opção 1 dia 23/11/2026 às 8 ou 7 ou 13 horas.
    """
    base = base_dt or datetime.now(BUSINESS_TIMEZONE)
    # Procurar a partir de amanhã
    current = base + timedelta(days=1)
    
    # Horários pretendidos: 08:00, 13:00
    slot_hours = [8, 13]

    hours_info = ""
    if info_rows:
        for r in info_rows:
            kind = r.get("kind") if isinstance(r, dict) else r["kind"]
            if kind in ("horarios", "horario"):
                hours_info = (r.get("content") if isinstance(r, dict) else r["content"]) or ""
                break

    options = []
    opt_idx = 1
    checked_days = 0

    while len(options) < 8 and checked_days < 14:
        # Pula fins de semana se o negócio fecha aos sábados/domingos
        if current.weekday() in (5, 6):
            current += timedelta(days=1)
            checked_days += 1
            continue

        day_str = current.strftime("%d/%m/%Y")
        for hour in slot_hours:
            dt_slot = current.replace(hour=hour, minute=0, second=0, microsecond=0)
            iso_str = dt_slot.astimezone(timezone.utc).isoformat()
            time_str = f"{hour:02d}:00"
            label = f"Opção {opt_idx}: Dia {day_str} às {time_str}"
            options.append({
                "id": f"opt_{opt_idx}",
                "label": label,
                "date": day_str,
                "time": time_str,
                "iso": iso_str,
            })
            opt_idx += 1
            if len(options) >= 8:
                break
        current += timedelta(days=1)
        checked_days += 1

    return options


def extract_booking_option_choice(text: str, options: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Identifica se a mensagem do cliente seleciona uma das opções de marcação oferecidas no Gmail.
    Aceita:
      - "Opção 1", "opcao 2", "Opção 3"
      - "Seleciono a Opção 1: Dia 23/11/2026 às 08:00"
      - "Quero a opção 1", "Pode ser a opção 2", "Prefiro a opção 3"
      - "1" ou "2" (se o cliente apenas responder com o número da opção)
      - Correspondência por data e hora de uma das opções
    """
    if not text or not options:
        return None
    cleaned = clean_email_body(text).strip()

    # 1. Procura 'Opção X' ou 'opcao X'
    match = re.search(r"\bop[cç][aã]o\s*(\d+)\b", cleaned, re.IGNORECASE)
    if match:
        opt_idx = int(match.group(1)) - 1
        if 0 <= opt_idx < len(options):
            return options[opt_idx]

    # 2. Se a mensagem for apenas o número da opção (ex: "1" ou "2")
    if cleaned.isdigit():
        opt_idx = int(cleaned) - 1
        if 0 <= opt_idx < len(options):
            return options[opt_idx]

    # 3. Procura correspondência por data e hora de uma das opções
    for opt in options:
        if opt.get("date") and opt["date"] in cleaned and opt.get("time") and opt["time"] in cleaned:
            return opt

    return None


async def handle_booking_selection(
    user_id: int,
    contact_id: int,
    customer_email: str,
    customer_name: str,
    slot_label: str,
    scheduled_at: str,
    notes: str = "",
) -> Dict[str, Any]:
    """
    Processa a escolha feita pelo cliente através do botão e opções de marcação.
    - No modo totalmente automático ('full'):
      Registra imediatamente no quadro de marcações e envia a mensagem confirmando a marcação
      com sucesso e os detalhes (nome e data e horário escolhida).
    - No modo semi-automático ('semi'):
      A intenção vai para 'pedidos aguardando validação' (pending).
      Após ser validada pelo proprietário, a marcação é adicionada ao quadro de marcações
      e a mensagem de confirmação com detalhes é enviada ao cliente.
    """
    resolved_scheduled_at = scheduled_at
    parsed_dt = _parse_utc_datetime(scheduled_at)
    if parsed_dt is None:
        extracted = extract_scheduled_at(f"{slot_label} {scheduled_at}")
        if extracted:
            resolved_scheduled_at = extracted
            parsed_dt = _parse_utc_datetime(extracted)

    summary = _extract_booking_summary(slot_label, "booking", resolved_scheduled_at)
    date_str = summary["date_str"] or slot_label

    with connect() as c:
        user = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise ValueError("Conta de negócio não encontrada.")
        user_dict = dict(user)

        contact = c.execute("SELECT * FROM contacts WHERE id = ? AND user_id = ?", (contact_id, user_id)).fetchone()
        contact_dict = dict(contact) if contact else {}

        final_customer_name = customer_name.strip() if customer_name else (contact_dict.get("name") or "Cliente")
        if customer_name.strip() and contact:
            c.execute(
                "UPDATE contacts SET name = ?, last_message_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
                (customer_name.strip(), contact_id, user_id),
            )

        mandatory = {}
        if user_dict.get("mandatory_responses"):
            try:
                mandatory = json.loads(user_dict["mandatory_responses"])
            except Exception:
                mandatory = {}
        automation_level = mandatory.get("automation_level", "full")
        business_name = user_dict.get("name") or "nosso negócio"

        existing_req = c.execute(
            """SELECT id, status FROM conversion_requests
               WHERE user_id = ? AND contact_id = ?
                 AND status IN ('pending', 'validating', 'awaiting_schedule', 'awaiting_client_confirmation')
               ORDER BY id DESC LIMIT 1""",
            (user_id, contact_id),
        ).fetchone()

        details_text = f"Opção de marcação escolhida pelo cliente: {slot_label}\nData e hora escolhidas pelo cliente: {date_str}"
        if notes:
            details_text += f"\nNotas: {notes}"

        integration = c.execute(
            "SELECT * FROM email_integrations WHERE user_id = ? AND status = 'connected' AND provider = 'google'",
            (user_id,),
        ).fetchone()

        email_thread = c.execute(
            "SELECT subject, thread_id, last_message_id FROM email_threads WHERE contact_id = ? AND user_id = ? ORDER BY updated_at DESC LIMIT 1",
            (contact_id, user_id),
        ).fetchone()

        thread_id = email_thread["thread_id"] if email_thread else None
        last_message_id = email_thread["last_message_id"] if email_thread else None
        thread_subject = email_thread["subject"] if email_thread else f"Confirmação de Agendamento - {business_name}"
        if thread_subject and not thread_subject.lower().startswith("re:"):
            thread_subject = f"Re: {thread_subject}"

    if automation_level == "full":
        # MODO TOTALMENTE AUTOMÁTICO:
        # Registra imediatamente no quadro de marcações (confirmed)
        with connect() as c:
            if existing_req:
                c.execute(
                    """UPDATE conversion_requests
                       SET status = 'confirmed', scheduled_at = ?, resolved_at = CURRENT_TIMESTAMP, details = ?
                       WHERE id = ? AND user_id = ?""",
                    (resolved_scheduled_at, details_text, existing_req["id"], user_id),
                )
                req_id = existing_req["id"]
            else:
                cur = c.execute(
                    """INSERT INTO conversion_requests
                       (user_id, contact_id, request_type, details, status, scheduled_at, resolved_at)
                       VALUES (?, ?, 'booking', ?, 'confirmed', ?, CURRENT_TIMESTAMP)""",
                    (user_id, contact_id, details_text, resolved_scheduled_at),
                )
                req_id = cur.lastrowid

            c.execute(
                "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'customer', ?)",
                (user_id, contact_id, f"[Portal de Agendamento] O cliente selecionou: {slot_label}"),
            )

        _safe_invalidate_dashboard_cache(user_id)

        reply_text = _build_request_status_reply(
            customer_name=final_customer_name,
            business_name=business_name,
            details=details_text,
            confirmed=True,
            language=detect_message_language(slot_label),
            request_type="booking",
            scheduled_at=resolved_scheduled_at,
        )

        if integration and customer_email:
            try:
                await send_email(
                    integration=dict(integration),
                    to_email=customer_email,
                    subject=thread_subject,
                    body_text=reply_text,
                    thread_id=thread_id,
                    in_reply_to=last_message_id,
                    references=last_message_id,
                )
            except Exception as e:
                logger.warning(f"Erro ao enviar e-mail de confirmação automática: {e}")

        with connect() as c:
            c.execute(
                "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'agent', ?)",
                (user_id, contact_id, reply_text),
            )
            c.execute("UPDATE contacts SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?", (contact_id,))

        return {
            "ok": True,
            "mode": "full",
            "mode_full": True,   # flag para AMP mustache {{#mode_full}}
            "mode_semi": False,
            "status": "confirmed",
            "request_id": req_id,
            "message": "A sua marcação foi registada com sucesso!",
            "customer_name": final_customer_name,
            "slot_label": slot_label,
            "scheduled_at": resolved_scheduled_at,
            "date_str": date_str,
        }

    else:
        # MODO SEMI-AUTOMÁTICO:
        # Vai para pedidos aguardando validação (pending)
        with connect() as c:
            if existing_req:
                c.execute(
                    """UPDATE conversion_requests
                       SET status = 'pending', scheduled_at = ?, details = ?
                       WHERE id = ? AND user_id = ?""",
                    (resolved_scheduled_at, details_text, existing_req["id"], user_id),
                )
                req_id = existing_req["id"]
            else:
                cur = c.execute(
                    """INSERT INTO conversion_requests
                       (user_id, contact_id, request_type, details, status, scheduled_at)
                       VALUES (?, ?, 'booking', ?, 'pending', ?)""",
                    (user_id, contact_id, details_text, resolved_scheduled_at),
                )
                req_id = cur.lastrowid

            c.execute(
                "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'customer', ?)",
                (user_id, contact_id, f"[Portal de Agendamento] Intenção de marcação selecionada: {slot_label}"),
            )
            c.execute("UPDATE contacts SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?", (contact_id,))

        _safe_invalidate_dashboard_cache(user_id)

        return {
            "ok": True,
            "mode": "semi",
            "mode_full": False,
            "mode_semi": True,   # flag para AMP mustache {{#mode_semi}}
            "status": "pending",
            "request_id": req_id,
            "message": "O seu pedido de marcação foi recebido e aguarda validação da equipa.",
            "customer_name": final_customer_name,
            "slot_label": slot_label,
            "scheduled_at": resolved_scheduled_at,
            "date_str": date_str,
        }
