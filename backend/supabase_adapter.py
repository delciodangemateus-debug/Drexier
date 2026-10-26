"""
Adaptador de Banco de Dados Supabase para Drexier AI.
Converte chamadas do padrão DB-API (connect, execute, fetchone, fetchall)
diretamente em operações seguras no Supabase (PostgreSQL) através do Supabase Client SDK.
"""

import re
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

from backend.supabase_client import get_supabase_client

logger = logging.getLogger("drexier.supabase_adapter")


class SupabaseRow(dict):
    """
    Linha de resultado compatível com sqlite3.Row e dicionário.
    Permite acesso tanto por nome de coluna (row["col"]) quanto por índice (row[0]),
    e conversão limpa para dict(row).
    """
    def __init__(self, data: Dict[str, Any], columns: Optional[List[str]] = None):
        super().__init__(data)
        self._columns = columns if columns is not None else list(data.keys())

    def __getitem__(self, key: Union[str, int]) -> Any:
        if isinstance(key, int):
            col_name = self._columns[key]
            return super().__getitem__(col_name)
        return super().__getitem__(key)

    def keys(self):
        return self._columns

    def values(self):
        return [super(SupabaseRow, self).__getitem__(c) for c in self._columns]

    def items(self):
        return [(c, super(SupabaseRow, self).__getitem__(c)) for c in self._columns]


def _format_row_for_app(table: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza os tipos do Supabase (PostgreSQL) para total compatibilidade
    com o que o backend do Drexier espera:
    - JSONB (dict) -> string JSON para colunas mandatory_responses e metadata
    - Booleans -> int/bool (compatível)
    """
    res = dict(row)
    if "mandatory_responses" in res and isinstance(res["mandatory_responses"], (dict, list)):
        res["mandatory_responses"] = json.dumps(res["mandatory_responses"], ensure_ascii=False)
    if "metadata" in res and isinstance(res["metadata"], (dict, list)):
        res["metadata"] = json.dumps(res["metadata"], ensure_ascii=False)
    if "auto_reply_enabled" in res and isinstance(res["auto_reply_enabled"], bool):
        res["auto_reply_enabled"] = 1 if res["auto_reply_enabled"] else 0
    if "webhook_subscribed" in res and isinstance(res["webhook_subscribed"], bool):
        res["webhook_subscribed"] = 1 if res["webhook_subscribed"] else 0
    return res


def _apply_where_conditions(query, where_clause: str, params: list, param_offset: int = 0) -> Tuple[Any, int]:
    """Aplica condições da cláusula WHERE tolerando qualquer variação de espaçamento."""
    if not where_clause:
        return query, param_offset

    conds = [c.strip() for c in where_clause.split("AND")]
    p_idx = param_offset

    for cond in conds:
        c_norm = re.sub(r"\s*=\s*", "=", cond)
        # Remove eventuais prefixos de tabela (ex: r.id -> id, ct.id -> id)
        if "=?" in c_norm:
            col_part = c_norm.split("=?")[0].strip()
            col = col_part.split(".")[-1] if "." in col_part else col_part
            val = params[p_idx]
            p_idx += 1
            query = query.eq(col, val)
        elif "='" in c_norm:
            parts = c_norm.split("='")
            col_part = parts[0].strip()
            col = col_part.split(".")[-1] if "." in col_part else col_part
            val = parts[1].rstrip("'").strip()
            query = query.eq(col, val)
        elif "!=" in c_norm:
            parts = c_norm.split("!=")
            col_part = parts[0].strip()
            col = col_part.split(".")[-1] if "." in col_part else col_part
            val = parts[1].strip().strip("'")
            query = query.neq(col, val)

    return query, p_idx


class SupabaseCursor:
    def __init__(self, client):
        self.client = client
        self.lastrowid: Optional[int] = None
        self.rowcount: int = 0
        self._rows: List[SupabaseRow] = []
        self._idx: int = 0

    def __iter__(self):
        return iter(self._rows)

    def fetchone(self) -> Optional[SupabaseRow]:
        if self._idx < len(self._rows):
            r = self._rows[self._idx]
            self._idx += 1
            return r
        return None

    def fetchall(self) -> List[SupabaseRow]:
        r = self._rows[self._idx:]
        self._idx = len(self._rows)
        return r

    def _get_next_id(self, table: str) -> int:
        """Gera o próximo ID sequencial seguro para uma tabela no Supabase."""
        try:
            res = self.client.table(table).select("id").order("id", desc=True).limit(1).execute()
            if res.data and len(res.data) > 0 and res.data[0].get("id") is not None:
                return int(res.data[0]["id"]) + 1
        except Exception:
            pass
        return 1

    def execute(self, sql: str, params: Optional[Union[tuple, list, dict]] = None) -> "SupabaseCursor":
        clean_sql = " ".join(sql.strip().split())
        self._rows = []
        self._idx = 0
        self.rowcount = 0

        p = list(params) if isinstance(params, (list, tuple)) else ([] if params is None else [params])

        # =========================================================================
        # 1. SPECIAL QUERIES: DASHBOARD, ANALYTICS & CONVERSION REQUESTS JOIN
        # =========================================================================
        # 1.1 Conversion requests with contacts join (dashboard list or single action)
        if "FROM conversion_requests r" in clean_sql and "JOIN contacts ct" in clean_sql:
            query = self.client.table("conversion_requests").select(
                "id, request_type, details, created_at, status, user_id, contact_id"
            )
            where_part = clean_sql.split("WHERE", 1)[1] if "WHERE" in clean_sql else ""
            if "r.id" in where_part or "id = ?" in where_part.replace(" ", ""):
                req_id = p[0]
                query = query.eq("id", req_id)
                if len(p) > 1:
                    query = query.eq("user_id", p[1])
            elif "status='pending'" in where_part.replace(" ", ""):
                uid = p[0]
                query = query.eq("user_id", uid).eq("status", "pending")

            reqs = query.order("created_at", desc=True).execute().data
            rows = []
            for r in reqs:
                c_data = self.client.table("contacts").select("name, contact_key").eq("id", r["contact_id"]).execute().data
                name = c_data[0]["name"] if c_data else ""
                ckey = c_data[0]["contact_key"] if c_data else ""
                rows.append(SupabaseRow({
                    "id": r["id"],
                    "request_type": r["request_type"],
                    "details": r["details"],
                    "created_at": r["created_at"],
                    "status": r.get("status", "pending"),
                    "contact_id": r["contact_id"],
                    "name": name,
                    "contact_key": ckey
                }))
            self._rows = rows
            self.rowcount = len(rows)
            return self

        # 1.2 Contacts list with last_message subquery
        if "FROM contacts ct WHERE ct.user_id" in clean_sql and "last_message" in clean_sql:
            uid = p[0]
            contacts = self.client.table("contacts").select("*").eq("user_id", uid).execute().data
            contacts.sort(key=lambda x: x.get("last_message_at") or x.get("created_at") or "", reverse=True)
            
            rows = []
            for ct in contacts:
                m_res = self.client.table("messages").select("content").eq("contact_id", ct["id"]).order("id", desc=True).limit(1).execute().data
                last_msg = m_res[0]["content"] if m_res else None
                row_dict = _format_row_for_app("contacts", ct)
                row_dict["last_message"] = last_msg
                rows.append(SupabaseRow(row_dict))
            self._rows = rows
            self.rowcount = len(rows)
            return self

        # 1.3 COUNT(*) queries (Dashboard & Analytics)
        if clean_sql.upper().startswith("SELECT COUNT(*)"):
            m_alias = re.search(r"SELECT COUNT\(\*\)\s+(?:AS\s+)?(\w+)\s+FROM\s+(\w+)", clean_sql, re.IGNORECASE)
            alias = m_alias.group(1) if m_alias else "n"
            table = m_alias.group(2) if m_alias else "contacts"

            # Count contacts today
            if "date(created_at)=date('now','localtime')" in clean_sql.replace(" ", ""):
                uid = p[0]
                today_start = datetime.now(timezone.utc).strftime("%Y-%m-%d 00:00:00")
                cnt = self.client.table("contacts").select("id", count="exact").eq("user_id", uid).gte("created_at", today_start).execute().count or 0
                self._rows = [SupabaseRow({alias: cnt})]
                self.rowcount = 1
                return self

            # Count contacts yesterday
            if "date('now','localtime','-1 day')" in clean_sql.replace(" ", ""):
                uid = p[0]
                now_utc = datetime.now(timezone.utc)
                yesterday = now_utc - timedelta(days=1)
                y_start = yesterday.strftime("%Y-%m-%d 00:00:00")
                y_end = now_utc.strftime("%Y-%m-%d 00:00:00")
                cnt = self.client.table("contacts").select("id", count="exact").eq("user_id", uid).gte("created_at", y_start).lt("created_at", y_end).execute().count or 0
                self._rows = [SupabaseRow({alias: cnt})]
                self.rowcount = 1
                return self

            # Count contacts by specific date (daily_acquisitions)
            if "date(created_at)=?" in clean_sql.replace(" ", ""):
                uid = p[0]
                day_str = p[1]
                day_start = f"{day_str} 00:00:00"
                next_day = (datetime.strptime(day_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
                cnt = self.client.table("contacts").select("id", count="exact").eq("user_id", uid).gte("created_at", day_start).lt("created_at", next_day).execute().count or 0
                self._rows = [SupabaseRow({alias: cnt})]
                self.rowcount = 1
                return self

            # General count with filters
            query = self.client.table(table).select("id", count="exact")
            if "WHERE" in clean_sql:
                where_part = clean_sql.split("WHERE", 1)[1]
                query, _ = _apply_where_conditions(query, where_part, p)
            res = query.execute()
            cnt = res.count or 0
            self._rows = [SupabaseRow({alias: cnt})]
            self.rowcount = 1
            return self

        # 1.4 SELECT DISTINCT user_id FROM email_integrations
        if "SELECT DISTINCT user_id FROM email_integrations" in clean_sql:
            res = self.client.table("email_integrations").select("user_id").eq("status", "connected").execute()
            seen = set()
            rows = []
            for item in res.data:
                uid = item["user_id"]
                if uid not in seen:
                    seen.add(uid)
                    rows.append(SupabaseRow({"user_id": uid}))
            self._rows = rows
            self.rowcount = len(rows)
            return self

        # 1.5 Recent history in incoming messages: id != last_insert_rowid()
        if "FROM messages" in clean_sql and "last_insert_rowid()" in clean_sql:
            cid, uid = p[0], p[1]
            query = self.client.table("messages").select("sender, content").eq("contact_id", cid).eq("user_id", uid).order("id", desc=True).limit(10)
            res = query.execute()
            self._rows = [SupabaseRow(r) for r in res.data]
            self.rowcount = len(self._rows)
            return self

        # =========================================================================
        # 2. GENERIC INSERT
        # =========================================================================
        if clean_sql.upper().startswith("INSERT INTO"):
            m_ins = re.match(r"INSERT\s+INTO\s+(\w+)\s*\((.*?)\)\s*VALUES\s*\((.*?)\)", clean_sql, re.IGNORECASE)
            if not m_ins:
                raise ValueError(f"Não foi possível processar INSERT: {clean_sql}")
            table = m_ins.group(1)
            columns = [c.strip() for c in m_ins.group(2).split(",")]
            values_tokens = [v.strip() for v in m_ins.group(3).split(",")]

            insert_data: Dict[str, Any] = {}
            param_idx = 0
            for col, token in zip(columns, values_tokens):
                if token == "?":
                    val = p[param_idx]
                    param_idx += 1
                elif token.upper() in ("CURRENT_TIMESTAMP", "NOW()"):
                    val = datetime.now(timezone.utc).isoformat()
                elif token.startswith("'") and token.endswith("'"):
                    val = token[1:-1]
                else:
                    try:
                        val = int(token)
                    except ValueError:
                        val = token

                if col in ("mandatory_responses", "metadata") and isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except Exception:
                        val = {}
                elif col in ("auto_reply_enabled", "webhook_subscribed"):
                    val = bool(val)

                insert_data[col] = val

            if "id" not in insert_data:
                insert_data["id"] = self._get_next_id(table)

            try:
                res = self.client.table(table).insert(insert_data).execute()
            except Exception as e:
                err_str = str(e)
                if "duplicate key" in err_str or "23505" in err_str:
                    raise Exception(f"UNIQUE constraint failed: {err_str}")
                raise

            if res.data and len(res.data) > 0:
                inserted_row = res.data[0]
                self.lastrowid = inserted_row.get("id")
                self._rows = [SupabaseRow(_format_row_for_app(table, inserted_row))]
                self.rowcount = 1
            else:
                self.lastrowid = insert_data.get("id")
                self.rowcount = 1
            return self

        # =========================================================================
        # 3. GENERIC UPDATE
        # =========================================================================
        if clean_sql.upper().startswith("UPDATE"):
            m_up = re.match(r"UPDATE\s+(\w+)\s+SET\s+(.*?)(?:\s+WHERE\s+(.*))?$", clean_sql, re.IGNORECASE)
            if not m_up:
                raise ValueError(f"Não foi possível processar UPDATE: {clean_sql}")
            table = m_up.group(1)
            set_clause = m_up.group(2)
            where_clause = m_up.group(3)

            set_assignments = [s.strip() for s in set_clause.split(",")]
            update_data: Dict[str, Any] = {}
            param_idx = 0

            for assign in set_assignments:
                parts = assign.split("=")
                col = parts[0].strip()
                val_token = parts[1].strip()
                if val_token == "?":
                    val = p[param_idx]
                    param_idx += 1
                elif val_token.upper() in ("CURRENT_TIMESTAMP", "NOW()"):
                    val = datetime.now(timezone.utc).isoformat()
                elif val_token.startswith("'") and val_token.endswith("'"):
                    val = val_token[1:-1]
                else:
                    try:
                        val = int(val_token)
                    except ValueError:
                        val = val_token

                if col in ("mandatory_responses", "metadata") and isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except Exception:
                        val = {}
                elif col in ("auto_reply_enabled", "webhook_subscribed"):
                    val = bool(val)

                update_data[col] = val

            query = self.client.table(table).update(update_data)
            if where_clause:
                query, _ = _apply_where_conditions(query, where_clause, p, param_idx)

            res = query.execute()
            self.rowcount = len(res.data) if res.data else 1
            return self

        # =========================================================================
        # 4. GENERIC DELETE
        # =========================================================================
        if clean_sql.upper().startswith("DELETE FROM"):
            m_del = re.match(r"DELETE\s+FROM\s+(\w+)(?:\s+WHERE\s+(.*))?$", clean_sql, re.IGNORECASE)
            if not m_del:
                raise ValueError(f"Não foi possível processar DELETE: {clean_sql}")
            table = m_del.group(1)
            where_clause = m_del.group(2)

            query = self.client.table(table).delete()
            if where_clause:
                query, _ = _apply_where_conditions(query, where_clause, p, 0)

            res = query.execute()
            self.rowcount = len(res.data) if res.data else 1
            return self

        # =========================================================================
        # 5. GENERIC SELECT
        # =========================================================================
        if clean_sql.upper().startswith("SELECT"):
            m_sel = re.match(
                r"SELECT\s+(.*?)\s+FROM\s+(\w+)(?:\s+WHERE\s+(.*?))?(?:\s+ORDER\s+BY\s+(.*?))?(?:\s+LIMIT\s+(\d+))?$",
                clean_sql,
                re.IGNORECASE
            )
            if m_sel:
                cols_str = m_sel.group(1).strip()
                table = m_sel.group(2).strip()
                where_clause = m_sel.group(3)
                order_clause = m_sel.group(4)
                limit_clause = m_sel.group(5)

                query = self.client.table(table).select("*" if cols_str == "*" else cols_str)

                if where_clause:
                    query, _ = _apply_where_conditions(query, where_clause, p, 0)

                if order_clause:
                    order_parts = order_clause.strip().split()
                    col_order = order_parts[0].strip()
                    desc = len(order_parts) > 1 and order_parts[1].upper() == "DESC"
                    query = query.order(col_order, desc=desc)

                if limit_clause:
                    query = query.limit(int(limit_clause))

                res = query.execute()
                rows = [_format_row_for_app(table, r) for r in res.data]
                self._rows = [SupabaseRow(r) for r in rows]
                self.rowcount = len(self._rows)
                return self

        logger.warning(f"[SupabaseCursor] Consulta não mapeada diretamente: {clean_sql}")
        return self


class SupabaseConnection:
    """Conexão Supabase compatível com o context manager (with connect() as c:)."""
    def __init__(self):
        self.client = get_supabase_client()
        if not self.client:
            raise RuntimeError("Supabase não configurado ou credenciais inválidas.")

    def cursor(self) -> SupabaseCursor:
        return SupabaseCursor(self.client)

    def execute(self, sql: str, params: Optional[Union[tuple, list, dict]] = None) -> SupabaseCursor:
        cur = self.cursor()
        return cur.execute(sql, params)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
