from google.cloud import bigquery
client = bigquery.Client(project='angular-axle-492812-q4')
table = client.get_table('angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual')
print(f"Total columns: {len(table.schema)}")
for f in table.schema:
    print(f.name)
