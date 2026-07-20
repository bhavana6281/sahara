# Databricks notebook source
# ============================================================================
# Step 2 — Desert Classifier  →  workspace.default.district_desert
# ----------------------------------------------------------------------------
# READS  : workspace.default.facility_trust   (from 02_trust_engine.py)
# WRITES : workspace.default.district_desert
#
# For each (state, district) x critical capability, classify into THREE states:
#   covered        — >=1 facility with the capability confirmed present
#   medical_desert — facilities exist, none provide it (genuinely absent)
#   data_desert    — coverage too low to know (missing text / no signal)
#
# The data_desert vs medical_desert split is the idea the brief demands twice
# and neither reference project made explicit. The app MUST render these in
# THREE distinct colors — a data desert must never look like a medical one.
# ============================================================================

from pyspark.sql import functions as F

TRUST_TABLE  = "workspace.default.facility_trust"
OUTPUT_TABLE = "workspace.default.district_desert"

CRITICAL_CAPS = ["icu", "oxygen", "emergency_surgery", "dialysis", "oncology",
                 "trauma", "neonatal", "blood_bank", "ventilator"]

# If fewer than this fraction of facilities in a district gave ANY usable signal
# for a capability, call it a data desert (we don't know) rather than asserting
# absence. Tune after seeing the status distribution printed below.
DATA_COVERAGE_THRESHOLD = 0.30

df = spark.table(TRUST_TABLE)

# 1. Explode caps -> one row per (facility, capability).
#    "signal" = status present OR absent (text said something); uncertain = unknown.
exploded = (df
    .select("unique_id", "state", "district", F.explode("caps").alias("c"))
    .select("unique_id", "state", "district",
            F.col("c.capability").alias("capability"),
            F.col("c.status").alias("status"),
            F.col("c.confidence").alias("confidence"))
    .filter(F.col("capability").isin(CRITICAL_CAPS)))

# 2. Aggregate per (state, district, capability).
agg = (exploded.groupBy("state", "district", "capability").agg(
    F.count("*").alias("n_facilities"),
    F.sum(F.when((F.col("status") == "present") & (F.col("confidence") > 0.5), 1).otherwise(0)).alias("n_present"),
    F.sum(F.when(F.col("status") == "absent", 1).otherwise(0)).alias("n_absent"),
    F.sum(F.when(F.col("status") == "uncertain", 1).otherwise(0)).alias("n_unknown"),
))
agg = agg.withColumn(
    "coverage_ratio",
    (F.col("n_present") + F.col("n_absent")) / F.greatest(F.col("n_facilities"), F.lit(1)))

# 3. Classify. covered wins; else enough signal -> medical_desert; else data_desert.
status_col = (F.when(F.col("n_present") > 0, F.lit("covered"))
               .when(F.col("coverage_ratio") >= DATA_COVERAGE_THRESHOLD, F.lit("medical_desert"))
               .otherwise(F.lit("data_desert")))

result = (agg.withColumn("status", status_col)
             .select("state", "district", "capability", "status",
                     "n_facilities", "n_present", "n_absent", "n_unknown",
                     F.round("coverage_ratio", 3).alias("coverage_ratio")))

# 4. Write to Delta.
(result.write.format("delta").mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(OUTPUT_TABLE))

print(f"Wrote {result.count()} (district x capability) rows to {OUTPUT_TABLE}")
print("Status distribution:")
display(result.groupBy("capability", "status").count().orderBy("capability", "status"))
print("Example DATA deserts (unknown — must NOT be shown as 'no care'):")
display(result.filter(F.col("status") == "data_desert").limit(20))
