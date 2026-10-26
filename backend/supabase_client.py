"""
Cliente oficial do Supabase para o sistema Drexier AI.
Gerencia a conexão com o banco de dados Supabase (PostgreSQL), autenticação
e acesso seguro via Client SDK.
"""

import os
import logging
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("drexier.supabase")

_supabase_client = None

def get_supabase_credentials() -> Dict[str, str]:
    """Obtém as credenciais do Supabase configuradas nas variáveis de ambiente."""
    url = os.getenv("SUPABASE_URL", "").strip()
    anon_key = os.getenv("SUPABASE_ANON_KEY", "").strip() or os.getenv("SUPABASE_KEY", "").strip()
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    return {
        "url": url,
        "anon_key": anon_key,
        "service_role_key": service_key,
    }

def is_supabase_configured() -> bool:
    """Verifica se o projeto Supabase possui URL e ao menos uma chave válida configurada."""
    creds = get_supabase_credentials()
    has_url = bool(creds["url"] and creds["url"].startswith("http"))
    has_key = bool(creds["service_role_key"] or creds["anon_key"])
    return has_url and has_key

def get_supabase_client(use_service_role: bool = True) -> Optional[Any]:
    """
    Retorna o cliente autenticado do Supabase.
    Dá prioridade à Service Role Key para operações administrativas seguras no backend,
    com fallback para a Anon Key se a Service Key não for fornecida.
    """
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    creds = get_supabase_credentials()
    url = creds["url"]
    key = creds["service_role_key"] if (use_service_role and creds["service_role_key"]) else creds["anon_key"]

    if not url or not key:
        return None

    try:
        from supabase import create_client, Client
        _supabase_client = create_client(url, key)
        logger.info(f"Cliente Supabase conectado com sucesso ao projeto: {url}")
        return _supabase_client
    except Exception as e:
        logger.error(f"Erro ao inicializar cliente Supabase ({url}): {e}")
        return None

def get_supabase_status() -> Dict[str, Any]:
    """
    Retorna um relatório detalhado do estado da conexão com o Supabase.
    Útil para diagnóstico na API e interface.
    """
    creds = get_supabase_credentials()
    configured = is_supabase_configured()
    status = {
        "configured": configured,
        "url": creds["url"] if creds["url"] else "Não configurado no .env",
        "has_anon_key": bool(creds["anon_key"]),
        "has_service_role_key": bool(creds["service_role_key"]),
        "connected": False,
        "details": "",
    }

    if configured:
        try:
            client = get_supabase_client()
            if client:
                # Testa leitura da tabela users para verificar a conectividade real
                res = client.table("users").select("id").limit(1).execute()
                status["connected"] = True
                status["details"] = "Conexão com o Supabase estabelecida e tabelas acessíveis."
            else:
                status["details"] = "Falha ao instanciar o cliente Supabase."
        except Exception as ex:
            status["connected"] = False
            status["details"] = f"Supabase configurado, mas retornou erro de consulta: {str(ex)}"
    else:
        status["details"] = "Configure SUPABASE_URL e SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY no seu arquivo .env"

    return status
