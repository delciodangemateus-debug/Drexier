from fastapi.testclient import TestClient

from backend.main import app


def signup_and_verify(client: TestClient, payload: dict):
    response = client.post("/api/auth/signup", json=payload)
    assert response.status_code == 200, response.text
    challenge = response.json()
    code = app.state.test_auth_codes[(payload["email"].lower(), "signup")]
    verified = client.post("/api/auth/verify", json={
        "challenge_id": challenge["challenge_id"],
        "code": code,
    })
    assert verified.status_code == 200, verified.text
    return verified


def login_and_verify(client: TestClient, email: str, password: str):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    challenge = response.json()
    code = app.state.test_auth_codes[(email.lower(), "login")]
    verified = client.post("/api/auth/verify", json={
        "challenge_id": challenge["challenge_id"],
        "code": code,
    })
    assert verified.status_code == 200, verified.text
    return verified
