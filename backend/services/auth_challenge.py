"""Short-lived authentication challenges kept in API process memory."""

import hashlib
import hmac
import logging
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from backend.supabase_client import get_supabase_client, get_supabase_credentials, is_supabase_configured
from backend.database import is_test_environment


TTL_SECONDS = 10 * 60
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60
logger = logging.getLogger("drexier.auth_challenge")


class AuthChallengeStoreError(RuntimeError):
    """Raised when the persistent authentication challenge store is unavailable."""


class AuthCodeLocked(RuntimeError):
    def __init__(self, retry_after: int):
        self.retry_after = max(1, retry_after)
        super().__init__("Foram feitas 5 tentativas inválidas. Tente novamente em 15 minutos.")


@dataclass
class AuthChallenge:
    code_hash: str
    payload: dict[str, Any]
    purpose: str
    expires_at: float
    attempts: int = 0


_challenges: dict[str, AuthChallenge] = {}
_failed_attempts: dict[tuple[str, str], tuple[int, float]] = {}
_lock = threading.Lock()


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _uses_supabase_store() -> bool:
    return not is_test_environment() and is_supabase_configured()


def _get_supabase_auth_client():
    credentials = get_supabase_credentials()
    if not credentials["service_role_key"]:
        raise AuthChallengeStoreError(
            "Configure SUPABASE_SERVICE_ROLE_KEY no servidor para habilitar a confirmação por email."
        )
    client = get_supabase_client(use_service_role=True)
    if client is None:
        raise AuthChallengeStoreError(
            "Não foi possível conectar ao Supabase para iniciar a confirmação por email."
        )
    return client


def get_auth_code_lockout_seconds(email: str, purpose: str) -> int:
    key = (email.strip().lower(), purpose)
    if _uses_supabase_store():
        try:
            result = _get_supabase_auth_client().rpc(
                "auth_code_lockout_seconds",
                {"p_email": key[0], "p_purpose": purpose},
            ).execute()
            seconds = result.data
            if isinstance(seconds, list):
                seconds = seconds[0] if seconds else 0
            if isinstance(seconds, dict):
                seconds = next(iter(seconds.values()), 0)
            return max(0, int(seconds or 0))
        except AuthChallengeStoreError:
            raise
        except Exception as exc:
            logger.exception("Falha ao consultar o bloqueio de códigos no Supabase.")
            raise AuthChallengeStoreError(
                "Não foi possível verificar as tentativas no Supabase. Confira se a migração de autenticação foi aplicada."
            ) from exc

    now = time.time()
    with _lock:
        failure = _failed_attempts.get(key)
        if not failure:
            return 0
        _, locked_until = failure
        if locked_until == 0:
            return 0
        if locked_until <= now:
            _failed_attempts.pop(key, None)
            return 0
        return max(1, int(locked_until - now))


def create_auth_challenge(purpose: str, payload: dict[str, Any]) -> tuple[str, str]:
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge_id = uuid.uuid4().hex
    now = time.time()
    challenge = AuthChallenge(
        code_hash=_hash_code(code),
        payload=dict(payload),
        purpose=purpose,
        expires_at=now + TTL_SECONDS,
    )

    if _uses_supabase_store():
        try:
            client = _get_supabase_auth_client()
            client.table("auth_challenges").delete().lt(
                "expires_at", datetime.now(timezone.utc).isoformat()
            ).execute()
            client.table("auth_challenges").insert({
                "challenge_id": challenge_id,
                "email": str(payload["email"]).strip().lower(),
                "code_hash": challenge.code_hash,
                "payload": challenge.payload,
                "purpose": purpose,
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=TTL_SECONDS)).isoformat(),
            }).execute()
        except AuthChallengeStoreError:
            raise
        except Exception as exc:
            logger.exception("Falha ao persistir o desafio de autenticação no Supabase.")
            raise AuthChallengeStoreError(
                "Falha ao salvar o desafio no Supabase. Confira se supabase_auth_challenges.sql foi aplicado "
                "e se SUPABASE_SERVICE_ROLE_KEY é válida."
            ) from exc
        return challenge_id, code

    with _lock:
        expired = [key for key, item in _challenges.items() if item.expires_at <= now]
        for key in expired:
            del _challenges[key]
        _challenges[challenge_id] = challenge
    return challenge_id, code


def consume_auth_challenge(challenge_id: str, code: str, purpose: str) -> Optional[dict[str, Any]]:
    normalized = "".join(code.split())
    if _uses_supabase_store():
        try:
            result = _get_supabase_auth_client().rpc(
                "consume_auth_challenge",
                {
                    "p_challenge_id": challenge_id,
                    "p_code_hash": _hash_code(normalized),
                    "p_purpose": purpose,
                },
            ).execute()
        except AuthChallengeStoreError:
            raise
        except Exception as exc:
            logger.exception("Falha ao consumir o desafio de autenticação no Supabase.")
            raise AuthChallengeStoreError(
                "Não foi possível validar o código no Supabase. Confira se supabase_auth_challenges.sql foi aplicado "
                "e se SUPABASE_SERVICE_ROLE_KEY é válida."
            ) from exc

        payload = result.data
        if isinstance(payload, list):
            payload = payload[0] if payload else None
        if isinstance(payload, dict) and set(payload) == {"consume_auth_challenge"}:
            payload = payload["consume_auth_challenge"]
        if isinstance(payload, str):
            import json

            payload = json.loads(payload)
        if isinstance(payload, dict) and payload.get("status") == "locked":
            raise AuthCodeLocked(int(payload.get("retry_after", LOCKOUT_SECONDS)))
        if isinstance(payload, dict) and payload.get("status") == "ok":
            result_payload = payload.get("payload")
            return result_payload if isinstance(result_payload, dict) else None
        if isinstance(payload, dict) and payload.get("status") in {"invalid", "expired"}:
            return None
        return payload if isinstance(payload, dict) else None

    with _lock:
        challenge = _challenges.get(challenge_id)
        if not challenge:
            return None
        if challenge.purpose != purpose:
            return None
        if challenge.expires_at <= time.time():
            _challenges.pop(challenge_id, None)
            return None
        if not hmac.compare_digest(challenge.code_hash, _hash_code(normalized)):
            challenge.attempts += 1
            key = (str(challenge.payload["email"]).strip().lower(), purpose)
            failed_count, locked_until = _failed_attempts.get(key, (0, 0.0))
            if locked_until > time.time():
                raise AuthCodeLocked(int(locked_until - time.time()))
            failed_count += 1
            if failed_count >= MAX_ATTEMPTS:
                locked_until = time.time() + LOCKOUT_SECONDS
                _failed_attempts[key] = (failed_count, locked_until)
                _challenges.pop(challenge_id, None)
                raise AuthCodeLocked(LOCKOUT_SECONDS)
            _failed_attempts[key] = (failed_count, 0.0)
            return None
        _failed_attempts.pop((str(challenge.payload["email"]).strip().lower(), purpose), None)
        _challenges.pop(challenge_id, None)
        return challenge.payload


def invalidate_auth_challenge(challenge_id: str) -> None:
    if _uses_supabase_store():
        try:
            _get_supabase_auth_client().table("auth_challenges").delete().eq(
                "challenge_id", challenge_id
            ).execute()
        except AuthChallengeStoreError:
            raise
        except Exception as exc:
            logger.exception("Falha ao remover o desafio de autenticação do Supabase.")
            raise AuthChallengeStoreError(
                "Não foi possível limpar o desafio de autenticação no Supabase."
            ) from exc
        return

    with _lock:
        _challenges.pop(challenge_id, None)
