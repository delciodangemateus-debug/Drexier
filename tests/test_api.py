import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import init_db, connect
from backend.services.billing_service import _save_stored_subscription
from tests.auth_helpers import login_and_verify, signup_and_verify

@pytest.fixture(autouse=True)
def setup_db():
    init_db()

client = TestClient(app)

def test_static_routes():
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "Drexier" in res_root.text

    res_css = client.get("/styles.css")
    assert res_css.status_code == 200

    res_js = client.get("/app.js")
    assert res_js.status_code == 200

def test_full_auth_and_business_flow():
    import time
    # 1. Signup com email exclusivo para garantir isolamento do teste
    email = f"testuser_{int(time.time()*1000)}@example.com"
    pwd = "SecurePassword123"
    signup_payload = {
        "name": "Maria Silva",
        "email": email,
        "password": pwd,
        "confirm_password": pwd,
        "business_type": "Serviços e vendas"
    }
    res_signup = signup_and_verify(client, signup_payload)
    assert res_signup.status_code == 200

    # 2. Login
    res_login = login_and_verify(client, email, pwd)
    token = res_login.json()["token"]
    user_id = res_login.json()["user_id"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Get profile
    res_me = client.get("/api/me", headers=headers)
    assert res_me.status_code == 200
    assert res_me.json()["email"] == email

    # 3.1 Verificação de Paywall: antes de subscrever, adicionar info é bloqueado com 402
    info_payload = {
        "kind": "horarios",
        "title": "Horário de Funcionamento",
        "content": "Segunda a Sexta das 09h00 às 18h00. Sábado das 10h00 às 14h00.",
        "metadata": {}
    }
    res_blocked = client.post("/api/business-info", json=info_payload, headers=headers)
    assert res_blocked.status_code == 402

    # 3.2 Ativação do Plano Business (59€/mês) para o utilizador
    _save_stored_subscription(user_id, {"status": "active", "plan_name": "Plano Business"})

    # 4. Add business info (agora com plano ativo, sucesso 200)
    res_info = client.post("/api/business-info", json=info_payload, headers=headers)
    assert res_info.status_code == 200
    info_id = res_info.json()["id"]

    # 5. Simulate incoming message from customer
    msg_payload = {
        "contact_key": "+351912345678",
        "customer_name": "João Pereira",
        "message": "Qual é o vosso horário de funcionamento na sexta-feira?"
    }
    res_msg = client.post("/api/simulate/incoming", json=msg_payload, headers=headers)
    assert res_msg.status_code == 200
    contact_id = res_msg.json()["contact_id"]
    reply = res_msg.json()["reply"]
    assert "Horário de Funcionamento" in reply or "09h00" in reply

    # 6. Check contacts list
    res_contacts = client.get("/api/contacts", headers=headers)
    assert res_contacts.status_code == 200
    assert any(c["contact_key"] == "+351912345678" for c in res_contacts.json())

    # 7. Check message history for contact
    res_history = client.get(f"/api/contacts/{contact_id}/messages", headers=headers)
    assert res_history.status_code == 200
    assert len(res_history.json()) >= 2

    # 8. Record conversion request
    res_conv = client.post(f"/api/contacts/{contact_id}/conversion", json={
        "request_type": "booking",
        "details": "Marcação para sexta às 11h"
    }, headers=headers)
    assert res_conv.status_code == 200
    conv_id = res_conv.json()["id"]

    # 9. Check dashboard
    res_dash = client.get("/api/dashboard", headers=headers)
    assert res_dash.status_code == 200
    dash_data = res_dash.json()
    assert dash_data["pending_count"] >= 1

    # 10. Resolve conversion
    res_resolve = client.post(f"/api/conversions/{conv_id}/resolve", headers=headers)
    assert res_resolve.status_code == 200

    # 11. Check analytics
    res_analytics = client.get("/api/analytics", headers=headers)
    assert res_analytics.status_code == 200
    assert "acquisitions" in res_analytics.json()

    # 12. Update agent settings
    res_agent = client.put("/api/agent-settings", json={
        "instructions": "Seja cordial e atencioso.",
        "mandatory_responses": {"greeting": "Olá! Como posso ajudar?"}
    }, headers=headers)
    assert res_agent.status_code == 200

    # 13. Delete individual message
    messages = client.get(f"/api/contacts/{contact_id}/messages", headers=headers).json()
    first_msg_id = messages[0]["id"]
    res_del_msg = client.delete(f"/api/messages/{first_msg_id}", headers=headers)
    assert res_del_msg.status_code == 200
    messages_after = client.get(f"/api/contacts/{contact_id}/messages", headers=headers).json()
    assert len(messages_after) == len(messages) - 1

    # 14. Delete entire contact/conversation
    res_del_contact = client.delete(f"/api/contacts/{contact_id}", headers=headers)
    assert res_del_contact.status_code == 200
    contacts_after = client.get("/api/contacts", headers=headers).json()
    assert not any(c["id"] == contact_id for c in contacts_after)


def test_owner_reply_and_conversion_actions():
    from unittest.mock import patch, AsyncMock
    from backend.database import connect

    import time
    email = f"owner_test_{int(time.time()*1000)}@example.com"
    contact_key = f"cliente_{int(time.time()*1000)}@externo.com"
    pwd = "SecurePassword123"
    signup_and_verify(client, {
        "name": "Dono da Loja",
        "email": email,
        "password": pwd,
        "confirm_password": pwd,
        "business_type": "Comércio"
    })
    res_login = login_and_verify(client, email, pwd)
    token = res_login.json()["token"]
    user_id = res_login.json()["user_id"]
    headers = {"Authorization": f"Bearer {token}"}

    # Conecta integração de e-mail simulada e ativa assinatura
    with connect() as c:
        c.execute("DELETE FROM email_integrations WHERE user_id=?", (user_id,))
        c.execute(
            """INSERT INTO email_integrations (user_id, provider, email_address, display_name, status)
               VALUES (?, 'smtp_imap', 'dono@empresa.com', 'Dono da Loja', 'connected')""",
            (user_id,)
        )
    _save_stored_subscription(user_id, {"status": "active", "plan_name": "Plano Business"})

    with patch("backend.services.email_service.send_email", new_callable=AsyncMock) as mock_send, \
         patch("backend.services.agent.draft_reply", new_callable=AsyncMock) as mock_draft:
        mock_send.return_value = True
        mock_draft.return_value = "Olá! A sua marcação para amanhã às 14h foi confirmada com sucesso!"

        # Simula mensagem de cliente
        res_msg = client.post("/api/simulate/incoming", json={
            "contact_key": contact_key,
            "customer_name": "Ana Silva",
            "message": "Gostaria de agendar para amanhã às 14h"
        }, headers=headers)
        assert res_msg.status_code == 200
        contact_id = res_msg.json()["contact_id"]

        # 1. Proprietário envia resposta manual diretamente
        res_reply = client.post(f"/api/contacts/{contact_id}/reply", json={
            "message": "Olá Ana, vou verificar a nossa disponibilidade para si."
        }, headers=headers)
        assert res_reply.status_code == 200
        messages = client.get(f"/api/contacts/{contact_id}/messages", headers=headers).json()
        owner_msgs = [m for m in messages if m["sender"] == "owner"]
        assert len(owner_msgs) == 1
        assert "Olá Ana" in owner_msgs[0]["content"]

        # 2. Cria pedido de conversão pendente
        res_conv = client.post(f"/api/contacts/{contact_id}/conversion", json={
            "request_type": "marcação",
            "details": "Marcação para amanhã às 14h"
        }, headers=headers)
        conv_id = res_conv.json()["id"]

        # 3. Ação de confirmar pedido com IA
        res_action_confirm = client.post(f"/api/conversions/{conv_id}/action", json={
            "action": "confirm",
            "note": "Horário reservado com sucesso"
        }, headers=headers)
        assert res_action_confirm.status_code == 200
        assert res_action_confirm.json()["action"] == "confirm"

def test_training_document_upload_and_isolated_topics():
    import time
    email = f"training_test_{int(time.time()*1000)}@example.com"
    pwd = "SecurePassword123"
    signup_and_verify(client, {
        "name": "Gestor de Treinamento",
        "email": email,
        "password": pwd,
        "confirm_password": pwd,
        "business_type": "Comércio"
    })
    res_login = login_and_verify(client, email, pwd)
    token = res_login.json()["token"]
    user_id = res_login.json()["user_id"]
    headers = {"Authorization": f"Bearer {token}"}

    # Ativa assinatura do Plano Business para o teste
    _save_stored_subscription(user_id, {"status": "active", "plan_name": "Plano Business"})

    # 1. Teste de upload de documento em texto plano
    file_content = b"Regulamento Interno da Empresa 2026.\nArtigo 1: Os clientes tem 15 dias de garantia total.\nArtigo 2: Entregas gratuitas em compras superiores a 50 euros."
    files = {"file": ("regulamento_loja.txt", file_content, "text/plain")}
    res_upload = client.post("/api/business-info/upload-document", files=files, headers=headers)
    assert res_upload.status_code == 200
    data = res_upload.json()
    assert "Regulamento Loja" in data["suggested_title"]
    assert "garantia total" in data["text"]
    assert data["word_count"] > 10

    # 2. Salva como tópico de treinamento isolado
    res_create = client.post("/api/business-info", json={
        "kind": "treinamento",
        "title": data["suggested_title"],
        "content": data["text"],
        "metadata": {
            "is_isolated_topic": True,
            "filename": data["filename"],
            "word_count": data["word_count"]
        }
    }, headers=headers)
    assert res_create.status_code == 200
    created = res_create.json()
    assert created["kind"] == "treinamento"
    assert created["metadata"]["is_isolated_topic"] is True


def test_paywall_strict_enforcement():
    """
    Ponto Crítico: Garante que utilizadores registados SEM subscrição ativa
    conseguem navegar e ver o painel, mas são estritamente bloqueados com 402
    em: adicionar dados à loja, dar instruções à IA, upload de documentos e integrações.
    """
    import time
    email = f"paywall_test_{int(time.time()*1000)}@example.com"
    pwd = "SecurePassword123"

    # 1. Utilizador cria conta normalmente
    res_signup = signup_and_verify(client, {
        "name": "Cliente Sem Plano",
        "email": email,
        "password": pwd,
        "confirm_password": pwd,
        "business_type": "Comércio"
    })
    assert res_signup.status_code == 200

    # 2. Utilizador entra na conta normalmente
    res_login = login_and_verify(client, email, pwd)
    assert res_login.status_code == 200
    token = res_login.json()["token"]
    user_id = res_login.json()["user_id"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Leitura do perfil e dashboard permitidos normalmente
    assert client.get("/api/me", headers=headers).status_code == 200
    assert client.get("/api/dashboard", headers=headers).status_code == 200
    assert client.get("/api/contacts", headers=headers).status_code == 200

    # 4. Tentar adicionar dados da loja -> BLOQUEADO 402
    res_biz = client.post("/api/business-info", json={
        "kind": "productos", "title": "Produto Teste", "content": "10€", "metadata": {}
    }, headers=headers)
    assert res_biz.status_code == 402
    assert "SUBSCRIPTION_REQUIRED" in str(res_biz.json())

    # 5. Tentar dar instruções ao agente IA -> BLOQUEADO 402
    res_agent = client.put("/api/agent-settings", json={
        "instructions": "Seja gentil com todos os clientes.",
        "mandatory_responses": {}
    }, headers=headers)
    assert res_agent.status_code == 402

    # 6. Tentar fazer upload de documento de treino -> BLOQUEADO 402
    files = {"file": ("manual.txt", b"Regras da loja...", "text/plain")}
    res_doc = client.post("/api/business-info/upload-document", files=files, headers=headers)
    assert res_doc.status_code == 402

    # 7. Tentar iniciar integração de e-mail (OAuth Google) -> BLOQUEADO 402
    res_oauth = client.get("/api/email/oauth/google/url", headers=headers)
    assert res_oauth.status_code == 402

    # 8. Tentar acionar sincronização de e-mails -> BLOQUEADO 402
    res_sync = client.post("/api/email/sync", headers=headers)
    assert res_sync.status_code == 402

    # 9. Tentar simular atendimento com IA -> BLOQUEADO 402
    res_sim = client.post("/api/simulate/incoming", json={
        "contact_key": "cliente@teste.com",
        "customer_name": "Cliente",
        "message": "Olá!"
    }, headers=headers)
    assert res_sim.status_code == 402

    # 10. Agora o utilizador subscreve o Plano Business (59€/mês)
    _save_stored_subscription(user_id, {"status": "active", "plan_name": "Plano Business"})

    # 11. Tudo passa a ser permitido com sucesso (200)
    res_biz_ok = client.post("/api/business-info", json={
        "kind": "productos", "title": "Produto Teste", "content": "10€", "metadata": {}
    }, headers=headers)
    assert res_biz_ok.status_code == 200

    res_agent_ok = client.put("/api/agent-settings", json={
        "instructions": "Seja gentil com todos os clientes.",
        "mandatory_responses": {}
    }, headers=headers)
    assert res_agent_ok.status_code == 200



