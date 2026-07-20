from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from db.sql_client import DatabricksQueryError, DatabricksQueryTimeout
from deps import get_readiness_repo
from models import ReviewDecisionCreate

router = APIRouter()


@router.get("/api/readiness/summary")
def readiness_summary():
    try:
        return get_readiness_repo().summary()
    except DatabricksQueryTimeout as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DatabricksQueryError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/api/readiness/queue")
def review_queue(
    reviewed: Literal["all", "unreviewed"] = "all",
    limit: int = Query(default=200, ge=1, le=200),
):
    try:
        rows = get_readiness_repo().review_queue(reviewed=reviewed, limit=limit)
        return {"count": len(rows), "queue": rows}
    except DatabricksQueryTimeout as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DatabricksQueryError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/api/readiness/queue/{unique_id}/decisions")
def list_decisions(unique_id: str):
    try:
        return {"decisions": get_readiness_repo().list_decisions(unique_id)}
    except DatabricksQueryTimeout as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DatabricksQueryError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/api/readiness/queue/{unique_id}/decisions", status_code=201)
def add_decision(unique_id: str, body: ReviewDecisionCreate):
    try:
        return get_readiness_repo().add_decision(
            unique_id=unique_id, reviewer=body.reviewer, decision=body.decision,
            note=body.note, leverage_score=body.leverage_score)
    except DatabricksQueryTimeout as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DatabricksQueryError as e:
        raise HTTPException(status_code=502, detail=str(e))
