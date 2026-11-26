import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.agent import (
    UNKNOWN_REPLY,
    build_system_instruction,
    format_gemini_contents,
    call_gemini_api,
    call_openai_compatible_api,
    draft_reply,
    ensure_complete_sentence
)

def test_unknown_reply_is_explicit():
    assert "não tenho essa informação" in UNKNOWN_REPLY.lower()

def test_format_gemini_contents():
    history = [
        {"sender": "customer", "content": "Olá, boa tarde!"},
        {"sender": "agent", "content": "Boa tarde! Como posso ajudar hoje?"},
        {"sender": "customer", "content": "Vocês vendem cafés especiais?"},
        {"sender": "customer", "content": "E têm grãos moídos na hora?"}
    ]
    current = "Qual o preço do expresso?"
    contents = format_gemini_contents(history, current)

    # Verifica se mensagens consecutivas do cliente foram unificadas
    assert len(contents) == 3
    assert contents[0]["role"] == "user"
    assert "Olá, boa tarde!" in contents[0]["parts"][0]["text"]
    assert contents[1]["role"] == "model"
    assert "Como posso ajudar" in contents[1]["parts"][0]["text"]
    assert contents[2]["role"] == "user"
    assert "cafés especiais" in contents[2]["parts"][0]["text"]
    assert "MENSAGEM ATUAL DO CLIENTE (responda somente a esta mensagem)" in contents[2]["parts"][0]["text"]
    assert "preço do expresso" in contents[2]["parts"][0]["text"]

def test_build_system_instruction():
    instruction = build_system_instruction(
        business_context="[PRODUTO] Café Arábica: 15€",
        instructions="Seja amigável e convide para provar na loja.",
        language="Português",
        business_name="Café Central",
        business_type="Cafetaria",
        business_description="Especialistas em cafés artesanais."
    )
    assert "Café Central" in instruction
    assert "Cafetaria" in instruction
    assert "Café Arábica: 15€" in instruction
    assert "DIRIGIR a conversa" in instruction
    assert "A ÚLTIMA mensagem do cliente é sempre a pergunta a responder" in instruction
    assert "Não acrescente produtos, ofertas" in instruction
    assert "Seja amigável e convide para provar na loja." in instruction

def test_full_automation_prompt_never_mentions_team_validation():
    instruction = build_system_instruction(
        business_context="[PRODUTO] Café Arábica: 15€",
        mandatory_responses={"automation_level": "full"},
    )
    assert "MODO TOTALMENTE AUTOMÁTICO" in instruction
    assert "NUNCA diga que o pedido aguarda validação" in instruction
    assert "NUNCA volte a perguntar qual é a data" in instruction
    assert "validação e confirmação da nossa equipe" not in instruction
    assert "automation_level" not in instruction

    semi_instruction = build_system_instruction(
        business_context="[PRODUTO] Café Arábica: 15€",
        mandatory_responses={"automation_level": "semi"},
    )
    assert "validação e confirmação da nossa equipe" in semi_instruction


def test_call_gemini_api_success():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Olá! Temos café Arábica por 15€. Gostaria de encomendar um pacote para entrega ou reservar para recolha na loja?"}]
                }
            }
        ]
    }
    fake_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = fake_response
        reply = asyncio.run(call_gemini_api(
            system_instruction="Instruções de teste",
            contents=[{"role": "user", "parts": [{"text": "Qual o preço do café?"}]}],
            api_key="test-gemini-key",
            model="gemini-1.5-flash"
        ))
        assert reply is not None
        assert "Temos café Arábica" in reply
        assert "Gostaria de encomendar" in reply
        assert mock_post.call_args.kwargs["json"]["generationConfig"]["temperature"] == 0

def test_draft_reply_with_gemini_mock():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Com certeza! O nosso horário na sexta é das 09h às 18h. Gostaria de marcar a sua visita para que horário?"}]
                }
            }
        ]
    }
    fake_response.raise_for_status = MagicMock()

    with patch("backend.services.agent.get_gemini_config", return_value={
        "api_key": "dummy-key",
        "model": "gemini-1.5-flash",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "provider": "gemini"
    }):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = fake_response
            reply = asyncio.run(draft_reply(
                message="Qual o horário na sexta?",
                info_rows=[{"kind": "horarios", "title": "Horário", "content": "09h às 18h"}],
                business_name="Barbearia Central"
            ))
            assert "Com certeza!" in reply
            assert "marcar a sua visita" in reply
            current_turn = mock_post.call_args.kwargs["json"]["contents"][-1]["parts"][0]["text"]
            assert "MENSAGEM ATUAL DO CLIENTE (responda somente a esta mensagem)" in current_turn
            assert "Qual o horário na sexta?" in current_turn

def test_draft_reply_fails_closed_for_an_empty_current_message():
    with patch("backend.services.agent.get_gemini_config", side_effect=AssertionError("API must not be called")):
        reply = asyncio.run(draft_reply(message="   ", info_rows=[]))

    assert reply == UNKNOWN_REPLY

def test_draft_reply_fallback_when_api_fails():
    with patch("backend.services.agent.get_gemini_config", return_value={
        "api_key": "dummy-key",
        "model": "gemini-1.5-flash",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "provider": "gemini"
    }):
        with patch("httpx.AsyncClient.post", side_effect=Exception("API Error")):
            reply = asyncio.run(draft_reply(
                message="Qual o horário na sexta?",
                info_rows=[{"kind": "horarios", "title": "Horário", "content": "Sexta das 09h às 18h"}]
            ))
            assert "Horário" in reply
            assert "09h às 18h" in reply

def test_local_fallback_does_not_guess_when_customer_asks_about_multiple_topics():
    from backend.services.agent import local_fallback

    reply = local_fallback(
        "Qual é o horário e o preço?",
        [
            {"kind": "horarios", "title": "Horários", "content": "Segunda a sexta, das 09h às 18h"},
            {"kind": "precos", "title": "Preços", "content": "Consulta por 50€"}
        ]
    )

    assert reply == UNKNOWN_REPLY

def test_local_fallback_answers_one_explicit_topic_from_registered_metadata():
    from backend.services.agent import local_fallback

    reply = local_fallback(
        "Qual o horário na sexta?",
        [{
            "kind": "horarios",
            "title": "Horários de atendimento",
            "content": "",
            "metadata": {"items": [{"name": "Sexta-feira", "price": "09h às 18h"}]}
        }]
    )

    assert "Sexta-feira" in reply
    assert "09h às 18h" in reply

def test_ensure_complete_sentence():
    # Frase já completa preserva pontuação
    assert ensure_complete_sentence("Olá! Como posso ajudar hoje?") == "Olá! Como posso ajudar hoje?"
    assert ensure_complete_sentence("Temos o produto por 50€.") == "Temos o produto por 50€."
    
    # Frase cortada no meio: descarta o pedaço cortado após o último ponto válido
    cut_text = "Olá! Temos o iPhone 13 por 650€. Ele é excelente para fotos e você vai"
    completed = ensure_complete_sentence(cut_text)
    assert completed == "Olá! Temos o iPhone 13 por 650€."
    
    # Frase sem pontuação final recebe ponto
    assert ensure_complete_sentence("Temos disponibilidade para amanhã") == "Temos disponibilidade para amanhã."
    
    # Frase terminando com vírgula ou traço solto
    assert ensure_complete_sentence("Temos café expresso por 1€,") == "Temos café expresso por 1€."

def test_call_gemini_api_handles_multiple_parts():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"thought": True, "text": "Raciocínio interno..."},
                        {"text": "Parte um da resposta. "},
                        {"text": "Parte dois que completa o pensamento com sucesso!"}
                    ]
                }
            }
        ]
    }
    fake_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = fake_response
        reply = asyncio.run(call_gemini_api(
            system_instruction="Instruções",
            contents=[{"role": "user", "parts": [{"text": "Teste"}]}],
            api_key="test-key",
            model="gemini-3.5-flash"
        ))
        assert reply is not None
        assert "Raciocínio interno" not in reply
        assert "Parte um da resposta." in reply
        assert "Parte dois que completa o pensamento com sucesso!" in reply

def test_openai_compatible_api_marks_the_current_customer_message():
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {
        "choices": [{"message": {"content": "O nosso horário é das 9h às 18h."}}]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = fake_response
        reply = asyncio.run(call_openai_compatible_api(
            system_instruction="Responda à mensagem atual.",
            history=[{"sender": "customer", "content": "Qual o preço?"}],
            current_message="Qual é o horário hoje?",
            api_key="test-key",
            model="test-model",
            base_url="https://example.com/v1",
        ))

    assert reply == "O nosso horário é das 9h às 18h."
    payload = mock_post.call_args.kwargs["json"]
    assert payload["messages"][-1]["role"] == "user"
    assert "MENSAGEM ATUAL DO CLIENTE (responda somente a esta mensagem)" in payload["messages"][-1]["content"]
    assert "Qual é o horário hoje?" in payload["messages"][-1]["content"]
    assert payload["temperature"] == 0

def test_compose_context_with_isolated_training_topics():
    from backend.services.agent import compose_context
    info_rows = [
        {
            "kind": "horarios",
            "title": "Horários de Atendimento",
            "content": "",
            "metadata": {"items": [{"name": "Segunda a Sexta", "price": "09h às 19h"}]}
        },
        {
            "kind": "treinamento",
            "title": "Regulamento de Devoluções 2026",
            "content": "Artigo 1: As devoluções são aceites em até 30 dias com recibo original.",
            "metadata": {"is_isolated_topic": True, "category_tag": "Políticas e Trocas"}
        }
    ]
    context = compose_context(info_rows)
    assert "ESTRUTURA E DADOS DE NEGÓCIO" in context
    assert "Horários de Atendimento" in context
    assert "09h às 19h" in context
    assert "TREINAMENTO PROFUNDO, REGULAMENTOS E POLÍTICAS OFICIAIS" in context
    assert "TÓPICO ISOLADO DE TREINAMENTO: REGULAMENTO DE DEVOLUÇÕES 2026" in context
    assert "Artigo 1: As devoluções são aceites" in context
    assert "NUNCA misture, confunda ou aplique as cláusulas de um tópico a outro diferente" in context

def test_local_fallback_handles_order_confirmation():
    from backend.services.agent import local_fallback, UNKNOWN_REPLY

    reply = local_fallback("Quero confirmar o pedido", [], business_name="Padaria Central")
    assert reply != UNKNOWN_REPLY
    assert "pedido foi registado com sucesso" in reply or "confirm" in reply.lower()

    reply_en = local_fallback("I want to confirm my order", [], business_name="Bakery Central")
    assert reply_en != UNKNOWN_REPLY
    assert "order has been registered" in reply_en or "confirm" in reply_en.lower()

def test_format_gemini_contents_deduplicates_current_message():
    history = [
        {"sender": "customer", "content": "Olá, boa tarde!"},
        {"sender": "agent", "content": "Boa tarde! Como posso ajudar?"},
        {"sender": "customer", "content": "Quero confirmar o pedido."}
    ]
    current = "Quero confirmar o pedido."
    contents = format_gemini_contents(history, current)
    # Garante que não repete a mensagem no histórico e no current_turn
    assert len(contents) == 3
    assert contents[-1]["role"] == "user"
    assert "Quero confirmar o pedido." in contents[-1]["parts"][0]["text"]


def test_complementary_investigative_chatbot_rules_in_prompt():
    instruction = build_system_instruction(
        business_context="[PRODUTOS] Porsche 911 Carrera 2023 | Preço/Condição: 145.000€",
        business_name="Stand Premium",
        business_type="Automóveis",
    )
    assert "COMPLEMENTAÇÃO DE INFORMAÇÕES POR INVESTIGAÇÃO" in instruction
    assert "NUNCA complemente nada que NÃO esteja na base de dados da empresa" in instruction
    assert "vantagens e adequação" in instruction


def test_check_business_availability_natural_language():
    from datetime import datetime
    from backend.services.agent import check_business_availability

    info_rows = [
        {"kind": "horarios", "title": "Horário", "content": "Segunda a Sexta das 09h às 18h"}
    ]
    # Quinta-feira da próxima semana -> aberto
    res_thu = check_business_availability(
        "Quero fazer uma marcação para a próxima quinta feira da próxima semana",
        info_rows=info_rows,
    )
    assert res_thu["available"] is True

    # Domingo -> fechado
    res_sun = check_business_availability(
        "Quero marcar para o próximo domingo da próxima semana",
        info_rows=info_rows,
    )
    assert res_sun["available"] is False
    assert "domingo" in res_sun["reason"].lower()

    # Horário fora do expediente
    res_late = check_business_availability(
        "Quero marcar na próxima quinta feira às 21h",
        info_rows=info_rows,
    )
    assert res_late["available"] is False
    assert "21" in res_late["reason"] or "expediente" in res_late["reason"].lower()

    # Metadata items support (ex: aberto apenas Terça a Sábado)
    meta_rows = [{
        "kind": "horarios",
        "title": "Horários",
        "content": "",
        "metadata": {"items": [{"name": "Terça a Sábado", "price": "10h às 19h"}]},
    }]
    res_mon = check_business_availability(
        "Posso marcar para a próxima segunda feira?",
        info_rows=meta_rows,
        now=datetime(2026, 11, 26, 10, 0),
    )
    assert res_mon["available"] is False
    assert "segunda" in res_mon["reason"].lower()


def test_extract_scheduled_at_next_thursday_of_next_week():
    from datetime import datetime
    from backend.services.email_service import BUSINESS_TIMEZONE, extract_scheduled_at, detect_booking_or_purchase_intent

    # Sábado 28/11/2026 -> "próxima quinta feira da próxima semana às 10h" deve ser Quinta 03/12/2026 (não 10/12)
    sat_now = datetime(2026, 11, 28, 12, 0, tzinfo=BUSINESS_TIMEZONE)
    assert (
        extract_scheduled_at(
            "Quero fazer uma marcação para a próxima quinta feira da próxima semana às 10h",
            sat_now,
        )
        == "2026-12-03T10:00:00+00:00"
    )

    # Segunda 23/11/2026 -> "próxima quinta feira da próxima semana às 10h" deve ser Quinta 03/12/2026
    mon_now = datetime(2026, 11, 23, 12, 0, tzinfo=BUSINESS_TIMEZONE)
    assert (
        extract_scheduled_at(
            "Quero fazer uma marcação para a próxima quinta feira da próxima semana às 10h",
            mon_now,
        )
        == "2026-12-03T10:00:00+00:00"
    )

    # Linguagem natural sem verbo "marcar"
    intent = detect_booking_or_purchase_intent(
        "Tem vaga para a próxima quinta feira da próxima semana?",
        "Disponibilidade",
    )
    assert intent is not None
    assert intent["type"] == "booking"

def test_system_instruction_enforces_mandatory_conversation_flow():
    from backend.services.agent import build_system_instruction
    prompt = build_system_instruction(
        business_context="Café Expresso: 1.20€",
        instructions="Seja educado.",
        business_name="Café Central"
    )
    assert "FLUXO MANDATÓRIO E OBRIGATÓRIO DE ATENDIMENTO" in prompt
    assert "ETAPA 1 — LEITURA E CONTEXTUALIZAÇÃO TOTAL DA CONVERSA" in prompt
    assert "ETAPA 2 — IDENTIFICAÇÃO DO QUE O USUÁRIO QUER PERGUNTAR OU SOLICITAR" in prompt
    assert "ETAPA 3 — RESPOSTA ESTRITA, DIRETA E EXCLUSIVA" in prompt
    assert "responder SOMENTE ao que foi perguntado ou solicitado" in prompt

