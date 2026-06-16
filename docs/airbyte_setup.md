# Airbyte Cloud Setup Guide

**Time needed:** ~15 minutes of clicking  
**URL:** https://cloud.airbyte.com  
**Plan:** Free (Cloud Free tier — no credit card needed)

---

## Step 1 — Sign up

Go to https://cloud.airbyte.com → Sign up with your Google account (use rana.khalid@qoyod.com).

---

## Step 2 — BigQuery Destination (do this FIRST — used by all connectors)

1. Left sidebar → **Destinations** → **+ New destination**
2. Search: **BigQuery** → Select it
3. Fill in:

| Field | Value |
|---|---|
| Destination name | `Qoyod BQ` |
| Project ID | `angular-axle-492812-q4` |
| Dataset Location | `me-central1` |
| Default Dataset ID | `airbyte_raw` |
| Loading Method | **Batched Standard Inserts** ← important, matches our no-streaming rule |
| Service Account Key JSON | *(paste contents of `bigquery-key.json` file)* |

4. Click **Test and Save**

---

## Step 3 — Sources (one per channel)

### 3a. Google Ads

1. Left sidebar → **Sources** → **+ New source**
2. Search: **Google Ads** → Select
3. Fill in:

| Field | Value |
|---|---|
| Source name | `Google Ads` |
| Developer Token | `WijwaDSS81dtGrTHAX8wbA` |
| Client ID | `160399108734-9tiflh39bn41r9lq245ejgf6bh2tqtgg.apps.googleusercontent.com` |
| Client Secret | `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` |
| Refresh Token | `1//03Tot8nBXSH33CgYIARAAGAMSNwF-L9IrirPJrhi_yHKSVqnMhGHCMrw79erfH5lyFDx6kJ0RfNqCsj0KYitR_iyD0PbyjXcf3uA` |
| Login Customer ID | `5789762982` *(no dashes)* |
| Customer ID | `1513020554,5753494964` *(no dashes, comma-separated)* |
| Start Date | `2024-01-01` |

4. **Streams to enable** (disable everything else to save sync time):
   - ✅ `campaign_performance_report`
   - ✅ `ad_group_performance_report` *(for ad group data)*

5. Test → Save

---

### 3b. Meta (Facebook) Ads

1. **+ New source** → Search: **Facebook Marketing**
2. Fill in:

| Field | Value |
|---|---|
| Source name | `Meta Ads` |
| App ID | `506000922536697` |
| App Secret | `4d4bcdb2624ef28e738831e8f9a0b292` |
| Access Token | `EAAHMNIUZBavkBREmWx1QeRYIMyt683hISUhyDzBKVRvtGTBxMDVc3oEBU2zdCT5M6KsKyWmnYsldn3mLrOZAso9ZAgVhFaxJGPQe47nwOImOxbMeJZC2YXDdiCZBhsep5q5fIIENtX5yPuyQwUDUWMcaVnC7yKYcPBFrrhevSabsyWt5KTIMkCefQj0l8CwZDZD` |
| Account IDs | `1366192231206913, 835030860363827` *(without act_ prefix)* |
| Start Date | `2024-01-01T00:00:00` |

3. **Streams to enable:**
   - ✅ `ads_insights` — with breakdowns: **none** (campaign level)
   - ✅ `ads_insights_action_type` *(for lead counts)*

4. Test → Save

---

### 3c. Snapchat Ads

1. **+ New source** → Search: **Snapchat Marketing**
2. Fill in:

| Field | Value |
|---|---|
| Source name | `Snapchat Ads` |
| Client ID | `0ef9983d-b615-42fb-9f9f-543cbad8de21` |
| Client Secret | `875955226665ca054708` |
| Refresh Token | `hCgwKCjE3NzA1OTg4MTgSpQE8Buzl2Lq0KSzqfoNd-XhovCtNXkm_j3kRlT6PK4w42bhbvr-8icyFfuypN6VX3h0EW0_ESTETawqYCZ4AC3--nBiccVimai0JrrpUdNui7bvCBk6v9DYXTYcg9gXhrS0rM0eibx-XpGJn3rpC5Pn392OWNXYGvhwBFejgyzIUnzaE_IzrJC37TFy94uMKr20SMwHYgh0mTiOgc8FPmTzvrklue-g` |
| Start Date | `2024-01-01` |

3. **Streams:** ✅ `campaign_stats`
4. Test → Save

---

### 3d. TikTok Ads

1. **+ New source** → Search: **TikTok Marketing**
2. Fill in:

| Field | Value |
|---|---|
| Source name | `TikTok Ads` |
| App ID | `7633259632252682241` |
| App Secret | `ea4d626330584de0226e85feadd8e726ab9f8c97` |
| Access Token | `ca15073da4f0a8e9698793691fe0a714ce992331` |
| Advertiser IDs | `7304642840767021057, 7565475813811093521` |
| Start Date | `2024-01-01` |

3. **Streams:** ✅ `ads_reports_daily`
4. Test → Save

---

### 3e. LinkedIn Ads

1. **+ New source** → Search: **LinkedIn Ads**
2. Fill in:

| Field | Value |
|---|---|
| Source name | `LinkedIn Ads` |
| Client ID | `78zn55gkwpx2pt` |
| Client Secret | `WPL_AP1.Id0puxKsJka9T1C1.sPOYWA==` |
| Refresh Token | `AQX4ZL-GVQMzBoD-YUMwPlj2jWcqKNk-4wdYZOIVpoh_HuhCplfozUciy1ecEApzG9v5izCVfF-zaKwyHo7JEuellXSZRA7ynI-SFqaxHUAkBPO8z9XGQCkRtbDFAG_-IJsNPm_hoFaD-Sp_YS4nOr0ywxV21hn7ie7IawMms6Kms3iMZOxRQhPCaBOF-LtWh8HdepPwL6AEzbHaoQYNWIKVt4ESyczVNo4QZtEXLG9T6wO7eVClBSK7cZ2U_7qIDfjGDk3llKxLRfrxfU5DfjCJIDhQEV9Q5mzC5EoRKiHygzGA0jznE4FyLOvYBfi2AVf_oBklICXWefWAyJhyQB-AaPs6Iw` |
| Account IDs | `506171805` |
| Start Date | `2024-01-01` |

3. **Streams:** ✅ `ad_campaign_analytics`
4. Test → Save

> ⚠️ LinkedIn tokens expire every 60 days. If test fails, re-run `python scripts/linkedin_oauth.py`

---

### 3f. Microsoft Ads

1. **+ New source** → Search: **Microsoft Advertising**
2. Fill in:

| Field | Value |
|---|---|
| Source name | `Microsoft Ads` |
| Developer Token | *(see Railway env: `MS_DEVELOPER_TOKEN`)* |
| Client ID | *(see Railway env: `MS_CLIENT_ID`)* |
| Client Secret | *(see Railway env: `MS_CLIENT_SECRET`)* |
| Tenant ID | *(see Railway env: `MS_TENANT_ID`)* |
| Refresh Token | *(run `python scripts/microsoft_oauth.py` first to generate)* |
| Customer ID | `254476670` |
| Start Date | `2024-01-01` |

3. **Streams:** ✅ `campaign_performance_report`
4. Test → Save

---

## Step 4 — Create Connections (source → destination)

For each source, create a connection to the BigQuery destination:

1. Left sidebar → **Connections** → **+ New connection**
2. Select source → Select `Qoyod BQ` destination
3. Settings:

| Setting | Value |
|---|---|
| Replication frequency | **Every 6 hours** |
| Destination namespace | **Custom** → `airbyte_raw` |
| Destination stream prefix | Leave blank |
| Sync mode | **Full Refresh \| Overwrite** for small streams; **Incremental \| Append+Dedup** for large |

4. Enable only the streams listed above for that source
5. Click **Set up connection**

Repeat for all 6 sources.

---

## Step 5 — Add env var to Railway

Add this to your Railway service (nexa-web) environment variables:

```
AIRBYTE_RAW_DATASET=airbyte_raw
```

This tells our normalizer where to find the raw Airbyte tables.

---

## Step 6 — Trigger first sync

1. Go to each connection → click **Sync now**
2. Wait for all 6 to complete (5–15 min each)
3. Then run manually to test normalization:
   ```
   python collectors/airbyte_normalize.py
   ```
   Should print rows merged for each channel.

---

## How it works after setup

```
Airbyte (every 6h)
  → pulls from 6 ad platforms
  → writes raw to BQ: airbyte_raw.{channel_table}

reporting_scheduler.py (every 6h, after Airbyte)
  → calls airbyte_normalize.py
  → MERGEs raw → qoyod_marketing.campaigns_daily
  → refreshes utm_paid_attribution_daily view
  → dashboard shows fresh data
```

Our existing HubSpot collector still runs separately (leads/SQLs don't come from ad platforms).
