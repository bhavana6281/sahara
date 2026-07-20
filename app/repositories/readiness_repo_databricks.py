"""Data Readiness Desk: leverage-scored review queue over facility_trust, plus
reviewer-decision persistence in review_decisions. A reviewer's triage tool —
AI surfaces high-leverage records (suspect AND consequential), a human
decides; nothing here auto-corrects a record.

Leverage = suspect (contradictions, missing supports, low trust) AND
consequential (claims a critical capability like ICU/surgery/oncology/trauma/
neonatal — the kind of claim that, if wrong, would silently misinform a
planner). Sorting by trust_score alone would miss a Medium-trust facility
with several cited contradictions; sorting by "has any contradiction" is
useless here — 9,982 of 10,088 facilities have at least one (verified before
building this), so leverage_score is a real ranking, not a binary flag.
"""
import json
import logging
import uuid

from config import REVIEW_DECISIONS_TABLE, TRUST_TABLE
from db.sql_client import DatabricksSQLClient

logger = logging.getLogger(__name__)

_ARRAY_COLUMNS = ("matched_capabilities", "contradictions")

_CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {REVIEW_DECISIONS_TABLE} (
  action_id      STRING,
  unique_id      STRING,
  reviewer       STRING,
  decision       STRING,
  note           STRING,
  leverage_score INT,
  reviewed_at    TIMESTAMP
) USING DELTA
"""

_LEVERAGE_EXPR = """
    ( size(f.contradictions) * 3
      + size(f.missing_supports) * 2
      + CASE WHEN arrays_overlap(f.matched_capabilities,
                array('icu','emergency_surgery','oncology','trauma','neonatal'))
             THEN 5 ELSE 0 END
      + CASE WHEN f.trust_level = 'Low' THEN 4
             WHEN f.trust_level = 'Medium' THEN 2 ELSE 0 END
    )
"""


def _parse_row(row: dict) -> dict:
    parsed = dict(row)
    for col in _ARRAY_COLUMNS:
        if col in parsed and isinstance(parsed[col], str):
            parsed[col] = json.loads(parsed[col]) if parsed[col] else []
    for col in ("trust_score", "n_contradictions", "n_missing", "leverage_score"):
        if parsed.get(col) is not None:
            parsed[col] = int(parsed[col])
    return parsed


class DatabricksReadinessRepo:
    def __init__(self, client: DatabricksSQLClient):
        self.client = client

    def ensure_table(self) -> None:
        try:
            self.client.execute(_CREATE_TABLE)
        except Exception:
            logger.warning("Could not ensure review_decisions table exists", exc_info=True)

    def summary(self) -> dict:
        rows = self.client.execute(f"""
            SELECT
              COUNT(*) AS total_facilities,
              SUM(CASE WHEN size(contradictions) > 0 THEN 1 ELSE 0 END) AS with_contradictions,
              SUM(CASE WHEN trust_level = 'Low' THEN 1 ELSE 0 END) AS low_trust,
              SUM(CASE WHEN size(missing_supports) > 0 THEN 1 ELSE 0 END) AS with_missing
            FROM {TRUST_TABLE}
        """)
        return {k: int(v) for k, v in rows[0].items()}

    def review_queue(self, reviewed: str = "all", limit: int = 200) -> list[dict]:
        reviewed_clause = "WHERE ld.unique_id IS NULL" if reviewed == "unreviewed" else ""
        statement = f"""
            WITH latest_decision AS (
                SELECT unique_id, decision, reviewed_at,
                       ROW_NUMBER() OVER (PARTITION BY unique_id ORDER BY reviewed_at DESC) AS rn
                FROM {REVIEW_DECISIONS_TABLE}
            )
            SELECT
              f.unique_id, f.name, f.state, f.district,
              f.trust_score, f.trust_level,
              size(f.contradictions) AS n_contradictions,
              size(f.missing_supports) AS n_missing,
              f.matched_capabilities, f.contradictions, f.explanation,
              {_LEVERAGE_EXPR} AS leverage_score,
              ld.decision AS latest_decision
            FROM {TRUST_TABLE} f
            LEFT JOIN latest_decision ld ON f.unique_id = ld.unique_id AND ld.rn = 1
            {reviewed_clause}
            ORDER BY leverage_score DESC, f.trust_score ASC
            LIMIT {int(limit)}
        """
        rows = self.client.execute(statement)
        return [_parse_row(r) for r in rows]

    def list_decisions(self, unique_id: str) -> list[dict]:
        rows = self.client.execute(f"""
            SELECT action_id, unique_id, reviewer, decision, note, leverage_score, reviewed_at
            FROM {REVIEW_DECISIONS_TABLE}
            WHERE unique_id = :unique_id
            ORDER BY reviewed_at DESC
        """, {"unique_id": unique_id})
        for r in rows:
            r["reviewed_at"] = str(r["reviewed_at"])
            if r.get("leverage_score") is not None:
                r["leverage_score"] = int(r["leverage_score"])
        return rows

    def add_decision(self, unique_id: str, reviewer: str, decision: str,
                      note: str, leverage_score: int) -> dict:
        action_id = str(uuid.uuid4())
        self.client.execute(f"""
            INSERT INTO {REVIEW_DECISIONS_TABLE}
            (action_id, unique_id, reviewer, decision, note, leverage_score, reviewed_at)
            VALUES (:action_id, :unique_id, :reviewer, :decision, :note,
                    CAST(:leverage_score AS INT), current_timestamp())
        """, {
            "action_id": action_id, "unique_id": unique_id, "reviewer": reviewer,
            "decision": decision, "note": note, "leverage_score": leverage_score,
        })
        created = self.list_decisions(unique_id)
        return next((d for d in created if d["action_id"] == action_id), created[0])
