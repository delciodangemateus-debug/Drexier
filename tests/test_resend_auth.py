import sys
import uuid
from types import SimpleNamespace
from unittest.mock import Mock
import hashlib

from fastapi.testclient import TestClient

from backend.main import app
from backend.services import auth_challenge
from backend.services.resend_email import (
    get_resend_config,
    is_resend_test_sender,
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


def test_resend_test_sender_is_detected():
    assert is_resend_test_sender("Drexier <onboarding@resend.dev>")
    assert not is_resend_test_sender("Drexier <no-reply@example.com>")


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

        wrong_code = "000000" if sent_codes[-1][2] != "000000" else "000001"
        rejected = client.post("/api/auth/verify", json={
            "challenge_id": signup_challenge,
            "code": wrong_code,
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


def test_signup_reports_missing_resend_configuration(monkeypatch):
    monkeypatch.setattr(
        "backend.main.send_auth_code_email",
        Mock(return_value={"status": "skipped", "reason": "resend_not_configured"}),
    )

    with TestClient(app) as client:
        response = client.post("/api/auth/signup", json={
            "name": "Resend Test",
            "email": f"resend-missing-{uuid.uuid4().hex}@example.com",
            "password": "SecurePassword123",
            "confirm_password": "SecurePassword123",
            "business_type": "Serviços",
        })

    assert response.status_code == 503
    assert "RESEND_API_KEY" in response.json()["detail"]
    assert "RESEND_FROM_EMAIL" in response.json()["detail"]


def test_signup_reports_resend_delivery_failure(monkeypatch):
    monkeypatch.setenv("RESEND_FROM_EMAIL", "Drexier <hello@example.com>")
    monkeypatch.setattr(
        "backend.main.send_auth_code_email",
        Mock(return_value={"status": "failed", "error": "provider rejected sender"}),
    )

    with TestClient(app) as client:
        response = client.post("/api/auth/signup", json={
            "name": "Resend Test",
            "email": f"resend-failed-{uuid.uuid4().hex}@example.com",
            "password": "SecurePassword123",
            "confirm_password": "SecurePassword123",
            "business_type": "Serviços",
        })

    assert response.status_code == 503
    assert "autorizado no Resend" in response.json()["detail"]


def test_signup_explains_resend_test_sender_restriction(monkeypatch):
    monkeypatch.setenv("RESEND_FROM_EMAIL", "Drexier <onboarding@resend.dev>")
    monkeypatch.setattr(
        "backend.main.send_auth_code_email",
        Mock(return_value={"status": "failed", "error": "recipient not allowed"}),
    )

    with TestClient(app) as client:
        response = client.post("/api/auth/signup", json={
            "name": "Resend Test",
            "email": f"resend-test-sender-{uuid.uuid4().hex}@example.com",
            "password": "SecurePassword123",
            "confirm_password": "SecurePassword123",
            "business_type": "Serviços",
        })

    assert response.status_code == 503
    assert "só permite enviar" in response.json()["detail"]
    assert "domínio verificado" in response.json()["detail"]


def test_auth_challenge_uses_persistent_supabase_store(monkeypatch):
    stored_challenges = {}
    rpc_calls = []

    class FakeQuery:
        def __init__(self, table):
            self.table_name = table
            self.challenge_id = None

        def insert(self, values):
            values.setdefault("attempts", 0)
            stored_challenges[values["challenge_id"]] = values
            return self

        def delete(self):
            return self

        def lt(self, column, value):
            assert column == "expires_at"
            return self

        def eq(self, column, value):
            assert column == "challenge_id"
            self.challenge_id = value
            return self

        def execute(self):
            if self.challenge_id:
                stored_challenges.pop(self.challenge_id, None)
            return SimpleNamespace(data=[])

    class FakeSupabase:
        def table(self, name):
            assert name == "auth_challenges"
            return FakeQuery(name)

        def rpc(self, name, params):
            assert name == "consume_auth_challenge"
            rpc_calls.append(params)

            class FakeRpc:
                def execute(self):
                    challenge = stored_challenges.get(params["p_challenge_id"])
                    if not challenge or challenge["purpose"] != params["p_purpose"]:
                        return SimpleNamespace(data=None)
                    if challenge["code_hash"] != params["p_code_hash"]:
                        challenge["attempts"] += 1
                        return SimpleNamespace(data=None)
                    stored_challenges.pop(params["p_challenge_id"])
                    return SimpleNamespace(data=challenge["payload"])

            return FakeRpc()

    monkeypatch.setattr(auth_challenge, "_uses_supabase_store", lambda: True)
    monkeypatch.setattr(auth_challenge, "_get_supabase_auth_client", lambda: FakeSupabase())

    challenge_id, code = auth_challenge.create_auth_challenge("signup", {"email": "owner@example.com"})

    assert challenge_id in stored_challenges
    assert stored_challenges[challenge_id]["code_hash"] == hashlib.sha256(code.encode()).hexdigest()
    assert code not in str(stored_challenges[challenge_id])
    assert auth_challenge.consume_auth_challenge(challenge_id, "000000", "signup") is None
    assert auth_challenge.consume_auth_challenge(challenge_id, code, "signup") == {
        "email": "owner@example.com"
    }
    assert auth_challenge.consume_auth_challenge(challenge_id, code, "signup") is None
    assert rpc_calls[-1]["p_code_hash"] == hashlib.sha256(code.encode()).hexdigest()
