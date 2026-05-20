"""Pull all sitelinks, callouts, structured snippets currently linked to
ZATCAPhase2 on Acc 1 (1513020554, camp 23851270716). Write JSON so we can
replay on Acc 2."""
import sys, json
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from executors.google_ads import get_client

ACCOUNT = "1513020554"
CAMP_ID = "23851270716"

client = get_client()
ga = client.get_service("GoogleAdsService")

out = {"sitelinks": [], "callouts": [], "snippets": []}

q = f"""
SELECT campaign.id,
       campaign_asset.field_type,
       asset.id, asset.name, asset.type,
       asset.sitelink_asset.link_text,
       asset.sitelink_asset.description1,
       asset.sitelink_asset.description2,
       asset.final_urls,
       asset.callout_asset.callout_text,
       asset.structured_snippet_asset.header,
       asset.structured_snippet_asset.values
FROM campaign_asset
WHERE campaign.id = {CAMP_ID}
  AND campaign_asset.status = 'ENABLED'
  AND campaign_asset.field_type IN ('SITELINK','CALLOUT','STRUCTURED_SNIPPET')
"""
for r in ga.search(customer_id=ACCOUNT, query=q):
    ft = r.campaign_asset.field_type.name
    if ft == "SITELINK":
        out["sitelinks"].append({
            "text": r.asset.sitelink_asset.link_text,
            "d1":   r.asset.sitelink_asset.description1,
            "d2":   r.asset.sitelink_asset.description2,
            "url":  list(r.asset.final_urls)[0] if r.asset.final_urls else "",
        })
    elif ft == "CALLOUT":
        out["callouts"].append(r.asset.callout_asset.callout_text)
    elif ft == "STRUCTURED_SNIPPET":
        out["snippets"].append({
            "header": r.asset.structured_snippet_asset.header,
            "values": list(r.asset.structured_snippet_asset.values),
        })

# Dedupe (in case multiple link rows reference same asset)
out["callouts"] = sorted(set(out["callouts"]))
seen_s = set(); dedup_s = []
for sl in out["sitelinks"]:
    k = (sl["text"], sl["url"])
    if k in seen_s: continue
    seen_s.add(k); dedup_s.append(sl)
out["sitelinks"] = dedup_s
seen_n = set(); dedup_n = []
for sn in out["snippets"]:
    k = (sn["header"], tuple(sn["values"]))
    if k in seen_n: continue
    seen_n.add(k); dedup_n.append(sn)
out["snippets"] = dedup_n

print(f"sitelinks: {len(out['sitelinks'])}")
for sl in out["sitelinks"]:
    print(f"  {sl['text']:<28} → {sl['url']}")
print(f"\ncallouts: {len(out['callouts'])}")
for c in out["callouts"]:
    print(f"  {c}")
print(f"\nsnippets: {len(out['snippets'])}")
for sn in out["snippets"]:
    print(f"  {sn['header']}: {sn['values']}")

with open("scripts/_phase2_ext_plan.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"\n✅ saved scripts/_phase2_ext_plan.json")
