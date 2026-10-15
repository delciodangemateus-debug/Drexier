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

