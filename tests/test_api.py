import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import init_db

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
    # 1. Signup
    email = "testuser@example.com"
    pwd = "SecurePassword123"
    signup_payload = {
        "name": "Maria Silva",
        "email": email,
        "password": pwd,
        "confirm_password": pwd,
        "business_type": "Serviços e vendas"
    }
    res_signup = client.post("/api/auth/signup", json=signup_payload)
    assert res_signup.status_code in [200, 409]

    # 2. Login
    res_login = client.post("/api/auth/login", json={"email": email, "password": pwd})
    assert res_login.status_code == 200
    token = res_login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Get profile
    res_me = client.get("/api/me", headers=headers)
    assert res_me.status_code == 200
    assert res_me.json()["email"] == email

    # 4. Add business info
    info_payload = {
        "kind": "horarios",
        "title": "Horário de Funcionamento",
        "content": "Segunda a Sexta das 09h00 às 18h00. Sábado das 10h00 às 14h00.",
        "metadata": {}
    }
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

    email = "owner_test@example.com"
    pwd = "SecurePassword123"
    client.post("/api/auth/signup", json={
        "name": "Dono da Loja",
        "email": email,
        "password": pwd,
        "confirm_password": pwd,
        "business_type": "Comércio"
    })
    res_login = client.post("/api/auth/login", json={"email": email, "password": pwd})
    token = res_login.json()["token"]
    user_id = res_login.json()["user_id"]
    headers = {"Authorization": f"Bearer {token}"}

    # Conecta integração de e-mail simulada
    with connect() as c:
        c.execute(
            """INSERT INTO email_integrations (user_id, provider, email_address, display_name, status)
               VALUES (?, 'smtp_imap', 'dono@empresa.com', 'Dono da Loja', 'connected')""",
            (user_id,)
        )

    with patch("backend.services.email_service.send_email", new_callable=AsyncMock) as mock_send, \
         patch("backend.services.agent.draft_reply", new_callable=AsyncMock) as mock_draft:
        mock_send.return_value = True
        mock_draft.return_value = "Olá! A sua marcação para amanhã às 14h foi confirmada com sucesso!"

        # Simula mensagem de cliente
        res_msg = client.post("/api/simulate/incoming", json={
            "contact_key": "cliente@externo.com",
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



