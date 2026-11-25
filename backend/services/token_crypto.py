"""
Módulo de Criptografia Segura para Tokens e Segredos em Repouso (Drexier AI).
Utiliza criptografia autenticada Fernet (AES-128-CBC + HMAC-SHA256) derivada da SECRET_KEY / ENCRYPTION_KEY.
Garante compatibilidade total e transparente com tokens não criptografados (legados/testes).
"""

import base64
import hashlib
import logging
import os
from typing import Optional
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    secret = os.getenv("ENCRYPTION_KEY") or os.getenv("SECRET_KEY", "development-only-change-me")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_token(plain_text: Optional[str]) -> str:
    """Criptografa um token ou segredo sensível para armazenamento na base de dados."""
    if not plain_text:
        return ""
    # Se já estiver criptografado, não criptografa duplamente
    if str(plain_text).startswith("gAAAAA"):
        return str(plain_text)
    try:
        f = _get_fernet()
        return f.encrypt(str(plain_text).encode("utf-8")).decode("utf-8")
    except Exception as exc:
        logger.critical("Falha ao criptografar token sensível: %s", exc)
        raise RuntimeError("Falha crítica no sistema de criptografia de tokens") from exc


def decrypt_token(cipher_text: Optional[str]) -> str:
    """Descriptografa um token ou segredo. Retorna o texto original se não estiver criptografado."""
    if not cipher_text:
        return ""
    text = str(cipher_text)
    # Tokens não criptografados (ex: em testes ou base de dados pré-migração) são retornados intactos
    if not text.startswith("gAAAAA"):
        return text
    try:
        f = _get_fernet()
        return f.decrypt(text.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        logger.error("Falha ao descriptografar token: %s", exc)
        return text
