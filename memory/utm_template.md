---
name: Canonical UTM template — Google Ads
description: Standard final_url_suffix template for all Google Ads campaigns. Stop reinventing — apply this verbatim.
type: reference
---

**Template (apply as `campaign.final_url_suffix` — never as part of the final_url itself):**

```
utm_source=Google&utm_medium=ppc&utm_campaign={_campaign}&utm_content={_adname}&utm_audience={_adgroupname}&campaign_id={campaignid}&ad_group_id={_adgroupid}&ad_id={creative}&utm_term={keyword}
```

Notes:
- `utm_source=Google` — capital G (not lowercase)
- `utm_medium=ppc` — never `cpc`
- `{_campaign}`, `{_adname}`, `{_adgroupname}`, `{_adgroupid}` are **custom parameters** that must be defined per-campaign via `url_custom_parameters`. Set them at campaign creation:
  - `_campaign` = campaign name (e.g. `Google_Search_AR_ZATCAPhase2_Broad`)
  - `_adname` = ad name (e.g. `Google_Search_AR_ZATCAPhase2V1`)
  - `_adgroupname` = ad group name
  - `_adgroupid` = ad group numeric id
- `{campaignid}`, `{creative}`, `{keyword}` are standard Google ValueTrack — Google auto-substitutes them at click time.

**Where this lives in code:**
- Constant: `executors/google_ads.py` → `STANDARD_UTM_SUFFIX`
- Applied automatically by `create_full_campaign()` since 2026-05-18.

**What NOT to do:**
- Don't hardcode UTMs into the RSA `final_url` — the suffix covers RSA + sitelinks + every clickable URL uniformly. Hardcoding causes double UTMs (one in URL, one appended by suffix).
- Don't propose alternative templates in chat. There is ONE template. Apply it.
