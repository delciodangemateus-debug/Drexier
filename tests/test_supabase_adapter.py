import pytest

from backend.supabase_adapter import SupabaseCursor


class InsertQuery:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.insert_data = None

    def insert(self, data):
        self.insert_data = data
        return self

    def select(self, columns):
        assert columns == "*"
        return self

    def execute(self):
        if self.error:
            raise self.error
        return self.result


class SupabaseClient:
    def __init__(self, query):
        self.query = query

    def table(self, name):
        assert name == "business_info"
        return self.query


def test_insert_uses_database_identity_and_returns_created_row():
    query = InsertQuery(result=type("Result", (), {
        "data": [{
            "id": 42,
            "user_id": 7,
            "kind": "personalizado",
            "title": "Card",
            "content": "Conteúdo",
            "metadata": {"items": []},
        }]
    })())
    cursor = SupabaseCursor(SupabaseClient(query))

    cursor.execute(
        "INSERT INTO business_info(user_id,kind,title,content,metadata) VALUES(?,?,?,?,?)",
        (7, "personalizado", "Card", "Conteúdo", '{"items": []}'),
    )

    assert "id" not in query.insert_data
    assert cursor.lastrowid == 42
    assert cursor.fetchone()["metadata"] == '{"items": []}'


def test_insert_errors_are_not_reported_as_success():
    query = InsertQuery(error=RuntimeError("Supabase indisponível"))
    cursor = SupabaseCursor(SupabaseClient(query))

    with pytest.raises(RuntimeError, match="Supabase indisponível"):
        cursor.execute(
            "INSERT INTO business_info(user_id,kind,title,content,metadata) VALUES(?,?,?,?,?)",
            (7, "personalizado", "Card", "Conteúdo", "{}"),
        )
