"""Show columns of paid_channel_daily so we use the right field names."""
import os
from google.cloud import bigquery
c = bigquery.Client(project="angular-axle-492812-q4", location="me-central1")
table = c.get_table("angular-axle-492812-q4.qoyod_marketing.paid_channel_daily")
for f in table.schema:
    print(f"  {f.name}: {f.field_type}")
