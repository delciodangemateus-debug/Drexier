import pytest
from backend.services.agent import (
    ARMORED_BASE_FLOW,
    build_system_instruction,
    local_fallback,
    detect_message_language,
)

def test_armored_base_flow_definition():
    """Valida que a constante do fluxo base blindado existe e possui os 3 pilares invioláveis."""
    assert ARMORED_BASE_FLOW is not None
    assert "FLUXO BASE BLINDADO, SUPREMO E ESTRITAMENTE OBRIGATÓRIO" in ARMORED_BASE_FLOW
    assert "NADA NO SOFTWARE PODE SE SOBREPOR A ESTE FLUXO" in ARMORED_BASE_FLOW
    assert "1. O AGENTE LÊ A MENSAGEM ENVIADA PELO CLIENTE" in ARMORED_BASE_FLOW
    assert "2. O AGENTE ENTENDE A MENSAGEM" in ARMORED_BASE_FLOW
    assert "3. O AGENTE RESPONDE EXATAMENTE À MENSAGEM OU SOLICITAÇÃO DO CLIENTE" in ARMORED_BASE_FLOW

def test_system_instruction_embeds_armored_base_flow():
    """Valida que build_system_instruction inclui o fluxo base blindado no topo."""
    instruction = build_system_instruction(
        business_context="Temos consultoria por 100€.",
        instructions="Seja sempre cordial.",
        language="Português",
        business_name="Drexier Test",
        business_type="Tecnologia",
    )
    assert "FLUXO BASE BLINDADO, SUPREMO E ESTRITAMENTE OBRIGATÓRIO" in instruction
    assert "NUNCA NADA NO SOFTWARE PODE SE SOBREPOR A ESTE FLUXO" in instruction
    assert "O AGENTE LÊ A MENSAGEM ENVIADA PELO CLIENTE" in instruction
    assert "O AGENTE ENTENDE A MENSAGEM" in instruction
    assert "O AGENTE RESPONDE EXATAMENTE À MENSAGEM OU SOLICITAÇÃO DO CLIENTE" in instruction
    assert "O FLUXO BASE BLINDADO É SUPREMO" in instruction

def test_local_fallback_responds_exactly_to_customer_message():
    """Garante que o fallback local lê, compreende e responde exatamente à solicitação do cliente."""
    # Saudação
    res_greeting = local_fallback("Olá, boa tarde!", [], business_name="Oficina Del")
    assert "Oficina Del" in res_greeting
    assert "Em que podemos ajudar" in res_greeting

    # Agradecimento
    res_thanks = local_fallback("Muito obrigado pela ajuda!", [], business_name="Oficina Del")
    assert "disposição" in res_thanks or "conte connosco" in res_thanks

    # Informação específica cadastrada
    info_rows = [{
        "kind": "horario",
        "title": "Horário de Funcionamento",
        "content": "Segunda a sexta das 09h às 18h.",
    }]
    res_info = local_fallback("Qual é o horário de funcionamento?", info_rows, business_name="Oficina Del")
    assert "09h às 18h" in res_info

def test_no_booking_system_rules():
    """Garante que as diretrizes do agente proíbem a criação de marcações e proíbem dizer que não faz marcações."""
    instruction = build_system_instruction(
        business_context="Disponibilidade: Segunda a Sexta das 9h às 18h.",
        instructions="",
    )
    assert "NUNCA realiza nem efetua marcações" in instruction
    assert "É TERMINANTEMENTE PROIBIDO dizer ao cliente 'não fazemos marcações'" in instruction
    assert "informe cordialmente os dias e horários de funcionamento" in instruction
    assert "O agente NUNCA efetua marcações" in instruction

def test_no_booking_card_in_frontend():
    """Garante que nenhum card de marcações existe no frontend index.html."""
    from pathlib import Path
    html = (Path(__file__).parent.parent / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "card-metric-bookings" not in html
    assert "bookings-expand-modal" not in html
    assert 'data-tab="board"' not in html
