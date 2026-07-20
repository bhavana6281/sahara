"""Repository singletons backed by the Databricks SQL Warehouse."""
from functools import lru_cache

import config
from db.sql_client import DatabricksSQLClient


@lru_cache
def get_sql_client():
    return DatabricksSQLClient(config.DATABRICKS_HOST, config.DATABRICKS_TOKEN, config.WAREHOUSE_ID)


@lru_cache
def get_facility_repo():
    from repositories.facility_repo_databricks import DatabricksFacilityRepo
    return DatabricksFacilityRepo(get_sql_client())


@lru_cache
def get_planner_actions_repo():
    from repositories.planner_actions_repo_databricks import DatabricksPlannerActionsRepo
    return DatabricksPlannerActionsRepo(get_sql_client())


@lru_cache
def get_desert_repo():
    from repositories.desert_repo_databricks import DatabricksDesertRepo
    return DatabricksDesertRepo(get_sql_client())


@lru_cache
def get_readiness_repo():
    from repositories.readiness_repo_databricks import DatabricksReadinessRepo
    return DatabricksReadinessRepo(get_sql_client())


@lru_cache
def get_llm_client():
    from openai import OpenAI
    return OpenAI(api_key=config.LLM_TOKEN, base_url=config.LLM_BASE_URL)


@lru_cache
def get_nl_agent():
    from agent import NLQueryAgent
    return NLQueryAgent(get_llm_client(), config.LLM_ENDPOINT)
