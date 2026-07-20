"""Read-only district_desert reads. Approximates each district's map position
as the centroid (mean lat/lng) of its facility_trust rows — district_desert
has no coordinates of its own, and this project has no district-boundary
GeoJSON. This is an approximate marker position, not a polygon boundary; the
frontend (desertMap.js / the legend) says so explicitly.
"""
from typing import Optional

from config import DISTRICT_DESERT_TABLE, TRUST_TABLE
from db.sql_client import DatabricksSQLClient
from repositories.region_data import raw_variants_for, valid_region_filter


def _parse_row(row: dict) -> dict:
    parsed = dict(row)
    for col in ("n_facilities", "n_present", "n_absent", "n_unknown", "n_geolocated_facilities"):
        if parsed.get(col) is not None:
            parsed[col] = int(parsed[col])
    if parsed.get("coverage_ratio") is not None:
        parsed["coverage_ratio"] = float(parsed["coverage_ratio"])
    for col in ("latitude", "longitude"):
        if parsed.get(col) is not None:
            parsed[col] = float(parsed[col])
    return parsed


class DatabricksDesertRepo:
    def __init__(self, client: DatabricksSQLClient):
        self.client = client

    def list_capabilities(self) -> list[str]:
        rows = self.client.execute(
            f"SELECT DISTINCT capability FROM {DISTRICT_DESERT_TABLE} ORDER BY capability"
        )
        return [r["capability"] for r in rows]

    def desert_map(self, capability: str, state: Optional[str] = None) -> list[dict]:
        params = {"capability": capability}
        state_clause = ""
        centroid_state_clause = ""
        if state:
            variants = raw_variants_for(state)
            variant_params = {f"state_variant_{i}": v for i, v in enumerate(variants)}
            placeholders = ", ".join(f"upper(:state_variant_{i})" for i in range(len(variants)))
            state_clause = f"AND upper(d.state) IN ({placeholders})"
            centroid_state_clause = f"AND upper(state) IN ({placeholders})"
            params.update(variant_params)

        statement = f"""
            WITH facility_centroids AS (
                SELECT state, district,
                       avg(latitude) AS centroid_lat,
                       avg(longitude) AS centroid_lng,
                       count(*) AS n_geolocated_facilities
                FROM {TRUST_TABLE}
                WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                  AND {valid_region_filter()}
                  {centroid_state_clause}
                GROUP BY state, district
            )
            SELECT
                d.state, d.district, d.capability, d.status,
                d.n_facilities, d.n_present, d.n_absent, d.n_unknown, d.coverage_ratio,
                c.centroid_lat AS latitude, c.centroid_lng AS longitude,
                COALESCE(c.n_geolocated_facilities, 0) AS n_geolocated_facilities
            FROM {DISTRICT_DESERT_TABLE} d
            LEFT JOIN facility_centroids c ON d.state = c.state AND d.district = c.district
            WHERE d.capability = :capability
              AND d.state IS NOT NULL AND d.district IS NOT NULL
              {state_clause}
            ORDER BY d.state, d.district
        """
        rows = self.client.execute(statement, params)
        return [_parse_row(r) for r in rows]
