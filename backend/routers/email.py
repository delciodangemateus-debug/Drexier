import json
import logging
import time
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

from backend.auth import decode_token, create_token
from backend.database import connect
from backend.services.billing_service import is_subscription_active
from backend.services.email_service import (
    build_google_auth_url,
    build_microsoft_auth_url,
    exchange_google_code,
    exchange_microsoft_code,
    fetch_google_user_profile,
    fetch_microsoft_user_profile,
    get_email_config,
    send_email,
    sync_emails_for_user,
)

logger = logging.getLogger("drexier.email_router")

router = APIRouter(prefix="/api/email", tags=["Email"])


def get_current_user(authorization: Optional[str] = Header(default=None)):
    """Dependência para autenticar utilizador autenticado."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sessão necessária.")
    uid = decode_token(authorization[7:])
    if not uid:
        raise HTTPException(401, "Sessão inválida ou expirada.")
    with connect() as c:
        row = c.execute(
            "SELECT id, name, email, business_type, business_description, language, agent_instructions, mandatory_responses FROM users WHERE id=?",
            (uid,),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Conta não encontrada.")
    return dict(row)


def require_email_subscription(user: dict = Depends(get_current_user)):
    """
    Bloqueia integrações e automações de e-mail se o utilizador não possuir
    o Plano Business (59€/mês) ativo e com pagamento em dia.
    """
    if not is_subscription_active(user["id"]):
        raise HTTPException(
            status_code=402,
            detail={
                "code": "SUBSCRIPTION_REQUIRED",
                "message": (
                    "Acesso bloqueado. O Plano Business (59€/mês) é necessário para configurar "
                    "a integração de e-mail e respostas automáticas. Ative a subscrição na aba Faturação."
                )
            }
        )
    return user


class ManualEmailConnectPayload(BaseModel):
    provider: str = Field(default="smtp_imap", pattern="^(google|microsoft|smtp_imap)$")
    email_address: EmailStr
    display_name: Optional[str] = ""
    smtp_host: str = Field(min_length=3)
    smtp_port: int = Field(default=587)
    smtp_user: Optional[str] = ""
    smtp_password: str = Field(min_length=1)
    imap_host: Optional[str] = ""
    imap_port: Optional[int] = 993


class ToggleAutoReplyPayload(BaseModel):
    enabled: bool


class TestEmailSendPayload(BaseModel):
    to: EmailStr
    subject: str = Field(default="Teste de Integração Drexier AI", min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=4000)


@router.get("/config")
def get_email_public_config():
    """Retorna o estado de configuração dos provedores oficiais Google e Microsoft."""
    config = get_email_config()
    return {
        "google": {
            "configured": config["google"]["configured"],
            "redirect_uri": config["google"]["redirect_uri"],
        },
        "microsoft": {
            "configured": config["microsoft"]["configured"],
            "redirect_uri": config["microsoft"]["redirect_uri"],
        },
    }


@router.get("/status")
def get_email_status(user: dict = Depends(get_current_user)):
    """Retorna o estado da ligação do e-mail oficial da conta autenticada."""
    with connect() as c:
        row = c.execute(
            """SELECT id, user_id, provider, email_address, display_name,
                      status, auto_reply_enabled, last_sync_at, created_at, updated_at
               FROM email_integrations
               WHERE user_id = ?""",
            (user["id"],),
        ).fetchone()

    if not row or row["status"] != "connected":
        return {
            "connected": False,
            "integration": None,
        }

    return {
        "connected": True,
        "integration": {
            "id": row["id"],
            "provider": row["provider"],
            "email_address": row["email_address"],
            "display_name": row["display_name"],
            "status": row["status"],
            "auto_reply_enabled": bool(row["auto_reply_enabled"]),
            "last_sync_at": row["last_sync_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        },
    }


@router.get("/oauth/google/url")
def get_google_oauth_url(user: dict = Depends(require_email_subscription)):
    """
    Retorna o link oficial de autorização da Google para que o utilizador
    possa aceder e conceder as permissões solicitadas.
    """
    state_payload = json.dumps({"uid": user["id"], "ts": int(time.time())})
    state_token = create_token(user["id"])
    try:
        url = build_google_auth_url(state=state_token)
        return {"url": url}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/oauth/google/callback")
async def google_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """
    Callback oficial do Google OAuth 2.0.
    Troca o código por tokens, obtém o e-mail do cliente e grava a integração.
    """
    if error:
        return RedirectResponse(f"/?email_auth=error&reason={error}")

    if not code or not state:
        return RedirectResponse("/?email_auth=error&reason=missing_code_or_state")

    uid = decode_token(state)
    if not uid:
        return RedirectResponse("/?email_auth=error&reason=invalid_state")

    if not is_subscription_active(uid):
        return RedirectResponse("/?billing=paywall&reason=subscription_required")

    try:
        token_data = await exchange_google_code(code)
        access_token = token_data.get("access_token", "")
        refresh_token = token_data.get("refresh_token", "")
        expires_in = token_data.get("expires_in", 3600)
        expires_at = str(time.time() + expires_in)

        email_addr, display_name = await fetch_google_user_profile(access_token)
        if not email_addr:
            email_addr = f"google_user_{uid}@gmail.com"

        with connect() as c:
            c.execute(
                """INSERT INTO email_integrations (
                       user_id, provider, email_address, display_name,
                       access_token, refresh_token, token_expires_at, status, updated_at
                   )
                   VALUES (?, 'google', ?, ?, ?, ?, ?, 'connected', CURRENT_TIMESTAMP)
                   ON CONFLICT(user_id) DO UPDATE SET
                       provider = 'google',
                       email_address = excluded.email_address,
                       display_name = excluded.display_name,
                       access_token = excluded.access_token,
                       refresh_token = CASE WHEN excluded.refresh_token != '' THEN excluded.refresh_token ELSE email_integrations.refresh_token END,
                       token_expires_at = excluded.token_expires_at,
                       status = 'connected',
                       updated_at = CURRENT_TIMESTAMP""",
                (uid, email_addr, display_name, access_token, refresh_token, expires_at),
            )

        session_token = create_token(uid)
        return RedirectResponse(f"/?email_auth=success&provider=google&token={session_token}")
    except Exception as e:
        logger.error(f"Erro no callback do Google OAuth: {e}")
        return RedirectResponse(f"/?email_auth=error&reason={str(e)}")


@router.get("/oauth/microsoft/url")
def get_microsoft_oauth_url(user: dict = Depends(require_email_subscription)):
    """
    Retorna o link oficial de autorização da Microsoft para que o utilizador
    possa aceder e conceder as permissões solicitadas.
    """
    state_token = create_token(user["id"])
    try:
        url = build_microsoft_auth_url(state=state_token)
        return {"url": url}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/oauth/microsoft/callback")
async def microsoft_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
):
    """
    Callback oficial do Microsoft OAuth 2.0.
    Troca o código por tokens, obtém o e-mail do cliente e grava a integração.
    """
    if error:
        return RedirectResponse(f"/?email_auth=error&reason={error_description or error}")

    if not code or not state:
        return RedirectResponse("/?email_auth=error&reason=missing_code_or_state")

    uid = decode_token(state)
    if not uid:
        return RedirectResponse("/?email_auth=error&reason=invalid_state")

    if not is_subscription_active(uid):
        return RedirectResponse("/?billing=paywall&reason=subscription_required")

    try:
        token_data = await exchange_microsoft_code(code)
        access_token = token_data.get("access_token", "")
        refresh_token = token_data.get("refresh_token", "")
        expires_in = token_data.get("expires_in", 3600)
        expires_at = str(time.time() + expires_in)

        email_addr, display_name = await fetch_microsoft_user_profile(access_token)
        if not email_addr:
            email_addr = f"outlook_user_{uid}@outlook.com"

        with connect() as c:
            c.execute(
                """INSERT INTO email_integrations (
                       user_id, provider, email_address, display_name,
                       access_token, refresh_token, token_expires_at, status, updated_at
                   )
                   VALUES (?, 'microsoft', ?, ?, ?, ?, ?, 'connected', CURRENT_TIMESTAMP)
                   ON CONFLICT(user_id) DO UPDATE SET
                       provider = 'microsoft',
                       email_address = excluded.email_address,
                       display_name = excluded.display_name,
                       access_token = excluded.access_token,
                       refresh_token = CASE WHEN excluded.refresh_token != '' THEN excluded.refresh_token ELSE email_integrations.refresh_token END,
                       token_expires_at = excluded.token_expires_at,
                       status = 'connected',
                       updated_at = CURRENT_TIMESTAMP""",
                (uid, email_addr, display_name, access_token, refresh_token, expires_at),
            )

        return RedirectResponse("/?email_auth=success&provider=microsoft")
    except Exception as e:
        logger.error(f"Erro no callback do Microsoft OAuth: {e}")
        return RedirectResponse(f"/?email_auth=error&reason={str(e)}")


@router.post("/connect-manual")
def connect_manual_email(
    payload: ManualEmailConnectPayload,
    user: dict = Depends(require_email_subscription),
):
    """Permite ligação direta por credenciais SMTP/IMAP para testes ou servidores próprios."""
    with connect() as c:
        c.execute(
            """INSERT INTO email_integrations (
                   user_id, provider, email_address, display_name,
                   smtp_host, smtp_port, smtp_user, smtp_password,
                   imap_host, imap_port, status, updated_at
               )
               VALUES (?, 'smtp_imap', ?, ?, ?, ?, ?, ?, ?, ?, 'connected', CURRENT_TIMESTAMP)
               ON CONFLICT(user_id) DO UPDATE SET
                   provider = 'smtp_imap',
                   email_address = excluded.email_address,
                   display_name = excluded.display_name,
                   smtp_host = excluded.smtp_host,
                   smtp_port = excluded.smtp_port,
                   smtp_user = excluded.smtp_user,
                   smtp_password = excluded.smtp_password,
                   imap_host = excluded.imap_host,
                   imap_port = excluded.imap_port,
                   status = 'connected',
                   updated_at = CURRENT_TIMESTAMP""",
            (
                user["id"],
                payload.email_address.lower().strip(),
                payload.display_name or user["name"],
                payload.smtp_host.strip(),
                payload.smtp_port,
                payload.smtp_user or payload.email_address.lower().strip(),
                payload.smtp_password,
                payload.imap_host or "",
                payload.imap_port or 993,
            ),
        )

    return {"ok": True, "message": "Email configurado com sucesso via SMTP!"}


@router.post("/auto-reply")
def toggle_auto_reply(
    payload: ToggleAutoReplyPayload,
    user: dict = Depends(require_email_subscription),
):
    """Ativa ou desativa as respostas automáticas da IA para a integração de e-mail."""
    with connect() as c:
        row = c.execute(
            "SELECT id FROM email_integrations WHERE user_id = ? AND status = 'connected'",
            (user["id"],)
        ).fetchone()
        if not row:
            raise HTTPException(400, "Nenhuma integração de e-mail conectada nesta conta.")

        c.execute(
            "UPDATE email_integrations SET auto_reply_enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (1 if payload.enabled else 0, row["id"]),
        )

    status_str = "ativadas" if payload.enabled else "desativadas"
    return {
        "ok": True,
        "auto_reply_enabled": payload.enabled,
        "message": f"Respostas automáticas do agente {status_str} com sucesso.",
    }


@router.post("/disconnect")
def disconnect_email(user: dict = Depends(get_current_user)):
    """Desconecta a integração de e-mail do utilizador autenticado."""
    with connect() as c:
        c.execute(
            "UPDATE email_integrations SET status = 'disconnected', updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (user["id"],),
        )
    return {"ok": True, "message": "Email desconectado com sucesso."}


@router.post("/sync")
async def trigger_email_sync(user: dict = Depends(require_email_subscription)):
    """
    Sincroniza os e-mails recebidos na caixa de entrada do utilizador,
    aciona a IA Drexier para cada mensagem nova e envia as respostas.
    """
    try:
        processed = await sync_emails_for_user(user["id"])
        return {
            "ok": True,
            "processed_count": len(processed),
            "processed": processed,
            "message": f"Sincronização concluída: {len(processed)} e-mail(s) verificado(s) e respondido(s)."
        }
    except Exception as e:
        logger.error(f"Erro ao sincronizar e-mails: {e}")
        raise HTTPException(400, f"Falha na sincronização de e-mails: {str(e)}")


@router.post("/test-send")
async def test_send_email(
    payload: TestEmailSendPayload,
    user: dict = Depends(require_email_subscription),
):
    """Envia um e-mail de teste para verificar se o envio está 100% funcional."""
    with connect() as c:
        integration = c.execute(
            "SELECT * FROM email_integrations WHERE user_id = ? AND status = 'connected'",
            (user["id"],),
        ).fetchone()

    if not integration:
        raise HTTPException(400, "Nenhuma integração de e-mail conectada nesta conta.")

    try:
        res = await send_email(
            integration=dict(integration),
            to_email=payload.to,
            subject=payload.subject,
            body_text=payload.message,
        )
        return {
            "ok": True,
            "message": f"E-mail de teste enviado com sucesso para {payload.to}!",
            "details": res,
        }
    except Exception as e:
        logger.error(f"Erro no envio de teste de e-mail: {e}")
        raise HTTPException(400, f"Falha ao enviar e-mail de teste: {str(e)}")
