import pytest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from backend.database import connect
from backend.services.email_service import (
    BUSINESS_TIMEZONE,
    create_mime_message,
    generate_booking_options,
    extract_booking_option_choice,
    process_and_reply_email,
)
from backend.auth import create_booking_token

@pytest.mark.anyio
async def test_email_options_have_no_redirect_button():
    """O email com opções deve ter seleção de data sem emojis, sem menção ao Gmail e sem botão de redirecionamento."""
    opts = generate_booking_options()[:3]
    token = create_booking_token(1, 1, "cliente@teste.com", "Cliente Teste")

    msg = create_mime_message(
        sender="empresa@drexier.com",
        to="cliente@teste.com",
        subject="Horários de Agendamento",
        body_text="Olá, temos estes horários disponíveis.",
        booking_token=token,
        booking_options=opts,
    )

    payloads = msg.get_payload()
    plain_text = payloads[0].get_payload(decode=True).decode("utf-8")
    html_text = payloads[1].get_payload(decode=True).decode("utf-8")

    # Não deve ter o botão antigo de redirecionamento
    assert "Escolher Horário de Marcação" not in html_text
    assert "Escolher Horário de Marcação" not in plain_text

    # Deve ter o título exato sem emojis e sem menção ao Gmail
    assert "Selecione a sua data disponível para efectuar a marcação" in html_text
    assert "Selecione a sua data disponível para efectuar a marcação" in plain_text

    # Não deve ter menções ao Gmail nem emojis
    assert "Gmail" not in html_text
    assert "Gmail" not in plain_text
    emojis = ["🕒", "✉️", "✔", "📅", "⏰"]
    for em in emojis:
        assert em not in html_text, f"Emoji {em} encontrado no HTML"
        assert em not in plain_text, f"Emoji {em} encontrado no PlainText"

    assert "mailto:empresa@drexier.com" in html_text
    assert "Opção 1" in html_text
    assert "Opção 2" in html_text


@pytest.mark.anyio
async def test_options_only_delivered_on_booking_inquiry(monkeypatch):
    """
    As opções de escolha de data só são entregues quando o cliente perguntar sobre marcações,
    e NÃO em todas as mensagens (ex: dúvidas gerais, morada, preço).
    """
    sent_emails = []
    async def mock_send_email(integration, to_email, subject, body_text, **kwargs):
        sent_emails.append({
            "to": to_email,
            "subject": subject,
            "body": body_text,
            "include_booking_options": kwargs.get("include_booking_options", False),
        })
        return {"id": "msg_mock"}

    monkeypatch.setattr("backend.services.email_service.send_email", mock_send_email)

    with connect() as c:
        c.execute("DELETE FROM users WHERE email='user_inquiry@teste.com'")
        cur = c.execute(
            """INSERT INTO users (name, email, password_hash, business_type, mandatory_responses)
               VALUES ('Negócio Inquiry', 'user_inquiry@teste.com', 'hash', 'Serviços', '{"automation_level": "full"}')"""
        )
        uid = cur.lastrowid
        c.execute(
            "INSERT INTO email_integrations (user_id, provider, email_address, status, auto_reply_enabled) VALUES (?, 'google', 'user_inquiry@teste.com', 'connected', 1)",
            (uid,)
        )
        c.execute(
            "INSERT INTO business_info (user_id, kind, title, content) VALUES (?, 'morada', 'Localização', 'Rua das Flores 123, Lisboa')",
            (uid,)
        )
        c.execute(
            "INSERT INTO business_info (user_id, kind, title, content) VALUES (?, 'horarios', 'Horário', 'Segunda a Sexta 8h às 18h')",
            (uid,)
        )

        user_dict = dict(c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
        integration = dict(c.execute("SELECT * FROM email_integrations WHERE user_id=?", (uid,)).fetchone())

    # 1. Cliente pergunta sobre morada/localização (NÃO é pergunta sobre marcações)
    sent_emails.clear()
    await process_and_reply_email(
        user_dict=user_dict,
        integration=integration,
        customer_email="cliente_geral@gmail.com",
        customer_name="Carlos Lima",
        subject="Onde fica a loja?",
        incoming_content="Olá, gostaria de saber onde fica localizada a vossa clínica?",
    )
    assert len(sent_emails) == 1
    assert sent_emails[0]["include_booking_options"] is False

    # 2. Cliente pergunta sobre marcação de consulta (É pergunta sobre marcações)
    sent_emails.clear()
    await process_and_reply_email(
        user_dict=user_dict,
        integration=integration,
        customer_email="cliente_geral@gmail.com",
        customer_name="Carlos Lima",
        subject="Marcação de consulta",
        incoming_content="Queria agendar uma consulta, quais são os horários disponíveis para marcar?",
    )
    assert len(sent_emails) == 1
    assert sent_emails[0]["include_booking_options"] is True


def test_extract_booking_option_choice_various_formats():
    """Identifica opções de marcação digitadas pelo cliente de várias formas no Gmail."""
    opts = [
        {"id": "opt_1", "label": "Opção 1: Dia 23/11/2026 às 08:00", "date": "23/11/2026", "time": "08:00", "iso": "2026-11-23T08:00:00+00:00"},
        {"id": "opt_2", "label": "Opção 2: Dia 23/11/2026 às 13:00", "date": "23/11/2026", "time": "13:00", "iso": "2026-11-23T13:00:00+00:00"},
        {"id": "opt_3", "label": "Opção 3: Dia 24/11/2026 às 08:00", "date": "24/11/2026", "time": "08:00", "iso": "2026-11-24T08:00:00+00:00"},
    ]

    # Clicado via mailto: ou escrito com label completo
    assert extract_booking_option_choice("Seleciono a Opção 1: Dia 23/11/2026 às 08:00", opts)["id"] == "opt_1"
    # Escrito naturalmente
    assert extract_booking_option_choice("Opção 1", opts)["id"] == "opt_1"
    assert extract_booking_option_choice("opcao 2", opts)["id"] == "opt_2"
    assert extract_booking_option_choice("Quero a opção 3, por favor", opts)["id"] == "opt_3"
    assert extract_booking_option_choice("Pode ser a Opção 2", opts)["id"] == "opt_2"
    assert extract_booking_option_choice("Prefiro a opção 1", opts)["id"] == "opt_1"
    # Apenas o número da opção em resposta
    assert extract_booking_option_choice("1", opts)["id"] == "opt_1"
    assert extract_booking_option_choice("2", opts)["id"] == "opt_2"


@pytest.mark.anyio
async def test_gmail_selection_full_auto_adds_to_weekly_bookings(monkeypatch):
    """
    Quando o cliente seleciona a opção no Gmail em modo totalmente automático:
    A marcação entra automaticamente no card de Marcações da Semana (status='confirmed').
    """
    sent_emails = []
    async def mock_send_email(integration, to_email, subject, body_text, **kwargs):
        sent_emails.append({"to": to_email, "subject": subject, "body": body_text})
        return {"id": "msg_mock"}

    monkeypatch.setattr("backend.services.email_service.send_email", mock_send_email)

    with connect() as c:
        # Cria utilizador em modo full
        c.execute("DELETE FROM users WHERE email='user_full@teste.com'")
        cur = c.execute(
            """INSERT INTO users (name, email, password_hash, business_type, mandatory_responses)
               VALUES ('Negócio Full', 'user_full@teste.com', 'hash', 'Serviços', '{"automation_level": "full"}')"""
        )
        uid = cur.lastrowid
        c.execute(
            "INSERT INTO email_integrations (user_id, provider, email_address, status, auto_reply_enabled) VALUES (?, 'google', 'user_full@teste.com', 'connected', 1)",
            (uid,)
        )
        c.execute(
            "INSERT INTO business_info (user_id, kind, title, content) VALUES (?, 'horarios', 'Horário', 'Segunda a Sexta 8h às 18h')",
            (uid,)
        )

        user_dict = dict(c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
        integration = dict(c.execute("SELECT * FROM email_integrations WHERE user_id=?", (uid,)).fetchone())

    # Cliente envia no Gmail a seleção da Opção 1
    res = await process_and_reply_email(
        user_dict=user_dict,
        integration=integration,
        customer_email="cliente_full@gmail.com",
        customer_name="Maria Silva",
        subject="Re: Agendamento",
        incoming_content="Seleciono a Opção 1: Dia 25/11/2026 às 08:00",
    )

    assert "Marcações da Semana" in res or "confirmada" in res

    # Verifica no banco de dados se foi para confirmed (Marcações da Semana)
    with connect() as c:
        req = c.execute(
            "SELECT * FROM conversion_requests WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (uid,)
        ).fetchone()
        assert req is not None
        assert req["status"] == "confirmed"
        assert req["scheduled_at"] is not None
        assert "Opção 1" in req["details"]


@pytest.mark.anyio
async def test_gmail_selection_semi_auto_adds_to_pending_validation(monkeypatch):
    """
    Quando o cliente seleciona a opção no Gmail em modo semi-automático:
    A marcação entra no card de Esperando Validação (status='pending') até ser validada.
    """
    sent_emails = []
    async def mock_send_email(integration, to_email, subject, body_text, **kwargs):
        sent_emails.append({"to": to_email, "subject": subject, "body": body_text})
        return {"id": "msg_mock"}

    monkeypatch.setattr("backend.services.email_service.send_email", mock_send_email)

    with connect() as c:
        # Cria utilizador em modo semi
        c.execute("DELETE FROM users WHERE email='user_semi@teste.com'")
        cur = c.execute(
            """INSERT INTO users (name, email, password_hash, business_type, mandatory_responses)
               VALUES ('Negócio Semi', 'user_semi@teste.com', 'hash', 'Serviços', '{"automation_level": "semi"}')"""
        )
        uid = cur.lastrowid
        c.execute(
            "INSERT INTO email_integrations (user_id, provider, email_address, status, auto_reply_enabled) VALUES (?, 'google', 'user_semi@teste.com', 'connected', 1)",
            (uid,)
        )
        c.execute(
            "INSERT INTO business_info (user_id, kind, title, content) VALUES (?, 'horarios', 'Horário', 'Segunda a Sexta 8h às 18h')",
            (uid,)
        )

        user_dict = dict(c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
        integration = dict(c.execute("SELECT * FROM email_integrations WHERE user_id=?", (uid,)).fetchone())

    # Cliente envia no Gmail: "Opção 2"
    res = await process_and_reply_email(
        user_dict=user_dict,
        integration=integration,
        customer_email="cliente_semi@gmail.com",
        customer_name="João Santos",
        subject="Re: Horários",
        incoming_content="Opção 2",
    )

    assert "aguardando validação" in res or "Semi-Automático" in res

    # Verifica no banco de dados se foi para pending (Esperando validação)
    with connect() as c:
        req = c.execute(
            "SELECT * FROM conversion_requests WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (uid,)
        ).fetchone()
        assert req is not None
        assert req["status"] == "pending"
        assert req["scheduled_at"] is not None
        assert "Opção 2" in req["details"]


@pytest.mark.anyio
async def test_booking_inquiry_does_not_ask_preferred_time_and_does_not_use_sent_timestamp(monkeypatch):
    """
    Quando o cliente mostra intenção de marcação:
    - Escreve apenas a instrução de seleção ('Selecione a sua data disponível para efectuar a marcação')
    - NÃO envia 'Temos disponibilidade para a sua marcação de marcação em [timestamp do envio]'
    - NÃO pergunta 'informe qual dia pretendido e o horario de sua preferencia' nem 'aguardamos o seu retorno'
    - As opções de horários aparecem no e-mail (include_booking_options=True).
    """
    sent_emails = []
    async def mock_send_email(integration, to_email, subject, body_text, **kwargs):
        sent_emails.append({
            "to": to_email,
            "subject": subject,
            "body": body_text,
            "include_booking_options": kwargs.get("include_booking_options", False),
        })
        return {"id": "msg_mock"}

    monkeypatch.setattr("backend.services.email_service.send_email", mock_send_email)

    with connect() as c:
        c.execute("DELETE FROM users WHERE email='user_clean_inquiry@teste.com'")
        cur = c.execute(
            """INSERT INTO users (name, email, password_hash, business_type, mandatory_responses)
               VALUES ('Negócio Clean', 'user_clean_inquiry@teste.com', 'hash', 'Serviços', '{"automation_level": "full"}')"""
        )
        uid = cur.lastrowid
        c.execute(
            "INSERT INTO email_integrations (user_id, provider, email_address, status, auto_reply_enabled) VALUES (?, 'google', 'user_clean_inquiry@teste.com', 'connected', 1)",
            (uid,)
        )
        c.execute(
            "INSERT INTO business_info (user_id, kind, title, content) VALUES (?, 'horarios', 'Horário', 'Segunda a Sexta 8h às 18h')",
            (uid,)
        )
        user_dict = dict(c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
        integration = dict(c.execute("SELECT * FROM email_integrations WHERE user_id=?", (uid,)).fetchone())

    # Email de cliente com intenção de marcação e carimbo de data/hora do próprio envio no corpo/cabeçalho
    incoming = (
        "20/11/2026 às 20:23\n"
        "Olá, gostaria de fazer uma marcação de consulta no vosso consultório."
    )

    await process_and_reply_email(
        user_dict=user_dict,
        integration=integration,
        customer_email="cliente_novo@gmail.com",
        customer_name="Rui Sousa",
        subject="Marcação",
        incoming_content=incoming,
    )

    assert len(sent_emails) == 1
    sent = sent_emails[0]
    body = sent["body"]

    # 1. As opções de agendamento devem ser incluídas
    assert sent["include_booking_options"] is True

    # 2. Deve orientar a selecionar a data disponível
    assert "Selecione a sua data disponível para efectuar a marcação" in body

    # 3. NÃO deve enviar a frase com 'marcação de marcação' nem com o horário do envio
    assert "marcação de marcação" not in body.lower()
    assert "20:23" not in body

    # 4. NÃO deve perguntar por dia/horário de preferência nem aguardar retorno
    assert "informe qual dia pretendido" not in body.lower()
    assert "horário de sua preferência" not in body.lower()
    assert "horario de sua preferencia" not in body.lower()
    assert "aguardamos o seu retorno" not in body.lower()
    assert "qual é a data e a hora que prefere" not in body.lower()

