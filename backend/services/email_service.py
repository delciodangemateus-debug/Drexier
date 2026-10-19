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
import smtplib
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
from dotenv import load_dotenv
import httpx

from backend.database import connect
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


async def sync_google_emails(user_dict: dict, integration: dict) -> List[Dict[str, Any]]:
    """
    Sincroniza e-mails não lidos da caixa de entrada do Gmail,
    gera respostas inteligentes com a IA e envia automaticamente ao cliente.
    """
    token = await refresh_google_token_if_needed(integration)
    headers = {"Authorization": f"Bearer {token}"}
    my_email = (integration.get("email_address") or "").lower().strip()

    processed_items = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Busca mensagens não lidas na caixa de entrada
        query = "label:INBOX is:unread"
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

            # Extrai corpo de texto de forma segura e completa
            extracted_body = extract_gmail_body(payload)
            body_text = clean_email_body(extracted_body) or "(Email sem corpo de texto legível)"

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

            if not sender_email or sender_email == my_email:
                continue

            if content_type.lower() == "html":
                text_clean = re.sub(r"<[^>]+>", " ", body_content)
                text_clean = html.unescape(text_clean)
            else:
                text_clean = body_content

            body_text = clean_email_body(text_clean) or "(Email sem corpo de texto legível)"

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
    provider = integration_dict.get("provider")

    processed = []
    if provider == "google":
        processed = await sync_google_emails(user_dict, integration_dict)
    elif provider == "microsoft":
        processed = await sync_microsoft_emails(user_dict, integration_dict)

    with connect() as c:
        c.execute(
            "UPDATE email_integrations SET last_sync_at = CURRENT_TIMESTAMP WHERE id = ?",
            (integration_dict["id"],)
        )

    return processed
