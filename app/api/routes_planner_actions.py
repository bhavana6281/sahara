from fastapi import APIRouter, HTTPException

from db.sql_client import DatabricksQueryError, DatabricksQueryTimeout
from deps import get_facility_repo, get_planner_actions_repo
from models import PlannerActionCreate

router = APIRouter()


def _require_facility(unique_id: str):
    try:
        detail = get_facility_repo().facility_detail(unique_id)
    except DatabricksQueryTimeout as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DatabricksQueryError as e:
        raise HTTPException(status_code=502, detail=str(e))
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No facility with unique_id={unique_id!r}")


@router.get("/api/facilities/{unique_id}/actions")
def list_actions(unique_id: str):
    _require_facility(unique_id)
    try:
        return {"actions": get_planner_actions_repo().list_actions(unique_id)}
    except DatabricksQueryTimeout as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DatabricksQueryError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/api/facilities/{unique_id}/actions", status_code=201)
def add_action(unique_id: str, body: PlannerActionCreate):
    _require_facility(unique_id)
    if body.action_type == "override" and body.override_trust_level is None:
        raise HTTPException(
            status_code=400,
            detail="override_trust_level is required when action_type is 'override'",
        )
    try:
        return get_planner_actions_repo().add_action(
            unique_id=unique_id,
            action_type=body.action_type,
            note_text=body.note_text,
            override_trust_level=body.override_trust_level,
            planner_name=body.planner_name,
        )
    except DatabricksQueryTimeout as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DatabricksQueryError as e:
        raise HTTPException(status_code=502, detail=str(e))
