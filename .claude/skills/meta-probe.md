# Skill — Probe Meta / IG metric availability

Use when a Meta organic call 400s with
`(#100) Tried accessing nonexisting field`. APIs deprecate metrics silently;
this skill isolates the offender.

## Probe one metric at a time

```python
import requests, os
from dotenv import load_dotenv; load_dotenv()
T = os.environ["META_PAGE_ACCESS_TOKEN"]
PAGE = os.environ["META_FB_PAGE_ID"]

for m in ["page_impressions_unique","page_post_engagements","page_follows",
          "page_daily_follows_unique","page_views_total"]:
    r = requests.get(f"https://graph.facebook.com/v21.0/{PAGE}/insights",
                     params={"metric":m,"period":"day","access_token":T})
    print(m, r.status_code, r.json().get("error",{}).get("message","OK")[:80])
```

## Known survivors (as of Nov 2025)

See `memory/08_pitfalls.md` → Meta section. Do NOT add metrics back without
probing first.

## IG specifics

- `reach` is the only reliable daily time-series left
- `profile_views`, `website_clicks`, `accounts_engaged`,
  `total_interactions` must use `metric_type=total_value` and can't be
  mixed with day-series metrics in one call

## If a metric 400s in production

1. Probe it with the snippet above
2. If confirmed dead, remove from `FB_PAGE_METRICS` / `IG_METRICS_*` in
   `collectors/meta_organic_bq.py`
3. Log it in `memory/08_pitfalls.md` with the date and the replacement
