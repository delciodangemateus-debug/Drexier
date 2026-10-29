import pytest

from backend.main import app


@pytest.fixture(autouse=True)
def capture_auth_codes(monkeypatch):
    sent_codes = {}

    def send_auth_code(email, name, code, purpose):
        sent_codes[(email.lower(), purpose)] = code
        return {"status": "sent", "id": "test-email-id"}

    monkeypatch.setattr("backend.main.send_auth_code_email", send_auth_code)
    app.state.test_auth_codes = sent_codes
    yield
    del app.state.test_auth_codes
