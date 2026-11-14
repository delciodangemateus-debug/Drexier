import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from backend.main import app
from backend.database import connect, init_db
from backend.auth import create_token
from backend.services.billing_service import _save_stored_subscription
from backend.services.email_service import (
    capture_scheduled_request,
    clean_email_body,
    extract_scheduled_at,
    get_email_response_cutoff,
    parse_sender_info,
    create_mime_message,
    process_and_reply_email,
    process_confirmation_action,
    send_ai_booking_reminder,
    send_email,
    sync_google_emails,
    sync_emails_for_user,
)
from tests.auth_helpers import signup_and_verify


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_email.db"
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
        "email": "carlos@empresa.com",
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


def test_extract_scheduled_at_requires_future_date_and_time():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime(2026, 11, 5, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
    assert extract_scheduled_at("Amanhã às 14h", now) == "2026-11-06T14:00:00+00:00"
    assert extract_scheduled_at("Dia 6 de novembro às 14h30", now) == "2026-11-06T14:30:00+00:00"
    assert extract_scheduled_at("Amanhã", now) is None
    assert extract_scheduled_at("Hoje às 09h", now) is None


@pytest.mark.anyio
async def test_failed_email_reply_is_not_recorded_as_sent(auth_client):
    _, _, user_id = auth_client
    with patch(
        "backend.services.email_service.draft_reply",
        new_callable=AsyncMock,
        return_value="Resposta gerada pela IA",
    ), patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        side_effect=RuntimeError("provider unavailable"),
    ):
        with pytest.raises(RuntimeError, match="provider unavailable"):
            await process_and_reply_email(
                user_dict={"id": user_id, "name": "Carlos Atendimento"},
                integration={
                    "provider": "google",
                    "email_address": "empresa@gmail.com",
                    "auto_reply_enabled": 1,
                },
                customer_email="cliente@example.com",
                customer_name="Cliente",
                subject="Dúvida",
                incoming_content="Qual é o preço?",
                thread_id="gmail-thread",
                message_id_header="<customer-message@example.com>",
            )

    with connect() as c:
        messages = c.execute(
            "SELECT sender, content FROM messages WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    assert [(row["sender"], row["content"]) for row in messages] == [
        ("customer", "Assunto: Dúvida\n\nQual é o preço?")
    ]


@pytest.mark.anyio
async def test_failed_email_reply_is_retried_after_provider_recovers(auth_client):
    _, _, user_id = auth_client
    with patch(
        "backend.services.email_service.draft_reply",
        new_callable=AsyncMock,
        return_value="Resposta enviada após nova tentativa.",
    ), patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        side_effect=[RuntimeError("provider unavailable"), {"status": "sent"}],
    ) as mock_send:
        message = {
            "user_dict": {"id": user_id, "name": "Carlos Atendimento"},
            "integration": {
                "provider": "google",
                "email_address": "empresa@gmail.com",
                "auto_reply_enabled": 1,
            },
            "customer_email": "cliente@example.com",
            "customer_name": "Cliente",
            "subject": "Dúvida",
            "incoming_content": "Qual é o preço?",
            "thread_id": "gmail-thread",
            "message_id_header": "<customer-message@example.com>",
        }

        with pytest.raises(RuntimeError, match="provider unavailable"):
            await process_and_reply_email(**message)

        reply = await process_and_reply_email(**message)

    assert reply == "Resposta enviada após nova tentativa."
    assert mock_send.await_count == 2
    mock_send.assert_awaited_with(
        integration=message["integration"],
        to_email="cliente@example.com",
        subject="Re: Dúvida",
        body_text="Resposta enviada após nova tentativa.",
        thread_id="gmail-thread",
        in_reply_to="<customer-message@example.com>",
        references="<customer-message@example.com>",
    )


@pytest.mark.anyio
async def test_semi_automation_replies_while_request_awaits_owner_confirmation(auth_client):
    _, _, user_id = auth_client
    with connect() as c:
        contact_id = c.execute(
            "INSERT INTO contacts(user_id, name, contact_key) VALUES (?, 'Cliente', 'cliente@example.com')",
            (user_id,),
        ).lastrowid
        c.execute(
            "INSERT INTO email_integrations(user_id, provider, email_address, status) VALUES (?, 'google', 'empresa@gmail.com', 'connected')",
            (user_id,),
        )

    with patch(
        "backend.services.email_service.draft_reply",
        new_callable=AsyncMock,
        return_value="Qual data e hora prefere para a marcação?",
    ) as mock_draft, patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        return_value={"status": "sent"},
    ) as mock_send:
        reply = await process_and_reply_email(
            user_dict={
                "id": user_id,
                "name": "Carlos Atendimento",
                "business_type": "Serviços",
                "mandatory_responses": "{}",
            },
            integration={
                "provider": "google",
                "email_address": "empresa@gmail.com",
                "auto_reply_enabled": 1,
            },
            customer_email="cliente@example.com",
            customer_name="Cliente",
            subject="Marcação",
            incoming_content="Gostaria de marcar uma consulta amanhã.",
            thread_id="gmail-thread",
            message_id_header="<customer-message@example.com>",
        )

    assert reply == "Qual data e hora prefere para a marcação?"
    assert "Pergunte de forma cordial qual é a data e a hora pretendidas" in mock_draft.await_args.kwargs["message"]
    mock_send.assert_awaited_once()
    with connect() as c:
        request = c.execute(
            "SELECT status, scheduled_at FROM conversion_requests WHERE user_id = ? AND contact_id = ?",
            (user_id, contact_id),
        ).fetchone()
    assert request["status"] == "awaiting_schedule"
    assert request["scheduled_at"] is None


@pytest.mark.anyio
async def test_email_followup_records_requested_date_and_time(auth_client):
    _, _, user_id = auth_client
    with patch(
        "backend.services.email_service.draft_reply",
        new_callable=AsyncMock,
        side_effect=[
            "Qual data e hora prefere?",
            "Registei a sua preferência e vou encaminhar para confirmação.",
        ],
    ), patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        return_value={"status": "sent"},
    ):
        params = {
            "user_dict": {
                "id": user_id,
                "name": "Carlos Atendimento",
                "business_type": "Serviços",
                "mandatory_responses": "{}",
            },
            "integration": {
                "provider": "google",
                "email_address": "empresa@gmail.com",
                "auto_reply_enabled": 1,
            },
            "customer_email": "cliente@example.com",
            "customer_name": "Cliente",
            "subject": "Marcação de consulta",
            "thread_id": "gmail-thread",
            "message_id_header": "<customer-message@example.com>",
        }
        await process_and_reply_email(
            **params,
            incoming_content="Gostaria de marcar uma consulta.",
        )
        await process_and_reply_email(
            **params,
            incoming_content="Amanhã às 14h.",
        )

    with connect() as c:
        request = c.execute(
            "SELECT status, scheduled_at, details FROM conversion_requests WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    assert request["status"] == "pending"
    assert request["scheduled_at"] == extract_scheduled_at("Amanhã às 14h.")
    assert "Data e hora escolhidas pelo cliente" in request["details"]


@pytest.mark.anyio
async def test_ai_reminder_uses_context_and_sends_email(auth_client):
    _, _, user_id = auth_client
    scheduled_at = extract_scheduled_at("Amanhã às 14h")
    with connect() as c:
        contact_id = c.execute(
            "INSERT INTO contacts(user_id, name, contact_key) VALUES (?, 'Ana Cliente', 'ana@example.com')",
            (user_id,),
        ).lastrowid
        request_id = c.execute(
            """INSERT INTO conversion_requests
               (user_id, contact_id, request_type, details, status, scheduled_at)
               VALUES (?, ?, 'booking', 'Consulta de fisioterapia', 'confirmed', ?)""",
            (user_id, contact_id, scheduled_at),
        ).lastrowid
        c.execute(
            "INSERT INTO email_integrations(user_id, provider, email_address, status) VALUES (?, 'google', 'empresa@gmail.com', 'connected')",
            (user_id,),
        )

    with patch(
        "backend.services.email_service.draft_reply",
        new_callable=AsyncMock,
        return_value="Olá Ana, lembramos da sua consulta amanhã às 14h.",
    ) as mock_draft, patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        return_value={"status": "sent"},
    ) as mock_send:
        result = await send_ai_booking_reminder(user_id, request_id)

    assert result["ok"] is True
    assert result["channel"] == "email"
    assert "Consulta de fisioterapia" in mock_draft.await_args.kwargs["message"]
    assert "amanhã" in mock_draft.await_args.kwargs["message"]
    mock_send.assert_awaited_once()
    with connect() as c:
        message = c.execute(
            "SELECT sender, content FROM messages WHERE contact_id = ?",
            (contact_id,),
        ).fetchone()
    assert message["sender"] == "agent"
    assert message["content"] == "Olá Ana, lembramos da sua consulta amanhã às 14h."


@pytest.mark.anyio
async def test_ai_reminder_rejects_phone_contact_without_email(auth_client):
    _, _, user_id = auth_client
    with connect() as c:
        contact_id = c.execute(
            "INSERT INTO contacts(user_id, name, contact_key) VALUES (?, 'João Cliente', '351911111111')",
            (user_id,),
        ).lastrowid
        request_id = c.execute(
            """INSERT INTO conversion_requests
               (user_id, contact_id, request_type, details, status, scheduled_at)
               VALUES (?, ?, 'booking', 'Consulta', 'pending', ?)""",
            (user_id, contact_id, extract_scheduled_at("Amanhã às 14h")),
        ).lastrowid

    with pytest.raises(ValueError, match="não tem um endereço de e-mail"):
        await send_ai_booking_reminder(user_id, request_id)


@pytest.mark.anyio
async def test_full_automation_retries_failed_confirmation_email(auth_client):
    _, _, user_id = auth_client
    with patch(
        "backend.services.email_service.check_business_availability",
        return_value={"available": True},
    ), patch(
        "backend.services.email_service.draft_reply",
        new_callable=AsyncMock,
        return_value="A sua marcação foi confirmada.",
    ), patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        side_effect=[RuntimeError("provider unavailable"), {"status": "sent"}],
    ) as mock_send:
        message = {
            "user_dict": {
                "id": user_id,
                "name": "Carlos Atendimento",
                "business_type": "Serviços",
                "mandatory_responses": '{"automation_level":"full"}',
            },
            "integration": {
                "provider": "google",
                "email_address": "empresa@gmail.com",
                "auto_reply_enabled": 1,
            },
            "customer_email": "cliente@example.com",
            "customer_name": "Cliente",
            "subject": "Marcação",
            "incoming_content": "Gostaria de marcar uma consulta amanhã às 14h.",
            "thread_id": "gmail-thread",
            "message_id_header": "<customer-message@example.com>",
        }

        with pytest.raises(RuntimeError, match="provider unavailable"):
            await process_and_reply_email(**message)
        reply = await process_and_reply_email(**message)

    assert "confirmada automaticamente" in reply
    assert mock_send.await_count == 2
    with connect() as c:
        conversions = c.execute(
            "SELECT status FROM conversion_requests WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        agent_messages = c.execute(
            "SELECT content FROM messages WHERE user_id = ? AND sender = 'agent'",
            (user_id,),
        ).fetchall()
    assert [row["status"] for row in conversions] == ["confirmed"]
    assert [row["content"] for row in agent_messages] == ["A sua marcação foi confirmada."]


@pytest.mark.anyio
async def test_confirmation_email_failure_keeps_request_pending(auth_client):
    _, _, user_id = auth_client
    with connect() as c:
        contact_id = c.execute(
            "INSERT INTO contacts(user_id, name, contact_key) VALUES (?, 'Cliente', 'cliente@example.com')",
            (user_id,),
        ).lastrowid
        request_id = c.execute(
            """INSERT INTO conversion_requests
               (user_id, contact_id, request_type, details)
               VALUES (?, ?, 'purchase', 'Produto X para amanhã às 14h')""",
            (user_id, contact_id),
        ).lastrowid
        c.execute(
            "INSERT INTO email_integrations(user_id, provider, email_address, status) VALUES (?, 'google', 'empresa@gmail.com', 'connected')",
            (user_id,),
        )

    with patch(
        "backend.services.email_service.draft_reply",
        new_callable=AsyncMock,
        return_value="O seu pedido foi confirmado.",
    ), patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        side_effect=RuntimeError("provider unavailable"),
    ):
        with pytest.raises(RuntimeError, match="provider unavailable"):
            await process_confirmation_action(user_id, request_id, "confirm")

    with connect() as c:
        request = c.execute(
            "SELECT status FROM conversion_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        messages = c.execute(
            "SELECT sender FROM messages WHERE contact_id = ?",
            (contact_id,),
        ).fetchall()
    assert request["status"] == "pending"
    assert messages == []


@pytest.mark.anyio
async def test_confirmation_email_replies_in_thread_before_marking_confirmed(auth_client):
    _, _, user_id = auth_client
    with connect() as c:
        contact_id = c.execute(
            "INSERT INTO contacts(user_id, name, contact_key) VALUES (?, 'Cliente', 'cliente@example.com')",
            (user_id,),
        ).lastrowid
        request_id = c.execute(
            """INSERT INTO conversion_requests
               (user_id, contact_id, request_type, details)
               VALUES (?, ?, 'purchase', 'Produto X para amanhã às 14h')""",
            (user_id, contact_id),
        ).lastrowid
        c.execute(
            "INSERT INTO email_integrations(user_id, provider, email_address, status) VALUES (?, 'google', 'empresa@gmail.com', 'connected')",
            (user_id,),
        )
        c.execute(
            """INSERT INTO email_threads(user_id, contact_id, provider, thread_id, last_message_id, subject)
               VALUES (?, ?, 'google', 'gmail-thread', '<customer-message@example.com>', 'Pedido do cliente')""",
            (user_id, contact_id),
        )

    async def send_email_while_pending(**kwargs):
        with connect() as c:
            request = c.execute(
                "SELECT status FROM conversion_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
            messages = c.execute(
                "SELECT sender FROM messages WHERE contact_id = ?",
                (contact_id,),
            ).fetchall()
        assert request["status"] == "pending"
        assert messages == []
        return {"status": "sent"}

    with patch(
        "backend.services.email_service.draft_reply",
        new_callable=AsyncMock,
        return_value="O seu pedido foi confirmado.",
    ), patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        side_effect=send_email_while_pending,
    ) as mock_send:
        result = await process_confirmation_action(user_id, request_id, "confirm")

    assert result["ok"] is True
    mock_send.assert_awaited_once_with(
        integration=mock_send.await_args.kwargs["integration"],
        to_email="cliente@example.com",
        subject="Re: Pedido do cliente",
        body_text="O seu pedido foi confirmado.",
        thread_id="gmail-thread",
        in_reply_to="<customer-message@example.com>",
        references="<customer-message@example.com>",
    )
    with connect() as c:
        request = c.execute(
            "SELECT status FROM conversion_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        message = c.execute(
            "SELECT sender, content FROM messages WHERE contact_id = ?",
            (contact_id,),
        ).fetchone()
    assert request["status"] == "confirmed"
    assert message["sender"] == "agent"
    assert message["content"] == "O seu pedido foi confirmado."


def test_email_response_cutoff_starts_after_payment_and_connection():
    integration = {
        "last_successful_payment_at": "2026-10-10T12:00:00+00:00",
        "created_at": "2026-10-09 12:00:00",
    }
    assert get_email_response_cutoff(integration).isoformat() == "2026-10-10T12:00:00+00:00"

    integration["created_at"] = "2026-10-11 12:00:00"
    assert get_email_response_cutoff(integration).isoformat() == "2026-10-11T12:00:00+00:00"
    assert get_email_response_cutoff({"created_at": "2026-10-09 12:00:00"}) is None


def test_email_public_config(auth_client):
    client, _, _ = auth_client
    res = client.get("/api/email/config")
    assert res.status_code == 200
    data = res.json()
    assert set(data) == {"google"}
    assert data["google"]["configured"] is True


def test_email_status_when_disconnected(auth_client):
    client, token, _ = auth_client
    res = client.get("/api/email/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["connected"] is False
    assert data["integration"] is None


def test_email_status_exposes_paid_response_start(auth_client):
    client, token, user_id = auth_client
    with connect() as c:
        c.execute(
            """INSERT INTO email_integrations
               (user_id, provider, email_address, display_name, access_token, status, created_at)
               VALUES (?, 'google', 'empresa@gmail.com', 'Empresa Silva', 'ya29_token', 'connected', ?)""",
            (user_id, "2026-10-01 09:00:00"),
        )
    _save_stored_subscription(user_id, {
        "status": "active",
        "last_successful_payment_at": "2026-10-15T10:00:00+00:00",
    })

    res = client.get("/api/email/status", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    assert res.json()["integration"]["response_since_at"] == "2026-10-15T10:00:00+00:00"


def test_non_gmail_email_routes_are_not_exposed(auth_client):
    client, token, user_id = auth_client
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/email/connect-manual", json={}, headers=headers).status_code == 404
    assert client.get("/api/email/oauth/microsoft/url", headers=headers).status_code == 404


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
    _save_stored_subscription(user_id, {
        "status": "active",
        "last_successful_payment_at": "2026-10-01T10:00:00+00:00",
    })

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


@pytest.mark.anyio
async def test_email_sync_does_not_run_without_successful_payment(auth_client):
    client, token, user_id = auth_client
    with connect() as c:
        c.execute(
            """INSERT INTO email_integrations (user_id, provider, email_address, display_name, access_token, status)
               VALUES (?, 'google', 'empresa@gmail.com', 'Empresa Silva', 'ya29_token', 'connected')""",
            (user_id,),
        )

    with patch("backend.services.email_service.sync_google_emails", new_callable=AsyncMock) as mock_sync:
        assert await sync_emails_for_user(user_id) == []
        mock_sync.assert_not_awaited()


@pytest.mark.anyio
async def test_gmail_list_failure_is_reported_instead_of_successful_empty_sync():
    response = type("Response", (), {"status_code": 503, "text": "temporary provider error"})()

    with patch(
        "backend.services.email_service.refresh_google_token_if_needed",
        new_callable=AsyncMock,
        return_value="access-token",
    ), patch(
        "backend.services.email_service.httpx.AsyncClient.get",
        new_callable=AsyncMock,
        return_value=response,
    ):
        with pytest.raises(RuntimeError, match="HTTP 503"):
            await sync_google_emails(
                {"id": 7, "email": "owner@example.com"},
                {
                    "id": 11,
                    "user_id": 7,
                    "provider": "google",
                    "email_address": "owner@gmail.com",
                    "last_successful_payment_at": "2026-10-01T10:00:00+00:00",
                    "created_at": "2026-10-01T10:00:00+00:00",
                },
            )


@pytest.mark.anyio
async def test_failed_gmail_sync_does_not_advance_last_sync_at(auth_client):
    _, _, user_id = auth_client
    with connect() as c:
        integration_id = c.execute(
            """INSERT INTO email_integrations
               (user_id, provider, email_address, status)
               VALUES (?, 'google', 'empresa@gmail.com', 'connected')""",
            (user_id,),
        ).lastrowid
    _save_stored_subscription(user_id, {
        "status": "active",
        "last_successful_payment_at": "2026-10-01T10:00:00+00:00",
    })

    with patch(
        "backend.services.email_service.sync_google_emails",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Gmail indisponível"),
    ):
        with pytest.raises(RuntimeError, match="Gmail indisponível"):
            await sync_emails_for_user(user_id)

    with connect() as c:
        row = c.execute(
            "SELECT last_sync_at FROM email_integrations WHERE id = ?",
            (integration_id,),
        ).fetchone()
    assert row["last_sync_at"] is None


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


@pytest.mark.anyio
async def test_duplicate_email_is_never_replied_twice(auth_client):
    """
    Garante que uma mensagem idêntica recebida repetidamente pelo cliente
    só é respondida uma única vez pelo agente, evitando loops e envios repetidos.
    """
    _, _, user_id = auth_client
    with patch(
        "backend.services.email_service.draft_reply",
        new_callable=AsyncMock,
        return_value="Olá! Como posso ajudar?",
    ) as mock_draft, patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        return_value={"status": "sent"},
    ) as mock_send:
        msg = {
            "user_dict": {"id": user_id, "name": "Drexier Business"},
            "integration": {
                "provider": "google",
                "email_address": "empresa@gmail.com",
                "auto_reply_enabled": 1,
            },
            "customer_email": "cliente.repetido@example.com",
            "customer_name": "Cliente Repetido",
            "subject": "Informações de Serviços",
            "incoming_content": "Quais são os serviços disponíveis?",
            "thread_id": "thread-123",
            "message_id_header": "<msg-unique-123@example.com>",
        }

        # Primeiro envio: deve gerar resposta e enviar email
        reply1 = await process_and_reply_email(**msg)
        assert reply1 == "Olá! Como posso ajudar?"
        assert mock_send.await_count == 1
        assert mock_draft.await_count == 1

        # Segundo envio idêntico (lag ou repetição): deve detectar duplicado e NÃO enviar novamente
        reply2 = await process_and_reply_email(**msg)
        assert reply2 == "Olá! Como posso ajudar?"
        assert mock_send.await_count == 1  # Mantém 1, não incrementou!
        assert mock_draft.await_count == 1  # Não gastou chamada de IA!

    with connect() as c:
        agent_msgs = c.execute(
            "SELECT count(*) as total FROM messages WHERE user_id = ? AND sender = 'agent'",
            (user_id,),
        ).fetchone()["total"]
        customer_msgs = c.execute(
            "SELECT count(*) as total FROM messages WHERE user_id = ? AND sender = 'customer'",
            (user_id,),
        ).fetchone()["total"]

    assert agent_msgs == 1
    assert customer_msgs == 1


def test_natural_language_booking_time_extraction():
    """
    Garante flexibilidade na extração de datas e horas em linguagem natural portuguesa.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime(2026, 11, 5, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
    
    # Horas numéricas
    assert extract_scheduled_at("amanhã às 14h", now) == "2026-11-06T14:00:00+00:00"
    assert extract_scheduled_at("amanhã às 14:30", now) == "2026-11-06T14:30:00+00:00"
    assert extract_scheduled_at("dia 10 de novembro às 11h", now) == "2026-11-10T11:00:00+00:00"

    # Períodos naturais do dia
    assert extract_scheduled_at("amanhã de tarde", now) == "2026-11-06T15:00:00+00:00"
    assert extract_scheduled_at("amanhã de manhã", now) == "2026-11-06T09:00:00+00:00"
    assert extract_scheduled_at("depois de amanhã às 11h", now) == "2026-11-07T11:00:00+00:00"

    # Sem hora -> Deve retornar None para que o agente pergunte o horário pretendido
    assert extract_scheduled_at("amanhã", now) is None
    assert extract_scheduled_at("próxima terça", now) is None


@pytest.mark.anyio
async def test_email_from_user_account_email_is_processed(auth_client):
    """
    Garante que mensagens enviadas pelo e-mail de login da conta (ex: proprietário testando)
    para o e-mail oficial integrado da empresa NÃO são bloqueadas pelo anti-loop.
    Apenas mensagens originadas pelo próprio endereço oficial integrado devem ser ignoradas.
    """
    _, _, user_id = auth_client
    with patch(
        "backend.services.email_service.draft_reply",
        new_callable=AsyncMock,
        return_value="Olá! Sim, temos viaturas disponíveis nessa faixa.",
    ) as mock_draft, patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        return_value={"status": "sent"},
    ) as mock_send:
        msg = {
            "user_dict": {"id": user_id, "name": "Autos Del", "email": "dono@gmail.com"},
            "integration": {
                "provider": "google",
                "email_address": "empresa@gmail.com",
                "auto_reply_enabled": 1,
            },
            "customer_email": "dono@gmail.com",
            "customer_name": "Karim / Dono",
            "subject": "Informação sobre viaturas",
            "incoming_content": "Gostaria de saber se tem alguma viatura de 15 a 20 mil euros?",
            "thread_id": "thread-karim-001",
            "message_id_header": "<karim-test-001@example.com>",
        }

        reply = await process_and_reply_email(**msg)
        assert reply == "Olá! Sim, temos viaturas disponíveis nessa faixa."
        assert mock_send.await_count == 1
        assert mock_draft.await_count == 1


