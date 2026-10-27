import asyncio
import base64
import email
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import html
import imaplib
import json
import logging
import os
import re
import smtplib
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
from dotenv import load_dotenv
import httpx

from backend.database import connect
from backend.services.billing_service import get_last_successful_payment_at
from backend.services.agent import draft_reply

load_dotenv()

logger = logging.getLogger("drexier.email_service")

# Constantes de OAuth para Google e Microsoft
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

MICROSOFT_AUTH_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
MICROSOFT_TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
MICROSOFT_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

MICROSOFT_SCOPES = [
    "offline_access",
    "User.Read",
    "Mail.ReadWrite",
    "Mail.Send",
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

    ms_client_id = os.getenv("MICROSOFT_CLIENT_ID", "").strip()
    ms_client_secret = os.getenv("MICROSOFT_CLIENT_SECRET", "").strip()
    ms_tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common").strip() or "common"
    ms_redirect_uri = os.getenv(
        "MICROSOFT_REDIRECT_URI",
        "http://localhost:8000/api/email/oauth/microsoft/callback"
    ).strip()

    return {
        "google": {
            "client_id": google_client_id,
            "client_secret": google_client_secret,
            "redirect_uri": google_redirect_uri,
            "configured": bool(google_client_id and google_client_secret),
        },
        "microsoft": {
            "client_id": ms_client_id,
            "client_secret": ms_client_secret,
            "tenant_id": ms_tenant_id,
            "redirect_uri": ms_redirect_uri,
            "configured": bool(ms_client_id and ms_client_secret),
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


# ==============================================================================
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


async def refresh_google_token_if_needed(integration: dict) -> str:
    """Renova o token da Google se expirado ou prestes a expirar."""
    access_token = integration.get("access_token", "")
    refresh_token = integration.get("refresh_token", "")
    expires_at = integration.get("token_expires_at")

    now = time.time()
    # Se ainda tem validade (com margem de 60s), usa o atual
    if expires_at and float(expires_at) > (now + 60) and access_token:
        return access_token

    if not refresh_token:
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
            expires_in = data.get("expires_in", 3600)
            new_expires_at = str(now + expires_in)
            with connect() as c:
                c.execute(
                    "UPDATE email_integrations SET access_token=?, token_expires_at=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (new_access_token, new_expires_at, integration["id"])
                )
            return new_access_token
        else:
            logger.warning(f"Erro ao renovar token Google: {res.text}")
            return access_token


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


# ==============================================================================
# MICROSOFT OAUTH2 (OUTLOOK / GRAPH)
# ==============================================================================

def build_microsoft_auth_url(state: str) -> str:
    """Gera o link oficial da Microsoft para conceder permissões de leitura e envio de e-mails."""
    config = get_email_config()["microsoft"]
    if not config["client_id"]:
        raise ValueError("MICROSOFT_CLIENT_ID não configurado no ficheiro .env")

    auth_url = MICROSOFT_AUTH_URL_TEMPLATE.format(tenant=config["tenant_id"])
    params = {
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "response_type": "code",
        "scope": " ".join(MICROSOFT_SCOPES),
        "response_mode": "query",
        "state": state,
    }
    return f"{auth_url}?{urllib.parse.urlencode(params)}"


async def exchange_microsoft_code(code: str) -> Dict[str, Any]:
    """Troca o authorization code pelo access_token e refresh_token da Microsoft."""
    config = get_email_config()["microsoft"]
    token_url = MICROSOFT_TOKEN_URL_TEMPLATE.format(tenant=config["tenant_id"])
    payload = {
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": config["redirect_uri"],
        "scope": " ".join(MICROSOFT_SCOPES),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(token_url, data=payload)
        data = res.json()
        if res.status_code != 200:
            err = data.get("error_description") or data.get("error") or "Erro na autorização com Microsoft"
            raise ValueError(f"Falha Microsoft OAuth: {err}")
        return data


async def refresh_microsoft_token_if_needed(integration: dict) -> str:
    """Renova o token da Microsoft se expirado ou prestes a expirar."""
    access_token = integration.get("access_token", "")
    refresh_token = integration.get("refresh_token", "")
    expires_at = integration.get("token_expires_at")

    now = time.time()
    if expires_at and float(expires_at) > (now + 60) and access_token:
        return access_token

    if not refresh_token:
        return access_token

    config = get_email_config()["microsoft"]
    token_url = MICROSOFT_TOKEN_URL_TEMPLATE.format(tenant=config["tenant_id"])
    payload = {
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": " ".join(MICROSOFT_SCOPES),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(token_url, data=payload)
        if res.status_code == 200:
            data = res.json()
            new_access_token = data.get("access_token")
            new_refresh = data.get("refresh_token", refresh_token)
            expires_in = data.get("expires_in", 3600)
            new_expires_at = str(now + expires_in)
            with connect() as c:
                c.execute(
                    "UPDATE email_integrations SET access_token=?, refresh_token=?, token_expires_at=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (new_access_token, new_refresh, new_expires_at, integration["id"])
                )
            return new_access_token
        else:
            logger.warning(f"Erro ao renovar token Microsoft: {res.text}")
            return access_token


async def fetch_microsoft_user_profile(access_token: str) -> Tuple[str, str]:
    """Obtém o endereço de e-mail e nome da conta Microsoft Graph conectada."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        res = await client.get(f"{MICROSOFT_GRAPH_BASE}/me", headers=headers)
        if res.status_code == 200:
            data = res.json()
            email_addr = data.get("mail") or data.get("userPrincipalName", "")
            return email_addr, data.get("displayName", "")
    return "", ""


# ==============================================================================
# ENVIO DE E-MAILS (GMAIL, MICROSOFT GRAPH OU SMTP)
# ==============================================================================

def create_mime_message(
    sender: str,
    to: str,
    subject: str,
    body_text: str,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None
) -> MIMEMultipart:
    """Cria mensagem MIME em formato texto e HTML simples."""
    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    # Texto puro
    part1 = MIMEText(body_text, "plain", "utf-8")
    msg.attach(part1)

    # HTML com quebras de linha preservadas
    html_content = (
        "<div style=\"font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 15px; color: #222; line-height: 1.6;\">"
        + "<p style=\"white-space: pre-line; margin: 0;\">"
        + html.escape(body_text)
        + "</p>"
        + "</div>"
    )
    part2 = MIMEText(html_content, "html", "utf-8")
    msg.attach(part2)

    return msg


async def send_email(
    integration: dict,
    to_email: str,
    subject: str,
    body_text: str,
    thread_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Envia uma mensagem de e-mail usando o provedor conectado (Google Gmail, Microsoft Outlook ou SMTP).
    """
    provider = integration.get("provider")
    sender_email = integration.get("email_address")
    sender_name = integration.get("display_name")
    from_header = f"{sender_name} <{sender_email}>" if sender_name else sender_email

    if provider == "google":
        token = await refresh_google_token_if_needed(integration)
        mime_msg = create_mime_message(from_header, to_email, subject, body_text, in_reply_to, references)
        raw_base64 = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")

        payload: Dict[str, Any] = {"raw": raw_base64}
        if thread_id:
            payload["threadId"] = thread_id

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(f"{GMAIL_API_BASE}/messages/send", headers=headers, json=payload)
            if res.status_code not in (200, 201):
                logger.error(f"Erro Gmail send: {res.text}")
                raise ValueError(f"Falha ao enviar e-mail via Gmail: {res.text}")
            return res.json()

    elif provider == "microsoft":
        token = await refresh_microsoft_token_if_needed(integration)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        mail_payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "Text",
                    "content": body_text,
                },
                "toRecipients": [
                    {"emailAddress": {"address": to_email}}
                ],
            },
            "saveToSentItems": "true",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(f"{MICROSOFT_GRAPH_BASE}/me/sendMail", headers=headers, json=mail_payload)
            if res.status_code not in (200, 202):
                logger.error(f"Erro Microsoft sendMail: {res.text}")
                raise ValueError(f"Falha ao enviar e-mail via Outlook: {res.text}")
            return {"status": "sent", "provider": "microsoft"}

    elif provider == "smtp_imap":
        # Envio padrão via SMTP
        smtp_host = integration.get("smtp_host")
        smtp_port = integration.get("smtp_port") or 587
        smtp_user = integration.get("smtp_user") or sender_email
        smtp_pass = integration.get("smtp_password")

        mime_msg = create_mime_message(from_header, to_email, subject, body_text, in_reply_to, references)

        if not smtp_host:
            raise ValueError("Servidor SMTP não configurado.")

        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20) as server:
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.send_message(mime_msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
                server.ehlo()
                try:
                    server.starttls()
                    server.ehlo()
                except Exception:
                    pass
                if smtp_user and smtp_pass:
                    server.login(smtp_user, smtp_pass)
                server.send_message(mime_msg)

        return {"status": "sent", "provider": "smtp"}

    else:
        raise ValueError(f"Provedor de email desconhecido: {provider}")


# ==============================================================================
# SINCRONIZAÇÃO E PROCESSAMENTO AUTOMÁTICO DE RESPOSTAS (IA DREXIER)
# ==============================================================================

def clean_email_body(body: str) -> str:
    """Limpa assinaturas e citações antigas de respostas de e-mail."""
    if not body:
        return ""
    # Corta em marcadores comuns de resposta
    lines = body.splitlines()
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^On\s+.+wrote:$", stripped, re.IGNORECASE):
            break
        if re.match(r"^-+\s*Original Message\s*-+", stripped, re.IGNORECASE):
            break
        if re.match(r"^Em\s+.+escreveu:$", stripped, re.IGNORECASE):
            break
        if stripped.startswith(">"):
            continue
        clean_lines.append(line)
    result = "\n".join(clean_lines).strip()
    return result if result else body.strip()


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

    # 1. Filtro por Categorias/Labels do Gmail
    forbidden_labels = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES", "CATEGORY_FORUMS", "SPAM", "TRASH"}
    found_forbidden = forbidden_labels.intersection(label_ids)
    if found_forbidden:
        return False, f"Categoria de publicidade/atualização ({', '.join(found_forbidden)})"

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
    """
    text = f"{subject}\n{incoming_content}".lower()

    booking_patterns = [
        r"\b(marcar|marca[çc][aã]o|agendar|agendamento|reservar?|reserva)\b",
        r"\b(disponibilidade\s+(para|no|na)|vaga\s+(para|no|na)|hor[aá]rio\s+(para|dispon[ií]vel))\b",
        r"\b(segunda|ter[çc]a|quarta|quinta|sexta|s[aá]bado|domingo)\b.*(\b[aà]s\s+\d{1,2}(h|:\d{2})?|\bmanh[aã]|\btarde)",
        r"\b(\d{1,2}/\d{1,2}|\d{1,2}\s+de\s+[a-z]+)\b.*(\b[aà]s\s+\d{1,2}|\bhor[aá]rio)"
    ]

    purchase_patterns = [
        r"\b(comprar|compra|adquirir|encomendar?|encomenda)\b",
        r"\b(fechar\s+(o\s+)?pedido|fechar\s+(o\s+)?or[çc]amento|quero\s+contratar|quero\s+o\s+produto)\b"
    ]

    for pat in booking_patterns:
        if re.search(pat, text, re.IGNORECASE):
            return {"type": "booking", "details": incoming_content[:300].strip()}

    for pat in purchase_patterns:
        if re.search(pat, text, re.IGNORECASE):
            return {"type": "purchase", "details": incoming_content[:300].strip()}

    return None


async def sync_google_emails(user_dict: dict, integration: dict) -> List[Dict[str, Any]]:
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
        # Busca mensagens não lidas apenas da categoria principal, ignorando spam e promoções
        query = "label:INBOX is:unread -category:promotions -category:social -category:updates -category:forums -label:spam -label:trash"
        list_url = f"{GMAIL_API_BASE}/messages?q={urllib.parse.quote(query)}&maxResults=15"
        res = await client.get(list_url, headers=headers)
        if res.status_code != 200:
            logger.warning(f"Falha ao listar mensagens do Gmail: {res.text}")
            return []

        messages_list = res.json().get("messages", [])
        for m in messages_list:
            msg_id = m.get("id")
            thread_id = m.get("threadId")

            msg_res = await client.get(f"{GMAIL_API_BASE}/messages/{msg_id}?format=full", headers=headers)
            if msg_res.status_code != 200:
                continue

            msg_data = msg_res.json()
            label_ids = msg_data.get("labelIds", [])

            # Filtro por data de recebimento: após pagamento e ligação da integração
            if cutoff_ts is not None:
                try:
                    internal_date = msg_data.get("internalDate")
                    if internal_date is None or int(internal_date) < cutoff_ts:
                        if internal_date is not None:
                            await client.post(
                                f"{GMAIL_API_BASE}/messages/{msg_id}/modify",
                                headers=headers,
                                json={"removeLabelIds": ["UNREAD"]}
                            )
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

            # Ignora se for enviado pelo próprio utilizador
            if not sender_email or sender_email == my_email:
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
                # Remove unread para não verificar repetidamente
                await client.post(
                    f"{GMAIL_API_BASE}/messages/{msg_id}/modify",
                    headers=headers,
                    json={"removeLabelIds": ["UNREAD"]}
                )
                continue

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

            # Remove a label UNREAD do Gmail para não responder repetidamente
            await client.post(
                f"{GMAIL_API_BASE}/messages/{msg_id}/modify",
                headers=headers,
                json={"removeLabelIds": ["UNREAD"]}
            )

            processed_items.append({
                "message_id": msg_id,
                "from": sender_email,
                "subject": subject,
                "reply": reply_text
            })

    return processed_items


async def sync_microsoft_emails(user_dict: dict, integration: dict) -> List[Dict[str, Any]]:
    """
    Sincroniza e-mails não lidos do Microsoft Outlook / Graph,
    gera respostas inteligentes com a IA e envia automaticamente ao cliente.
    """
    token = await refresh_microsoft_token_if_needed(integration)
    headers = {"Authorization": f"Bearer {token}"}
    my_email = (integration.get("email_address") or "").lower().strip()

    cutoff_at = get_email_response_cutoff(integration)
    if cutoff_at is None:
        logger.warning("Sincronização Outlook bloqueada: não há data de pagamento confirmado válida.")
        return []

    processed_items = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Busca mensagens não lidas
        url = f"{MICROSOFT_GRAPH_BASE}/me/mailFolders/Inbox/messages?$filter=isRead eq false&$top=15&$orderby=receivedDateTime desc"
        res = await client.get(url, headers=headers)
        if res.status_code != 200:
            logger.warning(f"Falha ao listar mensagens do Outlook: {res.text}")
            return []

        messages = res.json().get("value", [])
        for m in messages:
            msg_id = m.get("id")
            conversation_id = m.get("conversationId")
            subject = m.get("subject", "Sem assunto")
            sender_obj = m.get("from", {}).get("emailAddress", {})
            sender_email = (sender_obj.get("address") or "").lower().strip()
            customer_name = sender_obj.get("name", "")
            body_content = m.get("body", {}).get("content", "")
            content_type = m.get("body", {}).get("contentType", "text")
            received_dt = m.get("receivedDateTime")

            # Filtro por data de recebimento: após pagamento e ligação da integração
            if received_dt:
                try:
                    received_at = _parse_utc_datetime(received_dt)
                    if received_at is None:
                        raise ValueError("data de recebimento ausente ou inválida")
                    if received_at < cutoff_at:
                        await client.patch(
                            f"{MICROSOFT_GRAPH_BASE}/me/messages/{msg_id}",
                            headers=headers,
                            json={"isRead": True}
                        )
                        logger.info(f"E-mail Outlook {msg_id} anterior ao início da cobertura paga ignorado.")
                        continue
                except ValueError:
                    logger.warning(f"Data de recebimento inválida no e-mail Outlook {msg_id}; mensagem mantida sem resposta.")
                    continue
            else:
                logger.warning(f"Data de recebimento ausente no e-mail Outlook {msg_id}; mensagem mantida sem resposta.")
                continue

            if not sender_email or sender_email == my_email:
                continue

            if content_type.lower() == "html":
                text_clean = re.sub(r"<[^>]+>", " ", body_content)
                text_clean = html.unescape(text_clean)
            else:
                text_clean = body_content

            body_text = clean_email_body(text_clean) or "(Email sem corpo de texto legível)"

            # Filtro anti-spam / anúncios
            is_valid, reject_reason = is_genuine_customer_inquiry(
                sender_email=sender_email,
                customer_name=customer_name,
                subject=subject,
                body=body_text,
            )
            if not is_valid:
                logger.info(f"[Filtro Anti-Spam] E-mail Outlook de {sender_email} ('{subject}') ignorado: {reject_reason}")
                await client.patch(
                    f"{MICROSOFT_GRAPH_BASE}/me/messages/{msg_id}",
                    headers=headers,
                    json={"isRead": True}
                )
                continue

            reply_text = await process_and_reply_email(
                user_dict=user_dict,
                integration=integration,
                customer_email=sender_email,
                customer_name=customer_name,
                subject=subject,
                incoming_content=body_text,
                thread_id=conversation_id,
                message_id_header=msg_id,
            )

            # Marca como lida na Microsoft Graph
            await client.patch(
                f"{MICROSOFT_GRAPH_BASE}/me/messages/{msg_id}",
                headers=headers,
                json={"isRead": True}
            )

            processed_items.append({
                "message_id": msg_id,
                "from": sender_email,
                "subject": subject,
                "reply": reply_text
            })

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

    with connect() as c:
        # Localiza ou cria o contacto pelo e-mail
        contact = c.execute(
            "SELECT id, name FROM contacts WHERE user_id = ? AND contact_key = ?",
            (user_id, customer_email)
        ).fetchone()

        if contact:
            cid = contact["id"]
            new_name = customer_name or contact["name"] or ""
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

        # Salva mensagem recebida do cliente
        c.execute(
            "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'customer', ?)",
            (user_id, cid, f"Assunto: {subject}\n\n{incoming_content}")
        )

        # Detecção automática de marcação ou compra para o painel de pedidos a confirmar do proprietário
        intent = detect_booking_or_purchase_intent(incoming_content, subject)
        if intent:
            has_pending = c.execute(
                "SELECT id FROM conversion_requests WHERE user_id = ? AND contact_id = ? AND status = 'pending'",
                (user_id, cid)
            ).fetchone()
            if not has_pending:
                c.execute(
                    """INSERT INTO conversion_requests(user_id, contact_id, request_type, details, status)
                       VALUES (?, ?, ?, ?, 'pending')""",
                    (user_id, cid, intent["type"], intent["details"])
                )
                logger.info(f"[Conversão Automática] Pedido de {intent['type']} detectado e registrado para {customer_email}.")

        # Histórico recente de mensagens desse cliente
        history_rows = c.execute(
            "SELECT sender, content FROM messages WHERE contact_id = ? AND user_id = ? AND id != last_insert_rowid() ORDER BY id DESC LIMIT 10",
            (cid, user_id)
        ).fetchall()
        history = [{"sender": r["sender"], "content": r["content"]} for r in reversed(history_rows)]

        # Base de conhecimento do negócio
        info = c.execute(
            "SELECT kind, title, content, metadata FROM business_info WHERE user_id = ?",
            (user_id,)
        ).fetchall()

        mandatory = {}
        try:
            mandatory = json.loads(user_dict.get("mandatory_responses") or "{}")
        except Exception:
            pass

    # Verifica se as respostas automáticas estão ativadas para o agente
    auto_reply = bool(integration.get("auto_reply_enabled", 1))
    if not auto_reply:
        logger.info(
            f"[Auto-Reply Desativado] Mensagem de {customer_email} registada com sucesso. Resposta automática pausada pelo utilizador."
        )
        return "(Resposta automática desativada pelo utilizador)"

    # Gerar resposta com a IA Drexier (Gemini ou fallback)
    try:
        reply_text = await draft_reply(
            message=incoming_content,
            info_rows=info,
            instructions=user_dict.get("agent_instructions") or "",
            language=user_dict.get("language") or "Português",
            history=history,
            business_name=user_dict.get("name") or integration.get("display_name") or "nosso negócio",
            business_type=user_dict.get("business_type") or "Serviços",
            business_description=user_dict.get("business_description") or "",
            mandatory_responses=mandatory,
        )
    except Exception as e:
        logger.error(f"Erro ao gerar resposta com a IA: {e}")
        reply_text = "Agradecemos o seu e-mail! Recebemos a sua mensagem e daremos retorno brevemente."

    # Salva a resposta da IA no banco de dados
    with connect() as c:
        c.execute(
            "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'agent', ?)",
            (user_id, cid, reply_text)
        )
        c.execute("UPDATE contacts SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?", (cid,))

        # Atualiza a tabela de tópicos (email_threads)
        reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
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

    # Envia o e-mail de resposta de volta ao cliente pelo provedor configurado
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
        logger.info(f"Resposta enviada com sucesso por e-mail para {customer_email}")
    except Exception as e:
        logger.error(f"Erro ao enviar resposta por e-mail: {e}")

    return reply_text


def extract_imap_body(msg: email.message.Message) -> str:
    """Extrai texto legível de uma mensagem de e-mail MIME recebida via IMAP."""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdisp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in cdisp:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        for part in msg.walk():
            ctype = part.get_content_type()
            cdisp = str(part.get("Content-Disposition") or "")
            if ctype == "text/html" and "attachment" not in cdisp:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    raw_html = payload.decode(charset, errors="replace")
                    return html.unescape(re.sub(r"<[^>]+>", " ", raw_html))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                return html.unescape(re.sub(r"<[^>]+>", " ", text))
            return text
    return ""


async def sync_imap_emails(user_dict: dict, integration: dict) -> List[Dict[str, Any]]:
    """
    Sincroniza e-mails não lidos via IMAP (servidores próprios ou genéricos),
    gera respostas inteligentes com a IA Drexier e responde de forma real ao cliente.
    """
    imap_host = integration.get("imap_host")
    if not imap_host:
        return []
    imap_port = int(integration.get("imap_port") or 993)
    user = integration.get("smtp_user") or integration.get("email_address")
    password = integration.get("smtp_password")
    my_email = (integration.get("email_address") or "").lower().strip()

    cutoff_at = get_email_response_cutoff(integration)
    if cutoff_at is None:
        logger.warning("Sincronização IMAP bloqueada: não há data de pagamento confirmado válida.")
        return []

    processed_items = []

    def _fetch_imap_messages():
        items = []
        try:
            if imap_port == 993:
                mail = imaplib.IMAP4_SSL(imap_host, imap_port)
            else:
                mail = imaplib.IMAP4(imap_host, imap_port)
            mail.login(user, password)
            mail.select("INBOX")
            status, search_data = mail.search(None, "(UNSEEN)")
            if status != "OK" or not search_data or not search_data[0]:
                try:
                    mail.close()
                    mail.logout()
                except Exception:
                    pass
                return items

            msg_ids = search_data[0].split()
            for mid in msg_ids[-15:]:
                res, data = mail.fetch(mid, "(RFC822)")
                if res != "OK" or not data or not data[0]:
                    continue
                raw_bytes = data[0][1]
                msg = email.message_from_bytes(raw_bytes)
                raw_from = msg.get("From", "")
                subject = msg.get("Subject", "Sem assunto")
                if subject:
                    decoded = decode_header(subject)
                    subject = "".join(
                        part.decode(enc or "utf-8", errors="replace") if isinstance(part, bytes) else str(part)
                        for part, enc in decoded
                    )
                message_id = msg.get("Message-ID", "")
                date_hdr = msg.get("Date")
                sender_email, customer_name = parse_sender_info(raw_from)
                if not sender_email or sender_email == my_email:
                    continue

                # Filtro por data de recebimento: após pagamento e ligação da integração
                if date_hdr:
                    try:
                        from email.utils import parsedate_to_datetime
                        received_at = parsedate_to_datetime(date_hdr)
                        if received_at.tzinfo is None:
                            received_at = received_at.replace(tzinfo=timezone.utc)
                        received_at = received_at.astimezone(timezone.utc)
                        if received_at < cutoff_at:
                            mail.store(mid, "+FLAGS", "\\Seen")
                            logger.info(f"E-mail IMAP {message_id or mid} anterior ao início da cobertura paga ignorado.")
                            continue
                    except (TypeError, ValueError):
                        logger.warning(f"Data de recebimento inválida no e-mail IMAP {message_id or mid}; mensagem mantida sem resposta.")
                        continue
                else:
                    logger.warning(f"Data de recebimento ausente no e-mail IMAP {message_id or mid}; mensagem mantida sem resposta.")
                    continue

                body_text = clean_email_body(extract_imap_body(msg)) or "(Email sem corpo legível)"

                # Marca como lida para não reprocessar
                mail.store(mid, "+FLAGS", "\\Seen")

                # Filtro anti-spam / anúncios
                is_valid, reject_reason = is_genuine_customer_inquiry(
                    sender_email=sender_email,
                    customer_name=customer_name,
                    subject=subject,
                    body=body_text,
                )
                if not is_valid:
                    logger.info(f"[Filtro Anti-Spam] E-mail IMAP de {sender_email} ('{subject}') ignorado: {reject_reason}")
                    continue

                items.append({
                    "mid": mid,
                    "sender_email": sender_email,
                    "customer_name": customer_name,
                    "subject": subject,
                    "body_text": body_text,
                    "message_id": message_id,
                })

            mail.close()
            mail.logout()
        except Exception as e:
            logger.warning(f"Erro ao verificar mensagens IMAP: {e}")
        return items

    loop = asyncio.get_running_loop()
    raw_emails = await loop.run_in_executor(None, _fetch_imap_messages)

    for item in raw_emails:
        reply_text = await process_and_reply_email(
            user_dict=user_dict,
            integration=integration,
            customer_email=item["sender_email"],
            customer_name=item["customer_name"],
            subject=item["subject"],
            incoming_content=item["body_text"],
            thread_id=None,
            message_id_header=item["message_id"],
        )
        processed_items.append({
            "message_id": item["message_id"],
            "from": item["sender_email"],
            "subject": item["subject"],
            "reply": reply_text
        })

    return processed_items


async def sync_emails_for_user(user_id: int) -> List[Dict[str, Any]]:
    """Dispara a sincronização de e-mails para um utilizador específico."""
    with connect() as c:
        user = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        integration = c.execute(
            "SELECT * FROM email_integrations WHERE user_id = ? AND status = 'connected'",
            (user_id,)
        ).fetchone()

    if not user or not integration:
        return []

    user_dict = dict(user)
    integration_dict = dict(integration)
    payment_at = get_last_successful_payment_at(user_id)
    integration_dict["last_successful_payment_at"] = payment_at
    if get_email_response_cutoff(integration_dict) is None:
        logger.info(f"[SaaS Paywall] Sincronização de e-mail bloqueada para user {user_id}: aguarda pagamento confirmado.")
        return []
    provider = integration_dict.get("provider")

    processed = []
    if provider == "google":
        processed = await sync_google_emails(user_dict, integration_dict)
    elif provider == "microsoft":
        processed = await sync_microsoft_emails(user_dict, integration_dict)
    elif provider == "smtp_imap":
        processed = await sync_imap_emails(user_dict, integration_dict)

    with connect() as c:
        c.execute(
            "UPDATE email_integrations SET last_sync_at = CURRENT_TIMESTAMP WHERE id = ?",
            (integration_dict["id"],)
        )

    return processed


async def process_confirmation_action(
    user_id: int,
    request_id: int,
    action: str,  # 'confirm' or 'reject'
    custom_note: str = ""
) -> Dict[str, Any]:
    """
    Gera uma mensagem contextualizada via IA e envia um e-mail oficial ao cliente
    confirmando a marcação/pedido ou propondo alternativas com educação.
    """
    with connect() as c:
        req = c.execute(
            """SELECT r.id, r.request_type, r.details, r.contact_id, ct.name, ct.contact_key
               FROM conversion_requests r
               JOIN contacts ct ON ct.id = r.contact_id
               WHERE r.id = ? AND r.user_id = ?""",
            (request_id, user_id)
        ).fetchone()
        if not req:
            raise ValueError("Pedido de confirmação não encontrado.")

        user = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        integration = c.execute(
            "SELECT * FROM email_integrations WHERE user_id = ? AND status = 'connected'",
            (user_id,)
        ).fetchone()
        wa_integration = c.execute(
            "SELECT * FROM whatsapp_integrations WHERE user_id = ? AND status = 'connected'",
            (user_id,)
        ).fetchone()

        is_whatsapp = ("@" not in req["contact_key"]) or (not integration and wa_integration is not None)
        if not is_whatsapp and not integration:
            raise ValueError("Nenhuma conta de e-mail conectada para envio da confirmação.")
        if is_whatsapp and not wa_integration:
            raise ValueError("Nenhuma conta de WhatsApp conectada para envio da confirmação.")

        # Histórico recente
        history_rows = c.execute(
            "SELECT sender, content FROM messages WHERE contact_id = ? AND user_id = ? ORDER BY id DESC LIMIT 8",
            (req["contact_id"], user_id)
        ).fetchall()
        history = [{"sender": r["sender"], "content": r["content"]} for r in reversed(history_rows)]

        info = c.execute(
            "SELECT kind, title, content, metadata FROM business_info WHERE user_id = ?",
            (user_id,)
        ).fetchall()

    user_dict = dict(user)
    integration_dict = dict(integration) if integration else {}
    business_name = user_dict.get("name") or integration_dict.get("display_name") or "nosso negócio"
    customer_name = req["name"] or req["contact_key"]
    customer_email = req["contact_key"]

    channel_name = "WhatsApp" if is_whatsapp else "e-mail"
    if action == "confirm":
        instruction = (
            f"Você é o atendente oficial de {business_name}. "
            f"O proprietário analisou e acaba de CONFIRMAR a solicitação de {req['request_type']} do cliente ({customer_name}). "
            f"Detalhes do agendamento/pedido: {req['details']}. "
            f"Nota adicional do proprietário: {custom_note or 'Tudo confirmado.'}. "
            f"Escreva uma mensagem acolhedora, profissional e clara confirmando a realização do pedido/marcação para enviar via {channel_name}."
        )
        new_status = "confirmed"
        subject = f"Confirmação de Agendamento - {business_name}"
    else:
        instruction = (
            f"Você é o atendente oficial de {business_name}. "
            f"O proprietário analisou a solicitação de {req['request_type']} do cliente ({customer_name}) "
            f"e informou que INFELIZMENTE NÃO SERÁ POSSÍVEL atender naquele dia/horário/condição específica. "
            f"Detalhes do pedido original: {req['details']}. "
            f"Motivo ou alternativa sugerida pelo proprietário: {custom_note or 'Sem vaga neste dia; consultar outras datas disponíveis.'}. "
            f"Escreva uma mensagem extremamente educada, empática e atenciosa explicando a indisponibilidade e sugerindo alternativa para enviar via {channel_name}."
        )
        new_status = "rejected"
        subject = f"Atualização sobre a sua solicitação - {business_name}"

    # Redige a resposta com IA
    reply_text = await draft_reply(
        message=instruction,
        info_rows=info,
        instructions=user_dict.get("agent_instructions") or "",
        language=user_dict.get("language") or "Português",
        history=history,
        business_name=business_name,
        business_type=user_dict.get("business_type") or "Serviços",
        business_description=user_dict.get("business_description") or "",
    )

    # Salva na base de dados
    with connect() as c:
        c.execute(
            "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'agent', ?)",
            (user_id, req["contact_id"], reply_text)
        )
        c.execute("UPDATE contacts SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?", (req["contact_id"],))
        c.execute(
            "UPDATE conversion_requests SET status = ?, resolved_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
            (new_status, request_id, user_id)
        )

    # Envia resposta oficial pelo canal correto
    try:
        if is_whatsapp:
            from backend.services.whatsapp import send_whatsapp_message
            wa_dict = dict(wa_integration)
            await send_whatsapp_message(
                phone_number_id=wa_dict["phone_number_id"],
                to=req["contact_key"],
                text=reply_text,
                access_token=wa_dict.get("access_token") or None,
            )
        else:
            await send_email(
                integration=integration_dict,
                to_email=customer_email,
                subject=subject,
                body_text=reply_text,
            )
    except Exception as e:
        logger.error(f"Erro ao enviar confirmação ({channel_name}): {e}")
        raise RuntimeError(f"Mensagem gerada, mas falha no envio: {str(e)}")

    return {
        "ok": True,
        "action": action,
        "status": new_status,
        "reply_text": reply_text,
        "customer_email": customer_email
    }


async def send_owner_reply(user_id: int, contact_id: int, message_text: str) -> Dict[str, Any]:
    """
    Envia uma resposta oficial escrita manualmente pelo proprietário via WhatsApp ou e-mail.
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
            "SELECT * FROM email_integrations WHERE user_id = ? AND status = 'connected'",
            (user_id,)
        ).fetchone()

        wa_integration = c.execute(
            "SELECT * FROM whatsapp_integrations WHERE user_id = ? AND status = 'connected'",
            (user_id,)
        ).fetchone()

        thread = c.execute(
            "SELECT subject, thread_id, last_message_id FROM email_threads WHERE contact_id = ? AND user_id = ? ORDER BY updated_at DESC LIMIT 1",
            (contact_id, user_id)
        ).fetchone()

    is_whatsapp = ("@" not in contact["contact_key"]) or (not email_integration and wa_integration is not None)

    if is_whatsapp:
        if not wa_integration:
            raise ValueError("Nenhuma conta de WhatsApp conectada para envio desta mensagem.")

        from backend.services.whatsapp import send_whatsapp_message
        wa_dict = dict(wa_integration)
        await send_whatsapp_message(
            phone_number_id=wa_dict["phone_number_id"],
            to=contact["contact_key"],
            text=message_text,
            access_token=wa_dict.get("access_token") or None,
        )

        with connect() as c:
            cur = c.execute(
                "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'owner', ?)",
                (user_id, contact_id, message_text)
            )
            msg_id = cur.lastrowid
            c.execute("UPDATE contacts SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?", (contact_id,))

        return {"ok": True, "channel": "whatsapp", "message_id": msg_id, "content": message_text}

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
