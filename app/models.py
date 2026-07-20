from typing import Literal, Optional

from pydantic import BaseModel, Field

TrustLevel = Literal["High", "Medium", "Low"]
ActionType = Literal["note", "override"]


class CapabilityEvidence(BaseModel):
    capability: str
    status: str  # present | absent | uncertain
    confidence: float
    evidence: str


class Contradiction(BaseModel):
    reason: str
    evidence: str


class FacilitySummary(BaseModel):
    unique_id: str
    name: str
    state: str
    district: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    trust_score: int
    trust_level: TrustLevel
    matched_capabilities: list[str]
    explanation: str


class FacilityDetail(FacilitySummary):
    contradictions: list[Contradiction]
    positive_evidence: list[str]
    missing_supports: list[str]
    caps: list[CapabilityEvidence]


class Region(BaseModel):
    state: str
    district: str


class PlannerAction(BaseModel):
    action_id: str
    unique_id: str
    action_type: ActionType
    note_text: str
    override_trust_level: Optional[TrustLevel] = None
    planner_name: str
    created_at: str


class PlannerActionCreate(BaseModel):
    action_type: ActionType
    note_text: str = Field(min_length=3, max_length=2000)
    override_trust_level: Optional[TrustLevel] = None
    planner_name: str = Field(default="Anonymous planner", max_length=200)


ReviewDecisionType = Literal["confirmed_issue", "looks_fine", "needs_field_check", "corrected"]


class ReviewDecisionCreate(BaseModel):
    decision: ReviewDecisionType
    note: str = Field(default="", max_length=2000)
    leverage_score: int = Field(ge=0)
    reviewer: str = Field(default="Anonymous reviewer", max_length=200)


class LLMQueryFilterRaw(BaseModel):
    """Unvalidated shape the LLM is asked to produce. Every field optional — a
    missing or malformed field is treated as null, never an error, so a
    partially-sane LLM response still degrades gracefully field-by-field."""
    capability: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    min_trust_score: Optional[int] = None
    trust_level: Optional[TrustLevel] = None
    desert_status: Optional[Literal["covered", "medical_desert", "data_desert"]] = None
    model_config = {"extra": "ignore"}


class NLQueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
