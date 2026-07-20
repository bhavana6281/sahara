from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from db.sql_client import DatabricksQueryError, DatabricksQueryTimeout
from deps import get_facility_repo

router = APIRouter()


@router.get("/api/capabilities")
def list_capabilities():
    try:
        return {"capabilities": get_facility_repo().list_capabilities()}
    except DatabricksQueryTimeout as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DatabricksQueryError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/api/regions")
def list_regions():
    try:
        return {"regions": get_facility_repo().list_regions()}
    except DatabricksQueryTimeout as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DatabricksQueryError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/api/facilities")
def ranked_facilities(
    capability: str, state: str, district: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    min_trust_score: Optional[int] = Query(default=None, ge=0, le=100),
    trust_level: Optional[str] = Query(default=None),
):
    try:
        facilities = get_facility_repo().ranked_facilities(
            capability, state, district, limit=limit,
            min_trust_score=min_trust_score, trust_level=trust_level)
        return {"count": len(facilities), "facilities": facilities}
    except DatabricksQueryTimeout as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DatabricksQueryError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/api/facilities/{unique_id}")
def facility_detail(unique_id: str):
    try:
        detail = get_facility_repo().facility_detail(unique_id)
    except DatabricksQueryTimeout as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DatabricksQueryError as e:
        raise HTTPException(status_code=502, detail=str(e))
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No facility with unique_id={unique_id!r}")
    return detail
