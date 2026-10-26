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

load_dotenv()
logger = logging.getLogger("drexier.database")

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = os.getenv("DATABASE_PATH", str(DATA_DIR / "drexier.db"))

def connect():
    """
    Retorna a conexão local do banco de dados (SQLite).
    Mantém compatibilidade imediata e suporte offline para os repositórios locais.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """
    Inicializa a estrutura do banco de dados:
    1. Verifica o estado da conexão com o Supabase;
    2. Inicializa as tabelas locais com todas as entidades e tabelas reservadas para expansão.
    """
    if is_supabase_configured():
        logger.info("Supabase detectado nas variáveis de ambiente. Cliente pronto para uso.")
    else:
        logger.info("Supabase ainda não configurado no .env. Utilizando banco local SQLite.")

    with connect() as c:
        c.executescript("""
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

        -- Tabela de integração WhatsApp (reservada para expansão futura)
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
        CREATE INDEX IF NOT EXISTS idx_whatsapp_phone_number_id ON whatsapp_integrations(phone_number_id);
        CREATE INDEX IF NOT EXISTS idx_whatsapp_waba_id ON whatsapp_integrations(waba_id);
        CREATE INDEX IF NOT EXISTS idx_whatsapp_user_id ON whatsapp_integrations(user_id);

        -- Tabela de integração de email oficial (Google Gmail ativo; Microsoft Outlook e SMTP para expansão)
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
        CREATE INDEX IF NOT EXISTS idx_email_user_id ON email_integrations(user_id);
        CREATE INDEX IF NOT EXISTS idx_email_address ON email_integrations(email_address);

        -- Tabela de tópicos/threads de e-mail para manter histórico e contexto de conversa
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
        CREATE INDEX IF NOT EXISTS idx_email_threads_thread_id ON email_threads(thread_id);
        CREATE INDEX IF NOT EXISTS idx_email_threads_user_id ON email_threads(user_id);
        """)
