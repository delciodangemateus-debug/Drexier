import os
import bcrypt
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from dotenv import load_dotenv

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY", "development-only-change-me")
ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("utf-8"))
    except Exception:
        return False

def create_token(user_id: int) -> str:
    # Sessão permanente dentro do software (o utilizador pode mexer por tempo ilimitado)
    exp = datetime.now(timezone.utc) + timedelta(days=365)
    return jwt.encode({"sub": str(user_id), "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)


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
    except (JWTError, KeyError, ValueError):
        return None


def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("purpose") in ("password_reset", "booking"):
            return None
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None


def create_booking_token(user_id: int, contact_id: int, email: str, name: str = "") -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=60)
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
    except (JWTError, KeyError, ValueError):
        return None
