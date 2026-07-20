"""Real facility_trust reads via the Databricks SQL Statements REST API.

facility_trust's array/struct columns come back JSON-encoded as strings under
format=JSON_ARRAY + disposition=INLINE, so they're parsed with json.loads
before being handed to route handlers.
"""
import json
from typing import Optional

from config import PINCODE_TABLE, SOURCE_TABLE, TRUST_TABLE
from db.sql_client import DatabricksSQLClient
from repositories.region_data import (
    looks_like_garbage, normalize_state, raw_variants_for, title_case_place,
)

_ARRAY_COLUMNS = ("matched_capabilities", "contradictions", "positive_evidence",
                   "missing_supports", "caps")


def _parse_row(row: dict) -> dict:
    parsed = dict(row)
    for col in _ARRAY_COLUMNS:
        if col in parsed and isinstance(parsed[col], str):
            parsed[col] = json.loads(parsed[col]) if parsed[col] else []
    if "trust_score" in parsed and parsed["trust_score"] is not None:
        parsed["trust_score"] = int(parsed["trust_score"])
    for col in ("latitude", "longitude"):
        if parsed.get(col) is not None:
            parsed[col] = float(parsed[col])
    return parsed


class DatabricksFacilityRepo:
    def __init__(self, client: DatabricksSQLClient):
        self.client = client

    def list_capabilities(self) -> list[str]:
        rows = self.client.execute(
            f"""
            SELECT DISTINCT c.capability AS capability
            FROM {TRUST_TABLE}
            LATERAL VIEW explode(caps) t AS c
            ORDER BY capability
            """
        )
        return [r["capability"] for r in rows]

    def list_regions(self) -> list[dict]:
        """Builds the region picker from two sources per facility: the raw
        state/district text where it's already a real state/UT name (most
        rows), and a pincode-directory lookup (via the source table's zip
        code) for the ~4% of rows where `state` actually holds a city/district
        name instead. Rows with neither a recognized state nor a pincode match
        are excluded — never guessed, since a hand-curated city->state map
        can't be trusted at this scale (220+ distinct bad values)."""
        rows = self.client.execute(f"""
            WITH pin_dedup AS (
                SELECT pincode, first(statename) AS statename, first(district) AS district
                FROM {PINCODE_TABLE}
                GROUP BY pincode
            )
            SELECT ft.state AS orig_state, ft.district AS orig_district,
                   pin.statename AS pin_state, pin.district AS pin_district
            FROM {TRUST_TABLE} ft
            LEFT JOIN {SOURCE_TABLE} src ON ft.unique_id = src.unique_id
            LEFT JOIN pin_dedup pin ON try_cast(src.address_zipOrPostcode AS BIGINT) = pin.pincode
        """)

        regions = set()
        for r in rows:
            canonical = normalize_state(r["orig_state"])
            if canonical and not looks_like_garbage(r["orig_district"]):
                regions.add((canonical, r["orig_district"].strip()))
            elif (not looks_like_garbage(r["pin_state"])
                  and not looks_like_garbage(r["pin_district"])):
                # Pincode-directory names are ALL CAPS ("JAMMU AND KASHMIR") —
                # re-run through normalize_state() so they collapse onto the
                # same canonical bucket as clean rows rather than creating a
                # near-duplicate ("Jammu And Kashmir" vs "Jammu and Kashmir").
                pin_state = normalize_state(r["pin_state"]) or title_case_place(r["pin_state"])
                regions.add((pin_state, title_case_place(r["pin_district"])))
        return [{"state": s, "district": d} for s, d in sorted(regions)]

    def ranked_facilities(self, capability: str, state: str, district: Optional[str],
                           limit: int = 20, min_trust_score: Optional[int] = None,
                           trust_level: Optional[str] = None) -> list[dict]:
        """`state` is a canonical name from the (now-corrected) region picker.
        Most facilities match it directly via a known raw spelling variant
        (e.g. searching "Odisha" also matches raw rows stored as "Orissa");
        the rest are facilities recovered only via the pincode-directory join
        (list_regions()'s other path — e.g. raw state "Ahmedabad" whose real
        state is "Gujarat") and are matched through the same join here so the
        picker never offers a combination that then silently returns nothing.
        """
        variants = raw_variants_for(state)
        variant_params = {f"state_variant_{i}": v for i, v in enumerate(variants)}
        variant_placeholders = ", ".join(
            f"upper(:state_variant_{i})" for i in range(len(variants)))

        district_clause = ""
        if district:
            district_clause = "AND (ft.district = :district OR upper(pin.district) = upper(:district))"

        extra_clauses = ""
        if min_trust_score is not None:
            extra_clauses += "AND ft.trust_score >= :min_trust_score\n"
        if trust_level:
            extra_clauses += "AND ft.trust_level = :trust_level\n"

        statement = f"""
            WITH pin_dedup AS (
                SELECT pincode, first(statename) AS statename, first(district) AS district
                FROM {PINCODE_TABLE}
                GROUP BY pincode
            )
            SELECT ft.unique_id, ft.name, ft.state, ft.district, ft.latitude, ft.longitude,
                   ft.trust_score, ft.trust_level, ft.matched_capabilities, ft.explanation
            FROM {TRUST_TABLE} ft
            LEFT JOIN {SOURCE_TABLE} src ON ft.unique_id = src.unique_id
            LEFT JOIN pin_dedup pin ON try_cast(src.address_zipOrPostcode AS BIGINT) = pin.pincode
            WHERE array_contains(ft.matched_capabilities, :capability)
              AND (upper(ft.state) IN ({variant_placeholders}) OR upper(pin.statename) = upper(:state))
              {district_clause}
              {extra_clauses}
            ORDER BY ft.trust_score DESC
            LIMIT {int(limit)}
        """
        params = {"capability": capability, "state": state, **variant_params}
        if district:
            params["district"] = district
        if min_trust_score is not None:
            params["min_trust_score"] = min_trust_score
        if trust_level:
            params["trust_level"] = trust_level
        rows = self.client.execute(statement, params)
        return [_parse_row(r) for r in rows]

    def facility_detail(self, unique_id: str) -> Optional[dict]:
        rows = self.client.execute(
            f"""
            SELECT unique_id, name, state, district, latitude, longitude,
                   trust_score, trust_level, matched_capabilities, contradictions,
                   positive_evidence, missing_supports, explanation, caps
            FROM {TRUST_TABLE}
            WHERE unique_id = :unique_id
            LIMIT 1
            """,
            {"unique_id": unique_id},
        )
        return _parse_row(rows[0]) if rows else None
