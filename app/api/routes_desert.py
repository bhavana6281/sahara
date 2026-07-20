from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from db.sql_client import DatabricksQueryError, DatabricksQueryTimeout
from deps import get_desert_repo

router = APIRouter()


@router.get("/api/desert/capabilities")
def desert_capabilities():
    try:
        return {"capabilities": get_desert_repo().list_capabilities()}
    except DatabricksQueryTimeout as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DatabricksQueryError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/api/desert/map")
def desert_map(capability: str, state: Optional[str] = Query(default=None)):
    try:
        valid_capabilities = get_desert_repo().list_capabilities()
        if capability not in valid_capabilities:
            raise HTTPException(
                status_code=400,
                detail=f"capability must be one of {valid_capabilities}",
            )
        districts = get_desert_repo().desert_map(capability, state)
        plotted = sum(1 for d in districts if d["latitude"] is not None)
        return {"count": len(districts), "plotted": plotted, "districts": districts}
    except DatabricksQueryTimeout as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DatabricksQueryError as e:
        raise HTTPException(status_code=502, detail=str(e))
