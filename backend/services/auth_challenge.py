"""Short-lived authentication challenges kept in API process memory."""

import hashlib
import hmac
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional


TTL_SECONDS = 10 * 60
MAX_ATTEMPTS = 5


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


def create_auth_challenge(purpose: str, payload: dict[str, Any]) -> tuple[str, str]:
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge_id = uuid.uuid4().hex
    now = time.time()
    with _lock:
        expired = [key for key, item in _challenges.items() if item.expires_at <= now]
        for key in expired:
            del _challenges[key]
        _challenges[challenge_id] = AuthChallenge(
            code_hash=_hash_code(code),
            payload=dict(payload),
            purpose=purpose,
            expires_at=now + TTL_SECONDS,
        )
    return challenge_id, code


def consume_auth_challenge(challenge_id: str, code: str, purpose: str) -> Optional[dict[str, Any]]:
    normalized = "".join(code.split())
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
    with _lock:
        _challenges.pop(challenge_id, None)
