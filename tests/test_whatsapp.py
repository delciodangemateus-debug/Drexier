import hashlib
import hmac
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from backend.main import app
from backend.database import connect, init_db
from backend.services.whatsapp import (
    extract_incoming_messages,
    verify_webhook_signature,
)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_whatsapp.db"
    monkeypatch.setattr("backend.database.DB_PATH", str(test_db))
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "test_verify_token_123")
    monkeypatch.setenv("META_APP_SECRET", "test_app_secret_abc")
    monkeypatch.setenv("META_APP_ID", "1234567890")
    init_db()
    yield


@pytest.fixture
def auth_client():
    client = TestClient(app)
    # Cria conta de usuário para teste
    signup_res = client.post(
        "/api/auth/signup",
        json={
            "name": "Maria Silva",
            "email": "maria@empresa.com",
            "password": "Password123",
            "confirm_password": "Password123",
            "business_type": "Serviços",
        },
    )
    assert signup_res.status_code == 200
    token = signup_res.json()["token"]
    user_id = signup_res.json()["user_id"]
    with connect() as c:
        c.execute(
            """INSERT OR REPLACE INTO subscriptions (user_id, plan_name, amount, currency, status)
               VALUES (?, 'Plano Business', 5900, 'eur', 'active')""",
            (user_id,)
        )
    return client, token, user_id


def test_whatsapp_public_config(auth_client):
    client, _, _ = auth_client
    res = client.get("/api/whatsapp/config")
    assert res.status_code == 200
    data = res.json()
    assert data["app_id"] == "1234567890"
    assert data["configured"] is True


def test_whatsapp_status_when_disconnected(auth_client):
    client, token, _ = auth_client
    res = client.get("/api/whatsapp/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["connected"] is False
    assert data["integration"] is None


def test_whatsapp_connect_and_status(auth_client):
    client, token, user_id = auth_client

    with patch("backend.routers.whatsapp.subscribe_waba_webhook", new_callable=AsyncMock) as mock_sub:
        mock_sub.return_value = True

        connect_res = client.post(
            "/api/whatsapp/connect",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "phone_number_id": "phone_id_999",
                "waba_id": "waba_id_888",
                "phone_number": "+351912345678",
                "business_name": "Minha Loja Oficial",
                "access_token": "EAA_test_token",
            },
        )
        assert connect_res.status_code == 200
        assert connect_res.json()["ok"] is True

    # Verifica status agora conectado
    status_res = client.get("/api/whatsapp/status", headers={"Authorization": f"Bearer {token}"})
    assert status_res.status_code == 200
    st_data = status_res.json()
    assert st_data["connected"] is True
    assert st_data["integration"]["phone_number_id"] == "phone_id_999"
    assert st_data["integration"]["waba_id"] == "waba_id_888"
    assert st_data["integration"]["business_name"] == "Minha Loja Oficial"


def test_whatsapp_disconnect(auth_client):
    client, token, _ = auth_client

    # Conecta
    with patch("backend.routers.whatsapp.subscribe_waba_webhook", new_callable=AsyncMock) as mock_sub:
        mock_sub.return_value = True
        client.post(
            "/api/whatsapp/connect",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "phone_number_id": "phone_id_disconnect_test",
                "waba_id": "waba_id_disc",
            },
        )

    # Desconecta
    disc_res = client.post("/api/whatsapp/disconnect", headers={"Authorization": f"Bearer {token}"})
    assert disc_res.status_code == 200
    assert disc_res.json()["ok"] is True

    # Status deve estar desconectado
    status_res = client.get("/api/whatsapp/status", headers={"Authorization": f"Bearer {token}"})
    assert status_res.json()["connected"] is False


def test_meta_webhook_verification(auth_client):
    client, _, _ = auth_client

    # Token correto
    res_ok = client.get(
        "/api/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test_verify_token_123",
            "hub.challenge": "11582012",
        },
    )
    assert res_ok.status_code == 200
    assert res_ok.text == "11582012"

    # Token incorreto
    res_bad = client.get(
        "/api/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "token_errado",
            "hub.challenge": "11582012",
        },
    )
    assert res_bad.status_code == 403


@pytest.mark.anyio
async def test_meta_webhook_incoming_message_triggers_ai_and_reply(auth_client):
    client, token, user_id = auth_client

    # 1. Configura informações do negócio para o usuário
    with connect() as c:
        c.execute(
            "INSERT INTO business_info(user_id, kind, title, content) VALUES (?, 'servicos', 'Preço de Consultoria', 'Consultoria completa custa 50€.')",
            (user_id,),
        )
        c.execute(
            """INSERT INTO whatsapp_integrations (user_id, waba_id, phone_number_id, phone_number, business_name, access_token, status)
               VALUES (?, 'waba_100', 'phone_100', '+351910000000', 'Consultoria Silva', 'EAAB_test', 'connected')""",
            (user_id,),
        )

    # 2. Prepara payload oficial da Meta
    meta_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba_100",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "+351910000000",
                                "phone_number_id": "phone_100",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "João Cliente"},
                                    "wa_id": "351988888888",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "351988888888",
                                    "id": "wamid.HBgLMDExMQ==",
                                    "timestamp": "1729250000",
                                    "text": {"body": "Olá, quanto custa a consultoria?"},
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    body_bytes = json.dumps(meta_payload).encode("utf-8")
    sig = hmac.new(b"test_app_secret_abc", body_bytes, hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": f"sha256={sig}",
    }

    with patch("backend.routers.whatsapp.send_whatsapp_message", new_callable=AsyncMock) as mock_send, \
         patch("backend.routers.whatsapp.mark_message_as_read", new_callable=AsyncMock) as mock_read:
        mock_send.return_value = {"messages": [{"id": "wamid.out123"}]}

        res = client.post("/api/webhooks/whatsapp", content=body_bytes, headers=headers)
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}

        # Confirma que a mensagem de resposta foi enviada via WhatsApp Cloud API
        assert mock_send.call_count == 1
        args, kwargs = mock_send.call_args
        assert kwargs.get("phone_number_id") == "phone_100" or args[0] == "phone_100"
        assert kwargs.get("to") == "351988888888" or args[1] == "351988888888"

    # Verifica se o contacto e mensagens foram salvos no banco de dados do utilizador
    with connect() as c:
        contact = c.execute("SELECT * FROM contacts WHERE user_id = ? AND contact_key = '351988888888'", (user_id,)).fetchone()
        assert contact is not None
        assert contact["name"] == "João Cliente"

        msgs = c.execute("SELECT sender, content FROM messages WHERE contact_id = ? ORDER BY id", (contact["id"],)).fetchall()
        assert len(msgs) == 2
        assert msgs[0]["sender"] == "customer"
        assert "quanto custa a consultoria" in msgs[0]["content"]
        assert msgs[1]["sender"] == "agent"
        # O agente deve ter respondido com base na informação cadastrada (consultoria 50€)
        assert "50" in msgs[1]["content"] or "consultoria" in msgs[1]["content"].lower()


def test_extract_incoming_messages_helpers():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba_xyz",
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "pid_123"},
                            "contacts": [{"wa_id": "351111", "profile": {"name": "Carlos"}}],
                            "messages": [
                                {"from": "351111", "id": "mid_1", "type": "text", "text": {"body": "Oi"}},
                                {"from": "351111", "id": "mid_2", "type": "image", "image": {"caption": "Foto do produto"}},
                            ],
                        }
                    }
                ],
            }
        ],
    }

    msgs = extract_incoming_messages(payload)
    assert len(msgs) == 2
    assert msgs[0]["customer_name"] == "Carlos"
    assert msgs[0]["text"] == "Oi"
    assert msgs[1]["text"] == "Foto do produto"


def test_verify_webhook_signature():
    secret = "test_app_secret_abc"
    body = b'{"hello": "world"}'
    good_sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(body, good_sig) is True

    bad_sig = "sha256=abcdef1234567890"
    assert verify_webhook_signature(body, bad_sig) is False


def test_whatsapp_connect_use_env(auth_client, monkeypatch):
    client, token, user_id = auth_client
    monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "phone_env_123")
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "token_env_abc")

    with patch("backend.routers.whatsapp.subscribe_waba_webhook", new_callable=AsyncMock) as mock_sub:
        mock_sub.return_value = True

        res = client.post(
            "/api/whatsapp/connect",
            headers={"Authorization": f"Bearer {token}"},
            json={"use_env": True},
        )
        assert res.status_code == 200
        assert res.json()["ok"] is True
        assert res.json()["integration"]["phone_number_id"] == "phone_env_123"

    # Status agora deve constar como conectado
    st_res = client.get("/api/whatsapp/status", headers={"Authorization": f"Bearer {token}"})
    assert st_res.status_code == 200
    assert st_res.json()["connected"] is True


@pytest.mark.anyio
async def test_owner_reply_to_whatsapp_contact(auth_client):
    client, token, user_id = auth_client

    # Cria integração WhatsApp e contacto com telefone
    with connect() as c:
        c.execute(
            """INSERT INTO whatsapp_integrations (user_id, waba_id, phone_number_id, phone_number, business_name, access_token, status)
               VALUES (?, 'waba_test', 'phone_owner_test', '+351912000000', 'Loja Teste', 'EAAB_token', 'connected')""",
            (user_id,),
        )
        cur = c.execute(
            "INSERT INTO contacts (user_id, name, contact_key) VALUES (?, 'Ana Cliente', '+351933333333')",
            (user_id,),
        )
        contact_id = cur.lastrowid

    with patch("backend.services.whatsapp.send_whatsapp_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"messages": [{"id": "wamid.reply123"}]}

        res = client.post(
            f"/api/contacts/{contact_id}/reply",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": "Olá Ana, a sua encomenda está a caminho!"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data.get("channel") == "whatsapp"

        # Verifica se send_whatsapp_message foi chamado com o número do cliente
        assert mock_send.call_count == 1
        kwargs = mock_send.call_args.kwargs
        assert kwargs.get("to") == "+351933333333"
        assert kwargs.get("text") == "Olá Ana, a sua encomenda está a caminho!"


@pytest.mark.anyio
async def test_conversion_action_whatsapp(auth_client):
    client, token, user_id = auth_client

    # Cria integração WhatsApp, contacto e pedido de agendamento pendente
    with connect() as c:
        c.execute(
            """INSERT INTO whatsapp_integrations (user_id, waba_id, phone_number_id, phone_number, business_name, access_token, status)
               VALUES (?, 'waba_test', 'phone_conv_test', '+351912000000', 'Loja Teste', 'EAAB_token', 'connected')""",
            (user_id,),
        )
        cur = c.execute(
            "INSERT INTO contacts (user_id, name, contact_key) VALUES (?, 'Rui Santos', '+351922222222')",
            (user_id,),
        )
        contact_id = cur.lastrowid

        cur_req = c.execute(
            """INSERT INTO conversion_requests (user_id, contact_id, request_type, details, status)
               VALUES (?, ?, 'booking', 'Marcação para Segunda às 14h', 'pending')""",
            (user_id, contact_id),
        )
        req_id = cur_req.lastrowid

    with patch("backend.services.whatsapp.send_whatsapp_message", new_callable=AsyncMock) as mock_send, \
         patch("backend.services.email_service.draft_reply", new_callable=AsyncMock) as mock_draft:
        mock_draft.return_value = "A sua marcação para Segunda às 14h está confirmada!"
        mock_send.return_value = {"messages": [{"id": "wamid.conv_out"}]}

        res = client.post(
            f"/api/conversions/{req_id}/action",
            headers={"Authorization": f"Bearer {token}"},
            json={"action": "confirm", "custom_note": "Aguardamos a sua visita."},
        )
        assert res.status_code == 200
        assert res.json()["ok"] is True
        assert res.json()["status"] == "confirmed"

        # Confirma que enviou para o WhatsApp do cliente
        assert mock_send.call_count == 1
        assert mock_send.call_args.kwargs.get("to") == "+351922222222"


def test_whatsapp_oauth_callback(auth_client):
    client, _, _ = auth_client
    res = client.get("/api/whatsapp/oauth/callback?code=test_oauth_code_xyz")
    assert res.status_code == 200
    assert "WA_OAUTH_CODE" in res.text
    assert "test_oauth_code_xyz" in res.text

    res_err = client.get("/api/whatsapp/oauth/callback?error=access_denied&error_description=Cancelado")
    assert res_err.status_code == 200
    assert "WA_OAUTH_ERROR" in res_err.text
    assert "Cancelado" in res_err.text
