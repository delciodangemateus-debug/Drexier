import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from backend.auth import decode_token
from backend.database import connect
from backend.services.agent import draft_reply
from backend.services.whatsapp import (
    debug_token,
    exchange_code_for_token,
    extract_incoming_messages,
    fetch_phone_number_details,
    fetch_waba_phone_numbers,
    get_meta_config,
    mark_message_as_read,
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
            "SELECT id, name, email, business_type, business_description, language, agent_instructions, mandatory_responses FROM users WHERE id=?",
            (uid,),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Conta não encontrada.")
    return dict(row)


class WhatsAppConnectPayload(BaseModel):
    code: Optional[str] = None
    waba_id: Optional[str] = None
    phone_number_id: Optional[str] = None
    phone_number: Optional[str] = None
    business_name: Optional[str] = None
    access_token: Optional[str] = None


class TestSendPayload(BaseModel):
    to: str = Field(min_length=5, max_length=30)
    message: str = Field(min_length=1, max_length=4000)


@router.get("/whatsapp/config")
def get_whatsapp_public_config():
    """Retorna a configuração pública para o Embedded Signup no frontend."""
    config = get_meta_config()
    return {
        "app_id": config["app_id"],
        "config_id": config["config_id"],
        "version": config["version"],
        "configured": bool(config["app_id"] and config["app_secret"]),
    }


@router.get("/whatsapp/status")
def get_whatsapp_status(user: dict = Depends(get_current_user)):
    """Retorna o estado da ligação do WhatsApp da conta autenticada."""
    with connect() as c:
        row = c.execute(
            """SELECT id, user_id, waba_id, phone_number_id, phone_number,
                      business_name, status, webhook_subscribed, created_at, updated_at
               FROM whatsapp_integrations
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
            "waba_id": row["waba_id"],
            "phone_number_id": row["phone_number_id"],
            "phone_number": row["phone_number"],
            "business_name": row["business_name"],
            "status": row["status"],
            "webhook_subscribed": bool(row["webhook_subscribed"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        },
    }


@router.post("/whatsapp/connect")
async def connect_whatsapp(
    payload: WhatsAppConnectPayload,
    user: dict = Depends(get_current_user),
):
    """
    Conclui o Embedded Signup da Meta ou a ligação com credenciais.
    Troca o código pelo token, subscreve os webhooks e armazena os identificadores no banco.
    """
    token = payload.access_token or ""
    waba_id = (payload.waba_id or "").strip()
    phone_number_id = (payload.phone_number_id or "").strip()
    phone_number = (payload.phone_number or "").strip()
    business_name = (payload.business_name or "").strip()

    # Se recebemos um código OAuth do Embedded Signup, efetuamos a troca na Graph API
    if payload.code:
        try:
            token_data = await exchange_code_for_token(payload.code)
            token = token_data.get("access_token", token)
        except Exception as e:
            logger.error(f"Erro ao trocar código por token: {e}")
            raise HTTPException(400, f"Falha na autenticação com a Meta: {str(e)}")

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
        if numbers:
            first_num = numbers[0]
            phone_number_id = first_num.get("id", "")
            if not phone_number:
                phone_number = first_num.get("display_phone_number", "")
            if not business_name:
                business_name = first_num.get("verified_name", "")

    # Se temos phone_number_id mas faltam número legível ou nome, consulta os detalhes
    if phone_number_id and (not phone_number or not business_name):
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
        waba_id = f"waba_{phone_number_id}"

    # Subscrever a WABA aos webhooks da nossa aplicação
    subscribed = False
    if waba_id and token:
        subscribed = await subscribe_waba_webhook(waba_id, token)

    # Gravar na base de dados (upsert por user_id)
    with connect() as c:
        # Verifica se este phone_number_id já está em uso por outro utilizador
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
                   updated_at
               )
               VALUES (?, ?, ?, ?, ?, ?, 'connected', ?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id) DO UPDATE SET
                   waba_id = excluded.waba_id,
                   phone_number_id = excluded.phone_number_id,
                   phone_number = excluded.phone_number,
                   business_name = excluded.business_name,
                   access_token = CASE WHEN excluded.access_token != '' THEN excluded.access_token ELSE whatsapp_integrations.access_token END,
                   status = 'connected',
                   webhook_subscribed = excluded.webhook_subscribed,
                   updated_at = CURRENT_TIMESTAMP""",
            (
                user["id"],
                waba_id,
                phone_number_id,
                phone_number or phone_number_id,
                business_name or user["name"],
                token,
                1 if subscribed else 0,
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
        },
    }


@router.post("/whatsapp/disconnect")
def disconnect_whatsapp(user: dict = Depends(get_current_user)):
    """Desconecta a integração do WhatsApp do utilizador autenticado."""
    with connect() as c:
        c.execute(
            "UPDATE whatsapp_integrations SET status = 'disconnected', updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (user["id"],),
        )
    return {"ok": True, "message": "WhatsApp desconectado com sucesso."}


@router.post("/whatsapp/test-send")
async def test_send_message(
    payload: TestSendPayload,
    user: dict = Depends(get_current_user),
):
    """Envia uma mensagem de teste para verificar a ligação com a Meta Cloud API."""
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

    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        logger.info("Webhook da Meta verificado com sucesso.")
        return PlainTextResponse(content=hub_challenge or "", status_code=200)

    logger.warning(
        f"Tentativa de verificação do Webhook da Meta falhou. "
        f"Recebido: {hub_verify_token}, Esperado: {expected_token}"
    )
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

    # 1. Validar assinatura de segurança se o segredo estiver configurado
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
            # Localiza a integração correspondente
            integration = c.execute(
                "SELECT * FROM whatsapp_integrations WHERE phone_number_id = ? AND status = 'connected'",
                (phone_number_id,),
            ).fetchone()

            if not integration:
                # Tenta buscar por waba_id como contingência
                integration = c.execute(
                    "SELECT * FROM whatsapp_integrations WHERE waba_id = ? AND status = 'connected'",
                    (msg["waba_id"],),
                ).fetchone()

            if not integration:
                logger.warning(
                    f"Nenhuma conta de utilizador encontrada para phone_number_id={phone_number_id}. "
                    f"Mensagem ignorada."
                )
                continue

            user_id = integration["user_id"]
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

        # Gerar resposta com a IA (Gemini ou fallback)
        try:
            reply = await draft_reply(
                message=content,
                info_rows=info,
                instructions=user_dict.get("agent_instructions") or "",
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

        # Salvar a resposta da IA no banco de dados
        with connect() as c:
            c.execute(
                "INSERT INTO messages(user_id, contact_id, sender, content) VALUES(?, ?, 'agent', ?)",
                (user_id, cid, reply),
            )
            c.execute("UPDATE contacts SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?", (cid,))

        # Enviar a resposta via WhatsApp Cloud API
        try:
            await send_whatsapp_message(
                phone_number_id=phone_number_id,
                to=from_number,
                text=reply,
                access_token=integration["access_token"] or None,
            )
            logger.info(f"Resposta enviada com sucesso para o WhatsApp {from_number}")
        except Exception as e:
            logger.error(f"Erro ao enviar resposta via WhatsApp Cloud API: {e}")

    return {"status": "ok"}
