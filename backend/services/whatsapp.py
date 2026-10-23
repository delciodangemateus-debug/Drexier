import hashlib
import hmac
import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("drexier.whatsapp")

GRAPH_API_BASE = "https://graph.facebook.com"
DEFAULT_GRAPH_VERSION = "v21.0"


def get_meta_config() -> Dict[str, Any]:
    """Recupera as variáveis de configuração da Meta Cloud API / Embedded Signup."""
    load_dotenv(override=False)
    app_id = os.getenv("META_APP_ID", "").strip()
    app_secret = os.getenv("META_APP_SECRET", "").strip()
    config_id = os.getenv("META_CONFIG_ID", "").strip()
    system_user_token = (
        os.getenv("META_SYSTEM_USER_TOKEN", "").strip()
        or os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
    )
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip() or "drexier_webhook_secret_token"
    version = os.getenv("WHATSAPP_GRAPH_VERSION", "").strip() or DEFAULT_GRAPH_VERSION
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    # URL público HTTPS para redirect OAuth (obrigatório para Meta - usar ngrok/localtunnel em dev)
    public_url = os.getenv("PUBLIC_URL", "").strip().rstrip("/")

    return {
        "app_id": app_id,
        "app_secret": app_secret,
        "config_id": config_id,
        "system_user_token": system_user_token,
        "verify_token": verify_token,
        "version": version,
        "phone_number_id": phone_number_id,
        "public_url": public_url,
        "is_configured": bool(app_id and app_secret),
        "has_env_credentials": bool(phone_number_id and system_user_token),
    }


def verify_webhook_signature(payload_bytes: bytes, signature_header: Optional[str]) -> bool:
    """
    Valida a assinatura HMAC-SHA256 enviada pela Meta no cabeçalho X-Hub-Signature-256.
    Se META_APP_SECRET não estiver definido (modo de testes/desenvolvimento), permite a passagem.
    """
    config = get_meta_config()
    secret = config["app_secret"]
    if not secret:
        # Se o segredo não estiver configurado ainda, não bloqueia em ambiente de dev
        return True

    if not signature_header or not signature_header.startswith("sha256="):
        logger.warning("Cabeçalho X-Hub-Signature-256 em falta ou com formato inválido.")
        return False

    expected_sig = signature_header[7:]
    generated_sig = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(generated_sig, expected_sig)


async def exchange_code_for_token(code: str, redirect_uri: Optional[str] = None) -> Dict[str, Any]:
    """
    Troca o Authorization Code obtido via Embedded Signup pelo Access Token de Usuário da Meta.
    Endpoint: GET https://graph.facebook.com/{version}/oauth/access_token
    """
    config = get_meta_config()
    version = config["version"]
    url = f"{GRAPH_API_BASE}/{version}/oauth/access_token"

    params = {
        "client_id": config["app_id"],
        "client_secret": config["app_secret"],
        "code": code,
    }
    if redirect_uri:
        params["redirect_uri"] = redirect_uri

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, params=params)
        data = response.json()
        if response.status_code != 200:
            error_msg = data.get("error", {}).get("message", "Falha ao trocar código de autorização.")
            logger.error(f"Erro ao trocar código por token na Meta: {data}")
            raise ValueError(f"Meta OAuth Error: {error_msg}")
        return data


async def debug_token(input_token: str) -> Dict[str, Any]:
    """Inspeciona o token para obter o WABA ID, permissões e granular scopes."""
    config = get_meta_config()
    version = config["version"]
    app_id = config["app_id"]
    app_secret = config["app_secret"]
    app_access_token = f"{app_id}|{app_secret}"

    url = f"{GRAPH_API_BASE}/{version}/debug_token"
    params = {
        "input_token": input_token,
        "access_token": app_access_token,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, params=params)
        data = response.json()
        if response.status_code != 200:
            logger.warning(f"Erro ao depurar token na Meta: {data}")
            return {}
        return data.get("data", {})


async def subscribe_waba_webhook(waba_id: str, access_token: str) -> bool:
    """
    Subscreve o aplicativo Drexier aos Webhooks da conta WhatsApp Business (WABA).
    Endpoint: POST https://graph.facebook.com/{version}/{waba_id}/subscribed_apps
    """
    config = get_meta_config()
    version = config["version"]
    url = f"{GRAPH_API_BASE}/{version}/{waba_id}/subscribed_apps"

    token_to_use = access_token or config["system_user_token"]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {token_to_use}"},
            )
            data = response.json()
            if response.status_code == 200 and data.get("success"):
                logger.info(f"Subscrição de Webhook concluída com sucesso para WABA: {waba_id}")
                return True
            logger.warning(f"Resposta inesperada ao subscrever WABA ao webhook: {data}")
            return bool(data.get("success", False))
    except Exception as e:
        logger.error(f"Erro de conexão ao subscrever WABA {waba_id}: {e}")
        return False


async def fetch_phone_number_details(phone_number_id: str, access_token: str) -> Dict[str, Any]:
    """
    Obtém os detalhes do número de telefone registrado na Meta Cloud API.
    Endpoint: GET https://graph.facebook.com/{version}/{phone_number_id}?fields=display_phone_number,verified_name,code_verification_status,quality_rating
    """
    config = get_meta_config()
    version = config["version"]
    url = f"{GRAPH_API_BASE}/{version}/{phone_number_id}"
    token_to_use = access_token or config["system_user_token"]

    params = {
        "fields": "display_phone_number,verified_name,code_verification_status,quality_rating"
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {token_to_use}"},
                params=params,
            )
            if response.status_code == 200:
                return response.json()
            logger.warning(f"Não foi possível obter detalhes do número {phone_number_id}: {response.text}")
    except Exception as e:
        logger.error(f"Erro ao buscar detalhes do telefone {phone_number_id}: {e}")
    return {}


async def fetch_waba_phone_numbers(waba_id: str, access_token: str) -> List[Dict[str, Any]]:
    """
    Obtém a lista de números de telefone associados a uma WABA.
    Endpoint: GET https://graph.facebook.com/{version}/{waba_id}/phone_numbers
    """
    config = get_meta_config()
    version = config["version"]
    url = f"{GRAPH_API_BASE}/{version}/{waba_id}/phone_numbers"
    token_to_use = access_token or config["system_user_token"]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {token_to_use}"},
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("data", [])
            logger.warning(f"Erro ao listar números da WABA {waba_id}: {response.text}")
    except Exception as e:
        logger.error(f"Erro ao listar números de telefone da WABA: {e}")
    return []


async def send_whatsapp_message(
    phone_number_id: str,
    to: str,
    text: str,
    access_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Envia uma mensagem de texto oficial via WhatsApp Cloud API.
    Endpoint: POST https://graph.facebook.com/{version}/{phone_number_id}/messages
    """
    config = get_meta_config()
    version = config["version"]
    token_to_use = access_token or config["system_user_token"]

    if not token_to_use:
        raise ValueError("Nenhum token de acesso disponível para envio no WhatsApp.")

    # Remove caracteres não numéricos do telefone destinatário (mantém dígitos)
    clean_to = "".join(filter(str.isdigit, to))
    if not clean_to:
        raise ValueError("Número de telefone destinatário inválido.")

    url = f"{GRAPH_API_BASE}/{version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_to,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text.strip(),
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token_to_use}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        data = response.json()
        if response.status_code not in (200, 201):
            error_detail = data.get("error", {}).get("message", response.text)
            logger.error(f"Erro ao enviar mensagem WhatsApp para {clean_to}: {data}")
            raise RuntimeError(f"Erro WhatsApp Cloud API: {error_detail}")
        return data


async def mark_message_as_read(
    phone_number_id: str,
    message_id: str,
    access_token: Optional[str] = None,
) -> bool:
    """Marca a mensagem como lida na API oficial da Meta."""
    config = get_meta_config()
    version = config["version"]
    token_to_use = access_token or config["system_user_token"]

    if not token_to_use or not message_id:
        return False

    url = f"{GRAPH_API_BASE}/{version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token_to_use}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            return True
    except Exception as e:
        logger.debug(f"Não foi possível marcar mensagem como lida: {e}")
        return False


def extract_incoming_messages(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Analisa o payload oficial da Meta Cloud API e extrai mensagens recebidas.
    Estrutura:
    object: "whatsapp_business_account"
    entry[].changes[].value.messages[]
    """
    messages_out = []

    if payload.get("object") != "whatsapp_business_account":
        return messages_out

    for entry in payload.get("entry", []):
        waba_id = entry.get("id", "")
        for change in entry.get("changes", []):
            val = change.get("value", {})
            metadata = val.get("metadata", {})
            phone_number_id = metadata.get("phone_number_id", "")
            display_phone_number = metadata.get("display_phone_number", "")

            # Mapa de contatos (wa_id -> profile.name)
            contacts_map = {}
            for ct in val.get("contacts", []):
                wa_id = ct.get("wa_id")
                p_name = ct.get("profile", {}).get("name", "")
                if wa_id:
                    contacts_map[wa_id] = p_name

            raw_messages = val.get("messages", [])
            for msg in raw_messages:
                msg_type = msg.get("type")
                from_num = msg.get("from", "")
                msg_id = msg.get("id", "")
                timestamp = msg.get("timestamp", "")
                customer_name = contacts_map.get(from_num, "")

                body = ""
                if msg_type == "text":
                    body = msg.get("text", {}).get("body", "")
                elif msg_type == "interactive":
                    interactive = msg.get("interactive", {})
                    i_type = interactive.get("type")
                    if i_type == "button_reply":
                        body = interactive.get("button_reply", {}).get("title", "")
                    elif i_type == "list_reply":
                        body = interactive.get("list_reply", {}).get("title", "")
                elif msg_type == "button":
                    body = msg.get("button", {}).get("text", "")
                elif msg_type in ("image", "document", "audio", "voice", "video"):
                    caption = msg.get(msg_type, {}).get("caption", "")
                    body = caption or f"[{msg_type.capitalize()} recebido pelo WhatsApp]"
                elif msg_type == "location":
                    loc = msg.get("location", {})
                    name = loc.get("name") or loc.get("address") or ""
                    body = f"[Localização compartilhada: {name}]" if name else "[Localização compartilhada]"
                else:
                    body = "[Mensagem recebida]"

                if body.strip():
                    messages_out.append({
                        "waba_id": waba_id,
                        "phone_number_id": phone_number_id,
                        "display_phone_number": display_phone_number,
                        "from": from_num,
                        "customer_name": customer_name,
                        "message_id": msg_id,
                        "timestamp": timestamp,
                        "text": body.strip(),
                        "type": msg_type,
                    })

    return messages_out
