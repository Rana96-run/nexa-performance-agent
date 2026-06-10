from google.cloud import bigquery
client = bigquery.Client(project='angular-axle-492812-q4')

# First check what columns exist in hubspot_leads_individual
table = client.get_table('angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual')
cols = [f.name for f in table.schema]
id_cols = [c for c in cols if any(kw in c.lower() for kw in ['campaign', 'ad_group', 'ad_id', 'gclid', 'click', 'creative'])]
print("ID-related columns in hubspot_leads_individual:")
for c in id_cols:
    print(f"  {c}")

# Sample recent rows for these columns
if id_cols:
    select_cols = ', '.join(id_cols[:8])
    q = f"""
    SELECT {select_cols}, COUNT(*) as cnt
    FROM `angular-axle-492812-q4.qoyod_marketing.hubspot_leads_individual`
    WHERE hs_createdate >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
    GROUP BY {', '.join(str(i+1) for i in range(min(8, len(id_cols))))}
    HAVING cnt > 0
    ORDER BY cnt DESC
    LIMIT 15
    """
    print(f"\nSample values (last 14 days):")
    for r in client.query(q).result():
        print(dict(r))
