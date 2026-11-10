import json
import logging
import html
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from backend.auth import decode_token
from backend.database import connect
from backend.services.agent import draft_reply, effective_agent_instructions
from backend.services.email_service import (
    capture_scheduled_request,
    detect_booking_or_purchase_intent,
    ensure_date_time_question,
)
from backend.services.billing_service import is_subscription_active
from backend.services.whatsapp import (
    debug_token,
    exchange_code_for_token,
    extract_incoming_messages,
    fetch_phone_number_details,
    fetch_waba_phone_numbers,
    get_meta_config,
    mark_message_as_read,
    register_phone_number,
    send_whatsapp_message,
    subscribe_waba_webhook,
    verify_webhook_signature,
)

logger = logging.getLogger("drexier.whatsapp_router")

router = APIRouter(prefix="/api", tags=["WhatsApp"])


def get_current_user(authorization: Optional[str] = Header(default=None)):
    """Dependência para autenticar utilizador."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sessão necessária.")
    uid = decode_token(authorization[7:])
    if not uid:
        raise HTTPException(401, "Sessão inválida ou expirada.")
    with connect() as c:
        row = c.execute(
            "SELECT id, name, email, business_type, business_description, language, agent_instructions, agent_adopted_style, mandatory_responses FROM users WHERE id=?",
            (uid,),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Conta não encontrada.")
    return dict(row)


def require_whatsapp_subscription(user: dict) -> None:
    if not is_subscription_active(user["id"]):
        raise HTTPException(
            402,
            detail={
                "code": "SUBSCRIPTION_REQUIRED",
                "message": "Ative uma subscrição para utilizar a integração WhatsApp.",
            },
        )


class WhatsAppConnectPayload(BaseModel):
    code: Optional[str] = None
    redirect_uri: Optional[str] = None
    waba_id: Optional[str] = None
    phone_number_id: Optional[str] = None
    phone_number: Optional[str] = None
    business_name: Optional[str] = None
    access_token: Optional[str] = None
    use_env: Optional[bool] = False


class TestSendPayload(BaseModel):
    to: str = Field(min_length=5, max_length=30)
    message: str = Field(min_length=1, max_length=4000)


class WhatsAppRegistrationPayload(BaseModel):
    pin: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


@router.get("/whatsapp/config")
def get_whatsapp_public_config():
    """Retorna a configuração pública para o Embedded Signup no frontend."""
    config = get_meta_config()
    return {
        "app_id": config["app_id"],
        "config_id": config["config_id"],
        "version": config["version"],
        "configured": bool(config["app_id"] and config["app_secret"] and config["config_id"]),
        "has_env_credentials": bool(config.get("has_env_credentials")),
        "webhook_url": f"{config['public_url']}/api/webhooks/whatsapp" if config.get("public_url") else "",
    }


@router.get("/whatsapp/status")
def get_whatsapp_status(user: dict = Depends(get_current_user)):
    """Retorna o estado da ligação do WhatsApp da conta autenticada."""
    config = get_meta_config()
    with connect() as c:
        row = c.execute(
            """SELECT id, user_id, waba_id, phone_number_id, phone_number,
                      business_name, status, webhook_subscribed, phone_registered,
                      created_at, updated_at
               FROM whatsapp_integrations
               WHERE user_id = ?""",
            (user["id"],),
        ).fetchone()

    if not row or row["status"] != "connected":
        return {
            "connected": False,
            "integration": None,
            "can_connect_env": bool(config.get("has_env_credentials")),
        }

    return {
        "connected": True,
        "integration": {
            "id": row["id"],
            "waba_id": row["waba_id"],
            "phone_number_id": row["phone_number_id"],
            "phone_number": row["phone_number"],
            "business_name": row["business_name"],
            "status": row["status"],
            "webhook_subscribed": bool(row["webhook_subscribed"]),
            "phone_registered": bool(row["phone_registered"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "auto_reply_enabled": _user_auto_reply_enabled(user),
        },
        "can_connect_env": bool(config.get("has_env_credentials")),
    }


@router.get("/whatsapp/oauth/callback")
def whatsapp_oauth_callback(
    code: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
):
    """Callback do fluxo direto de autorização da Meta.
    Suporta dois modos:
    - Popup (window.opener existe): envia o código via postMessage e fecha a janela.
    - Aba direta (sem opener): guarda o código em localStorage e redireciona para a app.
    """
    if error:
        err_msg = error_description or error
        safe_error_json = json.dumps(err_msg).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        html = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;text-align:center;padding:40px;">
            <h3 style="color:#dc2626;">Erro na autorização da Meta</h3>
            <p>{html_escape(err_msg)}</p>
            <script>
                if (window.opener) {{
                    window.opener.postMessage({{ type: 'WA_OAUTH_ERROR', error: {safe_error_json} }}, window.location.origin);
                    window.close();
                }} else {{
                    localStorage.setItem('drexier_wa_oauth_error', {safe_error_json});
                    window.location.href = '/';
                }}
            </script></body></html>"""
        return HTMLResponse(content=html, status_code=200)

    safe_code_json = json.dumps(code or "").replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;text-align:center;padding:40px;">
        <h3 style="color:#059669;">✅ Ligação com a Meta autorizada!</h3>
        <p>A concluir a ligação com o Drexier...</p>
        <p style="color:#64748b;font-size:13px;">Esta janela fechará automaticamente ou será redirecionado.</p>
        <script>
            var code = {safe_code_json};
            if (window.opener) {{
                // Modo popup: envia código para a janela principal e fecha
                window.opener.postMessage({{ type: 'WA_OAUTH_CODE', code: code }}, '*');
                window.close();
            }} else {{
                // Modo aba direta: guarda código em localStorage e redireciona para a app
                if (code) {{
                    localStorage.setItem('drexier_wa_pending_code', code);
                    localStorage.setItem('drexier_wa_redirect_uri', window.location.origin + '/api/whatsapp/oauth/callback');
                }}
                window.location.href = '/';
            }}
        </script></body></html>"""
    return HTMLResponse(content=html, status_code=200)


@router.post("/whatsapp/connect")
async def connect_whatsapp(
    payload: WhatsAppConnectPayload,
    user: dict = Depends(get_current_user),
):
    """
    Conclui o Embedded Signup da Meta ou a ligação com credenciais.
    Troca o código pelo token, subscreve os webhooks e armazena os identificadores no banco.
    """
    require_whatsapp_subscription(user)
    config = get_meta_config()
    token = (payload.access_token or "").strip()
    waba_id = (payload.waba_id or "").strip()
    phone_number_id = (payload.phone_number_id or "").strip()
    phone_number = (payload.phone_number or "").strip()
    business_name = (payload.business_name or "").strip()

    # A credencial do Embedded Signup é específica do cliente; nunca a misture com IDs/token globais.
    if payload.code:
        try:
            token_data = await exchange_code_for_token(payload.code, payload.redirect_uri)
            token = (token_data.get("access_token") or "").strip()
            if not token:
                raise ValueError("A Meta concluiu a troca do código sem devolver access_token.")
        except Exception as e:
            logger.error(f"Erro ao trocar código por token: {e}")
            raise HTTPException(400, f"Falha na autenticação com a Meta: {str(e)}")
    else:
        # Credenciais globais só podem ser usadas no fluxo explícito de configuração do servidor.
        if payload.use_env or (not token and not phone_number_id):
            token = token or config["system_user_token"]
            phone_number_id = phone_number_id or config["phone_number_id"]
            waba_id = waba_id or config["waba_id"]

    # Se ainda faltam dados do WABA ou phone_number_id, tentamos descobrir via token
    if token and (not waba_id or not phone_number_id):
        token_debug = await debug_token(token)
        granular_scopes = token_debug.get("granular_scopes", [])
        for scope in granular_scopes:
            if scope.get("scope") == "whatsapp_business_management":
                target_ids = scope.get("target_ids", [])
                if target_ids and not waba_id:
                    waba_id = str(target_ids[0])

    if waba_id and not phone_number_id and token:
        # Busca os números associados a essa WABA
        numbers = await fetch_waba_phone_numbers(waba_id, token)
        if len(numbers) == 1:
            first_num = numbers[0]
            phone_number_id = first_num.get("id", "")
            if not phone_number:
                phone_number = first_num.get("display_phone_number", "")
            if not business_name:
                business_name = first_num.get("verified_name", "")
        elif len(numbers) > 1:
            raise HTTPException(
                400,
                "A conta WhatsApp tem vários números e a Meta não informou qual foi selecionado. "
                "Tente novamente ou selecione explicitamente o número no Embedded Signup.",
            )

    # Se temos phone_number_id mas faltam número legível ou nome, consulta os detalhes
    if phone_number_id and (not phone_number or not business_name) and token:
        phone_details = await fetch_phone_number_details(phone_number_id, token)
        if phone_details:
            phone_number = phone_number or phone_details.get("display_phone_number", "")
            business_name = business_name or phone_details.get("verified_name", "")

    if not phone_number_id:
        raise HTTPException(
            400,
            "Não foi possível identificar o Phone Number ID da conta WhatsApp. "
            "Certifique-se de que selecionou um número de WhatsApp durante o fluxo da Meta.",
        )

    if not waba_id:
        raise HTTPException(
            400,
            "Não foi possível identificar o ID da conta WhatsApp Business (WABA). "
            "Conclua o Embedded Signup da Meta ou configure META_WABA_ID.",
        )

    if not token:
        raise HTTPException(400, "A Meta não forneceu um token de acesso para esta conta WhatsApp.")

    with connect() as c:
        existing = c.execute(
            "SELECT user_id FROM whatsapp_integrations WHERE phone_number_id = ? AND user_id != ?",
            (phone_number_id, user["id"]),
        ).fetchone()
        current_integration = c.execute(
            "SELECT phone_number_id, phone_registered FROM whatsapp_integrations WHERE user_id = ?",
            (user["id"],),
        ).fetchone()
    if existing:
        raise HTTPException(
            409,
            "Este número de WhatsApp já se encontra ligado a outra conta no sistema.",
        )
    phone_registered = bool(
        current_integration
        and current_integration["phone_number_id"] == phone_number_id
        and current_integration["phone_registered"]
    )

    # Subscrever a WABA aos webhooks da nossa aplicação
    subscribed = False
    if waba_id and token:
        subscribed = await subscribe_waba_webhook(waba_id, token)
    if not subscribed:
        raise HTTPException(
            502,
            "A Meta não confirmou a subscrição do webhook desta conta. "
            "Verifique as permissões whatsapp_business_management e a configuração do app.",
        )

    # Gravar na base de dados (upsert por user_id)
    with connect() as c:
        # Revalida o número para cobrir conexões concorrentes.
        existing = c.execute(
            "SELECT user_id FROM whatsapp_integrations WHERE phone_number_id = ? AND user_id != ?",
            (phone_number_id, user["id"]),
        ).fetchone()
        if existing:
            raise HTTPException(
                409,
                "Este número de WhatsApp já se encontra ligado a outra conta no sistema.",
            )

        # Insere ou atualiza
        c.execute(
            """INSERT INTO whatsapp_integrations (
                   user_id, waba_id, phone_number_id, phone_number,
                   business_name, access_token, status, webhook_subscribed,
                   phone_registered, updated_at
               )
               VALUES (?, ?, ?, ?, ?, ?, 'connected', ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id) DO UPDATE SET
                   waba_id = excluded.waba_id,
                   phone_number_id = excluded.phone_number_id,
                   phone_number = excluded.phone_number,
                   business_name = excluded.business_name,
                   access_token = CASE WHEN excluded.access_token != '' THEN excluded.access_token ELSE whatsapp_integrations.access_token END,
                   status = 'connected',
                   webhook_subscribed = excluded.webhook_subscribed,
                   phone_registered = excluded.phone_registered,
                   updated_at = CURRENT_TIMESTAMP""",
            (
                user["id"],
                waba_id,
                phone_number_id,
                phone_number or phone_number_id,
                business_name or user["name"],
                token,
                1 if subscribed else 0,
                1 if phone_registered else 0,
            ),
        )

    return {
        "ok": True,
        "message": "WhatsApp ligado com sucesso!",
        "integration": {
            "waba_id": waba_id,
            "phone_number_id": phone_number_id,
            "phone_number": phone_number,
            "business_name": business_name,
            "webhook_subscribed": subscribed,
            "phone_registered": phone_registered,
        },
    }


@router.post("/whatsapp/register")
async def register_whatsapp_phone(
    payload: WhatsAppRegistrationPayload,
    user: dict = Depends(get_current_user),
):
    """Regista o número ligado e nunca armazena o PIN de verificação."""
    require_whatsapp_subscription(user)
    with connect() as c:
        integration = c.execute(
            """SELECT phone_number_id, access_token, phone_registered
               FROM whatsapp_integrations
               WHERE user_id = ? AND status = 'connected'""",
            (user["id"],),
        ).fetchone()

    if not integration:
        raise HTTPException(400, "Ligue primeiro uma conta WhatsApp.")
    if integration["phone_registered"]:
        return {"ok": True, "phone_registered": True}

    try:
        await register_phone_number(
            integration["phone_number_id"],
            payload.pin,
            integration["access_token"],
        )
    except Exception as e:
        logger.warning(
            "A Meta não confirmou o registo do número WhatsApp %s: %s",
            integration["phone_number_id"],
            e,
        )
        raise HTTPException(502, f"Falha ao registar o número na Meta: {e}") from e

    with connect() as c:
        c.execute(
            """UPDATE whatsapp_integrations
               SET phone_registered = 1, updated_at = CURRENT_TIMESTAMP
               WHERE user_id = ? AND status = 'connected'""",
            (user["id"],),
        )

    return {"ok": True, "phone_registered": True}


@router.post("/whatsapp/disconnect")
def disconnect_whatsapp(user: dict = Depends(get_current_user)):
    """Desconecta a integração do WhatsApp do utilizador autenticado."""
    require_whatsapp_subscription(user)
    with connect() as c:
        c.execute(
            """UPDATE whatsapp_integrations
               SET status = 'disconnected', access_token = '', updated_at = CURRENT_TIMESTAMP
               WHERE user_id = ?""",
            (user["id"],),
        )
    return {"ok": True, "message": "WhatsApp desconectado com sucesso."}


@router.post("/whatsapp/test-send")
async def test_send_message(
    payload: TestSendPayload,
    user: dict = Depends(get_current_user),
):
    """Envia uma mensagem de teste para verificar a ligação com a Meta Cloud API."""
    require_whatsapp_subscription(user)
    with connect() as c:
        integration = c.execute(
            "SELECT * FROM whatsapp_integrations WHERE user_id = ? AND status = 'connected'",
            (user["id"],),
        ).fetchone()

    if not integration:
        raise HTTPException(400, "Nenhuma integração de WhatsApp ativa nesta conta.")

    try:
        res = await send_whatsapp_message(
            phone_number_id=integration["phone_number_id"],
            to=payload.to,
            text=payload.message,
            access_token=integration["access_token"] or None,
        )
        return {"ok": True, "meta_response": res}
    except Exception as e:
        logger.error(f"Erro no envio de teste do WhatsApp: {e}")
        raise HTTPException(400, f"Falha ao enviar mensagem de teste: {str(e)}")


# ==============================================================================
# WEBHOOK OFICIAL DA META CLOUD API
# ==============================================================================

@router.get("/webhooks/whatsapp")
def verify_meta_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """
    Endpoint de verificação do Webhook chamado pela Meta.
    A Meta envia hub.mode=subscribe, hub.verify_token e hub.challenge.
    Se o token coincidir, retornamos hub.challenge.
    """
    config = get_meta_config()
    expected_token = config["verify_token"]

    if expected_token and hub_mode == "subscribe" and hub_verify_token == expected_token:
        logger.info("Webhook da Meta verificado com sucesso.")
        return PlainTextResponse(content=hub_challenge or "", status_code=200)

    logger.warning("A verificação do webhook falhou ou WHATSAPP_VERIFY_TOKEN não está configurado.")
    raise HTTPException(status_code=403, detail="Token de verificação inválido.")


@router.post("/webhooks/whatsapp")
async def receive_meta_webhook(request: Request):
    """
    Endpoint de recepção de eventos e mensagens da Meta Cloud API.
    Processa a mensagem recebida, localiza a conta proprietária,
    gera a resposta com o agente de IA e envia de volta ao WhatsApp.
    """
    body_bytes = await request.body()
    signature_header = request.headers.get("X-Hub-Signature-256")

    # 1. Validar assinatura de segurança da aplicação Meta
    if not verify_webhook_signature(body_bytes, signature_header):
        logger.warning("Rejeitado webhook da Meta por assinatura inválida.")
        raise HTTPException(status_code=403, detail="Assinatura inválida.")

    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception as e:
        logger.error(f"Payload do webhook não é um JSON válido: {e}")
        return {"status": "ignored"}

    # 2. Extrair mensagens do payload
    incoming_messages = extract_incoming_messages(payload)
    if not incoming_messages:
        # Podem ser confirmações de leitura, status de entrega, etc.
        return {"status": "ok"}

    for msg in incoming_messages:
        phone_number_id = msg["phone_number_id"]
        from_number = msg["from"]
        customer_name = msg["customer_name"]
        content = msg["text"]
        message_id = msg["message_id"]

        logger.info(
            f"Mensagem recebida do WhatsApp: De={from_number} (Nome={customer_name}) "
            f"para PhoneID={phone_number_id}: {content[:60]}..."
        )

        with connect() as c:
            # O identificador do número é a chave de roteamento da Meta; não
            # encaminhar mensagens para outra conta quando não houver correspondência.
            integration = c.execute(
                "SELECT * FROM whatsapp_integrations WHERE phone_number_id = ? AND status = 'connected'",
                (phone_number_id,),
            ).fetchone()

            if not integration:
                logger.warning(
                    f"Nenhuma conta de utilizador encontrada para phone_number_id={phone_number_id}. "
                    f"Mensagem ignorada."
                )
                continue

            user_id = integration["user_id"]
            if message_id:
                try:
                    c.execute(
                        "INSERT INTO processed_whatsapp_messages (user_id, message_id) VALUES (?, ?)",
                        (user_id, message_id),
                    )
                except Exception as exc:
                    if "UNIQUE constraint failed" in str(exc) or "duplicate key" in str(exc).lower():
                        logger.info("Evento WhatsApp repetido ignorado: %s", message_id)
                        continue
                    raise

            user = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user:
                logger.warning(f"Utilizador {user_id} não encontrado na base de dados.")
                continue

            user_dict = dict(user)

            # Localiza ou cria o contacto
            contact = c.execute(
                "SELECT id, name FROM contacts WHERE user_id = ? AND contact_key = ?",
                (user_id, from_number),
            ).fetchone()

            if contact:
                cid = contact["id"]
                # Atualiza nome se tivermos recebido um nome novo
                new_name = customer_name or contact["name"] or ""
                c.execute(
                    "UPDATE contacts SET name = ?, last_message_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (new_name, cid),
                )
            else:
                cur = c.execute(
                    "INSERT INTO contacts(user_id, name, contact_key, last_message_at) VALUES(?, ?, ?, CURRENT_TIMESTAMP)",
                    (user_id, customer_name or "", from_number),
                )
                cid = cur.lastrowid

            # Salva a mensagem recebida do cliente
            c.execute(
                "INSERT INTO messages(user_id, contact_id, sender, content) VALUES(?, ?, 'customer', ?)",
                (user_id, cid, content),
            )

            intent = detect_booking_or_purchase_intent(content, "Mensagem WhatsApp")
            scheduled_request = capture_scheduled_request(
                c, user_id, cid, content, "Mensagem WhatsApp", intent
            )
            if scheduled_request and scheduled_request["status"] == "awaiting_schedule":
                message_for_ai = (
                    f"O cliente quer avançar com este pedido de {scheduled_request['request_type']}: "
                    f"{scheduled_request['details']}. Ainda não informou uma data e hora específicas. "
                    "Pergunte de forma cordial qual é a data e a hora pretendidas, explicando que precisa "
                    "dessa informação para registar a marcação/pedido. Não diga que já foi confirmado."
                )
            elif scheduled_request:
                message_for_ai = (
                    f"O cliente enviou uma solicitação de {scheduled_request['request_type']} e indicou "
                    f"data e hora: {scheduled_request['scheduled_at']}. A solicitação está registada e "
                    "aguarda confirmação do proprietário. Confirme a receção sem afirmar que já foi "
                    "confirmada ou concluída."
                )
            else:
                message_for_ai = content

            # Histórico recente da conversa
            history_rows = c.execute(
                "SELECT sender, content FROM messages WHERE contact_id = ? AND user_id = ? AND id != last_insert_rowid() ORDER BY id DESC LIMIT 10",
                (cid, user_id),
            ).fetchall()
            history = [{"sender": r["sender"], "content": r["content"]} for r in reversed(history_rows)]

            # Conhecimento do negócio
            info = c.execute(
                "SELECT kind, title, content, metadata FROM business_info WHERE user_id = ?",
                (user_id,),
            ).fetchall()

            mandatory = {}
            try:
                mandatory = json.loads(user_dict.get("mandatory_responses") or "{}")
            except Exception:
                pass

        # Marca como lida na Meta para feedback imediato
        if message_id:
            try:
                await mark_message_as_read(
                    phone_number_id=phone_number_id,
                    message_id=message_id,
                    access_token=integration["access_token"] or None,
                )
            except Exception as e:
                logger.debug(f"Falha ao marcar como lida: {e}")

        if not is_subscription_active(user_id) or not _user_auto_reply_enabled(user_dict):
            logger.info("Resposta automática WhatsApp pausada para user_id=%s.", user_id)
            continue

        # Gerar resposta com a IA (Gemini ou fallback)
        try:
            reply = await draft_reply(
                message=message_for_ai,
                info_rows=info,
                instructions=effective_agent_instructions(user_dict),
                language=user_dict.get("language") or "Português",
                history=history,
                business_name=user_dict.get("name") or integration["business_name"] or "nosso negócio",
                business_type=user_dict.get("business_type") or "Serviços",
                business_description=user_dict.get("business_description") or "",
                mandatory_responses=mandatory,
            )
        except Exception as e:
            logger.error(f"Erro ao gerar resposta com a IA: {e}")
            reply = "Agradecemos o seu contacto! Em breve responderemos à sua mensagem."

        if scheduled_request and scheduled_request["status"] == "awaiting_schedule":
            reply = ensure_date_time_question(reply)

        # Enviar a resposta via WhatsApp Cloud API
        try:
            await send_whatsapp_message(
                phone_number_id=phone_number_id,
                to=from_number,
                text=reply,
                access_token=integration["access_token"] or None,
            )
            with connect() as c:
                c.execute(
                    "INSERT INTO messages(user_id, contact_id, sender, content) VALUES(?, ?, 'agent', ?)",
                    (user_id, cid, reply),
                )
                c.execute("UPDATE contacts SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?", (cid,))
            logger.info(f"Resposta enviada com sucesso para o WhatsApp {from_number}")
        except Exception as e:
            logger.error(f"Erro ao enviar resposta via WhatsApp Cloud API: {e}")

    return {"status": "ok"}


def _user_auto_reply_enabled(user: dict) -> bool:
    mandatory = user.get("mandatory_responses") or {}
    if isinstance(mandatory, str):
        try:
            mandatory = json.loads(mandatory)
        except (TypeError, json.JSONDecodeError):
            mandatory = {}
    return mandatory.get("automation_level", "semi") != "disabled"


def html_escape(value: str) -> str:
    return html.escape(value, quote=True)
