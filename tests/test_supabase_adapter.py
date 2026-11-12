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

    def upsert(self, data):
        self.insert_data = data
        self.upsert_called = True
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


class MutationQuery:
    def __init__(self, result_data):
        self.result_data = result_data
        self.filters = []
        self.selected = None

    def update(self, data):
        self.mutation = ("update", data)
        return self

    def delete(self):
        self.mutation = ("delete", None)
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def select(self, columns):
        self.selected = columns
        return self

    def execute(self):
        return type("Result", (), {"data": self.result_data})()


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


def test_on_conflict_insert_uses_supabase_upsert_for_gmail():
    query = InsertQuery(result=type("Result", (), {"data": [{
        "id": 42,
        "user_id": 7,
        "provider": "google",
    }]})())

    class EmailSupabaseClient:
        def table(self, name):
            assert name == "email_integrations"
            return query

    cursor = SupabaseCursor(EmailSupabaseClient())
    cursor.execute(
        """INSERT INTO email_integrations(user_id,provider)
           VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET provider=excluded.provider""",
        (7, "google"),
    )

    assert query.upsert_called is True
    assert query.insert_data == {"user_id": 7, "provider": "google"}
    assert cursor.fetchone()["provider"] == "google"


@pytest.mark.parametrize(
    ("sql", "mutation"),
    [
        ("UPDATE business_info SET title=? WHERE id=? AND user_id=?", "update"),
        ("DELETE FROM business_info WHERE id=? AND user_id=?", "delete"),
    ],
)
def test_mutations_report_zero_rows_when_user_scope_matches_nothing(sql, mutation):
    query = MutationQuery(result_data=[])
    cursor = SupabaseCursor(SupabaseClient(query))

    cursor.execute(sql, ("Título", 42, 7) if mutation == "update" else (42, 7))

    assert query.mutation[0] == mutation
    assert query.selected == "*"
    assert cursor.rowcount == 0


def test_mutations_report_rows_returned_by_supabase():
    query = MutationQuery(result_data=[{"id": 42}, {"id": 43}])
    cursor = SupabaseCursor(SupabaseClient(query))

    cursor.execute("DELETE FROM business_info WHERE user_id=?", (7,))

    assert cursor.rowcount == 2


def test_database_fails_closed_without_supabase_or_explicit_local_mode(monkeypatch):
    from backend import database

    monkeypatch.setattr(database, "is_test_environment", lambda: False)
    monkeypatch.setattr(database, "DB_PATH", "")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-key-is-not-enough")
    monkeypatch.delenv("ALLOW_LOCAL_DATABASE", raising=False)

    with pytest.raises(RuntimeError, match="SUPABASE_SERVICE_ROLE_KEY"):
        database.connect()


def test_init_db_preserves_existing_local_database_when_supabase_is_configured(
    tmp_path, monkeypatch
):
    from backend import database

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    legacy_db = data_dir / "drexier.db"
    legacy_db.write_bytes(b"legacy user data")

    monkeypatch.setattr(database, "ROOT", tmp_path)
    monkeypatch.setattr(database, "is_test_environment", lambda: False)
    monkeypatch.setattr(database, "is_supabase_configured", lambda: True)
    monkeypatch.setattr(
        database, "get_supabase_status", lambda: {"connected": True, "details": ""}
    )

    database.init_db()

    assert legacy_db.read_bytes() == b"legacy user data"
