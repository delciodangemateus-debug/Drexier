import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from starlette.testclient import TestClient
from backend.main import app
from backend.database import connect, init_db
from backend.services.token_crypto import encrypt_token
from tests.test_api import signup_and_verify
from backend.services.email_service import (
    EmailTokenExpiredError,
    mark_integration_token_expired,
    refresh_google_token_if_needed,
    sync_user_activity_and_check_inactivity,
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


@pytest.mark.anyio
async def test_active_user_within_7_days_refreshes_token_without_expiring(auth_client):
    client, token, user_id = auth_client
    recent_active = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    with connect() as c:
        c.execute("UPDATE users SET last_active_at = ? WHERE id = ?", (recent_active, user_id))
        c.execute(
            """INSERT INTO email_integrations
               (user_id, provider, email_address, access_token, refresh_token, token_expires_at, status, auto_reply_enabled)
               VALUES (?, 'google', 'ativo@gmail.com', ?, ?, ?, 'connected', 1)
               ON CONFLICT(user_id) DO UPDATE SET
                 access_token=excluded.access_token,
                 refresh_token=excluded.refresh_token,
                 token_expires_at=excluded.token_expires_at,
                 status='connected',
                 auto_reply_enabled=1""",
            (user_id, encrypt_token("old_access"), encrypt_token("valid_refresh"), str(time.time() - 60)),
        )
        integration = dict(c.execute("SELECT * FROM email_integrations WHERE user_id = ?", (user_id,)).fetchone())

    mock_response = MagicMock(status_code=200)
    mock_response.json.return_value = {"access_token": "new_fresh_access_token", "expires_in": 3600}
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post.return_value = mock_response

    with patch("backend.services.email_service.httpx.AsyncClient", return_value=mock_client):
        new_token = await refresh_google_token_if_needed(integration)

    assert new_token == "new_fresh_access_token"
    with connect() as c:
        row = dict(c.execute("SELECT status, auto_reply_enabled FROM email_integrations WHERE user_id = ?", (user_id,)).fetchone())
    assert row["status"] == "connected"
    assert row["auto_reply_enabled"] == 1


@pytest.mark.anyio
async def test_inactive_user_over_7_days_freezes_account_and_shows_on_dashboard(auth_client):
    client, token, user_id = auth_client
    stale_active = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    with connect() as c:
        c.execute("UPDATE users SET last_active_at = ? WHERE id = ?", (stale_active, user_id))
        c.execute(
            """INSERT INTO email_integrations
               (user_id, provider, email_address, access_token, refresh_token, token_expires_at, status, auto_reply_enabled)
               VALUES (?, 'google', 'inativo@gmail.com', ?, ?, ?, 'connected', 1)
               ON CONFLICT(user_id) DO UPDATE SET
                 access_token=excluded.access_token,
                 refresh_token=excluded.refresh_token,
                 token_expires_at=excluded.token_expires_at,
                 status='connected',
                 auto_reply_enabled=1""",
            (user_id, encrypt_token("access"), encrypt_token("refresh"), str(time.time() + 3600)),
        )
        integration = dict(c.execute("SELECT * FROM email_integrations WHERE user_id = ?", (user_id,)).fetchone())

    with pytest.raises(EmailTokenExpiredError):
        await refresh_google_token_if_needed(integration)

    with connect() as c:
        row = dict(c.execute("SELECT status, auto_reply_enabled FROM email_integrations WHERE user_id = ?", (user_id,)).fetchone())
    assert row["status"] == "needs_reconnect"
    assert row["auto_reply_enabled"] == 0

    dash_res = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert dash_res.status_code == 200
    assert dash_res.json()["email_needs_reconnect"] is True


def test_user_entering_after_8_days_triggers_freeze_on_dashboard(auth_client):
    client, token, user_id = auth_client
    stale_active = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    with connect() as c:
        c.execute("UPDATE users SET last_active_at = ? WHERE id = ?", (stale_active, user_id))
        c.execute(
            """INSERT INTO email_integrations
               (user_id, provider, email_address, status, auto_reply_enabled)
               VALUES (?, 'google', 'retorno@gmail.com', 'connected', 1)
               ON CONFLICT(user_id) DO UPDATE SET status='connected', auto_reply_enabled=1""",
            (user_id,),
        )

    dash_res = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert dash_res.status_code == 200
    assert dash_res.json()["email_needs_reconnect"] is True

    status_res = client.get("/api/email/status", headers={"Authorization": f"Bearer {token}"})
    assert status_res.status_code == 200
    assert status_res.json()["needs_reconnect"] is True


def test_google_oauth_callback_redirects_to_frontend_origin_not_8000(auth_client):
    client, token, user_id = auth_client
    res_url = client.get(
        "/api/email/oauth/google/url",
        params={"frontend_url": "http://localhost:5173"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_url.status_code == 200
    google_url = res_url.json()["url"]
    parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(google_url).query)
    state_token = parsed_qs["state"][0]

    with patch("backend.routers.email.exchange_google_code", new_callable=AsyncMock) as mock_exch, \
         patch("backend.routers.email.fetch_google_user_profile", new_callable=AsyncMock) as mock_profile:
        mock_exch.return_value = {
            "access_token": "ya29.test_access",
            "refresh_token": "1//test_refresh",
            "expires_in": 3600,
        }
        mock_profile.return_value = ("loja@gmail.com", "Loja")

        res_callback = client.get(
            "/api/email/oauth/google/callback",
            params={"code": "4/0AeanS0_test", "state": state_token},
            follow_redirects=False,
        )
        assert res_callback.status_code in (302, 307)
        location = res_callback.headers["location"]
        assert location.startswith("http://localhost:5173/?email_auth=success&provider=google")
        assert ":8000" not in location


def test_dashboard_html_contains_frozen_account_banner():
    html = (Path(__file__).parent.parent / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'id="dashboard-email-frozen-banner"' in html
    assert 'id="btn-dash-reconnect-gmail"' in html
