import json
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import init_db, connect
from backend.services.billing_service import _save_stored_subscription
from tests.auth_helpers import signup_and_verify, login_and_verify

@pytest.fixture(autouse=True)
def setup_db():
    init_db()

client = TestClient(app)


# ---------------------------------------------------------------------------
# Utilitário: mock genérico do Gemini (resposta válida com JSON de config)
# ---------------------------------------------------------------------------

def _make_gemini_mock(text: str):
    """Cria um mock de resposta do Gemini com texto arbitrário."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": text}]}}]
    }
    fake_response.raise_for_status = MagicMock()
    return fake_response


GEMINI_CONFIG_STUB = {
    "api_key": "test-key-drexier",
    "model": "gemini-1.5-flash",
    "base_url": "https://generativelanguage.googleapis.com/v1beta",
    "provider": "gemini",
}

# Respostas pré-definidas da IA para cada cenário de teste
GEMINI_REPLY_FIRST_PROMPT = (
    "Excelente! Compreendi a sua visão. Vou configurar um agente comercial e persuasivo com foco em "
    "agendamento de visitas a apartamentos. "
    "```json\n"
    '{"agent_name": "Consultor Imobiliário", "agent_role": "Especialista em Imóveis de Luxo", '
    '"theme_color": "#2563eb", "position": "bottom-right", '
    '"greeting_message": "Olá! Pronto para encontrar o seu imóvel de sonho?", '
    '"agent_instructions": "Foco em agendamento de visitas e persuasão.", '
    '"allowed_domain": "", "ready_to_generate": true}\n```'
)

GEMINI_REPLY_SECOND_PROMPT = (
    "Perfeito! Actualizei para um estilo minimalista em grafite com botão no canto inferior esquerdo. "
    "```json\n"
    '{"agent_name": "Consultor Imobiliário", "agent_role": "Especialista em Imóveis de Luxo", '
    '"theme_color": "#0f172a", "position": "bottom-left", '
    '"greeting_message": "Olá! Como posso ajudar hoje?", '
    '"agent_instructions": "Estilo minimalista, direto e conciso.", '
    '"allowed_domain": "", "ready_to_generate": true}\n```'
)

GEMINI_REPLY_GENERIC = (
    "Compreendi! O seu agente está configurado. "
    "```json\n"
    '{"agent_name": "Assistente Drexier", "agent_role": "Atendente Virtual", '
    '"theme_color": "#6366f1", "position": "bottom-right", '
    '"greeting_message": "Olá! Como posso ajudar hoje?", '
    '"agent_instructions": "", "allowed_domain": "", "ready_to_generate": true}\n```'
)

GEMINI_VISITOR_REPLY = (
    "Olá Maria! Claro, tenho todo o prazer em dar-lhe mais informações sobre o nosso T3 no Chiado. "
    "É um apartamento de luxo com 180m2 e vista para o Tejo. Gostaria de agendar uma visita?"
)


def _create_authenticated_user(name="Website Owner", email=None):
    import time
    if not email:
        email = f"web_owner_{int(time.time() * 1000)}@example.com"
    password = "SecurePassword123"
    signup_and_verify(client, {
        "name": name,
        "email": email,
        "password": password,
        "confirm_password": password,
        "business_type": "Imobiliária de Luxo",
        "business_description": "Venda e arrendamento de imóveis exclusivos em Lisboa e Cascais.",
    })
    auth = login_and_verify(client, email, password)
    user_id = auth.json()["user_id"]
    token = auth.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    _save_stored_subscription(user_id, {
        "status": "active",
        "plan_name": "Plano Business"
    })
    return user_id, headers


# ---------------------------------------------------------------------------
# TESTES
# ---------------------------------------------------------------------------

def test_widget_js_static_route():
    res = client.get("/widget.js")
    assert res.status_code == 200
    assert "drexierSettings" in res.text
    assert "drexier-widget-root" in res.text


def test_get_initial_website_integration():
    user_id, headers = _create_authenticated_user()
    res = client.get("/api/integrations/website", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["exists"] is False
    assert data["status"] == "pending"
    assert "Como imagina o seu agente virtual?" in data["initial_prompt"]


def test_ai_chat_creates_and_configures_agent():
    user_id, headers = _create_authenticated_user()

    # --- Primeira interação ---
    # Patch directo no interact_website_agent_ai para garantir resposta determinística
    prompt = "Quero um agente comercial e persuasivo com foco em agendar visitas a apartamentos, com cor azul royal #2563eb e botão na direita."

    first_cfg = {
        "agent_name": "Consultor Imobiliário",
        "agent_role": "Especialista em Imóveis de Luxo",
        "theme_color": "#2563eb",
        "position": "bottom-right",
        "greeting_message": "Olá! Pronto para encontrar o seu imóvel de sonho?",
        "agent_instructions": "Foco em agendamento de visitas e persuasão.",
        "allowed_domain": "",
    }

    with patch(
        "backend.routers.website.interact_website_agent_ai",
        new_callable=AsyncMock,
        return_value=("Excelente! Agente comercial configurado com cor azul e botão à direita.", first_cfg, True)
    ):
        res = client.post("/api/integrations/website/chat", json={"message": prompt}, headers=headers)

    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    assert len(data["reply"]) > 10

    integration = data["integration"]
    assert integration["status"] == "pending"
    assert integration["site_key"].startswith("drexier_live_sec_")
    assert integration["theme_color"] == "#2563eb"
    assert integration["position"] == "bottom-right"
    assert "widget.js" in data["head_code"]
    assert integration["site_key"] in data["head_code"]

    site_key = integration["site_key"]

    # --- Segunda interação: edição de posição e cor ---
    second_prompt = "Quero alterar a posição para o canto inferior esquerdo e um estilo mais minimalista em grafite #0f172a."

    second_cfg = {
        "agent_name": "Consultor Imobiliário",
        "agent_role": "Especialista em Imóveis de Luxo",
        "theme_color": "#0f172a",
        "position": "bottom-left",
        "greeting_message": "Olá! Como posso ajudar hoje?",
        "agent_instructions": "Estilo minimalista, direto e conciso.",
        "allowed_domain": "",
    }

    with patch(
        "backend.routers.website.interact_website_agent_ai",
        new_callable=AsyncMock,
        return_value=("Actualizado para estilo minimalista em grafite com botão no canto inferior esquerdo.", second_cfg, True)
    ):
        res2 = client.post("/api/integrations/website/chat", json={"message": second_prompt}, headers=headers)

    assert res2.status_code == 200
    data2 = res2.json()

    integration2 = data2["integration"]
    # Garante que o identificador original é preservado
    assert integration2["site_key"] == site_key
    assert integration2["position"] == "bottom-left"
    assert integration2["theme_color"] == "#0f172a"
    # Histórico de conversa preservado
    assert len(integration2["conversation_history"]) >= 4


def test_manual_config_update_and_regenerate():
    user_id, headers = _create_authenticated_user()

    # Cria agente via chat (sem IA real)
    with patch(
        "backend.routers.website.interact_website_agent_ai",
        new_callable=AsyncMock,
        return_value=("Agente criado.", {"agent_name": "Assistente", "theme_color": "#6366f1", "position": "bottom-right", "agent_role": "Atendente", "greeting_message": "Olá!", "agent_instructions": "", "allowed_domain": ""}, True)
    ):
        client.post("/api/integrations/website/chat", json={"message": "Criar agente"}, headers=headers)

    # Atualização manual dos campos
    update_payload = {
        "agent_name": "Consultor Imobiliário VIP",
        "agent_role": "Especialista em Lisboa",
        "greeting_message": "Olá! Seja bem-vindo à nossa seleção de imóveis exclusivos.",
        "theme_color": "#10b981",
        "position": "bottom-right",
        "allowed_domain": "imobiliaria-luxo.pt",
        "agent_instructions": "Trate o cliente com máxima cortesia e solicite o contacto telefónico.",
    }
    res = client.put("/api/integrations/website/config", json=update_payload, headers=headers)
    assert res.status_code == 200
    updated = res.json()
    assert updated["agent_name"] == "Consultor Imobiliário VIP"
    assert updated["agent_role"] == "Especialista em Lisboa"
    assert updated["theme_color"] == "#10b981"
    assert updated["allowed_domain"] == "imobiliaria-luxo.pt"

    # Regenerar código preservando a chave
    orig_key = updated["site_key"]
    regen = client.post("/api/integrations/website/regenerate-code", json={"reset_key": False}, headers=headers)
    assert regen.status_code == 200
    assert regen.json()["site_key"] == orig_key


def test_widget_handshake_and_automatic_active_state():
    user_id, headers = _create_authenticated_user()

    # Inicializa agente via chat
    with patch(
        "backend.routers.website.interact_website_agent_ai",
        new_callable=AsyncMock,
        return_value=("Agente criado para teste.", {"agent_name": "Assistente Teste", "theme_color": "#6366f1", "position": "bottom-right", "agent_role": "Atendente", "greeting_message": "Olá!", "agent_instructions": "", "allowed_domain": ""}, True)
    ):
        init_res = client.post("/api/integrations/website/chat", json={"message": "Criar agente para teste"}, headers=headers)

    site_key = init_res.json()["integration"]["site_key"]

    # Estado inicial: Pendente
    status_before = client.get("/api/integrations/website", headers=headers).json()
    assert status_before["status"] == "pending"

    # Widget carrega no website externo e solicita configuração pública
    widget_conf = client.get(f"/api/widget/config?key={site_key}", headers={"Origin": "https://meusite.com"})
    assert widget_conf.status_code == 200
    conf_data = widget_conf.json()
    assert conf_data["site_key"] == site_key

    # Widget envia ping de batimento cardíaco
    ping_res = client.post("/api/widget/ping", json={
        "site_key": site_key,
        "origin": "https://meusite.com",
        "url": "https://meusite.com/inicio"
    })
    assert ping_res.status_code == 200

    # Estado no Drexier atualizado automaticamente para ATIVO
    status_after = client.get("/api/integrations/website", headers=headers).json()
    assert status_after["status"] == "active"
    assert status_after["last_heartbeat_at"] is not None


def test_domain_security_protection():
    user_id, headers = _create_authenticated_user()

    # Cria e restringe domínio autorizado
    with patch(
        "backend.routers.website.interact_website_agent_ai",
        new_callable=AsyncMock,
        return_value=("Agente criado.", {"agent_name": "Assistente", "theme_color": "#6366f1", "position": "bottom-right", "agent_role": "Atendente", "greeting_message": "Olá!", "agent_instructions": "", "allowed_domain": ""}, True)
    ):
        client.post("/api/integrations/website/chat", json={"message": "Criar agente"}, headers=headers)

    conf = client.put("/api/integrations/website/config", json={"allowed_domain": "empresa-autorizada.com"}, headers=headers).json()
    site_key = conf["site_key"]

    # Tentativa de carregamento a partir de domínio não autorizado
    res_blocked = client.get(f"/api/widget/config?key={site_key}", headers={"Origin": "https://site-invasor.com"})
    assert res_blocked.status_code == 403

    # Estado no Drexier reflete o erro
    status = client.get("/api/integrations/website", headers=headers).json()
    assert status["status"] == "error"
    assert "exclusivos do website" in status["error_message"] or "não autorizado" in status["error_message"].lower()

    # Tentativa com domínio correto tem sucesso imediato
    res_allowed = client.get(f"/api/widget/config?key={site_key}", headers={"Origin": "https://empresa-autorizada.com"})
    assert res_allowed.status_code == 200
    status_ok = client.get("/api/integrations/website", headers=headers).json()
    assert status_ok["status"] == "active"


def test_visitor_chat_records_contact_and_messages():
    user_id, headers = _create_authenticated_user()

    # Adiciona card de conhecimento de negócio
    client.post("/api/business-info", json={
        "kind": "produto",
        "title": "Apartamento T3 Chiado",
        "content": "Apartamento de luxo com 180m2, vista para o Tejo e garagem dupla.",
        "metadata": {"items": [{"name": "Apartamento T3 Chiado", "price": "1.200.000€"}]}
    }, headers=headers)

    # Cria agente para website (mockando Gemini)
    with patch(
        "backend.routers.website.interact_website_agent_ai",
        new_callable=AsyncMock,
        return_value=("Agente criado para T3 Chiado.", {"agent_name": "Assistente Imobiliário", "theme_color": "#6366f1", "position": "bottom-right", "agent_role": "Especialista", "greeting_message": "Olá!", "agent_instructions": "Especializado no T3 Chiado.", "allowed_domain": ""}, True)
    ):
        chat_init = client.post("/api/integrations/website/chat", json={
            "message": "Quero um agente especializado no Apartamento T3 Chiado."
        }, headers=headers).json()

    site_key = chat_init["integration"]["site_key"]

    # Visitante no website externo envia mensagem através do widget
    # Mockamos o draft_reply directamente para evitar chamadas reais ao Gemini
    with patch(
        "backend.routers.website.draft_reply",
        new_callable=AsyncMock,
        return_value=GEMINI_VISITOR_REPLY
    ):
        visitor_res = client.post("/api/widget/chat", json={
            "site_key": site_key,
            "visitor_id": "test_visitor_99",
            "visitor_name": "Maria Silva",
            "message": "Olá! Gostaria de saber mais sobre o T3 no Chiado."
        }, headers={"Origin": "https://meusite.com"})

    assert visitor_res.status_code == 200
    assert "reply" in visitor_res.json()
    reply = visitor_res.json()["reply"]
    assert len(reply) > 5

    # Verifica se o contacto e mensagem foram persistidos no sistema Drexier
    with connect() as c:
        contact = c.execute(
            "SELECT * FROM contacts WHERE user_id=? AND contact_key=?",
            (user_id, f"web_{site_key[:8]}_test_visitor_99")
        ).fetchone()
        assert contact is not None
        assert contact["name"] == "Maria Silva"

        messages = c.execute(
            "SELECT sender, content FROM messages WHERE contact_id=? ORDER BY id ASC",
            (contact["id"],)
        ).fetchall()
        assert len(messages) >= 2
        assert messages[0]["sender"] == "customer"
        assert "Chiado" in messages[0]["content"]
        assert messages[1]["sender"] == "agent"


def test_undo_and_clear_website_instructions():
    user_id, headers = _create_authenticated_user()

    # 1. Cria com primeira instrução
    with patch(
        "backend.routers.website.interact_website_agent_ai",
        new_callable=AsyncMock,
        return_value=("Resposta 1", {"agent_name": "Agente 1", "theme_color": "#2563eb", "position": "bottom-right", "agent_role": "Vendas", "greeting_message": "Olá!", "agent_instructions": "Instrução 1", "allowed_domain": ""}, True)
    ):
        client.post("/api/integrations/website/chat", json={"message": "Instrução inicial"}, headers=headers)

    # 2. Envia segunda instrução
    with patch(
        "backend.routers.website.interact_website_agent_ai",
        new_callable=AsyncMock,
        return_value=("Resposta 2", {"agent_name": "Agente 2", "theme_color": "#0f172a", "position": "bottom-left", "agent_role": "Executivo", "greeting_message": "Olá!", "agent_instructions": "Instrução 2", "allowed_domain": ""}, True)
    ):
        res2 = client.post("/api/integrations/website/chat", json={"message": "Segunda instrução"}, headers=headers).json()

    assert len(res2["integration"]["conversation_history"]) >= 4
    orig_key = res2["integration"]["site_key"]

    # 3. Teste de Retroceder (Undo)
    undo_res = client.post("/api/integrations/website/chat/undo", headers=headers)
    assert undo_res.status_code == 200
    undo_data = undo_res.json()
    assert undo_data["ok"] is True
    assert undo_data["integration"]["site_key"] == orig_key
    # Histórico diminuiu um par de mensagens
    assert len(undo_data["integration"]["conversation_history"]) < len(res2["integration"]["conversation_history"])

    # 4. Teste de Apagar Tudo (Clear)
    clear_res = client.post("/api/integrations/website/chat/clear", headers=headers)
    assert clear_res.status_code == 200
    clear_data = clear_res.json()
    assert clear_data["ok"] is True
    assert clear_data["integration"]["site_key"] == orig_key
    # Histórico voltou apenas para a pergunta inicial e tema ao padrão neutro
    assert len(clear_data["integration"]["conversation_history"]) == 1
    assert "Como imagina o seu agente virtual?" in clear_data["integration"]["conversation_history"][0]["content"]
    assert clear_data["integration"]["theme_color"] == "#18181b"
    assert clear_data["integration"]["position"] == "bottom-right"
