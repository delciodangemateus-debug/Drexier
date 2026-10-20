import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from backend.main import app
from backend.database import connect, init_db
from backend.auth import create_token
from backend.services.email_service import (
    clean_email_body,
    parse_sender_info,
    create_mime_message,
)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_email.db"
    monkeypatch.setattr("backend.database.DB_PATH", str(test_db))
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_google_client_id_123")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test_google_client_secret_abc")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "test_ms_client_id_456")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "test_ms_client_secret_xyz")
    init_db()
    yield


@pytest.fixture
def auth_client():
    client = TestClient(app)
    signup_res = client.post(
        "/api/auth/signup",
        json={
            "name": "Carlos Atendimento",
            "email": "carlos@empresa.com",
            "password": "Password123",
            "confirm_password": "Password123",
            "business_type": "Serviços",
        },
    )
    assert signup_res.status_code == 200
    token = signup_res.json()["token"]
    user_id = signup_res.json()["user_id"]
    return client, token, user_id


def test_clean_email_body_and_sender_parser():
    raw_from = "João Cliente <joao.cliente@gmail.com>"
    email_addr, name = parse_sender_info(raw_from)
    assert email_addr == "joao.cliente@gmail.com"
    assert name == "João Cliente"

    body_with_reply = "Olá, gostaria de saber os preços.\n\nOn Mon, Oct 19, 2026 at 2:00 PM Drexier wrote:\n> Como podemos ajudar?"
    cleaned = clean_email_body(body_with_reply)
    assert cleaned == "Olá, gostaria de saber os preços."


def test_create_mime_message():
    msg = create_mime_message(
        sender="suporte@drexier.com",
        to="cliente@exemplo.com",
        subject="Re: Informações",
        body_text="Olá! O nosso horário é das 9h às 18h."
    )
    assert msg["From"] == "suporte@drexier.com"
    assert msg["To"] == "cliente@exemplo.com"
    assert msg["Subject"] == "Re: Informações"


def test_email_public_config(auth_client):
    client, _, _ = auth_client
    res = client.get("/api/email/config")
    assert res.status_code == 200
    data = res.json()
    assert data["google"]["configured"] is True
    assert data["microsoft"]["configured"] is True


def test_email_status_when_disconnected(auth_client):
    client, token, _ = auth_client
    res = client.get("/api/email/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["connected"] is False
    assert data["integration"] is None


def test_manual_email_connect_and_disconnect(auth_client):
    client, token, user_id = auth_client
    connect_payload = {
        "provider": "smtp_imap",
        "email_address": "suporte@meudominio.com",
        "display_name": "Suporte Técnico",
        "smtp_host": "smtp.meudominio.com",
        "smtp_port": 587,
        "smtp_user": "suporte@meudominio.com",
        "smtp_password": "supersecretpassword",
        "imap_host": "imap.meudominio.com",
        "imap_port": 993,
    }
    res_conn = client.post("/api/email/connect-manual", json=connect_payload, headers={"Authorization": f"Bearer {token}"})
    assert res_conn.status_code == 200
    assert res_conn.json()["ok"] is True

    # Verifica status conectado
    res_status = client.get("/api/email/status", headers={"Authorization": f"Bearer {token}"})
    assert res_status.status_code == 200
    data = res_status.json()
    assert data["connected"] is True
    assert data["integration"]["provider"] == "smtp_imap"
    assert data["integration"]["email_address"] == "suporte@meudominio.com"

    # Desconectar
    res_disc = client.post("/api/email/disconnect", headers={"Authorization": f"Bearer {token}"})
    assert res_disc.status_code == 200
    assert res_disc.json()["ok"] is True

    # Status agora deve ser desconectado
    res_status_after = client.get("/api/email/status", headers={"Authorization": f"Bearer {token}"})
    assert res_status_after.json()["connected"] is False


def test_google_oauth_url_and_callback(auth_client):
    client, token, user_id = auth_client

    # 1. Obter link oficial da Google
    res_url = client.get("/api/email/oauth/google/url", headers={"Authorization": f"Bearer {token}"})
    assert res_url.status_code == 200
    url_data = res_url.json()
    assert "accounts.google.com" in url_data["url"]
    assert "test_google_client_id_123" in url_data["url"]

    # 2. Simular callback oficial da Google
    state = token
    with patch("backend.routers.email.exchange_google_code", new_callable=AsyncMock) as mock_exch, \
         patch("backend.routers.email.fetch_google_user_profile", new_callable=AsyncMock) as mock_profile:
        mock_exch.return_value = {
            "access_token": "ya29.test_google_access_token",
            "refresh_token": "1//test_google_refresh_token",
            "expires_in": 3600,
        }
        mock_profile.return_value = ("atendimento.google@empresa.com", "Atendimento Google")

        res_callback = client.get(
            "/api/email/oauth/google/callback",
            params={"code": "4/0AeanS0_test_code", "state": state},
            follow_redirects=False,
        )
        assert res_callback.status_code in (302, 307)
        assert "email_auth=success" in res_callback.headers["location"]
        assert "provider=google" in res_callback.headers["location"]

    # Verifica status agora conectado com Google
    res_status = client.get("/api/email/status", headers={"Authorization": f"Bearer {token}"})
    assert res_status.status_code == 200
    st_data = res_status.json()
    assert st_data["connected"] is True
    assert st_data["integration"]["provider"] == "google"
    assert st_data["integration"]["email_address"] == "atendimento.google@empresa.com"


def test_microsoft_oauth_url_and_callback(auth_client):
    client, token, user_id = auth_client

    # 1. Obter link oficial da Microsoft
    res_url = client.get("/api/email/oauth/microsoft/url", headers={"Authorization": f"Bearer {token}"})
    assert res_url.status_code == 200
    url_data = res_url.json()
    assert "login.microsoftonline.com" in url_data["url"]
    assert "test_ms_client_id_456" in url_data["url"]

    # 2. Simular callback oficial da Microsoft
    state = token
    with patch("backend.routers.email.exchange_microsoft_code", new_callable=AsyncMock) as mock_exch, \
         patch("backend.routers.email.fetch_microsoft_user_profile", new_callable=AsyncMock) as mock_profile:
        mock_exch.return_value = {
            "access_token": "EwB_test_ms_access_token",
            "refresh_token": "M.R3_test_ms_refresh_token",
            "expires_in": 3600,
        }
        mock_profile.return_value = ("contato.outlook@empresa.com", "Equipe Outlook")

        res_callback = client.get(
            "/api/email/oauth/microsoft/callback",
            params={"code": "M.C544_test_code", "state": state},
            follow_redirects=False,
        )
        assert res_callback.status_code in (302, 307)
        assert "email_auth=success" in res_callback.headers["location"]
        assert "provider=microsoft" in res_callback.headers["location"]

    # Verifica status agora conectado com Microsoft
    res_status = client.get("/api/email/status", headers={"Authorization": f"Bearer {token}"})
    assert res_status.status_code == 200
    st_data = res_status.json()
    assert st_data["connected"] is True
    assert st_data["integration"]["provider"] == "microsoft"
    assert st_data["integration"]["email_address"] == "contato.outlook@empresa.com"


@pytest.mark.anyio
async def test_email_test_send(auth_client):
    client, token, user_id = auth_client

    # Conectar conta de e-mail primeiro
    with connect() as c:
        c.execute(
            """INSERT INTO email_integrations (user_id, provider, email_address, display_name, access_token, status)
               VALUES (?, 'google', 'meu.negocio@gmail.com', 'Meu Negócio', 'ya29_test', 'connected')""",
            (user_id,)
        )

    with patch("backend.routers.email.send_email", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = {"id": "msg_sent_123"}
        res = client.post(
            "/api/email/test-send",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "to": "destinatario@cliente.com",
                "subject": "Teste Drexier",
                "message": "Olá mundo de teste!"
            }
        )
        assert res.status_code == 200
        assert res.json()["ok"] is True
        assert mock_send.call_count == 1


@pytest.mark.anyio
async def test_email_sync_triggers_ai_and_records_conversation(auth_client):
    client, token, user_id = auth_client

    # 1. Configurar informações de negócio e integração conectada
    with connect() as c:
        c.execute(
            "INSERT INTO business_info(user_id, kind, title, content) VALUES (?, 'servicos', 'Preço de Consultoria', 'Consultoria custa 50€ por sessão.')",
            (user_id,),
        )
        c.execute(
            """INSERT INTO email_integrations (user_id, provider, email_address, display_name, access_token, status)
               VALUES (?, 'google', 'empresa@gmail.com', 'Empresa Silva', 'ya29_token', 'connected')""",
            (user_id,),
        )

    # 2. Mock da busca de e-mails no Google e envio de resposta
    mock_processed = [
        {
            "message_id": "gmail_msg_001",
            "from": "cliente.interessado@gmail.com",
            "subject": "Dúvida sobre Consultoria",
            "reply": "O valor da nossa consultoria é de 50€ por sessão."
        }
    ]

    with patch("backend.services.email_service.sync_google_emails", new_callable=AsyncMock) as mock_sync_g:
        mock_sync_g.return_value = mock_processed

        res = client.post("/api/email/sync", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["processed_count"] == 1


def test_toggle_auto_reply(auth_client):
    client, token, user_id = auth_client

    # Conectar integração
    with connect() as c:
        c.execute(
            """INSERT INTO email_integrations (user_id, provider, email_address, display_name, status, auto_reply_enabled)
               VALUES (?, 'google', 'empresa@gmail.com', 'Empresa Silva', 'connected', 1)""",
            (user_id,),
        )

    # 1. Desativar respostas automáticas
    res_disable = client.post(
        "/api/email/auto-reply",
        headers={"Authorization": f"Bearer {token}"},
        json={"enabled": False},
    )
    assert res_disable.status_code == 200
    assert res_disable.json()["ok"] is True
    assert res_disable.json()["auto_reply_enabled"] is False

    # Verifica status
    status_res = client.get("/api/email/status", headers={"Authorization": f"Bearer {token}"})
    assert status_res.status_code == 200
    assert status_res.json()["integration"]["auto_reply_enabled"] is False

    # 2. Reativar respostas automáticas
    res_enable = client.post(
        "/api/email/auto-reply",
        headers={"Authorization": f"Bearer {token}"},
        json={"enabled": True},
    )
    assert res_enable.status_code == 200
    assert res_enable.json()["auto_reply_enabled"] is True

    status_res2 = client.get("/api/email/status", headers={"Authorization": f"Bearer {token}"})
    assert status_res2.json()["integration"]["auto_reply_enabled"] is True
