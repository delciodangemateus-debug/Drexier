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


def test_dashboard_uses_consecutive_24_hour_windows_and_week_schedule():
    from datetime import datetime, timedelta, timezone
    import time
    from backend.main import _dashboard_cache

    email = f"dashboard_week_{int(time.time() * 1000)}@example.com"
    password = "SecurePassword123"
    signup_and_verify(client, {
        "name": "Dashboard Semana",
        "email": email,
        "password": password,
        "confirm_password": password,
        "business_type": "Serviços",
    })
    auth = login_and_verify(client, email, password)
    user_id = auth.json()["user_id"]
    headers = {"Authorization": f"Bearer {auth.json()['token']}"}

    now = datetime.now(timezone.utc)
    contact_ids = {}
    with connect() as c:
        for key, age in (("last24h", 5), ("previous24h", 30), ("older", 50)):
            created_at = (now - timedelta(hours=age)).strftime("%Y-%m-%d %H:%M:%S")
            contact_ids[key] = c.execute(
                """INSERT INTO contacts(user_id, name, contact_key, created_at)
                   VALUES (?, ?, ?, ?)""",
                (user_id, key, f"{key}@example.com", created_at),
            ).lastrowid

        for key, status, days_ahead in (
            ("previous24h", "confirmed", 1),
            ("last24h", "pending", 2),
            ("older", "pending", 8),
        ):
            c.execute(
                """INSERT INTO conversion_requests
                   (user_id, contact_id, request_type, details, status, scheduled_at)
                   VALUES (?, ?, 'booking', 'Consulta', ?, ?)""",
                (
                    user_id,
                    contact_ids[key],
                    status,
                    (now + timedelta(days=days_ahead)).isoformat(),
                ),
            )

    _dashboard_cache.clear()
    response = client.get("/api/dashboard", headers=headers)
    assert response.status_code == 200
    dashboard = response.json()
    assert dashboard["today_contacts"] == 1
    assert dashboard["yesterday_contacts"] == 1
    assert dashboard["bookings_count"] == 2
    assert [row["name"] for row in dashboard["confirmed_bookings"]] == [
        "previous24h",
        "last24h",
    ]
    assert [row["scheduled_at"] for row in dashboard["confirmed_bookings"]] == [
        (now + timedelta(days=1)).isoformat(),
        (now + timedelta(days=2)).isoformat(),
    ]
    assert all("with_whom" not in row for row in dashboard["confirmed_bookings"])


def test_requested_weekday_and_morning_time_are_parsed_as_the_reserved_datetime():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from backend.services.email_service import extract_scheduled_at

    now = datetime(2026, 11, 14, 12, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
    requested = "Quero a marcação para segunda-feira às 8 horas da manhã com o senhor Cordeiro."

    assert extract_scheduled_at(requested, now) == "2026-11-16T08:00:00+00:00"


def test_business_info_cards_persist_and_keep_multiple_custom_cards():
    import time

    email = f"business_cards_{int(time.time() * 1000)}@example.com"
    password = "SecurePassword123"
    signup = signup_and_verify(client, {
        "name": "Business Cards",
        "email": email,
        "password": password,
        "confirm_password": password,
        "business_type": "Serviços e vendas",
    })
    assert signup.status_code == 200
    auth = login_and_verify(client, email, password)
    headers = {"Authorization": f"Bearer {auth.json()['token']}"}
    _save_stored_subscription(auth.json()["user_id"], {
        "status": "active",
        "plan_name": "Plano Business",
    })

    payload = {
        "kind": "personalizado",
        "title": "Informação Personalizada",
        "content": "Detalhes da operação",
        "metadata": {"items": [{"name": "Item de teste"}], "generalNote": "Nota inicial"},
    }
    first = client.post("/api/business-info", json=payload, headers=headers)
    second = client.post("/api/business-info", json=payload | {"title": "Segundo Card"}, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    first_id = first.json()["id"]
    second_id = second.json()["id"]
    assert first_id != second_id

    update_payload = {
        **payload,
        "title": "Card Atualizado",
        "content": "Dados salvos",
        "metadata": {"items": [{"name": "Item atualizado"}], "generalNote": "Nota salva"},
    }
    updated = client.put(f"/api/business-info/{first_id}", json=update_payload, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["metadata"]["items"][0]["name"] == "Item atualizado"

    listed = client.get("/api/business-info", headers=headers)
    assert listed.status_code == 200
    listed_cards = {item["id"]: item for item in listed.json()}
    assert listed_cards[first_id]["title"] == "Card Atualizado"
    assert listed_cards[first_id]["metadata"]["generalNote"] == "Nota salva"
    assert listed_cards[second_id]["title"] == "Segundo Card"

    deleted = client.delete(f"/api/business-info/{first_id}", headers=headers)
    assert deleted.status_code == 200
    remaining = client.get("/api/business-info", headers=headers).json()
    assert [item["id"] for item in remaining] == [second_id]


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
               VALUES (?, 'google', 'dono@empresa.com', 'Dono da Loja', 'connected')""",
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


def test_conversation_reports_are_generated_on_demand_and_adopted_style_can_be_undone(monkeypatch):
    import time
    import backend.services.analytics as analytics

    email = f"reports_{int(time.time() * 1000)}@example.com"
    password = "SecurePassword123"
    signup_and_verify(client, {
        "name": "Relatórios",
        "email": email,
        "password": password,
        "confirm_password": password,
        "business_type": "Serviços e vendas",
    })
    auth = login_and_verify(client, email, password)
    user_id = auth.json()["user_id"]
    headers = {"Authorization": f"Bearer {auth.json()['token']}"}
    _save_stored_subscription(user_id, {"status": "active", "plan_name": "Plano Business"})

    with connect() as conn:
        contact_id = conn.execute(
            "INSERT INTO contacts(user_id, name, contact_key) VALUES (?, ?, ?)",
            (user_id, "Cliente teste", f"{email}"),
        ).lastrowid
        conn.execute(
            "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'customer', ?)",
            (user_id, contact_id, "Quero comprar a consulta inicial."),
        )
        conn.execute(
            "INSERT INTO messages(user_id, contact_id, sender, content) VALUES (?, ?, 'agent', ?)",
            (user_id, contact_id, "A consulta inicial custa 40 euros. Quer marcar?"),
        )
        conn.execute(
            """INSERT INTO conversion_requests(user_id, contact_id, request_type, details, status)
               VALUES (?, ?, 'booking', 'Consulta inicial', 'confirmed')""",
            (user_id, contact_id),
        )
        conn.execute(
            "UPDATE users SET agent_instructions=? WHERE id=?",
            ("Postura personalizada", user_id),
        )

    async def fake_gemini(**kwargs):
        prompt = kwargs["contents"][0]["parts"][0]["text"]
        assert "consulta inicial" in prompt
        if "identifique somente produtos" in prompt:
            return '{"items":[{"name":"Consulta inicial","type":"Serviço","result":"Vendido","count":1}]}'
        return (
            '{"successful":[{"label":"Preço claro e pergunta de fecho",'
            '"description":"Apresenta o valor e propõe marcação.",'
            '"evidence":"O pedido foi confirmado."}],'
            '"abandoned":[],"recommended_style":"Indique preços registados e proponha o próximo passo."}'
        )

    monkeypatch.setattr(analytics, "get_gemini_config", lambda: {
        "api_key": "test-key", "model": "test-model", "base_url": "https://example.test",
    })
    monkeypatch.setattr(analytics, "call_gemini_api", fake_gemini)

    before = client.get("/api/analytics", headers=headers).json()
    assert "top_products" not in before
    assert "best_approaches" not in before

    products = client.post("/api/reports/products-services", json={}, headers=headers)
    assert products.status_code == 200
    assert products.json()["items"][0]["name"] == "Consulta inicial"

    approaches = client.post("/api/reports/approaches", json={}, headers=headers)
    assert approaches.status_code == 200
    style = approaches.json()["recommended_style"]
    assert style

    adopted = client.post(
        "/api/reports/adopted-approach",
        json={"style": style},
        headers=headers,
    )
    assert adopted.status_code == 200
    profile = client.get("/api/me", headers=headers).json()
    assert profile["agent_adopted_style"] == style
    assert profile["agent_instructions"] == "Postura personalizada"

    undone = client.delete("/api/reports/adopted-approach", headers=headers)
    assert undone.status_code == 200
    profile = client.get("/api/me", headers=headers).json()
    assert profile["agent_adopted_style"] == ""
    assert profile["agent_instructions"] == "Postura personalizada"
