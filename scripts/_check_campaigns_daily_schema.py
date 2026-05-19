import os
from google.cloud import bigquery
c = bigquery.Client(project="angular-axle-492812-q4", location="me-central1")
t = c.get_table("angular-axle-492812-q4.qoyod_marketing.campaigns_daily")
for f in t.schema:
    print(f"  {f.name}: {f.field_type}")
