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
logger = logging.getLogger("drexier.auth_challenge")


class AuthChallengeStoreError(RuntimeError):
    """Raised when the persistent authentication challenge store is unavailable."""


@dataclass
class AuthChallenge:
    code_hash: str
    payload: dict[str, Any]
    purpose: str
    expires_at: float
    attempts: int = 0


_challenges: dict[str, AuthChallenge] = {}
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
            if challenge.attempts >= MAX_ATTEMPTS:
                _challenges.pop(challenge_id, None)
            return None
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
