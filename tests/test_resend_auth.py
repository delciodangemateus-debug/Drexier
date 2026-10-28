import sys
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.resend_email import (
    get_resend_config,
    send_account_created_email,
    send_login_confirmation_email,
)


class FakeEmails:
    send = Mock(return_value={"id": "email_123"})


fake_resend = SimpleNamespace(api_key=None, Emails=FakeEmails)


def test_resend_config_is_loaded_from_environment(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "Drexier <hello@example.com>")

    assert get_resend_config().api_key == "re_test_key"
    assert get_resend_config().from_email == "Drexier <hello@example.com>"


def test_account_email_is_sent_through_resend(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "Drexier <hello@example.com>")
    monkeypatch.setitem(sys.modules, "resend", fake_resend)
    FakeEmails.send.reset_mock()

    result = send_account_created_email("owner@example.com", "Maria")

    assert result == {"status": "sent", "id": "email_123"}
    payload = FakeEmails.send.call_args.args[0]
    assert payload["to"] == ["owner@example.com"]
    assert payload["from"] == "Drexier <hello@example.com>"
    assert "Conta criada" in payload["subject"]
    assert "Maria" in payload["html"]


def test_login_email_escapes_session_metadata(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "Drexier <hello@example.com>")
    monkeypatch.setitem(sys.modules, "resend", fake_resend)
    FakeEmails.send.reset_mock()

    send_login_confirmation_email(
        "owner@example.com",
        "Maria",
        ip_address="192.0.2.10",
        user_agent="Browser</td><script>alert(1)</script>",
    )

    payload = FakeEmails.send.call_args.args[0]
    assert "192.0.2.10" in payload["html"]
    assert "<script>" not in payload["html"]
    assert "Browser&lt;/td&gt;" in payload["html"]


def test_signup_and_login_require_resend_codes(monkeypatch):
    sent_codes = []

    def send_code(email, name, code, purpose):
        sent_codes.append((email, name, code, purpose))
        return {"status": "sent", "id": "email_123"}

    account_mock = Mock()
    login_mock = Mock()
    monkeypatch.setattr("backend.main.send_auth_code_email", send_code)
    monkeypatch.setattr("backend.main.send_account_created_email", account_mock)
    monkeypatch.setattr("backend.main.send_login_confirmation_email", login_mock)

    email = f"resend-auth-{uuid.uuid4().hex}@example.com"
    with TestClient(app) as client:
        signup = client.post("/api/auth/signup", json={
            "name": "Resend Test",
            "email": email,
            "password": "SecurePassword123",
            "confirm_password": "SecurePassword123",
            "business_type": "Serviços",
        })
        assert signup.status_code == 200
        assert signup.json()["challenge_required"] is True
        signup_challenge = signup.json()["challenge_id"]
        assert len(sent_codes[-1][2]) == 6
        assert sent_codes[-1][2].isdigit()

        rejected = client.post("/api/auth/verify", json={
            "challenge_id": signup_challenge,
            "code": "000000",
        })
        assert rejected.status_code == 400

        verified = client.post("/api/auth/verify", json={
            "challenge_id": signup_challenge,
            "code": sent_codes[-1][2],
        })
        assert verified.status_code == 200, verified.text
        assert verified.json()["token"]

        login = client.post(
            "/api/auth/login",
            json={"email": email, "password": "SecurePassword123"},
            headers={"user-agent": "Test Browser"},
        )
        assert login.status_code == 200
        assert login.json()["challenge_required"] is True

        verified_login = client.post("/api/auth/verify", json={
            "challenge_id": login.json()["challenge_id"],
            "code": sent_codes[-1][2],
        })
        assert verified_login.status_code == 200
        assert verified_login.json()["token"]

    assert [item[3] for item in sent_codes] == ["signup", "login"]
    assert account_mock.call_count == 1
    assert login_mock.call_count == 1
    assert login_mock.call_args.kwargs["user_agent"] == "Test Browser"
