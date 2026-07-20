# CLAUDE.md — Sahara (Hack-Nation Challenge 04, Databricks)

> This file is read automatically by Claude Code as project context. Keep it current.
> Read `ARCHITECTURE.md` alongside this for the full system design.

## What we're building

A **Healthcare Facility Intelligence App on Databricks Free Edition** for the Databricks
"Data Legend" challenge. A non-technical NGO planner asks about healthcare capability in a
region; the app returns trust-scored, evidence-cited facilities on a map, and honestly
separates *no facility* from *no data*. The renter/planner's notes and overrides persist.

**One-line thesis:** the trust score is computed **deterministically in Spark** and stored in
Delta — never judged by an LLM at request time. The LLM only does NL→SQL and phrasing. This is
what makes us different and what wins the Evidence & Trust criterion.

## What wins (rubric — optimize for this order)

| Criterion | Weight | Our lever |
|---|---|---|
| Evidence & Trust | 35% | Deterministic trust UDF + row-level citations + data-desert vs medical-desert |
| Product Judgment | 30% | Clear planner journey, honest uncertainty, persisted decisions |
| Technical Execution | 25% | Real Databricks App on Free Edition; Mosaic AI, SQL Warehouse, Delta, (Lakebase) |
| Ambition | 10% | MLflow 3 tracing; 405B as independent second opinion |

## The four differentiators (neither reference project had all of these)

1. **Deterministic trust/contradiction engine as a Spark job** → `facility_trust` Delta table.
2. **Data-desert vs medical-desert classifier** → `district_desert` Delta table (3 states).
3. **Databricks App + planner-action persistence** (Lakebase, fallback Delta) → `planner_actions`.
4. **MLflow 3 Tracing** over the whole request chain.

## Track strategy — ONE deep track + thin views (do NOT build four equal tracks)

The brief says: "Choose ONE mission track. Nail its minimum workflow end-to-end. You are not
expected to build all four." We obey that. The trick: three of the four tracks are the SAME two
Delta tables (`facility_trust`, `district_desert`) seen through a different lens, so we get
multi-track *coverage* from one deep spine. Multi-track integration is exactly what the 10%
Ambition criterion rewards.

- **PRIMARY (deep, demo spine): Facility Trust Desk** — "Can this facility do what it claims?"
  Full journey: pick capability + region → ranked facilities from `facility_trust` → expand →
  contradictions + cited source text → note/override persisted. This is where the 65% lives.
- **VIEW 2 (thin, near-free): Medical Desert Planner** — the 3-color district map rendered from
  `district_desert`. Already built in Step 2; just add the map view.
- **VIEW 3 (thin, near-free): Data Readiness Desk** — filter `facility_trust` + `district_desert`
  for low-confidence / contradicted / data-desert records into a "review queue". Showcases the
  data-desert-vs-medical-desert idea directly.
- **SKIP: Referral Copilot** — highest effort (geo-routing) for least new value; overlaps Trust
  Desk. Only attempt if everything else is done and demoing cleanly.

Rule: a VIEW may only be added AFTER the PRIMARY track demos end-to-end without breaking. A thin
view that reads an existing table is fine; anything requiring new backend work is out of scope
until the spine is solid.

## Build order (do in this sequence; each is independently demoable)

- ~~Step 0~~ **skipped** — the source share is already clean Delta (no Excel/CSV, no staging
  table needed); `02_trust_engine.py` reads `...virtue_foundation_dataset.facilities` directly.
- **Step 1** `notebooks/02_trust_engine.py` — trust + contradictions → `facility_trust`. ★ highest value
- **Step 2** `notebooks/03_desert_classifier.py` — desert classification → `district_desert`. ★
- **Step 3** `app/` — Databricks App: **PRIMARY track (Facility Trust Desk)** journey +
  persistence. This is the demo spine — get it fully working before anything below.
- **Step 4** `app/agent.py` — NL→SQL via Mosaic AI (join results to `facility_trust`).
- **Step 5** VIEW 2 — **Medical Desert Planner**: 3-color map from `district_desert`. Thin.
- **Step 6** VIEW 3 — **Data Readiness Desk**: review queue filtered from the two tables. Thin.
- **Step 7** `app/tracing.py` — MLflow 3 tracing wrappers (Ambition).
- **Step 8** 405B independent validation (optional).

**Time-boxed cut line.** If short on time, ship in this order and stop wherever the clock runs
out — each prefix is a complete, honest submission:
- Minimum winning submission: Steps 0 → 1 → 2 → 3 (one deep track, both tables, persistence).
- Add if time: Step 4 (NL query), then Step 5 (desert map), then Step 6 (readiness queue).
- Ambition multipliers last: Step 7 (MLflow), Step 8 (405B).
Never start a VIEW (5/6) until the PRIMARY track (3) demos end-to-end without breaking.

## Data — official Virtue Foundation share (10,088 rows, 51 cols, ALL string except lat/lng)

SOURCE (read-only Delta share, exact path):
`databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities`

READ from the share; WRITE derived tables to `workspace.default` (facility_trust,
district_desert, planner_actions) — you own that schema.

Key column: **`unique_id`** (string). There is NO `facility_id` and NO `full_text_blob`.

Text fields for capability detection (all STRING, arrays are JSON-ish text — just regex
over them, no array parsing): `description`, `specialties`, `procedure`, `equipment`,
`capability`, `name`.

Location: `address_stateOrRegion` (state), `address_city` (district), `address_line1`,
`address_zipOrPostcode`, and **real `latitude`/`longitude` as `double`** (use for the map).

Sparse / unreliable — measure coverage, do NOT trust as ground truth: `numberDoctors`,
`capacity`, `yearEstablished` (all string, frequently empty). Everything is typed `string`,
so cast where needed.

Companion shared tables (bonus enrichment, use after core works):
`...virtue_foundation_dataset.india_post_pincode_directory` (geography),
`...virtue_foundation_dataset.nfhs_5_district_health_indicators` (district health survey —
cross-check data-desert calls against real indicators).

## Trust engine spec (implement in `02_trust_engine.py`)

For each facility, compute over the joined text of description + full_text_blob + arrays:

**Capability detection** — regex/keyword match per capability, classify each as
`present | absent | uncertain`, with the matched **source substring** captured as evidence
(this substring is the row-level citation — required, no citation = no points).

**Contradiction rules (each lowers trust; store the human-readable reason + evidence):**
- ICU present but no oxygen AND no ventilator evidence → critical contradiction.
- Emergency surgery / appendectomy present but no anesthesiologist → critical.
- Surgery/OT present but no operation-theatre evidence → contradiction.
- NICU / neonatal present but no pediatric specialist AND no oxygen/incubator → contradiction.
- Dialysis present but evidence says "monthly" / "camp" (not recurring) → contradiction.
- 24/7 availability present but doctors documented "part-time" → contradiction.
- Blanket vague claims ("all facilities available", "complete healthcare") → penalty.
- Equipment "non-functional" / "under repair" / "broken" → penalty.
- Staleness: text references 2017–2019 or last-updated > 365 days → penalty.

**Output columns for `facility_trust`:** `facility_id`, `trust_score` (0–100),
`trust_level` (High≥70 / Medium 45–69 / Low<45), `matched_capabilities` (array),
`contradictions` (array<struct{reason, evidence}>), `positive_evidence` (array),
`missing_supports` (array), `explanation` (string).

## Desert classifier spec (implement in `03_desert_classifier.py`)

Group by `(address_stateOrRegion, address_city)` = district. For each critical capability
(ICU, oxygen, emergency surgery, dialysis, oncology, trauma, neonatal, blood bank, ventilator):

- **covered** — ≥1 facility with capability `present` at usable confidence.
- **medical_desert** — facilities exist in district, but capability genuinely absent.
- **data_desert** — field/coverage below threshold: we don't KNOW (e.g. most facilities in the
  district have empty capability text or the relevant fields are NULL). Never render this as "no".

Output `district_desert`: `state`, `district`, `capability`, `status`
(`covered|medical_desert|data_desert`), `n_facilities`, `coverage_ratio`, `n_present`.
Map layer must use **three visually distinct colors** — a data desert must never look like a
medical desert.

## Databricks connection pattern (CONFIRMED on this Free Edition workspace)

- LLM (optional feature only): use the `openai` Python SDK, OpenAI-compatible.
  `client = OpenAI(api_key=DATABRICKS_TOKEN, base_url=f"{DATABRICKS_HOST}/serving-endpoints")`
  then `client.chat.completions.create(model=LLM_ENDPOINT, messages=[...])`.
  Working model: **`databricks-qwen35-122b-a10b`** (Qwen3.5). NOTE: most other hosted
  models (GPT-5.6 Luna, etc.) return PERMISSION_DENIED "rate limit of 0" on this tier —
  Qwen works, treat it as the only reliable LLM. Endpoint name comes from `.env`, never hardcode.
- SQL: `POST {DATABRICKS_HOST}/api/2.0/sql/statements` with `{statement, warehouse_id,
  wait_timeout}`; poll `GET /api/2.0/sql/statements/{id}` until `SUCCEEDED`.
- Env (in `.env`, never commit):
  ```
  DATABRICKS_HOST=https://dbc-14e1658b-cbd6.cloud.databricks.com
  DATABRICKS_TOKEN=dapi...            # already generated (all-apis scope)
  WAREHOUSE_ID=<Serverless Starter Warehouse id — from SQL Warehouses > Connection details>
  LLM_ENDPOINT=databricks-qwen35-122b-a10b
  ```
- LLM is OPTIONAL (powers only the NL-query bonus). The trust engine, desert classifier,
  and the app's ranking/citations are pure Spark/SQL and need only the warehouse. If Qwen
  throttles mid-demo, the core still works — lean on that.

## Conventions

- Python 3, PySpark for notebooks, FastAPI for the app backend, Leaflet for the map.
- Keep trust logic OUT of the LLM hot path — the app reads precomputed Delta tables.
- Every user-facing capability claim must carry its source substring (citation).
- Communicate uncertainty as bands/labels, never fake-precise numbers.
- Deploy target is **Databricks Free Edition** — not enterprise/paid. Verify Lakebase is
  available; if not, persist `planner_actions` to a Delta table and note the fallback.

## Guardrails / do-not

- **Do NOT copy code from the reference projects (AarogyaMap TypeScript, VeriCare).** Reimplement
  the *ideas* as our own Spark/Python. Those repos have no OSS license = all rights reserved.
- Do not filter queries on the sparse `has_*` boolean columns — read text instead.
- Do not let the app approve/deny/rank people; it ranks *facilities by evidence quality* only.
- Never invent facilities or capabilities not present in the data.

## Definition of done (demo checklist)

Core (must have — the minimum winning submission):
- [ ] `facility_trust`, `district_desert` exist as Delta tables (`facility_trust` reads
      directly from the source share — no `clean_facilities`/Step 0).
- [ ] App runs live on Free Edition; **Facility Trust Desk** journey works end to end.
- [ ] Every ranked facility shows contradictions + cited source text.
- [ ] A planner note/override persists across sessions.

Views (add only after core demos cleanly):
- [ ] Medical Desert Planner map shows covered / medical-desert / data-desert in 3 colors.
- [ ] Data Readiness Desk lists low-confidence / contradicted / data-desert records.

Ambition (last):
- [ ] NL query via Mosaic AI joined to `facility_trust`.
- [ ] MLflow trace visible for one request.
- [ ] 405B independent validation shown alongside deterministic trust.

Always:
- [ ] One-minute demo script rehearsed; lead with the primary track, mention views as bonus.
