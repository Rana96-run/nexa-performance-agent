"""
One-shot: materialise updated views and verify adset_name / ad_name columns.
Run via: railway run python _add_names.py
"""
from collectors.views import materialize_heavy_views
from collectors.bq_writer import get_bq_client, PROJECT_ID, DATASET

print("=== Materialising views ===")
materialize_heavy_views()
print("Done.\n")

client = get_bq_client()

print("=== v_adset_performance: adset_name sample ===")
q1 = f"""
SELECT adset_name, utm_audience
FROM `{PROJECT_ID}.{DATASET}.v_adset_performance`
WHERE adset_name IS NOT NULL
LIMIT 5
"""
rows = list(client.query(q1).result())
if rows:
    for r in rows:
        print(f"  adset_name={r['adset_name']!r}  utm_audience={r['utm_audience']!r}")
else:
    print("  WARNING: no non-null adset_name rows found")

print()
print("=== v_ad_performance: ad_name sample ===")
q2 = f"""
SELECT ad_name, utm_content
FROM `{PROJECT_ID}.{DATASET}.v_ad_performance`
WHERE ad_name IS NOT NULL
LIMIT 5
"""
rows2 = list(client.query(q2).result())
if rows2:
    for r in rows2:
        print(f"  ad_name={r['ad_name']!r}  utm_content={r['utm_content']!r}")
else:
    print("  WARNING: no non-null ad_name rows found")

print("\nAll checks complete.")
