import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.agent import (
    UNKNOWN_REPLY,
    build_system_instruction,
    format_gemini_contents,
    call_gemini_api,
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
    assert "Seja amigável e convide para provar na loja." in instruction

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
            # Aciona fallback local seguro
            assert "Horário" in reply or "09h" in reply

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
