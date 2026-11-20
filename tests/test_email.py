import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from backend.main import app
from backend.database import connect, init_db
from backend.auth import create_token
from backend.services.billing_service import _save_stored_subscription
from backend.services.email_service import (
    BUSINESS_TIMEZONE,
    _parse_utc_datetime,
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
    assert mock_draft.await_args.kwargs["message"] == "Gostaria de marcar uma consulta amanhã."
    assert "Há um pedido anterior do cliente aguardando data e hora" in mock_draft.await_args.kwargs["instructions"]
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
    ) as mock_draft, patch(
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
            incoming_content="Gostaria de marcar uma consulta para 22/12/2099.",
        )
        await process_and_reply_email(
            **params,
            incoming_content="Às 14h.",
        )

    assert [call.kwargs["message"] for call in mock_draft.await_args_list] == [
        "Gostaria de marcar uma consulta para 22/12/2099.",
        "Às 14h.",
    ]

    with connect() as c:
        request = c.execute(
            "SELECT status, scheduled_at, details FROM conversion_requests WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    assert request["status"] == "pending"
    assert request["scheduled_at"] == "2099-12-22T14:00:00+00:00"
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
    mock_draft.assert_not_awaited()
    mock_send.assert_awaited_once()
    sent_body = mock_send.await_args.kwargs["body_text"]
    assert "Consulta de fisioterapia" in sent_body
    assert "marcado para" in sent_body
    with connect() as c:
        message = c.execute(
            "SELECT sender, content FROM messages WHERE contact_id = ?",
            (contact_id,),
        ).fetchone()
    assert message["sender"] == "agent"
    assert message["content"] == sent_body


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
               VALUES (?, ?, 'booking', 'Consulta', 'confirmed', ?)""",
            (user_id, contact_id, extract_scheduled_at("Amanhã às 14h")),
        ).lastrowid

    with pytest.raises(ValueError, match="não tem um endereço de e-mail"):
        await send_ai_booking_reminder(user_id, request_id)


@pytest.mark.anyio
async def test_ai_reminder_rejects_unvalidated_request(auth_client):
    _, _, user_id = auth_client
    with connect() as c:
        contact_id = c.execute(
            "INSERT INTO contacts(user_id, name, contact_key) VALUES (?, 'Cliente', 'cliente@example.com')",
            (user_id,),
        ).lastrowid
        request_id = c.execute(
            """INSERT INTO conversion_requests
               (user_id, contact_id, request_type, details, status, scheduled_at)
               VALUES (?, ?, 'booking', 'Consulta', 'pending', ?)""",
            (user_id, contact_id, extract_scheduled_at("Amanhã às 14h")),
        ).lastrowid

    with pytest.raises(ValueError, match="marcações já validadas"):
        await send_ai_booking_reminder(user_id, request_id)


@pytest.mark.anyio
async def test_full_automation_asks_client_before_confirming_booking(auth_client):
    _, _, user_id = auth_client
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

    with patch(
        "backend.services.email_service.check_business_availability",
        return_value={"available": True},
    ), patch(
        "backend.services.email_service.draft_reply",
        new_callable=AsyncMock,
        return_value="A sua marcação foi confirmada.",
    ) as mock_draft, patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        side_effect=[RuntimeError("provider unavailable"), {"status": "sent"}, {"status": "sent"}],
    ) as mock_send:
        with pytest.raises(RuntimeError, match="provider unavailable"):
            await process_and_reply_email(**message)

        reply = await process_and_reply_email(**message)
        assert "Confirmação da marcação solicitada" in reply
        with connect() as c:
            status = c.execute(
                "SELECT status FROM conversion_requests WHERE user_id = ?", (user_id,)
            ).fetchone()["status"]
        assert status == "awaiting_client_confirmation"

        reply = await process_and_reply_email(
            **{**message, "incoming_content": "Sim, confirmo a marcação."}
        )

    assert "confirmada pelo cliente" in reply
    mock_draft.assert_not_awaited()
    assert mock_send.await_count == 3
    bodies = [call.kwargs["body_text"] for call in mock_send.await_args_list]
    assert "Deseja prosseguir e confirmar a marcação?" in bodies[1]
    assert "O seu pedido foi confirmado." in bodies[2]
    with connect() as c:
        conversions = c.execute(
            "SELECT status, scheduled_at FROM conversion_requests WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        agent_messages = c.execute(
            "SELECT content FROM messages WHERE user_id = ? AND sender = 'agent'",
            (user_id,),
        ).fetchall()
    assert len(conversions) == 1
    assert conversions[0]["status"] == "confirmed"
    assert conversions[0]["scheduled_at"] is not None
    assert len(agent_messages) == 2
    assert "O seu pedido foi confirmado." in agent_messages[1]["content"]
    assert "Nome registado:" in agent_messages[1]["content"]


@pytest.mark.anyio
async def test_semi_automation_does_not_ask_client_confirmation(auth_client):
    _, _, user_id = auth_client
    message = {
        "user_dict": {
            "id": user_id,
            "name": "Carlos Atendimento",
            "business_type": "Serviços",
            "mandatory_responses": '{"automation_level":"semi"}',
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

    with patch(
        "backend.services.email_service.check_business_availability",
        return_value={"available": True},
    ), patch(
        "backend.services.email_service.draft_reply",
        new_callable=AsyncMock,
        return_value="Recebemos o seu pedido e aguardamos validação.",
    ), patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        return_value={"status": "sent"},
    ) as mock_send:
        await process_and_reply_email(**message)

    body = mock_send.await_args.kwargs["body_text"]
    assert "Deseja prosseguir e confirmar a marcação?" not in body
    with connect() as c:
        status = c.execute(
            "SELECT status FROM conversion_requests WHERE user_id = ?", (user_id,)
        ).fetchone()["status"]
    assert status == "pending"


@pytest.mark.anyio
async def test_full_automation_confirmation_adds_booking_to_week_board(auth_client):
    from backend.main import _dashboard_cache

    client, token, user_id = auth_client
    params = {
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
        "thread_id": "gmail-thread",
        "message_id_header": "<customer-message@example.com>",
    }

    with patch(
        "backend.services.email_service.check_business_availability",
        return_value={"available": True},
    ), patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        return_value={"status": "sent"},
    ):
        await process_and_reply_email(
            **{**params, "incoming_content": "Quero marcar para sexta-feira às 13 horas."}
        )
        await process_and_reply_email(
            **{**params, "incoming_content": "Combinado, pode confirmar."}
        )

    _dashboard_cache.clear()
    response = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    bookings = [
        booking for booking in response.json()["confirmed_bookings"]
        if booking["contact_key"] == "cliente@example.com"
    ]
    assert len(bookings) == 1
    assert bookings[0]["status"] == "confirmed"
    assert bookings[0]["scheduled_at"] is not None


@pytest.mark.anyio
async def test_full_automation_uses_date_from_subject_and_shows_confirmed_booking(auth_client):
    client, token, user_id = auth_client
    params = _full_automation_params(user_id)

    with patch(
        "backend.services.email_service.check_business_availability",
        return_value={"available": True},
    ), patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        return_value={"status": "sent"},
    ) as mock_send:
        await process_and_reply_email(**{
            **params,
            "subject": "Marcação quinta às 16h",
            "incoming_content": "Olá, gostaria de marcar uma consulta.",
        })
        confirmation_body = mock_send.await_args.kwargs["body_text"]
        assert "Deseja prosseguir e confirmar a marcação?" in confirmation_body
        assert "qual é a data" not in confirmation_body.lower()

        reply = await process_and_reply_email(**{**params, "incoming_content": "Sim, confirmo."})

    assert "confirmada pelo cliente" in reply
    with connect() as c:
        row = c.execute(
            "SELECT status, scheduled_at FROM conversion_requests WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    assert row["status"] == "confirmed"
    assert row["scheduled_at"] is not None

    response = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    bookings = [
        booking for booking in response.json()["confirmed_bookings"]
        if booking["contact_key"] == "cliente@example.com"
    ]
    assert len(bookings) == 1
    assert bookings[0]["scheduled_at"] == row["scheduled_at"]


def test_missing_schedule_question_only_asks_for_the_missing_field():
    from backend.services.email_service import ensure_date_time_question

    date_only = ensure_date_time_question("A sua marcação está registada.", need_date=False, need_time=True)
    assert "qual é a hora que prefere" in date_only
    assert "qual é a data" not in date_only

    time_only = ensure_date_time_question("A sua marcação está registada.", need_date=True, need_time=False)
    assert "qual é a data que prefere" in time_only
    assert "qual é a hora" not in time_only


def _full_automation_params(user_id):
    return {
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
        "thread_id": "gmail-thread",
        "message_id_header": "<customer-message@example.com>",
    }


@pytest.mark.anyio
async def test_confirmation_is_consumed_after_automation_level_changes(auth_client):
    _, _, user_id = auth_client
    params = _full_automation_params(user_id)

    with patch(
        "backend.services.email_service.check_business_availability",
        return_value={"available": True},
    ), patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        return_value={"status": "sent"},
    ):
        await process_and_reply_email(
            **{**params, "incoming_content": "Quero marcar para quinta feira às 15h."}
        )
        params["user_dict"]["mandatory_responses"] = '{"automation_level":"semi"}'
        reply = await process_and_reply_email(
            **{**params, "incoming_content": "Pode ser."}
        )

    assert "confirmada pelo cliente" in reply
    with connect() as c:
        status = c.execute(
            "SELECT status FROM conversion_requests WHERE user_id = ?", (user_id,)
        ).fetchone()["status"]
    assert status == "confirmed"


@pytest.mark.anyio
async def test_confirmation_reply_updates_schedule_before_confirming(auth_client):
    _, _, user_id = auth_client
    params = _full_automation_params(user_id)

    with patch(
        "backend.services.email_service.check_business_availability",
        return_value={"available": True},
    ), patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        return_value={"status": "sent"},
    ) as mock_send:
        await process_and_reply_email(
            **{**params, "incoming_content": "Quero marcar para quinta feira às 15h."}
        )
        await process_and_reply_email(
            **{**params, "incoming_content": "Sim, mas quinta feira às 16h."}
        )

    with connect() as c:
        scheduled_at = c.execute(
            "SELECT scheduled_at FROM conversion_requests WHERE user_id = ?", (user_id,)
        ).fetchone()["scheduled_at"]
    confirmed_body = mock_send.await_args.kwargs["body_text"]
    assert "16:00" in confirmed_body
    assert _parse_utc_datetime(scheduled_at).astimezone(BUSINESS_TIMEZONE).hour == 16


@pytest.mark.anyio
async def test_time_only_reply_does_not_repeat_confirmation_question(auth_client):
    _, _, user_id = auth_client
    params = _full_automation_params(user_id)

    with patch(
        "backend.services.email_service.check_business_availability",
        return_value={"available": True},
    ), patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        return_value={"status": "sent"},
    ) as mock_send:
        await process_and_reply_email(
            **{**params, "incoming_content": "Quero marcar para quinta feira às 15h."}
        )
        await process_and_reply_email(**{**params, "incoming_content": "Às 16h."})
        reply = await process_and_reply_email(**{**params, "incoming_content": "Sim"})

    assert "confirmada pelo cliente" in reply
    bodies = [call.kwargs["body_text"] for call in mock_send.await_args_list]
    assert "16:00" in bodies[-1]
    with connect() as c:
        status = c.execute(
            "SELECT status FROM conversion_requests WHERE user_id = ?", (user_id,)
        ).fetchone()["status"]
    assert status == "confirmed"


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
    ) as mock_draft, patch(
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
    mock_draft.assert_not_awaited()


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
        assert request["status"] == "validating"
        assert messages == []
        return {"status": "sent"}

    with patch(
        "backend.services.email_service.draft_reply",
        new_callable=AsyncMock,
        return_value="O seu pedido foi confirmado.",
    ) as mock_draft, patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        side_effect=send_email_while_pending,
    ) as mock_send:
        result = await process_confirmation_action(user_id, request_id, "confirm")

    assert result["ok"] is True
    mock_draft.assert_not_awaited()
    sent_body = mock_send.await_args.kwargs["body_text"]
    assert "Olá, Cliente." in sent_body
    assert "O seu pedido foi confirmado." in sent_body
    assert "Nome registado: Cliente." in sent_body
    mock_send.assert_awaited_once_with(
        integration=mock_send.await_args.kwargs["integration"],
        to_email="cliente@example.com",
        subject="Re: Pedido do cliente",
        body_text=sent_body,
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
    assert "O seu pedido foi confirmado." in message["content"]
    assert "Nome registado: Cliente." in message["content"]


@pytest.mark.anyio
async def test_confirmed_request_cannot_send_a_second_confirmation(auth_client):
    _, _, user_id = auth_client
    with connect() as c:
        contact_id = c.execute(
            "INSERT INTO contacts(user_id, name, contact_key) VALUES (?, 'Cliente', 'cliente@example.com')",
            (user_id,),
        ).lastrowid
        request_id = c.execute(
            """INSERT INTO conversion_requests
               (user_id, contact_id, request_type, details, status, scheduled_at)
               VALUES (?, ?, 'booking', 'Consulta amanhã às 14h', 'pending', ?)""",
            (user_id, contact_id, extract_scheduled_at("Amanhã às 14h")),
        ).lastrowid
        c.execute(
            "INSERT INTO email_integrations(user_id, provider, email_address, status) VALUES (?, 'google', 'empresa@gmail.com', 'connected')",
            (user_id,),
        )

    with patch(
        "backend.services.email_service.draft_reply",
        new_callable=AsyncMock,
        return_value="A sua marcação está confirmada.",
    ) as mock_draft, patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        return_value={"status": "sent"},
    ) as mock_send:
        first_result = await process_confirmation_action(user_id, request_id, "confirm")
        repeated_result = await process_confirmation_action(user_id, request_id, "confirm")

    assert first_result["status"] == "confirmed"
    assert repeated_result["already_confirmed"] is True
    mock_draft.assert_not_awaited()
    mock_send.assert_awaited_once()
    with connect() as c:
        messages = c.execute(
            "SELECT content FROM messages WHERE contact_id = ?",
            (contact_id,),
        ).fetchall()
    assert len(messages) == 1
    assert messages[0]["content"].startswith("Olá, Cliente.\n\nO seu pedido foi confirmado.")
    assert "Nome registado: Cliente." in messages[0]["content"]


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


@pytest.mark.anyio
async def test_purchase_intent_does_not_require_schedule(auth_client):
    from backend.services.email_service import capture_scheduled_request, detect_booking_or_purchase_intent
    _, _, user_id = auth_client
    with connect() as c:
        contact_id = c.execute(
            "INSERT INTO contacts(user_id, name, contact_key) VALUES (?, 'Comprador', 'comprador@example.com')",
            (user_id,)
        ).lastrowid
        intent = detect_booking_or_purchase_intent("Quero comprar 2 unidades do produto.", "Compra")
        assert intent is not None
        assert intent["type"] == "purchase"

        req = capture_scheduled_request(c, user_id, contact_id, "Quero comprar 2 unidades do produto.", "Compra", intent)
        assert req is not None
        assert req["status"] == "pending"
        assert req["request_type"] == "purchase"


def test_ensure_date_time_question_preserves_helpful_reply():
    from backend.services.email_service import ensure_date_time_question

    # Se já tem data e hora, não altera
    has_both = "O nosso agendamento está disponível para a data de amanhã à hora das 15h."
    assert ensure_date_time_question(has_both) == has_both

    # Se não tem, preserva o conteúdo respondido pela IA e anexa a pergunta
    ai_answer = "Sim, temos disponibilidade para consultas de fisioterapia."
    result = ensure_date_time_question(ai_answer)
    assert "Sim, temos disponibilidade para consultas de fisioterapia." in result
    assert "qual é a data e a hora que prefere" in result


def test_extract_scheduled_at_ignores_the_email_sent_time():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime(2026, 11, 17, 15, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
    expected = "2026-11-19T15:00:00+00:00"

    messages = [
        "Quero a marcação para quinta feira as 15 horas",
        "Enviei o email hoje às 10h. Quero a marcação para quinta feira às 15 horas.",
        "Quero a marcação para quinta feira às 15 horas. Enviei o email hoje às 10h.",
        "Data: 17/11/2026 às 10h\nQuero a marcação para quinta feira às 15 horas",
    ]
    for message in messages:
        assert extract_scheduled_at(message, now) == expected

    assert extract_scheduled_at("Quero a marcação para 19/11/2026 às 15h", now) == expected
    assert extract_scheduled_at("Enviei o email hoje às 10h.", now) is None


def test_extract_scheduled_at_ignores_metadata_when_booking_cue_and_time_are_apart():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime(2026, 11, 17, 15, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
    expected = "2026-11-19T15:00:00+00:00"

    assert extract_scheduled_at(
        "Quero marcar. Enviei este email às 10h. Quinta feira às 15h.", now
    ) == expected
    assert extract_scheduled_at(
        "Gostaria de agendar. Enviei o email hoje às 9h, quinta-feira às 15h.", now
    ) == expected


def test_extract_scheduled_at_accepts_a_bare_day_number():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime(2026, 11, 17, 15, 0, tzinfo=ZoneInfo("Europe/Lisbon"))

    assert extract_scheduled_at("Quero marcar para o dia 19 às 14h30.", now) == (
        "2026-11-19T14:30:00+00:00"
    )
    assert extract_scheduled_at("Quero marcar para 19 às 14h.", now) == (
        "2026-11-19T14:00:00+00:00"
    )
    assert extract_scheduled_at("Quero marcar para o dia 3 às 10h.", now) == (
        "2026-12-03T10:00:00+00:00"
    )


def test_booking_reply_uses_the_registered_schedule_only():
    from backend.services.email_service import _build_request_status_reply

    details = (
        "Assunto: Marcação\n"
        "Em 17/11/2026 às 10h, Cliente escreveu:\n"
        "> mensagem antiga\n"
        "Quero a marcação para quinta feira às 15 horas"
    )
    reply = _build_request_status_reply(
        customer_name="Cliente",
        business_name="Studio",
        details=details,
        confirmed=True,
        scheduled_at="2026-11-19T15:00:00+00:00",
    )

    assert "19/11/2026 às 15:00" in reply
    assert "17/11/2026 às 10h" not in reply


@pytest.mark.anyio
async def test_reminder_uses_registered_schedule_and_not_email_metadata(auth_client):
    _, _, user_id = auth_client
    scheduled_at = extract_scheduled_at("19/11/2099 às 15h")
    details = (
        "Em 17/11/2026 às 10h, Cliente escreveu:\n"
        "> mensagem antiga\n"
        "Quero a marcação para quinta feira às 15 horas"
    )
    with connect() as c:
        contact_id = c.execute(
            "INSERT INTO contacts(user_id, name, contact_key) VALUES (?, 'Cliente', 'cliente@example.com')",
            (user_id,),
        ).lastrowid
        request_id = c.execute(
            """INSERT INTO conversion_requests
               (user_id, contact_id, request_type, details, status, scheduled_at)
               VALUES (?, ?, 'booking', ?, 'confirmed', ?)""",
            (user_id, contact_id, details, scheduled_at),
        ).lastrowid
        c.execute(
            "INSERT INTO email_integrations(user_id, provider, email_address, status) VALUES (?, 'google', 'empresa@gmail.com', 'connected')",
            (user_id,),
        )

    with patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        return_value={"status": "sent"},
    ) as mock_send:
        result = await send_ai_booking_reminder(user_id, request_id)

    assert result["ok"] is True
    body = mock_send.await_args.kwargs["body_text"]
    assert "Data e hora da marcação: 19/11/2099 às 15:00" in body
    assert "17/11/2026 às 10h" not in body


def test_detect_client_confirmation_variations():
    from backend.services.email_service import detect_client_confirmation

    assert detect_client_confirmation("Sim") == "positive"
    assert detect_client_confirmation("Sim, confirmo") == "positive"
    assert detect_client_confirmation("Sim, no dia 20 às 15h") == "positive"
    assert detect_client_confirmation("Sim, confirmo no dia 20") == "positive"
    assert detect_client_confirmation("Pode agendar") == "positive"
    assert detect_client_confirmation("Por mim está ótimo") == "positive"
    assert detect_client_confirmation("Pode avançar com a marcação") == "positive"
    assert detect_client_confirmation("Confirmado") == "positive"
    assert detect_client_confirmation("Com certeza, confirmo") == "positive"
    assert detect_client_confirmation("Não confirmo") == "negative"
    assert detect_client_confirmation("Não quero agendar") == "negative"
    assert detect_client_confirmation("Prefiro cancelar") == "negative"


@pytest.mark.anyio
async def test_full_automation_no_loop_and_confirms_date_on_week_board(auth_client):
    client, token, user_id = auth_client
    params = {
        "user_dict": {
            "id": user_id,
            "name": "Clínica Drexier",
            "business_type": "Saúde",
            "mandatory_responses": '{"automation_level":"full"}',
        },
        "integration": {
            "provider": "google",
            "email_address": "clinica@gmail.com",
            "auto_reply_enabled": 1,
        },
        "customer_email": "paciente@example.com",
        "customer_name": "Ana Silva",
        "subject": "Agendamento de Consulta",
        "thread_id": "thread-123",
        "message_id_header": "<msg-1@example.com>",
    }

    with patch(
        "backend.services.email_service.check_business_availability",
        return_value={"available": True, "reason": "Horário disponível"},
    ), patch(
        "backend.services.email_service.send_email",
        new_callable=AsyncMock,
        return_value={"status": "sent"},
    ) as mock_send:
        # Turno 1: Cliente manifesta intenção sem data/hora
        reply1 = await process_and_reply_email(
            **{**params, "incoming_content": "Olá, boa tarde! Gostaria de agendar uma consulta."}
        )
        assert (
            "data e a hora" in reply1
            or "indique o dia" in reply1
            or "data e hor" in reply1.lower()
            or ("dia" in reply1.lower() and "hor" in reply1.lower())
            or ("data" in reply1.lower() and "hor" in reply1.lower())
        )

        # Turno 2: Cliente informa data e hora com citação típica do Gmail
        reply2 = await process_and_reply_email(
            **{
                **params,
                "incoming_content": (
                    "Pode ser sexta-feira às 15h.\n\n"
                    "No dia quarta-feira, 18 de novembro de 2026 às 08:00, Clínica Drexier escreveu:\n"
                    "> Para registar a sua marcação, qual é a data e a hora que prefere?"
                ),
                "message_id_header": "<msg-2@example.com>",
            }
        )
        # NÃO entra em loop pedindo data e hora novamente; avança para pedir confirmação
        assert "qual é a data e a hora que prefere" not in reply2
        assert "Deseja prosseguir e confirmar a marcação?" in reply2 or "Confirmação da marcação solicitada" in reply2

        # Turno 3: Cliente confirma positivamente (com "Sim, no dia...")
        reply3 = await process_and_reply_email(
            **{
                **params,
                "incoming_content": (
                    "Sim, confirmo no dia e hora indicados, obrigado!\n\n"
                    "No dia quarta-feira, 18 de novembro de 2026 às 08:05, Clínica Drexier escreveu:\n"
                    "> Temos disponibilidade..."
                ),
                "message_id_header": "<msg-3@example.com>",
            }
        )
        # A IA confirma explicitamente o agendamento para a data
        bodies = [call.kwargs["body_text"] for call in mock_send.await_args_list]
        last_body = bodies[-1]
        assert "O seu pedido foi confirmado." in last_body
        assert "O seu agendamento foi confirmado para" in last_body
        assert "15:00" in last_body

    # Verifica que a marcação está registada no dashboard como confirmed_bookings
    response = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    d = response.json()
    assert d["bookings_count"] >= 1
    matching = [b for b in d["confirmed_bookings"] if b["contact_key"] == "paciente@example.com"]
    assert len(matching) == 1
    assert matching[0]["status"] == "confirmed"
    assert matching[0]["scheduled_at"] is not None


def test_email_sending_headers_are_completely_blocked_from_scheduling():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime(2026, 11, 20, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))

    header_cases_without_booking = [
        "De João Silva, para Clínica, data 20/11/2026 às 15h. Olá, queria agendar.",
        "De xxxx , para xxxx , data 20/11/2026 15h Olá, queria agendar.",
        "De: xxxx , para: xxxx , data: 20/11/2026 15:00\nOlá, gostaria de agendar.",
        "Enviadas: sexta-feira, 20 de novembro de 2026 15:00\nOlá, queria agendar.",
        "Data de envio: 20/11/2026 às 15h\nOlá, gostaria de agendar uma consulta.",
        "Date: Fri, 20 Nov 2026 15:00:00\nOlá, gostaria de agendar.",
        "No dia 20/11/2026 às 15:00, Fulano escreveu:\nOlá, gostaria de agendar.",
        "Em 20 de nov. de 2026, às 15:00, Cliente escreveu:\nOlá, gostaria de marcar consulta.",
        "On 20/11/2026 at 14:00, John wrote:\nHello, want to book appointment.",
    ]
    for case in header_cases_without_booking:
        # Nenhum destes emails deve usar a data/hora do cabeçalho como marcação
        assert extract_scheduled_at(case, now) is None, f"Falhou para caso: {case}"

    # Quando o cliente especifica uma data no corpo juntamente com cabeçalhos de envio:
    with_custom_choice = (
        "De: Cliente <cli@ex.com>\n"
        "Data: 20/11/2026 10:00\n"
        "Para: Empresa <emp@ex.com>\n"
        "Assunto: Agendamento\n\n"
        "Olá, gostaria de marcar consulta para 15 de dezembro às 14h."
    )
    extracted = extract_scheduled_at(with_custom_choice, now)
    assert extracted == "2026-12-15T14:00:00+00:00"


def test_email_reply_quote_headers_below_message_are_completely_ignored():
    from backend.services.email_service import clean_email_body, strip_email_headers
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime(2026, 11, 20, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))

    msg = (
        "Olá, gostaria de saber os preços e marcar para amanhã às 14h.\n\n"
        "em sex., 20 de nov  de 2026 as 10: 38, Délcio Mateus (delciomateus42@gmail.com ) escreveu :\n"
        "> Olá Délcio, confirmamos para sexta às 10h.\n"
        "> Qualquer dúvida disponha."
    )
    cleaned = clean_email_body(msg)
    assert cleaned == "Olá, gostaria de saber os preços e marcar para amanhã às 14h."
    assert "Délcio Mateus" not in cleaned
    assert "10: 38" not in cleaned

    stripped = strip_email_headers(msg)
    assert stripped == "Olá, gostaria de saber os preços e marcar para amanhã às 14h."
    assert "Délcio Mateus" not in stripped

    # O agendamento é feito para amanhã às 14h, e NUNCA para 20 de nov às 10:38 da citação
    extracted = extract_scheduled_at(msg, now)
    assert extracted == "2026-11-21T14:00:00+00:00"


def test_bookings_are_atemporal_for_any_future_date():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime(2026, 11, 20, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))

    # Marcação para daqui a 2 meses
    res2m = extract_scheduled_at("Quero agendar para daqui a 2 meses às 16h.", now)
    assert res2m is not None
    assert "2027-01-" in res2m
    assert "16:00:00" in res2m

    # Marcação para próximo mês
    res_pm = extract_scheduled_at("Quero marcar para o próximo mês às 11h.", now)
    assert res_pm is not None
    assert "2026-12-" in res_pm
    assert "11:00:00" in res_pm

    # Marcação para data específica bem no futuro
    res_fut = extract_scheduled_at("Por favor agende para 20 de maio de 2027 às 10h.", now)
    assert res_fut == "2027-05-20T09:00:00+00:00"


def test_create_mime_message_includes_booking_button():
    booking_url = "https://drexier.loca.lt/booking?token=test_token_123"
    msg = create_mime_message(
        sender="suporte@drexier.com",
        to="cliente@exemplo.com",
        subject="Re: Informações de Marcação",
        body_text="Olá! Temos vários horários disponíveis.",
        booking_url=booking_url,
    )
    # Verifica texto puro
    payloads = msg.get_payload()
    plain_text = payloads[0].get_payload(decode=True).decode("utf-8")
    assert booking_url in plain_text
    assert "Para escolher o seu horário de marcação" in plain_text

    # Verifica HTML com botão
    html_text = payloads[1].get_payload(decode=True).decode("utf-8")
    assert booking_url in html_text
    assert "Escolher Horário de Marcação" in html_text
    assert "background-color: #2563eb" in html_text


def test_generate_booking_options_structure():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from backend.services.email_service import generate_booking_options
    base = datetime(2026, 11, 20, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
    options = generate_booking_options(base_dt=base)
    assert len(options) >= 2
    # Primeira opção na próxima segunda-feira 23/11/2026 às 08:00
    assert options[0]["date"] == "23/11/2026"
    assert "Opção 1" in options[0]["label"]
    assert "08:00" in options[0]["time"]
    assert options[1]["date"] == "23/11/2026"
    assert "13:00" in options[1]["time"]


@pytest.mark.anyio
async def test_public_booking_options_and_selection_full_auto(auth_client):
    from backend.auth import create_booking_token
    client, token, user_id = auth_client

    # Configura utilizador no modo totalmente automático ('full')
    with connect() as c:
        c.execute(
            "UPDATE users SET mandatory_responses=? WHERE id=?",
            (json.dumps({"automation_level": "full"}), user_id)
        )
        cur = c.execute(
            "INSERT INTO contacts (user_id, name, contact_key) VALUES (?, ?, ?)",
            (user_id, "Délcio Mateus", "delcio@exemplo.com")
        )
        contact_id = cur.lastrowid

    booking_tok = create_booking_token(user_id, contact_id, "delcio@exemplo.com", "Délcio Mateus")

    # 1. Carregar opções através do endpoint público
    resp_opts = client.get(f"/api/booking/options?token={booking_tok}")
    assert resp_opts.status_code == 200
    opts_data = resp_opts.json()
    assert opts_data["ok"] is True
    assert len(opts_data["options"]) > 0
    first_opt = opts_data["options"][0]

    # 2. Cliente seleciona a opção 1
    resp_sel = client.post("/api/booking/select", json={
        "token": booking_tok,
        "slot_label": first_opt["label"],
        "scheduled_at": first_opt["iso"],
        "customer_name": "Délcio Mateus"
    })
    assert resp_sel.status_code == 200
    sel_data = resp_sel.json()
    assert sel_data["ok"] is True
    assert sel_data["mode"] == "full"
    assert sel_data["status"] == "confirmed"

    # 3. Verifica que foi registrado no quadro de marcações do dashboard
    dash = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"}).json()
    assert dash["bookings_count"] >= 1
    matching = [b for b in dash["confirmed_bookings"] if b["contact_id"] == contact_id]
    assert len(matching) == 1
    assert "23/11/2026" in str(matching[0]["scheduled_at"]) or "2026-11-23" in str(matching[0]["scheduled_at"])


@pytest.mark.anyio
async def test_public_booking_selection_semi_auto_and_approval_moves_to_board(auth_client):
    from backend.auth import create_booking_token
    client, token, user_id = auth_client

    # Configura utilizador no modo semi-automático ('semi') com integração conectada
    with connect() as c:
        c.execute(
            "UPDATE users SET mandatory_responses=? WHERE id=?",
            (json.dumps({"automation_level": "semi"}), user_id)
        )
        c.execute(
            "INSERT INTO email_integrations (user_id, provider, email_address, status) VALUES (?, 'google', 'empresa@gmail.com', 'connected') ON CONFLICT(user_id) DO UPDATE SET status='connected'",
            (user_id,)
        )
        cur = c.execute(
            "INSERT INTO contacts (user_id, name, contact_key) VALUES (?, ?, ?)",
            (user_id, "Ana Costa", "ana@exemplo.com")
        )
        contact_id = cur.lastrowid

    booking_tok = create_booking_token(user_id, contact_id, "ana@exemplo.com", "Ana Costa")

    # Cliente escolhe uma opção
    slot_label = "Opção 2: Dia 23/11/2026 às 13:00"
    slot_iso = "2026-11-23T13:00:00+00:00"
    resp_sel = client.post("/api/booking/select", json={
        "token": booking_tok,
        "slot_label": slot_label,
        "scheduled_at": slot_iso,
        "customer_name": "Ana Costa"
    })
    assert resp_sel.status_code == 200
    sel_data = resp_sel.json()
    assert sel_data["ok"] is True
    assert sel_data["mode"] == "semi"
    assert sel_data["status"] == "pending"

    # 1. Deve constar nos pedidos aguardando validação do dashboard
    dash = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"}).json()
    pending_list = dash["pending_requests"]
    matching_pending = [p for p in pending_list if "Ana Costa" in (p.get("name") or "") or p.get("contact_key") == "ana@exemplo.com"]
    assert len(matching_pending) == 1
    req_id = matching_pending[0]["id"]

    # 2. O proprietário aprova/valida no dashboard
    with patch("backend.services.email_service.send_email", new_callable=AsyncMock) as mock_send:
        resp_act = client.post(
            f"/api/conversions/{req_id}/action",
            headers={"Authorization": f"Bearer {token}"},
            json={"action": "confirm", "custom_note": ""}
        )
        assert resp_act.status_code == 200
        # Confirma que enviou mensagem ao cliente dizendo que foi confirmada com sucesso e os detalhes
        mock_send.assert_called_once()
        body_sent = mock_send.call_args.kwargs["body_text"]
        assert "confirmado com sucesso" in body_sent
        assert "Ana Costa" in body_sent
        assert "23/11/2026" in body_sent

    # 3. Agora a marcação foi adicionada ao card de marcações
    dash_after = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"}).json()
    confirmed_list = dash_after["confirmed_bookings"]
    matching_confirmed = [b for b in confirmed_list if b["id"] == req_id]
    assert len(matching_confirmed) == 1
    assert matching_confirmed[0]["name"] == "Ana Costa"
    dash_after = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"}).json()
    confirmed_list = dash_after["confirmed_bookings"]
    matching_confirmed = [b for b in confirmed_list if b["id"] == req_id]
    assert len(matching_confirmed) == 1
    assert matching_confirmed[0]["name"] == "Ana Costa"






