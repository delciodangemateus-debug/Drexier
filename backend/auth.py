import os
import sys
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import jwt
from jwt.exceptions import InvalidTokenError
from dotenv import load_dotenv

load_dotenv()


def is_test_environment() -> bool:
    return bool(
        "pytest" in sys.modules
        or os.getenv("PYTEST_CURRENT_TEST")
        or os.getenv("DREXIER_TEST_MODE") == "1"
    )


SECRET_KEY = os.getenv("SECRET_KEY", "development-only-change-me")
if (os.getenv("APP_ENV") == "production" or os.getenv("ENVIRONMENT") == "production") and not is_test_environment():
    if not SECRET_KEY or SECRET_KEY in ("development-only-change-me", "change-this-to-a-long-random-secret-before-use"):
        raise RuntimeError("SECRET_KEY de produção não configurada ou insegura!")

ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > 72:
        raise ValueError("A palavra-passe não pode exceder 72 caracteres.")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    try:
        pwd_bytes = password.encode("utf-8")
        if len(pwd_bytes) > 72:
            return False
        return bcrypt.checkpw(pwd_bytes, hashed.encode("utf-8"))
    except Exception:
        return False

def create_token(user_id: int, token_version: int = 1) -> str:
    # Sessão ativa por até 7 dias (com suporte a revogação instantânea via token_version)
    exp = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {"sub": str(user_id), "v": int(token_version or 1), "exp": exp}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_token_claims(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except (InvalidTokenError, KeyError, ValueError, Exception):
        return None


def create_password_reset_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=10)
    return jwt.encode(
        {"sub": str(user_id), "purpose": "password_reset", "exp": exp},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_password_reset_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("purpose") != "password_reset":
            return None
        return int(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError, Exception):
        return None


def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("purpose") in ("password_reset", "booking"):
            return None
        return int(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError, Exception):
        return None


def create_booking_token(user_id: int, contact_id: int, email: str, name: str = "") -> str:
    # Token de booking expira em 48 horas (H2: reduzido de 60 dias para 48 horas)
    exp = datetime.now(timezone.utc) + timedelta(hours=48)
    payload = {
        "sub": str(user_id),
        "contact_id": int(contact_id),
        "email": str(email),
        "name": str(name or ""),
        "purpose": "booking",
        "exp": exp,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_booking_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("purpose") != "booking":
            return None
        return {
            "user_id": int(payload["sub"]),
            "contact_id": int(payload["contact_id"]),
            "email": str(payload.get("email", "")),
            "name": str(payload.get("name", "")),
        }
    except (InvalidTokenError, KeyError, ValueError, Exception):
        return None
