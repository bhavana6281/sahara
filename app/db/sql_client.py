"""Thin client for the Databricks SQL Statement Execution API.

Submits a statement, then polls for completion with exponential backoff.
Free Edition serverless warehouses can be stopped when idle and take tens of
seconds to resume on the first query of a session, so the timeout budget is
generous (90s) and a cold-start timeout is reported distinctly from a real
query failure.
"""
import time

import requests


class DatabricksQueryError(Exception):
    pass


class DatabricksQueryTimeout(Exception):
    def __init__(self, statement_id):
        super().__init__(
            f"Statement {statement_id} did not finish in time — the SQL "
            "warehouse may still be starting up. Try again in a moment."
        )
        self.statement_id = statement_id


_TERMINAL_STATES = ("SUCCEEDED", "FAILED", "CANCELED", "CLOSED")


class DatabricksSQLClient:
    def __init__(self, host, token, warehouse_id,
                 initial_backoff=0.5, max_backoff=4.0, max_wait_seconds=90):
        self.host = host
        self.token = token
        self.warehouse_id = warehouse_id
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.max_wait_seconds = max_wait_seconds

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    @staticmethod
    def _to_param_list(parameters):
        return [{"name": name, "value": None if value is None else str(value)}
                for name, value in parameters.items()]

    def _fetch_all_chunks(self, data):
        rows = list(data.get("result", {}).get("data_array", []) or [])
        manifest = data.get("manifest", {})
        total_chunks = manifest.get("total_chunk_count", 1)
        chunks = manifest.get("chunks", [])
        for chunk in chunks[1:] if total_chunks > 1 else []:
            link = chunk.get("next_chunk_internal_link") or chunk.get("external_link")
            if not link:
                continue
            resp = requests.get(f"{self.host}{link}", headers=self._headers(), timeout=15)
            resp.raise_for_status()
            rows.extend(resp.json().get("data_array", []) or [])
        return rows

    def execute(self, statement: str, parameters: dict | None = None) -> list[dict]:
        """Run a SQL statement and return rows as a list of dicts."""
        body = {
            "statement": statement,
            "warehouse_id": self.warehouse_id,
            "wait_timeout": "10s",
            "on_wait_timeout": "CONTINUE",
            "disposition": "INLINE",
            "format": "JSON_ARRAY",
            "parameters": self._to_param_list(parameters or {}),
        }
        resp = requests.post(
            f"{self.host}/api/2.0/sql/statements",
            headers=self._headers(), json=body, timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        statement_id = data["statement_id"]

        backoff = self.initial_backoff
        elapsed = 0.0
        while data["status"]["state"] not in _TERMINAL_STATES:
            if elapsed > self.max_wait_seconds:
                raise DatabricksQueryTimeout(statement_id)
            time.sleep(backoff)
            elapsed += backoff
            backoff = min(backoff * 1.6, self.max_backoff)
            poll = requests.get(
                f"{self.host}/api/2.0/sql/statements/{statement_id}",
                headers=self._headers(), timeout=15,
            )
            poll.raise_for_status()
            data = poll.json()

        if data["status"]["state"] != "SUCCEEDED":
            message = data["status"].get("error", {}).get("message", "query failed")
            raise DatabricksQueryError(message)

        # DDL/DML statements (CREATE TABLE, INSERT) have no result schema/columns.
        schema_columns = ((data.get("manifest") or {}).get("schema") or {}).get("columns") or []
        if not schema_columns:
            return []
        columns = [c["name"] for c in schema_columns]
        rows = self._fetch_all_chunks(data)
        return [dict(zip(columns, row)) for row in rows]
