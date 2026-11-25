import json
import logging
import time
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

import secrets
from datetime import datetime, timezone, timedelta
from jose import jwt
from backend.auth import decode_token, create_token, get_token_claims, SECRET_KEY, ALGORITHM
from backend.services.token_crypto import encrypt_token, decrypt_token
from backend.database import connect
from backend.services.billing_service import get_last_successful_payment_at, is_subscription_active
from backend.services.email_service import (
    EmailTokenExpiredError,
    get_email_response_cutoff,
    build_google_auth_url,
    exchange_google_code,
    fetch_google_user_profile,
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
    raw_token = authorization[7:]
    uid = decode_token(raw_token)
    if not uid:
        raise HTTPException(401, "Sessão inválida ou expirada.")
    with connect() as c:
        row = c.execute(
            "SELECT id, name, email, business_type, business_description, language, agent_instructions, agent_adopted_style, mandatory_responses, token_version FROM users WHERE id=?",
            (uid,),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Conta não encontrada.")
    user_data = dict(row)
    # Validação de revogação imediata de sessão via token_version
    claims = get_token_claims(raw_token)
    if claims and "v" in claims and "token_version" in user_data and user_data["token_version"] is not None:
        if int(claims["v"]) != int(user_data["token_version"]):
            raise HTTPException(401, "Sessão revogada. Por favor, inicie sessão novamente.")
    return user_data


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


class ToggleAutoReplyPayload(BaseModel):
    enabled: bool


class TestEmailSendPayload(BaseModel):
    to: EmailStr
    subject: str = Field(default="Teste de Integração Drexier AI", min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=4000)


@router.get("/config")
def get_email_public_config():
    """Retorna o estado de configuração do OAuth Google."""
    config = get_email_config()
    return {
        "google": {
            "configured": config["google"]["configured"],
            "redirect_uri": config["google"]["redirect_uri"],
        },
    }


@router.get("/status")
def get_email_status(user: dict = Depends(get_current_user)):
    """Retorna o estado da ligação do e-mail oficial da conta autenticada."""
    with connect() as c:
        row = c.execute(
            """SELECT id, user_id, provider, email_address, display_name,
                      status, auto_reply_enabled, token_expires_at, refresh_token, last_sync_at, created_at, updated_at
               FROM email_integrations
               WHERE user_id = ? AND provider = 'google'""",
            (user["id"],),
        ).fetchone()

    if not row:
        return {
            "connected": False,
            "needs_reconnect": False,
            "integration": None,
        }

    is_needs_reconnect = row["status"] == "needs_reconnect"

    # Verificação preventiva: se o token já expirou e não há refresh_token, marca como needs_reconnect e pausa o agente
    if not is_needs_reconnect and row["status"] == "connected":
        expires_at = row["token_expires_at"]
        try:
            exp_ts = float(expires_at) if expires_at else None
            ref = decrypt_token(row["refresh_token"]) if row["refresh_token"] else ""
            if exp_ts and exp_ts <= time.time() and not ref:
                is_needs_reconnect = True
                with connect() as c:
                    c.execute(
                        "UPDATE email_integrations SET status = 'needs_reconnect', auto_reply_enabled = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (row["id"],),
                    )
        except Exception:
            pass

    if row["status"] != "connected" and not is_needs_reconnect:
        return {
            "connected": False,
            "needs_reconnect": False,
            "integration": None,
        }

    integration_data = dict(row)
    integration_data["last_successful_payment_at"] = get_last_successful_payment_at(user["id"])
    response_cutoff = get_email_response_cutoff(integration_data)

    MSG_PT = "O agente foi pausado. Desconecte e reconecte o e-mail para voltar o funcionamento do agente."
    MSG_EN = "The agent was paused. Disconnect and reconnect your email to resume the agent."

    return {
        "connected": row["status"] == "connected" and not is_needs_reconnect,
        "needs_reconnect": is_needs_reconnect,
        "reconnect_message": MSG_PT,
        "reconnect_message_pt": MSG_PT,
        "reconnect_message_en": MSG_EN,
        "integration": {
            "id": row["id"],
            "provider": row["provider"],
            "email_address": row["email_address"],
            "display_name": row["display_name"],
            "status": "needs_reconnect" if is_needs_reconnect else row["status"],
            "needs_reconnect": is_needs_reconnect,
            "auto_reply_enabled": False if is_needs_reconnect else bool(row["auto_reply_enabled"]),
            "last_sync_at": row["last_sync_at"],
            "response_since_at": response_cutoff.isoformat() if response_cutoff else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        },
    }


@router.get("/oauth/google/url")
def get_google_oauth_url(user: dict = Depends(require_email_subscription)):
    """
    Retorna o link oficial de autorização da Google para que o utilizador
    possa aceder e conceder as permissões solicitadas.
    SEC-16: Gera um token de estado temporário (15min) com nonce único contra CSRF.
    """
    state_token = jwt.encode(
        {
            "sub": str(user["id"]),
            "nonce": secrets.token_hex(16),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
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
        import urllib.parse as _urlparse
        safe_err = _urlparse.quote(str(error), safe="")
        return RedirectResponse(f"/?email_auth=error&reason={safe_err}")

    if not code or not state:
        return RedirectResponse("/?email_auth=error&reason=missing_code_or_state")

    # SEC-16: Previne replay de state em ataques de Login CSRF (C3: DB-persisted)
    import hashlib as _hashlib
    state_hash = _hashlib.sha256(state.encode()).hexdigest()
    with connect() as c:
        c.execute("CREATE TABLE IF NOT EXISTS used_oauth_states (state_hash TEXT PRIMARY KEY, used_at TEXT NOT NULL, expires_at TEXT NOT NULL)")
        # Clean up expired states older than 15 minutes
        c.execute("DELETE FROM used_oauth_states WHERE expires_at < ?", (datetime.now(timezone.utc).isoformat(),))
        already_used = c.execute("SELECT 1 FROM used_oauth_states WHERE state_hash=?", (state_hash,)).fetchone()
        if already_used:
            return RedirectResponse("/?email_auth=error&reason=state_already_used")
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=16)).isoformat()
        c.execute("INSERT OR IGNORE INTO used_oauth_states(state_hash, used_at, expires_at) VALUES(?,?,?)",
                  (state_hash, datetime.now(timezone.utc).isoformat(), expires_at))

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

        # SEC-08: Armazenamento encriptado de tokens sensíveis (Fernet AES-128-CBC + HMAC)
        enc_access_token = encrypt_token(access_token)
        enc_refresh_token = encrypt_token(refresh_token) if refresh_token else ""

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
                (uid, email_addr, display_name, enc_access_token, enc_refresh_token, expires_at),
            )

        # SEC-03: O token JWT da sessão não é vazado na URL
        return RedirectResponse("/?email_auth=success&provider=google")
    except Exception as e:
        import urllib.parse as _urlparse
        logger.error("Erro no callback do Google OAuth: %s", str(e).replace('\n', '\\n'))
        safe_reason = _urlparse.quote("Falha na autenticação com a Google. Tente novamente.", safe="")
        return RedirectResponse(f"/?email_auth=error&reason={safe_reason}")


@router.post("/auto-reply")
def toggle_auto_reply(
    payload: ToggleAutoReplyPayload,
    user: dict = Depends(require_email_subscription),
):
    """Ativa ou desativa as respostas automáticas da IA para a integração de e-mail."""
    with connect() as c:
        row = c.execute(
            "SELECT id, status FROM email_integrations WHERE user_id = ? AND provider = 'google'",
            (user["id"],)
        ).fetchone()
        if not row or row["status"] != "connected":
            if row and row["status"] == "needs_reconnect":
                raise HTTPException(
                    400,
                    detail={
                        "code": "token_expired",
                        "message": "O agente foi pausado. Desconecte e reconecte o e-mail para voltar o funcionamento do agente.",
                        "message_en": "The agent was paused. Disconnect and reconnect your email to resume the agent.",
                        "needs_reconnect": True,
                    }
                )
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
            "UPDATE email_integrations SET status = 'disconnected', updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND provider = 'google'",
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
    except EmailTokenExpiredError:
        raise HTTPException(
            400,
            detail={
                "code": "token_expired",
                "message": "O agente foi pausado. Desconecte e reconecte o e-mail para voltar o funcionamento do agente.",
                "message_en": "The agent was paused. Disconnect and reconnect your email to resume the agent.",
                "needs_reconnect": True,
            }
        )
    except Exception as e:
        logger.error(f"Erro ao sincronizar e-mails: {e}")
        raise HTTPException(
            502,
            "Falha temporária ao sincronizar a caixa de e-mail. "
            "A sincronização não foi marcada como concluída; verifique a autorização e tente novamente.",
        ) from e


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

    integ_data = dict(integration)
    integ_data["access_token"] = decrypt_token(integ_data.get("access_token"))
    integ_data["refresh_token"] = decrypt_token(integ_data.get("refresh_token"))
    try:
        res = await send_email(
            integration=integ_data,
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
