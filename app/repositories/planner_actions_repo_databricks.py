"""planner_actions persistence via the Databricks SQL Statements REST API.

Append-only: notes/overrides are never edited or deleted, only added, which
keeps the audit trail honest.
"""
import logging
import uuid

from config import PLANNER_ACTIONS_TABLE
from db.sql_client import DatabricksSQLClient

logger = logging.getLogger(__name__)

_CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {PLANNER_ACTIONS_TABLE} (
  action_id STRING,
  unique_id STRING,
  action_type STRING,
  note_text STRING,
  override_trust_level STRING,
  planner_name STRING,
  created_at TIMESTAMP
) USING DELTA
"""


class DatabricksPlannerActionsRepo:
    def __init__(self, client: DatabricksSQLClient):
        self.client = client

    def ensure_table(self) -> None:
        try:
            self.client.execute(_CREATE_TABLE)
        except Exception:
            logger.warning("Could not ensure planner_actions table exists", exc_info=True)

    def list_actions(self, unique_id: str) -> list[dict]:
        rows = self.client.execute(
            f"""
            SELECT action_id, unique_id, action_type, note_text,
                   override_trust_level, planner_name, created_at
            FROM {PLANNER_ACTIONS_TABLE}
            WHERE unique_id = :unique_id
            ORDER BY created_at DESC
            """,
            {"unique_id": unique_id},
        )
        for r in rows:
            r["created_at"] = str(r["created_at"])
        return rows

    def add_action(self, unique_id: str, action_type: str, note_text: str,
                    override_trust_level: str | None, planner_name: str) -> dict:
        action_id = str(uuid.uuid4())
        self.client.execute(
            f"""
            INSERT INTO {PLANNER_ACTIONS_TABLE}
            (action_id, unique_id, action_type, note_text, override_trust_level,
             planner_name, created_at)
            VALUES (:action_id, :unique_id, :action_type, :note_text,
                    :override_trust_level, :planner_name, current_timestamp())
            """,
            {
                "action_id": action_id,
                "unique_id": unique_id,
                "action_type": action_type,
                "note_text": note_text,
                "override_trust_level": override_trust_level,
                "planner_name": planner_name,
            },
        )
        created = self.list_actions(unique_id)
        return next((a for a in created if a["action_id"] == action_id), created[0])
