# ARCHITECTURE — Sahara

Healthcare Facility Intelligence App on Databricks Free Edition.
Hack-Nation Challenge 04 ("Data Legend").

**Live app:** https://sahara-7474653017463724.aws.databricksapps.com (Databricks Apps, requires
workspace SSO login). Deployed via the Databricks CLI (`databricks sync` + `databricks apps
deploy`) from `app/` — see "Deployment" below.

## Design principle

The trust score is **deterministic, computed in Spark, and stored in Delta** — not judged by an
LLM at request time. The LLM only translates plain-English questions into a validated filter
object and writes cosmetic result summaries; it never touches `trust_score`, never generates SQL,
and never decides what counts as evidence. Clinical reasoning is auditable code. This is the core
differentiator and the reason the app is fast, cheap, and honest at demo time.

## The three views (one app, one nav bar, three tabs)

```
┌────────────────────────────────────────────────────────────────────────────┐
│  Sahara — tab bar: [Facility Trust Desk] [Medical Desert Planner]           │
│                     [Data Readiness Desk]                                   │
├────────────────────────────────────────────────────────────────────────────┤
│ TAB 1 — Facility Trust Desk (primary track)                                 │
│   Capability + region picker, OR "ask in plain English" (NL query)         │
│     → ranked facilities, split into High/Medium/Low confidence sub-tabs    │
│     → expand any facility: contradictions + cited source text,             │
│       full 16-capability evidence table, positive evidence, missing       │
│       supports, planner note/override (persists to planner_actions)       │
│     → Leaflet map, pins colored by trust level                            │
├────────────────────────────────────────────────────────────────────────────┤
│ TAB 2 — Medical Desert Planner                                             │
│   Capability + optional state filter → district-centroid map,             │
│   3-color legend: covered (aqua) / medical desert (violet) /               │
│   data desert (blue) — deliberately NOT the trust-level green/amber/red,   │
│   so the two legends are never confused. Honest "N of M plotted" count.   │
├────────────────────────────────────────────────────────────────────────────┤
│ TAB 3 — Data Readiness Desk                                                │
│   4 headline numbers (total / with contradictions / low-trust / missing   │
│   evidence) → 200-row queue ranked by LEVERAGE score (suspect AND          │
│   consequential — see below), not naive low-trust sorting → expand any    │
│   row for the same evidence view as Tab 1 → reviewer records a decision    │
│   (confirmed_issue / looks_fine / needs_field_check / corrected),         │
│   persisted to review_decisions, queue filters to unreviewed-only.        │
└────────────────────────────────────────────────────────────────────────────┘
```

## Layer diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│  EXPERIENCE LAYER — Databricks App (FastAPI + vanilla JS, no framework)   │
│  static/{index.html, css/styles.css, js/{api,map,desertMap,desertApp,     │
│  readiness,tabs,app}.js} — one shared Api IIFE, one shared color system   │
└───────────────┬────────────────────────────────────────────────────────────┘
                │ reads precomputed Delta tables · writes planner_actions /
                │ review_decisions · NL query translates to a validated filter
┌───────────────▼────────────────────────────────────────────────────────────┐
│  INTELLIGENCE LAYER                                                         │
│                                                                              │
│  A. NL→filter agent    Databricks Model Serving (Llama 4 Maverick, via     │
│                         a narrowly-scoped LLM-only token) — emits a small   │
│                         validated JSON filter, NEVER SQL (agent.py)        │
│  B. Answer summary      same model — cosmetic phrasing only, over already- │
│                         finalized results                                  │
│  C. Trust engine        Spark — DETERMINISTIC (precomputed) ★              │
│  D. Desert classifier   Spark — data vs medical (precomputed) ★            │
│  E. Leverage scoring    SQL, computed per-request over facility_trust ★    │
└───────────────┬──────────────────────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────────────────────┐
│  DATA LAYER — Delta Lake · Unity Catalog (workspace.default.*)                │
│                                                                                │
│   facility_trust      ★ trust_score, contradictions[], citations             │
│                         (reads directly from the read-only Virtue Foundation │
│                          Delta share — no raw/clean staging table)           │
│   district_desert     ★ per (district, capability): covered/medical/data    │
│   planner_actions     ★ Trust Desk notes/overrides — Delta table            │
│   review_decisions    ★ Readiness Desk reviewer decisions — Delta table     │
│                                                                                │
│   + companion share: india_post_pincode_directory — used to recover ~400    │
│     facilities whose state field held a city/district name instead of a     │
│     real state (see "Region-data recovery" below)                           │
└────────────────────────────────────────────────────────────────────────────────┘

★ = differentiators absent from both reference projects
```

## Request flow — Facility Trust Desk (per planner query)

```
1. Planner selects capability + region, OR types a plain-English question
2. [NL path only] LLM → validated JSON filter (capability/state/district/
   trust_level/min_trust_score/desert_status) — never SQL; unrecognized
   fields are dropped to null, never guessed through
3. [NL path, LLM unavailable] keyword_fallback_filter() — same allowlists,
   zero LLM, substring matching only — "core app works without LLM"
4. SQL Warehouse executes a parameterized query over facility_trust
   (capability array_contains + state/district match, including raw
   spelling-variant + pincode-recovered matches — see below)
5. Rank by trust_score DESC; split client-side into High/Medium/Low tabs
6. [NL path only] LLM → 2-3 sentence plain-language summary, over the
   already-finalized result set — cannot change what was returned
7. Planner expands a facility → contradictions + cited evidence + full
   capability table (all already computed, just looked up)
8. Planner note/override → write planner_actions (persists across sessions,
   verified via server restart)
```

Trust is looked up in step 4, never computed live — the LLM cannot alter it, in either the
dropdown path or the NL path.

## Batch flow (precompute, run once / on data change)

```
virtue_foundation_dataset.facilities (raw Delta share) ──02──▶ facility_trust
                                                    └──────────03──▶ district_desert
```

## Data-desert vs medical-desert (the idea that wins Evidence & Trust)

For each district × critical-capability:

| Status | Meaning | Rule of thumb |
|---|---|---|
| covered | capability verified present | ≥1 facility present at usable confidence |
| medical_desert | genuinely absent care | facilities exist, none provide capability |
| data_desert | we don't KNOW | field/text coverage below threshold |

Real numbers from the live data: **3,691 covered / 13,225 data_desert / only 4 medical_desert**
district×capability records — the dataset is overwhelmingly "we don't know," which is exactly
why this distinction matters and exactly what the Medical Desert Planner's 3-color map (aqua /
violet / blue — deliberately not the trust-level green/amber/red) makes visible.

## Trust engine (deterministic)

Inputs: joined text (description + specialties + procedure + equipment + capability). Steps:
detect capabilities (present/absent/uncertain) with source-substring evidence → apply clinical
contradiction rules (see CLAUDE.md spec) → score 0–100 → level band → explanation. Output
persisted to `facility_trust`. No LLM in this path at all.

## Leverage scoring (Data Readiness Desk)

High-leverage ≠ low-trust. A record is high-leverage when it's both **suspect** (contradictions,
missing supports) **and consequential** (claims a critical capability — ICU, emergency surgery,
oncology, trauma, neonatal — where a wrong claim would misdirect a real referral):

```
leverage_score = contradictions × 3 + missing_supports × 2
                + (claims a critical capability ? 5 : 0)
                + (Low trust ? 4 : Medium trust ? 2 : 0)
```

Verified empirically before building this: 9,982 of 10,088 facilities (98.9%) have at least one
contradiction, so a naive "has a contradiction" filter is nearly useless — `leverage_score` is a
real ranking, computed per-request over `facility_trust`, not a precomputed column.

## Region-data recovery (a real upstream data-quality fix)

~4.1% of facilities (412 of 10,088) have a city/district name in the `state` field instead of a
real state (e.g. "Ahmedabad" instead of "Gujarat"). Fixed via `repositories/region_data.py`: a
canonical allowlist of India's 28 states + 8 UTs (post-2019 Jammu & Kashmir Reorganisation) with
known spelling variants (`"Orissa"→"Odisha"`, etc.), plus a join through the source table's
`address_zipOrPostcode` against the `india_post_pincode_directory` companion share for rows that
don't normalize — recovering the true state/district rather than guessing (no hand-curated
city→state map; a row with no pincode match is honestly excluded, not faked). Search queries
(`ranked_facilities`, `desert_map`) match on both the canonical spelling *and* the
pincode-recovered raw value, so the picker never offers a combination that then silently returns
nothing.

## Tech stack (what's actually used, not just what was planned)

- Data / batch: PySpark on Databricks; Delta Lake; Unity Catalog.
- LLM serving: Databricks Model Serving, `system.ai.llama-4-maverick`, OpenAI-compatible SDK via
  a dedicated `ai-gateway/mlflow/v1` endpoint and a narrowly-scoped token (no `sql` scope) — kept
  separate from the SQL Warehouse credential on purpose. (Qwen3.5 was tried first; it turned out
  to be a reasoning model whose `message.content` comes back as typed parts — a `reasoning` part
  then a `text` part — which needed different parsing and a much larger token budget. Switched to
  Llama 4 Maverick for a plain-string response and lower latency.)
- Query: Databricks SQL Warehouse via the SQL Statement Execution API (named-parameter binding,
  cold-start-tolerant polling).
- App: **Databricks Apps**, deployed via `databricks sync` (source → workspace path) +
  `databricks apps deploy` (API-direct mode, no Asset Bundle needed); FastAPI backend; Leaflet
  map; static vanilla-JS frontend (no build step).
- Secrets: `DATABRICKS_TOKEN` and `LLM_TOKEN` stored in a Databricks secret scope
  (`sahara-secrets`), attached to the app as `resources` and referenced via `valueFrom` in
  `app.yaml` — never as plaintext in a file that ends up in the Git submission.
- Persistence: Delta tables (`planner_actions`, `review_decisions`) — not Lakebase (see
  SUBMISSION_ALIGNMENT.md for that tradeoff).
- Observability: not yet built (MLflow 3 Tracing is a stretch goal, still open).

## Deployment (how `deploy to databricks` actually works here)

1. `databricks apps create` (or the REST equivalent) — provisions the app + a dedicated service
   principal (`app-... sahara`) + URL.
2. `PATCH /api/2.0/apps/sahara` with a `resources` array wiring the two Databricks-secret
   references (`databricks-token`, `llm-token`) — done directly via the Apps REST API, no
   Asset Bundle (`databricks.yml`) required.
3. `databricks sync app/ /Workspace/Users/<you>/sahara_app` — uploads source, excluding `.venv/`,
   `__pycache__/`, and `.env` (local-dev-only, never uploaded).
4. `databricks apps deploy sahara --source-code-path /Workspace/Users/<you>/sahara_app` —
   SNAPSHOT deployment; on success the app's `app_status` becomes `RUNNING`.
5. The app itself needs no code changes to run in this mode vs. local `uvicorn` — it reads the
   same env vars (`DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `WAREHOUSE_ID`, `LLM_TOKEN`,
   `LLM_BASE_URL`, `LLM_ENDPOINT`) either from `app/.env` (local) or from `app.yaml`'s `env`
   block (deployed) — `config.py` doesn't know or care which.

Access is gated by the workspace's own SSO (Databricks Apps front all traffic through an OIDC
login) — verifying the live app end-to-end therefore requires a logged-in workspace user, not
just an API token.

## Failure / fallback modes

- LLM unavailable/throttled/unparseable → `keyword_fallback_filter()`, zero-LLM substring
  matching over the same allowlists; NL query still returns results, never a 5xx.
- SQL timeout → poll with backoff, 90s budget (tolerates a cold-started serverless warehouse);
  distinguished from a real query failure.
- Region text corrupted or unrecoverable (no pincode match) → excluded from the picker, never
  guessed.

## Non-goals (out of scope — do not spend time here)

- Real patient data (use provided dataset only).
- Approving/denying/ranking *people*; the app ranks facilities by evidence only.
- Enterprise/paid Databricks workspace; deploy on Free Edition.
- Four equal tracks. Referral Copilot skipped entirely — highest incremental effort
  (geo-routing) for the least new value given two of the three built tracks already surface
  evidence-attached facility lists.
- Auto-correcting facility records. The Data Readiness Desk surfaces and persists a human
  reviewer's decision; it never edits `facility_trust` itself — "AI surfaces, human decides."

See `SUBMISSION_ALIGNMENT.md` for the full section-by-section mapping against the actual
challenge brief, including honest gaps (Vector Search, Lakebase, MLflow tracing not used/built).
