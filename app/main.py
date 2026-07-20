import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import config
from api import (
    routes_architecture, routes_desert, routes_facilities, routes_meta,
    routes_planner_actions, routes_query, routes_readiness,
)
from deps import get_planner_actions_repo, get_readiness_repo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sahara")

app = FastAPI(title="Sahara — Healthcare Facility Intelligence")


@app.get("/health")
def health():
    return {"status": "ok"}


# API routers must be registered before the static mount below, or the
# catch-all static route would shadow /api/*.
app.include_router(routes_meta.router)
app.include_router(routes_facilities.router)
app.include_router(routes_planner_actions.router)
app.include_router(routes_desert.router)
app.include_router(routes_readiness.router)
app.include_router(routes_query.router)
app.include_router(routes_architecture.router)

app.mount("/", StaticFiles(directory="static", html=True), name="static")


@app.on_event("startup")
def on_startup():
    logger.info("Connected to Databricks SQL Warehouse at %s", config.DATABRICKS_HOST)
    get_planner_actions_repo().ensure_table()
    get_readiness_repo().ensure_table()
