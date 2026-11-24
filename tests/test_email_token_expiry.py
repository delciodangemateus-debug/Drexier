import time
import pytest
from starlette.testclient import TestClient
from backend.main import app
from backend.database import connect, init_db
from tests.test_api import signup_and_verify
from backend.services.email_service import (
    EmailTokenExpiredError,
    mark_integration_token_expired,
    refresh_google_token_if_needed,
)

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_token_expiry.db"
    monkeypatch.setattr("backend.database.DB_PATH", str(test_db))
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_google_client_id_123")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test_google_client_secret_abc")
    init_db()
    yield

@pytest.fixture
def auth_client():
    client = TestClient(app)
    signup_res = signup_and_verify(client, {
        "name": "Carlos Atendimento",
        "email": "carlos_token_test@empresa.com",
        "password": "Password123",
        "confirm_password": "Password123",
        "business_type": "Serviços",
    })
    token = signup_res.json()["token"]
    user_id = signup_res.json()["user_id"]
    with connect() as c:
        c.execute(
            """INSERT OR REPLACE INTO subscriptions (user_id, plan_name, amount, currency, status)
               VALUES (?, 'Plano Business', 5900, 'eur', 'active')""",
            (user_id,)
        )
    return client, token, user_id


@pytest.mark.anyio
async def test_mark_integration_token_expired_pauses_agent(auth_client):
    client, token, user_id = auth_client
    with connect() as c:
        c.execute(
            """INSERT INTO email_integrations (user_id, provider, email_address, status, auto_reply_enabled)
               VALUES (?, 'google', 'teste@gmail.com', 'connected', 1)
               ON CONFLICT(user_id) DO UPDATE SET status='connected', auto_reply_enabled=1""",
            (user_id,)
        )

    # Executa a função de marcar token expirado
    mark_integration_token_expired(user_id=user_id)

    with connect() as c:
        row = dict(c.execute("SELECT status, auto_reply_enabled FROM email_integrations WHERE user_id = ?", (user_id,)).fetchone())

    assert row["status"] == "needs_reconnect"
    assert row["auto_reply_enabled"] == 0

    # Verifica se o endpoint /api/email/status reflete needs_reconnect e as mensagens bilíngues
    res = client.get("/api/email/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["needs_reconnect"] is True
    assert data["connected"] is False
    assert "O agente foi pausado. Desconecte e reconecte o e-mail" in data["reconnect_message_pt"]
    assert "The agent was paused. Disconnect and reconnect your email" in data["reconnect_message_en"]

@pytest.mark.anyio
async def test_toggle_auto_reply_blocked_when_token_needs_reconnect(auth_client):
    client, token, user_id = auth_client
    with connect() as c:
        c.execute(
            """INSERT INTO email_integrations (user_id, provider, email_address, status, auto_reply_enabled)
               VALUES (?, 'google', 'teste@gmail.com', 'needs_reconnect', 0)
               ON CONFLICT(user_id) DO UPDATE SET status='needs_reconnect', auto_reply_enabled=0""",
            (user_id,)
        )

    res = client.post("/api/email/auto-reply", headers={"Authorization": f"Bearer {token}"}, json={"enabled": True})
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["code"] == "token_expired"
    assert detail["needs_reconnect"] is True
    assert "O agente foi pausado. Desconecte e reconecte o e-mail" in detail["message"]
    assert "The agent was paused. Disconnect and reconnect your email" in detail["message_en"]
