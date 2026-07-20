"""NL→filter translation. Owns the LLM prompt + validation only — never builds
or executes SQL, and never touches trust_score. The LLM emits a small
validated JSON filter object; routes_query.py turns that into calls against
the existing, already-parameterized repository methods. No LLM-generated
string ever reaches DatabricksSQLClient.execute() — this is what keeps trust
"looked up, never computed live" true even for the NL-query entry point.
"""
import json
import logging
from typing import Optional

from models import LLMQueryFilterRaw

logger = logging.getLogger(__name__)


class AgentUnavailable(Exception):
    """LLM could not be reached (timeout, throttled, auth). Caller should degrade."""


class AgentParseError(Exception):
    """LLM responded but output couldn't be parsed/validated. Caller should degrade."""


_SYSTEM_PROMPT_TEMPLATE = """You are a query-translation assistant for Sahara, a \
healthcare-facility-trust lookup tool for India. You NEVER answer questions about \
facilities directly and you NEVER generate SQL. Your ONLY job is to translate a plain \
English question into a single JSON object matching this exact schema, with no other text:

{{
  "capability": string | null,       // one of: {capabilities}, or null if not mentioned
  "state": string | null,            // a state name mentioned in the question, or null
  "district": string | null,         // a district/city name mentioned in the question, or null
  "min_trust_score": integer | null, // 0-100, only if the user asks for a trust/confidence floor
  "trust_level": string | null,      // one of: "High", "Medium", "Low", or null
  "desert_status": string | null     // one of: "covered", "medical_desert", "data_desert", or null
}}

Rules:
- desert_status is the ONLY signal that routes this question to district-level coverage
  results instead of facility-level results. Set it ONLY if the question is about data
  coverage / "do we know" / deserts, not about specific facilities. Default to
  "data_desert" if the question asks about deserts/coverage without specifying which kind.
- Only use values from the allowed capability list above. If the question mentions a
  capability, state, district, or trust level that you are not confident matches the
  allowed list, set that field to null instead of guessing or inventing a close match.
- Never output SQL, prose, or markdown code fences — JSON only, and nothing else.
- You do not know any facility names, trust scores, or contradictions. You only
  translate the question into filter fields. Do not fabricate an answer.

Example:
Question: "Show me high-trust ICU facilities in Bihar"
Output: {{"capability": "icu", "state": "Bihar", "district": null, "min_trust_score": null, \
"trust_level": "High", "desert_status": null}}

Example:
Question: "Where don't we have oxygen data in Jharkhand"
Output: {{"capability": "oxygen", "state": "Jharkhand", "district": null, \
"min_trust_score": null, "trust_level": null, "desert_status": "data_desert"}}
"""

_DESERT_KEYWORDS = ("desert", "coverage", "don't know", "do we know", "unknown", "no data")


def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    return t.strip()


def _extract_answer_text(content) -> str:
    """message.content is a plain string on most OpenAI-compatible endpoints, but
    this Qwen deployment is a reasoning model: content comes back as a list of
    typed parts — a 'reasoning' part holding the model's chain-of-thought, then
    a 'text' part holding the actual answer. Only 'text' parts are the answer;
    reasoning is discarded, never parsed as if it were the response."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
        return "".join(parts)
    return str(content) if content else ""


class NLQueryAgent:
    def __init__(self, llm_client, model_name: str):
        self.llm_client = llm_client
        self.model_name = model_name

    def nl_to_filter(self, question: str, capabilities: list[str],
                      regions: list[dict]) -> tuple[LLMQueryFilterRaw, list[str]]:
        """Single function boundary — the seam for a future @trace('sql_generation')
        decorator. Raises AgentUnavailable / AgentParseError; never returns anything
        that hasn't passed schema + allowlist validation."""
        prompt = _SYSTEM_PROMPT_TEMPLATE.format(capabilities=", ".join(sorted(capabilities)))
        try:
            resp = self.llm_client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "system", "content": prompt},
                          {"role": "user", "content": question}],
                temperature=0, max_tokens=1500, timeout=25,
            )
        except Exception as e:
            logger.warning("LLM call failed: %s", e)
            raise AgentUnavailable(str(e)) from e

        raw_text = _extract_answer_text(resp.choices[0].message.content)
        if not raw_text:
            raise AgentParseError("LLM produced no final answer text (reasoning-only response)")
        cleaned = _strip_code_fences(raw_text)
        try:
            obj = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise AgentParseError(f"LLM did not return valid JSON: {e}") from e
        try:
            parsed = LLMQueryFilterRaw.model_validate(obj)
        except Exception as e:
            raise AgentParseError(f"LLM JSON did not match schema: {e}") from e

        return self._validate_against_allowlists(parsed, set(capabilities), regions)

    @staticmethod
    def _validate_against_allowlists(parsed: LLMQueryFilterRaw, allowed_caps: set[str],
                                      regions: list[dict]) -> tuple[LLMQueryFilterRaw, list[str]]:
        warnings: list[str] = []
        if parsed.capability and parsed.capability not in allowed_caps:
            warnings.append(f"capability '{parsed.capability}' not recognized — ignored")
            parsed.capability = None
        if parsed.min_trust_score is not None and not (0 <= parsed.min_trust_score <= 100):
            warnings.append("min_trust_score out of range — ignored")
            parsed.min_trust_score = None
        valid_states = {r["state"] for r in regions}
        valid_pairs = {(r["state"], r["district"]) for r in regions}
        if parsed.state and parsed.state not in valid_states:
            warnings.append(f"state '{parsed.state}' not recognized — ignored")
            parsed.state, parsed.district = None, None
        if parsed.district and parsed.state and (parsed.state, parsed.district) not in valid_pairs:
            warnings.append(f"district '{parsed.district}' not recognized in {parsed.state} — ignored")
            parsed.district = None
        return parsed, warnings

    def summarize_results(self, question: str, parsed_filter: LLMQueryFilterRaw,
                           facilities: list[dict], desert_records: list[dict]) -> Optional[str]:
        """Second, independent LLM call — cosmetic phrasing only. Never affects
        trust_score, ranking, or which records were returned — those are already
        finalized before this runs. Caller swallows any failure and just omits
        the summary."""
        payload = {
            "question": question,
            "filter_applied": parsed_filter.model_dump(),
            "total_facilities_found": len(facilities),
            "total_desert_records_found": len(desert_records),
            "facilities_sample": [{"name": f["name"], "trust_level": f["trust_level"],
                                    "trust_score": f["trust_score"]} for f in facilities[:10]],
            "desert_records_sample": [{"district": d["district"], "capability": d["capability"],
                                        "status": d["status"]} for d in desert_records[:10]],
        }
        resp = self.llm_client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": (
                    "You write one short (2-3 sentence) plain-language paragraph "
                    "summarizing search results for a healthcare-facility planner. Use ONLY "
                    "the JSON facts you are given — never invent or restate a trust score, "
                    "capability, or coverage status that isn't already in the data. The "
                    "'*_sample' lists may be a truncated preview — always state the count from "
                    "'total_facilities_found'/'total_desert_records_found', never the length of "
                    "the sample list. If the total is zero, say so plainly and suggest this may "
                    "be a data desert rather than a confirmed absence of care. Plain text only, "
                    "no markdown.")},
                {"role": "user", "content": json.dumps(payload)},
            ],
            temperature=0.2, max_tokens=2000, timeout=30,
        )
        text = _extract_answer_text(resp.choices[0].message.content).strip()
        if not text:
            logger.info("summarize_results got a reasoning-only response (no final text) — "
                        "omitting summary, this is non-fatal")
        return text or None


def keyword_fallback_filter(question: str, capabilities: list[str],
                             regions: list[dict]) -> LLMQueryFilterRaw:
    """Zero-LLM structured extraction via substring matching. Used when the LLM is
    unavailable/throttled/unparseable so the NL box still returns something useful —
    the literal 'core app still works without LLM' promise, applied to NL-query too.
    Can only ever select values FROM the allowlists it iterates, never parse free
    text into a new value — no injection surface by construction."""
    q = question.lower()
    all_caps = sorted(capabilities, key=len, reverse=True)
    capability = next((c for c in all_caps if c.replace("_", " ") in q), None)
    state = next((r["state"] for r in regions if r["state"].lower() in q), None)
    district = None
    if state:
        district = next((r["district"] for r in regions
                          if r["state"] == state and r["district"].lower() in q), None)
    trust_level = next((lvl for lvl in ("High", "Medium", "Low") if lvl.lower() in q), None)
    desert_status = "data_desert" if any(k in q for k in _DESERT_KEYWORDS) else None
    return LLMQueryFilterRaw(capability=capability, state=state, district=district,
                              min_trust_score=None, trust_level=trust_level,
                              desert_status=desert_status)
