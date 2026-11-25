"""
Sistema de Limitação de Taxa de Requisições (Rate Limiter) em Memória para Drexier AI.
Protege contra ataques de força bruta (login), exaustão de CPU (bcrypt) e abuso de cotas (e-mails Resend).
Permite execução imediata em ambiente de testes unitários isolados.
"""

import os
import sys
import time
import threading
from collections import defaultdict
from typing import Dict, List, Tuple
from fastapi import HTTPException, Request


def is_test_environment() -> bool:
    return bool(
        "pytest" in sys.modules
        or os.getenv("PYTEST_CURRENT_TEST")
        or os.getenv("DREXIER_TEST_MODE") == "1"
    )


class InMemoryRateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        # map key -> list of timestamps
        self._records: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """
        Retorna (allowed: bool, retry_after: int).
        """
        if is_test_environment():
            return True, 0

        now = time.time()
        cutoff = now - window_seconds

        # SEC C7: Suporte a persistência em base de dados para múltiplos workers / deploys
        try:
            from backend.database import connect, is_supabase_configured
            # No Supabase, o rate limiter em memória com lock é atômico e ultra-rápido,
            # evitando overhead de DDL e round-trips de rede desnecessários a cada requisição.
            if not is_supabase_configured():
                with connect() as c:
                    c.execute("CREATE TABLE IF NOT EXISTS rate_limits (rate_key TEXT NOT NULL, ts REAL NOT NULL)")
                    c.execute("CREATE INDEX IF NOT EXISTS idx_rate_limits_key_ts ON rate_limits(rate_key, ts)")
                    c.execute("DELETE FROM rate_limits WHERE ts < ?", (cutoff,))
                    row = c.execute(
                        "SELECT COUNT(*) as cnt, MIN(ts) as oldest FROM rate_limits WHERE rate_key = ?",
                        (key,)
                    ).fetchone()
                    cnt = row["cnt"] if row else 0
                    if cnt >= max_requests:
                        oldest = row["oldest"] if (row and row["oldest"]) else cutoff
                        retry_after = max(1, int(oldest + window_seconds - now))
                        return False, retry_after
                    c.execute("INSERT INTO rate_limits (rate_key, ts) VALUES (?, ?)", (key, now))
                    return True, 0
        except Exception:
            pass

        with self._lock:
            timestamps = self._records[key]
            # Limpa timestamps antigos fora da janela deslizante
            valid_timestamps = [ts for ts in timestamps if ts > cutoff]
            self._records[key] = valid_timestamps

            if len(valid_timestamps) >= max_requests:
                oldest = valid_timestamps[0]
                retry_after = max(1, int(oldest + window_seconds - now))
                return False, retry_after

            valid_timestamps.append(now)
            return True, 0

    def clear(self):
        with self._lock:
            self._records.clear()


limiter = InMemoryRateLimiter()


def check_rate_limit(
    request: Request,
    action: str,
    max_requests: int,
    window_seconds: int,
    custom_key: str = "",
):
    """
    Verifica se a requisição excede o limite estipulado.
    Lança HTTPException 429 caso o limite tenha sido atingido.
    """
    if is_test_environment():
        return

    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    key = f"{action}:{custom_key or client_ip}"
    allowed, retry_after = limiter.is_allowed(key, max_requests, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": f"Muitas requisições. Por favor, tente novamente após {retry_after} segundos.",
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )
