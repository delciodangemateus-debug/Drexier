"""
Gerenciador de Banco de Dados Oficial do Drexier AI.
Supabase (PostgreSQL) como banco de dados principal e único na nuvem.
"""

import os
import sqlite3
import logging
from pathlib import Path
from dotenv import load_dotenv

from backend.supabase_client import (
    get_supabase_client,
    is_supabase_configured,
    get_supabase_status,
)
from backend.supabase_adapter import SupabaseConnection

load_dotenv()
logger = logging.getLogger("drexier.database")

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = os.getenv("DATABASE_PATH", "")

SQL_SCHEMA_FOR_TESTS = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  business_type TEXT NOT NULL,
  business_description TEXT DEFAULT '',
  language TEXT NOT NULL DEFAULT 'Português',
  agent_instructions TEXT DEFAULT '',
  mandatory_responses TEXT DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS business_info (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS contacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  contact_key TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_message_at TEXT,
  UNIQUE(user_id, contact_key),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  contact_id INTEGER NOT NULL,
  sender TEXT NOT NULL CHECK(sender IN ('customer','agent','owner')),
  content TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS conversion_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  contact_id INTEGER NOT NULL,
  request_type TEXT NOT NULL,
  details TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at TEXT,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS response_variants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  label TEXT NOT NULL,
  response_text TEXT NOT NULL,
  sent_count INTEGER NOT NULL DEFAULT 0,
  conversions INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS whatsapp_integrations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL UNIQUE,
  waba_id TEXT NOT NULL,
  phone_number_id TEXT NOT NULL UNIQUE,
  phone_number TEXT DEFAULT '',
  business_name TEXT DEFAULT '',
  access_token TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'connected',
  webhook_subscribed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS email_integrations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL UNIQUE,
  provider TEXT NOT NULL CHECK(provider IN ('google', 'microsoft', 'smtp_imap')),
  email_address TEXT NOT NULL,
  display_name TEXT DEFAULT '',
  access_token TEXT DEFAULT '',
  refresh_token TEXT DEFAULT '',
  token_expires_at TEXT,
  status TEXT NOT NULL DEFAULT 'connected',
  auto_reply_enabled INTEGER NOT NULL DEFAULT 1,
  last_sync_at TEXT,
  sync_cursor TEXT DEFAULT '',
  smtp_host TEXT DEFAULT '',
  smtp_port INTEGER DEFAULT 587,
  smtp_user TEXT DEFAULT '',
  smtp_password TEXT DEFAULT '',
  imap_host TEXT DEFAULT '',
  imap_port INTEGER DEFAULT 993,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS email_threads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  contact_id INTEGER NOT NULL,
  provider TEXT NOT NULL,
  thread_id TEXT NOT NULL,
  last_message_id TEXT NOT NULL,
  subject TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, thread_id),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
);
"""


def is_test_environment() -> bool:
    """Detecta se a execução atual é um teste unitário temporário isolado."""
    return bool(DB_PATH and ("tmp" in DB_PATH.lower() or "pytest" in DB_PATH.lower() or "test_" in DB_PATH.lower()))


def connect():
    """
    Retorna a conexão com o banco de dados.
    O Supabase é o banco de dados principal e único da aplicação Drexier AI.
    Ambientes de testes unitários isolados utilizam banco temporário em memória/tmp.
    """
    if is_test_environment():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # Supabase como banco de dados principal e único
    if is_supabase_configured():
        return SupabaseConnection()

    # Fallback exclusivo se credenciais não existirem
    local_path = DB_PATH or str(ROOT / "data" / "drexier.db")
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(local_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """
    Inicializa o banco de dados:
    - Em produção/desenvolvimento: valida Supabase e elimina qualquer banco local legado.
    - Em testes unitários isolados: inicializa a estrutura na base temporária de teste.
    """
    if is_test_environment():
        with connect() as c:
            c.executescript(SQL_SCHEMA_FOR_TESTS)
        return

    if is_supabase_configured():
        status = get_supabase_status()
        if status.get("connected"):
            logger.info("Drexier AI conectado ao Supabase como banco de dados principal e único.")
        else:
            logger.warning(f"Supabase conectado com aviso: {status.get('details')}")

        # Elimina banco local legado drexier.db caso ainda exista
        legacy_db = ROOT / "data" / "drexier.db"
        if legacy_db.exists():
            try:
                legacy_db.unlink()
                logger.info("Banco de dados local legado drexier.db eliminado com sucesso.")
            except Exception as e:
                logger.warning(f"Aviso ao remover banco local legado: {e}")

        data_dir = ROOT / "data"
        if data_dir.exists():
            for item in data_dir.iterdir():
                if item.suffix == ".db":
                    try:
                        item.unlink()
                    except Exception:
                        pass
        return

    # Fallback para ambiente local sem Supabase
    if DB_PATH:
        with connect() as c:
            c.executescript(SQL_SCHEMA_FOR_TESTS)
