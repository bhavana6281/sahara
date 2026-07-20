# Databricks notebook source
# ============================================================================
# Step 1 — Deterministic Trust Engine  →  workspace.default.facility_trust
# ----------------------------------------------------------------------------
# READS  : databricks_virtue_foundation_dataset_dais_2026
#              .virtue_foundation_dataset.facilities   (10,088 rows, all string)
# WRITES : workspace.default.facility_trust            (you own this schema)
#
# For EVERY facility computes:
#   - matched capabilities (present / absent / uncertain) + SOURCE EVIDENCE
#   - clinical contradictions (each with a reason + the cited substring)
#   - deterministic trust_score 0-100 + level band + explanation
#
# #1 differentiator: trust is auditable CODE, not an LLM guess.
# All capability/array-ish fields are STRINGS here, so we just regex over them.
# ============================================================================

from pyspark.sql import functions as F, types as T
import re

SOURCE_TABLE = ("databricks_virtue_foundation_dataset_dais_2026"
                ".virtue_foundation_dataset.facilities")
OUTPUT_TABLE = "workspace.default.facility_trust"

# ----------------------------------------------------------------------------
# 1. Capability lexicon: capability -> (positive patterns, negation patterns)
#    Lowercase regex fragments, matched on a combined lowercased text blob.
#    TUNE these against real text after the first run.
# ----------------------------------------------------------------------------
CAPABILITY_PATTERNS = {
    "icu":               ([r"\bicu\b", r"intensive care", r"critical care"],
                          [r"no icu", r"icu[^.]{0,20}not available", r"without icu"]),
    "oxygen":            ([r"\boxygen\b", r"o2 support", r"oxygen cylinder",
                           r"oxygen pipeline", r"oxygen concentrator", r"oxygen supply"],
                          [r"no oxygen", r"oxygen[^.]{0,20}unavailable"]),
    "ventilator":        ([r"ventilator", r"mechanical ventilation", r"life support"],
                          [r"no[^.]{0,15}ventilator", r"ventilator[^.]{0,20}non.?functional",
                           r"ventilator[^.]{0,20}broken"]),
    "neonatal":          ([r"\bnicu\b", r"neonatal", r"newborn care", r"incubator", r"neonate"],
                          [r"no nicu", r"neonatal[^.]{0,20}not available", r"no incubator"]),
    "pediatric":         ([r"paediatric", r"pediatric", r"child specialist",
                           r"paediatrician", r"pediatrician"],
                          [r"no p[a]?ediatrician"]),
    "dialysis":          ([r"dialysis", r"hemodialysis", r"haemodialysis",
                           r"renal replacement", r"\bcapd\b"],
                          [r"no dialysis", r"dialysis[^.]{0,20}unavailable"]),
    "oncology":          ([r"oncology", r"cancer care", r"chemotherapy",
                           r"radiotherapy", r"tumou?r"],
                          [r"no oncology"]),
    "trauma":            ([r"trauma", r"accident[^.]{0,15}emergency", r"casualty"],
                          []),
    "emergency_surgery": ([r"emergency surgery", r"emergency operation", r"appendectomy",
                           r"laparotomy", r"emergency c.?section"],
                          [r"no emergency surgery"]),
    "operation_theatre": ([r"operation theatre", r"operation theater",
                           r"surgical suite", r"modular ot", r"\bo\.?t\.?\b"],
                          [r"no operation theatre", r"ot[^.]{0,20}non.?functional"]),
    "surgeon":           ([r"surgeon", r"surgical team", r"general surgery"],
                          [r"no surgeon"]),
    "anesthesiologist":  ([r"an[a]?esthesiolog", r"an[a]?esthetist", r"an[a]?esthesia"],
                          [r"no an[a]?esth"]),
    "blood_bank":        ([r"blood bank", r"blood storage", r"blood transfusion"],
                          [r"no blood bank"]),
    "nurse":             ([r"\bnurse", r"nursing staff", r"nursing care"],
                          [r"no nurs"]),
    "physician":         ([r"physician", r"\bmbbs\b", r"medical officer", r"\bdoctor"],
                          []),
    "24x7":              ([r"24/?7", r"24 ?hours", r"round.the.clock", r"all day"],
                          [r"part.?time", r"day.?time only"]),
}

CRITICAL_CAPS = ["icu", "oxygen", "emergency_surgery", "dialysis", "oncology",
                 "trauma", "neonatal", "blood_bank", "ventilator"]

# ----------------------------------------------------------------------------
# 2. Build one lowercased text blob per facility from the text-bearing columns.
#    All columns are strings here, so concat directly (arrays are JSON text).
# ----------------------------------------------------------------------------
df = spark.table(SOURCE_TABLE)

TEXT_FIELDS = ["description", "specialties", "procedure", "equipment", "capability", "name"]
present_fields = [f for f in TEXT_FIELDS if f in df.columns]

blob = F.lower(F.concat_ws(" ", *[F.coalesce(F.col(f).cast("string"), F.lit(""))
                                   for f in present_fields]))
df = df.withColumn("_blob", blob)

# ----------------------------------------------------------------------------
# 3. Capability detection UDF -> array<struct> with cited evidence substrings.
# ----------------------------------------------------------------------------
cap_schema = T.ArrayType(T.StructType([
    T.StructField("capability", T.StringType()),
    T.StructField("status", T.StringType()),      # present | absent | uncertain
    T.StructField("confidence", T.DoubleType()),
    T.StructField("evidence", T.StringType()),     # cited source substring
]))

_PATTERNS = {k: ([re.compile(p) for p in pos], [re.compile(n) for n in neg])
             for k, (pos, neg) in CAPABILITY_PATTERNS.items()}

def _snippet(text, m, radius=40):
    s = max(0, m.start() - radius); e = min(len(text), m.end() + radius)
    return text[s:e].strip()

def detect_caps(blob):
    if not blob:
        return []
    out = []
    for cap, (pos, neg) in _PATTERNS.items():
        neg_hit = next((n.search(blob) for n in neg if n.search(blob)), None)
        pos_hit = next((p.search(blob) for p in pos if p.search(blob)), None)
        if neg_hit:
            out.append((cap, "absent", 0.9, _snippet(blob, neg_hit)))
        elif pos_hit:
            hits = sum(1 for p in pos if p.search(blob))
            out.append((cap, "present", min(0.95, 0.6 + 0.1 * hits), _snippet(blob, pos_hit)))
        else:
            out.append((cap, "uncertain", 0.3, ""))
    return out

detect_caps_udf = F.udf(detect_caps, cap_schema)
df = df.withColumn("caps", detect_caps_udf(F.col("_blob")))

# ----------------------------------------------------------------------------
# 4. Trust scoring + contradiction rules UDF.
# ----------------------------------------------------------------------------
trust_schema = T.StructType([
    T.StructField("trust_score", T.IntegerType()),
    T.StructField("trust_level", T.StringType()),
    T.StructField("matched_capabilities", T.ArrayType(T.StringType())),
    T.StructField("contradictions", T.ArrayType(T.StructType([
        T.StructField("reason", T.StringType()),
        T.StructField("evidence", T.StringType()),
    ]))),
    T.StructField("positive_evidence", T.ArrayType(T.StringType())),
    T.StructField("missing_supports", T.ArrayType(T.StringType())),
    T.StructField("explanation", T.StringType()),
])

def score_trust(caps, blob):
    blob = blob or ""
    status = {c["capability"]: c["status"] for c in caps}
    conf   = {c["capability"]: c["confidence"] for c in caps}
    ev     = {c["capability"]: c["evidence"] for c in caps}

    def present(n): return status.get(n) == "present" and conf.get(n, 0) > 0.5
    def absent(n):  return status.get(n) == "absent"

    score = 70
    contradictions, positive, missing = [], [], []
    def contra(reason, cap=""): contradictions.append((reason, ev.get(cap, "")))

    # positive corroboration
    hi = [c for c in caps if c["status"] == "present" and c["confidence"] > 0.8]
    if len(hi) >= 3:
        score += 10; positive.append(f"{len(hi)} capabilities verified with strong evidence")
    if present("oxygen") and present("icu"):
        score += 5; positive.append("ICU supported by confirmed oxygen supply")
    if present("surgeon") and present("anesthesiologist") and present("operation_theatre"):
        score += 5; positive.append("Complete surgical team: surgeon + anesthesiologist + OT")
    if present("nurse") and present("physician"):
        score += 3; positive.append("Core medical staff (physician + nursing) confirmed")

    # clinical contradiction rules
    if present("emergency_surgery") and not present("anesthesiologist"):
        score -= 25; contra("CRITICAL: surgery claimed but no anesthesiologist evidence", "emergency_surgery"); missing.append("anesthesiologist")
    if present("emergency_surgery") and not present("operation_theatre"):
        score -= 15; contra("Surgery claimed but no operation theatre confirmed", "emergency_surgery"); missing.append("operation_theatre")
    if present("operation_theatre") and absent("anesthesiologist") and not present("emergency_surgery"):
        score -= 15; contra("Operation theatre listed but no anesthesiologist — surgical safety concern", "operation_theatre")
    if present("icu") and not present("oxygen") and not present("ventilator"):
        score -= 20; contra("ICU listed but no oxygen or ventilator support — ICU claim unreliable", "icu"); missing.append("oxygen/ventilator")
    if present("icu") and not present("nurse"):
        score -= 8; contra("ICU listed but nursing staff availability unconfirmed", "icu")
    if present("neonatal") and not present("pediatric") and not present("oxygen"):
        score -= 15; contra("Neonatal care claimed but no pediatric specialist or oxygen evidence", "neonatal"); missing.append("pediatric/oxygen")
    if present("dialysis") and not present("physician"):
        score -= 10; contra("Dialysis listed but supporting medical staff unclear", "dialysis")
    d_ev = (ev.get("dialysis") or "").lower()
    if present("dialysis") and ("monthly" in d_ev or "camp" in d_ev):
        score -= 15; contra("Dialysis appears to be monthly camp only, not permanent", "dialysis")
    if present("24x7") and re.search(r"part.?time", blob):
        score -= 8; contra("24/7 availability claimed but doctors documented as part-time", "24x7")

    # data-quality penalties
    if re.search(r"all facilities available|all services available|complete healthcare", blob):
        score -= 10; contra("Vague blanket claim without specific evidence")
    if re.search(r"non.?functional|under repair|broken", blob):
        score -= 5; contra("Equipment listed as non-functional / under repair")
    if re.search(r"\b201[789]\b", blob):
        score -= 10; contra("Record references 2017-2019 data — potentially stale")
    unc = sum(1 for c in caps if c["status"] == "uncertain")
    if unc > 8:
        score -= 5; contra(f"{unc} capabilities uncertain — data completeness is low")

    score = max(0, min(100, int(round(score))))
    level = "High" if score >= 70 else ("Medium" if score >= 45 else "Low")
    matched = [c["capability"] for c in caps if c["status"] == "present" and c["confidence"] > 0.5]

    if level == "High":
        expl = f"Trust {score}/100 — strong evidence. " + (positive[0] if positive else "Multiple capabilities verified.")
    elif level == "Medium":
        expl = f"Trust {score}/100 — moderate. {(contradictions[0][0] if contradictions else 'some data gaps')}. Verify before critical referral."
    else:
        expl = f"Trust {score}/100 — low. {(contradictions[0][0] if contradictions else 'significant data quality issues')}. Do not rely without direct verification."

    return (score, level, matched, [(r, e) for (r, e) in contradictions], positive, missing, expl)

score_udf = F.udf(score_trust, trust_schema)
df = df.withColumn("trust", score_udf(F.col("caps"), F.col("_blob")))

# ----------------------------------------------------------------------------
# 5. Flatten and write to Delta (in a schema you own).
# ----------------------------------------------------------------------------
out = df.select(
    F.col("unique_id"),
    F.col("name"),
    F.col("address_stateOrRegion").alias("state"),
    F.col("address_city").alias("district"),
    F.col("latitude"), F.col("longitude"),
    F.col("trust.trust_score").alias("trust_score"),
    F.col("trust.trust_level").alias("trust_level"),
    F.col("trust.matched_capabilities").alias("matched_capabilities"),
    F.col("trust.contradictions").alias("contradictions"),
    F.col("trust.positive_evidence").alias("positive_evidence"),
    F.col("trust.missing_supports").alias("missing_supports"),
    F.col("trust.explanation").alias("explanation"),
    F.col("caps"),   # full capability + evidence detail, for citations in the app
)

(out.write.format("delta").mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(OUTPUT_TABLE))

print(f"Wrote {out.count()} rows to {OUTPUT_TABLE}")
display(out.orderBy(F.col("trust_score")).limit(20))   # inspect the LOW-trust rows first
