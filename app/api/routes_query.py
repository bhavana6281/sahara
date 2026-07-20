from fastapi import APIRouter, HTTPException

import agent
from db.sql_client import DatabricksQueryError, DatabricksQueryTimeout
from deps import get_desert_repo, get_facility_repo, get_nl_agent
from models import NLQueryRequest

router = APIRouter()


@router.post("/api/query")
def nl_query(body: NLQueryRequest):
    facility_repo = get_facility_repo()
    desert_repo = get_desert_repo()
    nl_agent = get_nl_agent()

    try:
        capabilities = facility_repo.list_capabilities()
        regions = facility_repo.list_regions()
    except DatabricksQueryTimeout as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DatabricksQueryError as e:
        raise HTTPException(status_code=502, detail=str(e))

    warnings: list[str] = []
    used_llm = True
    try:
        parsed, llm_warnings = nl_agent.nl_to_filter(body.question, capabilities, regions)
        warnings.extend(llm_warnings)
    except (agent.AgentUnavailable, agent.AgentParseError) as e:
        used_llm = False
        warnings.append(
            f"LLM unavailable or returned unusable output — used keyword matching instead ({e})")
        parsed = agent.keyword_fallback_filter(body.question, capabilities, regions)

    facilities, desert_records = [], []
    try:
        if parsed.desert_status:
            if parsed.capability:
                districts = desert_repo.desert_map(parsed.capability, parsed.state)
                desert_records = [d for d in districts if d["status"] == parsed.desert_status]
                if parsed.district:
                    desert_records = [d for d in desert_records if d["district"] == parsed.district]
            else:
                warnings.append(
                    "Could not determine a capability for the coverage question — "
                    "try the Medical Desert Planner tab directly.")
        elif parsed.capability and parsed.state:
            facilities = facility_repo.ranked_facilities(
                parsed.capability, parsed.state, parsed.district,
                min_trust_score=parsed.min_trust_score, trust_level=parsed.trust_level, limit=20)
        else:
            warnings.append(
                "Could not determine both a capability and a state from your question — "
                "try the capability/state picker above, or mention both explicitly.")
    except DatabricksQueryTimeout as e:
        raise HTTPException(status_code=504, detail=str(e))
    except DatabricksQueryError as e:
        raise HTTPException(status_code=502, detail=str(e))

    summary = None
    if used_llm and (facilities or desert_records):
        try:
            summary = nl_agent.summarize_results(body.question, parsed, facilities, desert_records)
        except Exception:
            summary = None  # cosmetic only — never fail the request over phrasing

    return {
        "query_text": body.question,
        "interpreted_filter": parsed.model_dump(),
        "used_llm": used_llm,
        "warnings": warnings,
        "facilities": facilities,
        "desert_records": desert_records,
        "summary": summary,
    }
