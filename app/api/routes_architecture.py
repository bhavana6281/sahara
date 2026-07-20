"""Live status for the in-app 'How Sahara Works' panel — real counts from the
Delta tables, not hardcoded numbers, so the panel stays honest as data changes.
"""
from typing import Optional

from fastapi import APIRouter

import config
from db.sql_client import DatabricksQueryError, DatabricksQueryTimeout
from deps import get_sql_client

router = APIRouter()


@router.get("/api/architecture/status")
def architecture_status():
    client = get_sql_client()

    def count(table: str) -> Optional[int]:
        try:
            rows = client.execute(f"SELECT COUNT(*) AS n FROM {table}")
            return int(rows[0]["n"]) if rows else 0
        except (DatabricksQueryError, DatabricksQueryTimeout):
            return None

    return {
        "databricks_host": config.DATABRICKS_HOST,
        "warehouse_id": config.WAREHOUSE_ID,
        "llm_endpoint": config.LLM_ENDPOINT,
        "tables": {
            "facility_trust": {"name": config.TRUST_TABLE, "row_count": count(config.TRUST_TABLE)},
            "district_desert": {"name": config.DISTRICT_DESERT_TABLE,
                                  "row_count": count(config.DISTRICT_DESERT_TABLE)},
            "planner_actions": {"name": config.PLANNER_ACTIONS_TABLE,
                                  "row_count": count(config.PLANNER_ACTIONS_TABLE)},
            "review_decisions": {"name": config.REVIEW_DECISIONS_TABLE,
                                   "row_count": count(config.REVIEW_DECISIONS_TABLE)},
        },
    }
