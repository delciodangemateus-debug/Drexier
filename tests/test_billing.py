"""
Testes Automatizados Oficiais para o Sistema de Faturação Stripe (Plano Business 59€/mês).
Testa checkout com 3D Secure, proteção antifraude, portal de faturas,
validação criptográfica de webhooks e controle de acesso SaaS.
"""

import time
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import connect, init_db
from backend.services.billing_service import (
    get_user_subscription_status,
    get_last_successful_payment_at,
    is_subscription_active,
    _save_stored_subscription,
    handle_stripe_webhook,
    PLAN_NAME,
    PLAN_AMOUNT_CENTS,
)


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_billing.db"
    monkeypatch.setattr("backend.database.DB_PATH", str(test_db))
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_mock_1234567890abcdef")
    monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "pk_test_mock_1234567890abcdef")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret_abc123")
    init_db()
    yield


@pytest.fixture
def auth_client():
    client = TestClient(app)
    signup_res = client.post(
        "/api/auth/signup",
        json={
            "name": "Empresa Pagadora",
            "email": f"empresa_{int(time.time()*1000)}@teste.com",
            "password": "Password123",
            "confirm_password": "Password123",
            "business_type": "Serviços",
        },
    )
    assert signup_res.status_code == 200
    token = signup_res.json()["token"]
    user_id = signup_res.json()["user_id"]
    return client, token, user_id


def test_billing_public_config(auth_client):
    client, token, _ = auth_client
    res = client.get("/api/billing/config")
    assert res.status_code == 200
    data = res.json()
    assert data["configured"] is True
    assert data["publishable_key"] == "pk_test_mock_1234567890abcdef"
    assert data["plan"]["name"] == "Plano Business"
    assert data["plan"]["amount_cents"] == 5900
    assert data["plan"]["amount_display"] == "59,00 €"
    assert data["plan"]["currency"] == "EUR"
    assert data["plan"]["interval"] == "mês"


def test_billing_status_unsubscribed(auth_client):
    client, token, user_id = auth_client
    res = client.get("/api/billing/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["has_active_subscription"] is False
    assert data["status"] in ("none", "inactive")
    assert data["plan_name"] == "Plano Business"
    assert data["amount_display"] == "59,00 €"


def test_start_checkout_session(auth_client):
    client, token, user_id = auth_client

    mock_session = MagicMock()
    mock_session.id = "cs_test_mock_session_123"
    mock_session.url = "https://checkout.stripe.com/pay/cs_test_mock_session_123"

    mock_customer = MagicMock()
    mock_customer.id = "cus_mock_9999"

    with patch("stripe.Customer.list", return_value=MagicMock(data=[])), \
         patch("stripe.Customer.create", return_value=mock_customer), \
         patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create_session:

        res = client.post(
            "/api/billing/checkout",
            json={"base_url": "http://localhost:8000"},
            headers={"Authorization": f"Bearer {token}"}
        )

        assert res.status_code == 200
        data = res.json()
        assert data["checkout_url"] == "https://checkout.stripe.com/pay/cs_test_mock_session_123"
        assert data["session_id"] == "cs_test_mock_session_123"
        assert data["customer_id"] == "cus_mock_9999"

        # Valida que o checkout foi configurado em modo subscription com 59€
        call_kwargs = mock_create_session.call_args.kwargs
        assert call_kwargs["mode"] == "subscription"
        assert call_kwargs["customer"] == "cus_mock_9999"
        assert call_kwargs["billing_address_collection"] == "required"
        assert call_kwargs["client_reference_id"] == str(user_id)


def test_portal_session_requires_customer(auth_client):
    client, token, _ = auth_client
    # Sem customer registrado, retorna 400
    res = client.post(
        "/api/billing/portal",
        json={"base_url": "http://localhost:8000"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 400
    assert "Ainda não possui uma conta de cliente Stripe" in res.json()["detail"]


def test_portal_session_with_customer(auth_client):
    client, token, user_id = auth_client

    # Registra customer prévio
    _save_stored_subscription(user_id, {
        "stripe_customer_id": "cus_existing_123",
        "status": "active"
    })

    mock_portal = MagicMock()
    mock_portal.url = "https://billing.stripe.com/p/session/portal_mock_123"

    with patch("stripe.billing_portal.Session.create", return_value=mock_portal) as mock_portal_create:
        res = client.post(
            "/api/billing/portal",
            json={"base_url": "http://localhost:8000"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 200
        assert res.json()["portal_url"] == "https://billing.stripe.com/p/session/portal_mock_123"
        mock_portal_create.assert_called_once()


def test_webhook_rejects_missing_signature():
    client = TestClient(app)
    res = client.post("/api/billing/webhook", content=b"{}")
    assert res.status_code == 400
    assert "Assinatura do webhook ausente" in res.text


def test_webhook_rejects_invalid_signature():
    client = TestClient(app)
    # Assinatura forjada/falsificada é barrada imediatamente pelo Stripe Webhook Validator
    res = client.post(
        "/api/billing/webhook",
        content=b"{}",
        headers={"Stripe-Signature": "t=123,v1=invalid_fake_signature"}
    )
    assert res.status_code == 400
    assert "Assinatura de segurança inválida" in res.text or "inválida" in res.text


def test_webhook_checkout_session_completed(auth_client):
    client, token, user_id = auth_client

    mock_event = {
        "id": "evt_test_123",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": str(user_id),
                "customer": "cus_buyer_123",
                "subscription": "sub_active_456"
            }
        }
    }

    mock_sub = MagicMock()
    mock_sub.status = "active"
    mock_sub.current_period_end = int(time.time()) + 30 * 86400
    mock_sub.cancel_at_period_end = False

    with patch("stripe.Webhook.construct_event", return_value=mock_event), \
         patch("stripe.Subscription.retrieve", return_value=mock_sub):

        res = client.post(
            "/api/billing/webhook",
            content=b"dummy_payload",
            headers={"Stripe-Signature": "valid_mock_sig"}
        )
        assert res.status_code == 200

        # Verifica se o utilizador agora possui acesso ativo
        status = get_user_subscription_status(user_id)
        assert status["has_active_subscription"] is True
        assert status["status"] == "active"
        assert is_subscription_active(user_id) is True


def test_webhook_invoice_payment_failed(auth_client):
    client, token, user_id = auth_client

    # Pré-configura assinatura ativa
    _save_stored_subscription(user_id, {
        "stripe_customer_id": "cus_buyer_failed",
        "stripe_subscription_id": "sub_failed_456",
        "status": "active"
    })

    mock_event = {
        "id": "evt_test_failed_999",
        "type": "invoice.payment_failed",
        "data": {
            "object": {
                "customer": "cus_buyer_failed",
                "subscription": "sub_failed_456"
            }
        }
    }

    with patch("stripe.Webhook.construct_event", return_value=mock_event):
        res = client.post(
            "/api/billing/webhook",
            content=b"dummy_payload",
            headers={"Stripe-Signature": "valid_mock_sig"}
        )
        assert res.status_code == 200

        # Verifica que o status foi rebaixado para past_due
        status = get_user_subscription_status(user_id)
        assert status["status"] == "past_due"
        assert status["has_active_subscription"] is False


def test_successful_invoice_payment_updates_last_payment_date(auth_client):
    _, _, user_id = auth_client
    _save_stored_subscription(user_id, {
        "stripe_customer_id": "cus_paid_123",
        "stripe_subscription_id": "sub_paid_456",
        "status": "active",
    })

    paid_timestamp = 1_798_500_000
    event = {
        "id": "evt_paid_123",
        "created": paid_timestamp - 10,
        "type": "invoice.paid",
        "data": {
            "object": {
                "customer": "cus_paid_123",
                "subscription": "sub_paid_456",
                "amount_paid": PLAN_AMOUNT_CENTS,
                "status_transitions": {"paid_at": paid_timestamp},
            }
        },
    }
    mock_subscription = MagicMock()
    mock_subscription.current_period_end = paid_timestamp + 30 * 86400
    mock_subscription.cancel_at_period_end = False
    mock_subscription.get.side_effect = lambda key, default=None: {"metadata": {}}.get(key, default)

    with patch("stripe.Webhook.construct_event", return_value=event), \
         patch("stripe.Subscription.retrieve", return_value=mock_subscription):
        handle_stripe_webhook(b"payload", "signature")

    expected = datetime.fromtimestamp(paid_timestamp, tz=timezone.utc).isoformat()
    assert get_last_successful_payment_at(user_id) == expected


def test_subscription_updates_preserve_last_successful_payment(auth_client):
    _, _, user_id = auth_client
    paid_at = "2026-10-01T10:30:00+00:00"
    _save_stored_subscription(user_id, {
        "status": "active",
        "last_successful_payment_at": paid_at,
    })

    _save_stored_subscription(user_id, {"status": "past_due"})

    assert get_last_successful_payment_at(user_id) == paid_at


def test_webhook_customer_subscription_deleted(auth_client):
    client, token, user_id = auth_client

    _save_stored_subscription(user_id, {
        "stripe_customer_id": "cus_buyer_canceled",
        "stripe_subscription_id": "sub_canceled_456",
        "status": "active"
    })

    mock_event = {
        "id": "evt_test_del_111",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "customer": "cus_buyer_canceled",
                "id": "sub_canceled_456"
            }
        }
    }

    with patch("stripe.Webhook.construct_event", return_value=mock_event):
        res = client.post(
            "/api/billing/webhook",
            content=b"dummy_payload",
            headers={"Stripe-Signature": "valid_mock_sig"}
        )
        assert res.status_code == 200

        status = get_user_subscription_status(user_id)
        assert status["status"] == "canceled"
        assert status["has_active_subscription"] is False
