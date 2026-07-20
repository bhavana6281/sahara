from fastapi import APIRouter

import config

router = APIRouter()


@router.get("/api/meta")
def get_meta():
    return {
        "databricks_host": config.DATABRICKS_HOST,
        "trust_table": config.TRUST_TABLE,
        "planner_actions_table": config.PLANNER_ACTIONS_TABLE,
    }
