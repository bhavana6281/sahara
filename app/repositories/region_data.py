"""Canonical Indian state/UT names, known spelling variants, and the shared
upstream-data-quality SQL filter used by every repo that reads raw state/district
text off facility_trust (Trust Desk, Medical Desert Planner, Data Readiness Desk).
"""

VALID_STATES = {
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
    "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir",
    "Ladakh", "Lakshadweep", "Puducherry",
}

# lowercase variant -> canonical. Identity entries let normalize_state() do a
# single dict lookup regardless of whether the source value was already clean.
# Extend this as more variants turn up in testing.
STATE_ALIASES = {
    **{s.lower(): s for s in VALID_STATES},
    "orissa": "Odisha",
    "tamilnadu": "Tamil Nadu",
    "tamil nadu.": "Tamil Nadu",
    "up": "Uttar Pradesh",
    "u.p.": "Uttar Pradesh",
    "uttaranchal": "Uttarakhand",
    "pondicherry": "Puducherry",
    "new delhi": "Delhi",
    "nct of delhi": "Delhi",
    "delhi ncr": "Delhi",
    "j&k": "Jammu and Kashmir",
    "jammu & kashmir": "Jammu and Kashmir",
    "andaman & nicobar islands": "Andaman and Nicobar Islands",
    "andaman and nicobar": "Andaman and Nicobar Islands",
    "punjab region": "Punjab",
    "the dadra and nagar haveli and daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "dadra and nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
    "daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
}

# Postal-data "missing value" sentinels (distinct from looks_like_garbage()'s
# structural checks — these are plausible-looking short strings, not obviously
# corrupted text, so they need an explicit denylist).
_MISSING_VALUE_SENTINELS = {"na", "n.a.", "n/a", "none", "nil", "-"}


def normalize_state(raw: str | None) -> str | None:
    """Return the canonical state/UT name for a raw value, or None if it isn't
    a recognized state/UT at all (as opposed to just being spelled oddly)."""
    if not raw:
        return None
    return STATE_ALIASES.get(raw.strip().lower())


# Reverse of STATE_ALIASES: canonical name -> every raw spelling seen for it.
# Used to search facility_trust.state by canonical name without an extra join
# for the majority of rows that just have an odd spelling (not a wrong field).
_CANONICAL_TO_RAW_VARIANTS: dict[str, list[str]] = {}
for _raw, _canonical in STATE_ALIASES.items():
    _CANONICAL_TO_RAW_VARIANTS.setdefault(_canonical, [])
    if _raw not in _CANONICAL_TO_RAW_VARIANTS[_canonical]:
        _CANONICAL_TO_RAW_VARIANTS[_canonical].append(_raw)


def raw_variants_for(canonical_state: str) -> list[str]:
    """Every raw spelling in the data that normalizes to this canonical
    state/UT (always includes the canonical spelling itself)."""
    return _CANONICAL_TO_RAW_VARIANTS.get(canonical_state, [canonical_state])


def looks_like_garbage(value: str | None) -> bool:
    """True for values that are clearly not real place names — GeoJSON blobs,
    'null' sentinels, bare numbers/dates, JSON-array fragments. A real,
    upstream data-quality artifact in a handful of source rows, not something
    we invented."""
    if not value or not value.strip():
        return True
    v = value.strip()
    if v.startswith("{") or "[" in v or "]" in v or '"' in v:
        return True
    if v.lower() in _MISSING_VALUE_SENTINELS or v.lower() == "null":
        return True
    if v.replace("-", "").isdigit():  # bare numbers and YYYY-MM-DD dates
        return True
    return False


def title_case_place(value: str) -> str:
    """Pincode-directory district/state names come back ALL CAPS; title-case
    them so they read consistently with the rest of the app's place names."""
    return " ".join(w.capitalize() for w in value.strip().split())


def valid_region_filter(alias: str = "") -> str:
    """SQL WHERE-clause fragment excluding the garbage values looks_like_garbage()
    checks for, for use in aggregate queries (desert centroids, readiness desk)
    where a fast SQL-side filter is more appropriate than fetching every row."""
    p = f"{alias}." if alias else ""
    return f"""
      {p}state IS NOT NULL AND {p}state != '' AND {p}district IS NOT NULL AND {p}district != ''
      AND {p}state NOT LIKE '{{%' AND {p}district NOT LIKE '{{%'
      AND lower({p}state) != 'null' AND lower({p}district) != 'null'
      AND NOT ({p}state RLIKE '^[0-9]+$') AND NOT ({p}district RLIKE '^[0-9]+$')
      AND NOT ({p}state RLIKE '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$') AND NOT ({p}district RLIKE '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$')
      AND {p}state NOT LIKE '%"%' AND {p}district NOT LIKE '%"%'
      AND {p}state NOT LIKE '%[%' AND {p}district NOT LIKE '%[%'
      AND {p}state NOT LIKE '%]%' AND {p}district NOT LIKE '%]%'
    """
