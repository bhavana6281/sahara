"""Environment/config loading for the Databricks connection."""
import os

from dotenv import load_dotenv

load_dotenv()

DATABRICKS_HOST = os.getenv("DATABRICKS_HOST", "").strip().rstrip("/")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "").strip()
WAREHOUSE_ID = os.getenv("WAREHOUSE_ID", "").strip()

if not (DATABRICKS_HOST and DATABRICKS_TOKEN and WAREHOUSE_ID):
    raise RuntimeError(
        "DATABRICKS_HOST, DATABRICKS_TOKEN and WAREHOUSE_ID must all be set "
        "(e.g. in app/.env, copied from app/.env.example) — there is no local "
        "fallback mode."
    )

TRUST_TABLE = os.getenv("TRUST_TABLE", "workspace.default.facility_trust")
PLANNER_ACTIONS_TABLE = os.getenv("PLANNER_ACTIONS_TABLE", "workspace.default.planner_actions")
DISTRICT_DESERT_TABLE = os.getenv(
    "DISTRICT_DESERT_TABLE", "workspace.default.district_desert")
REVIEW_DECISIONS_TABLE = os.getenv(
    "REVIEW_DECISIONS_TABLE", "workspace.default.review_decisions")

SOURCE_TABLE = os.getenv(
    "SOURCE_TABLE",
    "databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities",
)
PINCODE_TABLE = os.getenv(
    "PINCODE_TABLE",
    "databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset"
    ".india_post_pincode_directory",
)

# NL-query LLM — optional feature, kept on its own token/base-URL since it may
# be narrowly scoped (e.g. serving-endpoints/ai-gateway access only, no "sql"
# scope) and distinct from the SQL Warehouse credential above. Falls back to
# the main Databricks credential/host if not set separately.
LLM_TOKEN = os.getenv("LLM_TOKEN", "").strip() or DATABRICKS_TOKEN
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip().rstrip("/") or f"{DATABRICKS_HOST}/serving-endpoints"
LLM_ENDPOINT = os.getenv("LLM_ENDPOINT", "system.ai.llama-4-maverick")
