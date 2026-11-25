import pytest
from backend.supabase_adapter import SupabaseRow, _format_row_for_app

def test_supabase_row_missing_token_version_safe():
    # Simula retorno do Supabase onde a tabela users não tem a coluna token_version
    raw_data = {
        "id": 1,
        "name": "autos del",
        "email": "delciodangemateus@gmail.com",
        "business_type": "Serviços e vendas",
    }
    row = SupabaseRow(raw_data)
    
    # Não deve lançar KeyError: 'token_version'
    assert row["token_version"] == 1
    assert row.get("token_version") == 1
    assert row.get("token_version", 2) == 2
    assert row["agent_adopted_style"] == ""
    assert row["mandatory_responses"] == "{}"

def test_format_row_for_app_users_defaults():
    raw_user = {
        "id": 1,
        "name": "Teste",
        "email": "teste@drexier.ai",
        "business_type": "Consultoria",
    }
    formatted = _format_row_for_app("users", raw_user)
    assert formatted["token_version"] == 1
    assert formatted["agent_adopted_style"] == ""
    assert formatted["mandatory_responses"] == "{}"
    assert formatted["language"] == "Português"
    assert formatted["business_description"] == ""
    assert formatted["agent_instructions"] == ""
