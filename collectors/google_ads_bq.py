"""
Google Ads -> BigQuery collector.
Pulls per-day metrics at campaign / ad-group / keyword / ad grain.

  collect_and_write()          -> campaigns_daily
  collect_adgroups_and_write() -> adsets_daily
  collect_keywords_and_write() -> keywords_daily
  collect_ads_and_write()      -> ads_daily  (includes final_url for LP analysis)
"""
import os
import re
from datetime import date, timedelta, datetime, timezone
from urllib.parse import urlparse, parse_qs, unquote
from google.ads.googleads.client import GoogleAdsClient
from config import GOOGLE_ADS_CONFIG
from collectors.bq_writer import upsert_rows
from collectors.currency import to_usd, normalize_currency


# ── UTM extraction helpers ────────────────────────────────────────────────────
_CUSTOM_PARAM_RE = re.compile(r"\{_([A-Za-z0-9_]+)\}")


def _extract_utm_param(param_name, custom_params, *templates):
    """Pull a named utm_* parameter out of a tracking-URL template, resolving
    any Google Ads {_paramname} placeholders against the entity's
    url_custom_parameters dict.

    Walks the templates in order (typically: ad > ad_group > campaign) and
    returns the first fully-resolved value. Returns None if no template
    contains the param or all references stay unresolved.

    Example:
        _extract_utm_param("content", {"adname": "x_invoice_wp"},
                           "{lpurl}?utm_content={_adname}")
        → "x_invoice_wp"
    """
    pattern = re.compile(rf"utm_{param_name}=([^&\s\"']+)", re.IGNORECASE)
    for t in templates:
        if not t:
            continue
        m = pattern.search(t)
        if not m:
            continue
        raw = m.group(1)
        def _sub(match):
            name = match.group(1)
            return custom_params.get(name, match.group(0))
        resolved = _CUSTOM_PARAM_RE.sub(_sub, raw)
        if "{" not in resolved:
            return unquote(resolved)
    return None


# Backwards-compat shim — older callers used this name. Equivalent to
# _extract_utm_param("content", ...). Kept as a thin wrapper so we don't
# break anything pointed at the previous symbol.
def _extract_utm_content(custom_params, *templates):
    return _extract_utm_param("content", custom_params, *templates)


def _custom_params_dict(entity):
    """Convert any Google Ads entity's url_custom_parameters (repeated
    CustomParameter message) into a {key: value} dict. Works for ad,
    ad_group, campaign — any entity that exposes url_custom_parameters."""
    out = {}
    for cp in getattr(entity, "url_custom_parameters", []) or []:
        out[cp.key] = cp.value
    return out


def _merged_custom_params(*entities):
    """Merge url_custom_parameters from multiple entities (ad, ad_group,
    campaign...). Later entities override earlier ones, so the natural call
    order is (campaign, ad_group, ad) so the most-specific param wins."""
    merged = {}
    for e in entities:
        if e is None:
            continue
        merged.update(_custom_params_dict(e))
    return merged


def _client():
    return GoogleAdsClient.load_from_dict({
        "developer_token": GOOGLE_ADS_CONFIG["developer_token"],
        "client_id": GOOGLE_ADS_CONFIG["client_id"],
        "client_secret": GOOGLE_ADS_CONFIG["client_secret"],
        "refresh_token": GOOGLE_ADS_CONFIG["refresh_token"],
        "login_customer_id": GOOGLE_ADS_CONFIG["login_customer_id"],
        "use_proto_plus": True,
    })


def _customer_ids():
    raw = os.getenv("GOOGLE_ADS_CUSTOMER_IDS") or GOOGLE_ADS_CONFIG.get("customer_id", "")
    return [c.strip().replace("-", "") for c in raw.split(",") if c.strip()]


_RIYADH = timezone(timedelta(hours=3))


def _date_window(days, incremental):
    end = datetime.now(_RIYADH).date() - timedelta(days=1)   # Google Ads is T-1
    if incremental:
        start = end - timedelta(days=2)
    elif days:
        start = end - timedelta(days=days - 1)
    else:
        start = date(end.year, 1, 1)
    return start, end


# ── Campaign level ────────────────────────────────────────────────────────────

def collect_and_write(days: int = None, incremental: bool = False):
    """Campaign grain → campaigns_daily."""
    client = _client()
    ga     = client.get_service("GoogleAdsService")
    start, end = _date_window(days, incremental)

    query = f"""
        SELECT
            customer.id,
            customer.currency_code,
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.advertising_channel_type,
            metrics.cost_micros,
            metrics.conversions,
            metrics.clicks,
            metrics.impressions,
            metrics.ctr,
            metrics.search_impression_share,
            metrics.search_top_impression_share,
            metrics.search_budget_lost_impression_share,
            metrics.search_rank_lost_impression_share,
            segments.date
        FROM campaign
        WHERE segments.date BETWEEN '{start}' AND '{end}'
    """

    now  = datetime.now(timezone.utc).isoformat()
    rows = []
    accounts = _customer_ids()
    print(f"[google_ads] campaigns {start} -> {end} | {len(accounts)} account(s)")
    for cid in accounts:
        count = 0
        try:
            for r in ga.search(customer_id=cid, query=query):
                spend_native = r.metrics.cost_micros / 1_000_000
                native_cur   = normalize_currency(r.customer.currency_code)
                spend        = to_usd(spend_native, native_cur)
                conv         = r.metrics.conversions
                # Google Ads returns IS metrics in 0..1 range; some campaign
                # types (Display, Demand Gen) report -1 / 0 to mean "n/a".
                def _is(v):
                    try:
                        v = float(v)
                        return v if 0.0 <= v <= 1.0 else None
                    except (TypeError, ValueError):
                        return None
                rows.append({
                    "date":            str(r.segments.date),
                    "channel":         "google_ads",
                    "account_id":      cid,
                    "campaign_id":     str(r.campaign.id),
                    "campaign_name":   r.campaign.name,
                    "status":          r.campaign.status.name,
                    "objective":       r.campaign.advertising_channel_type.name,
                    "spend":           round(spend, 2),
                    "impressions":     int(r.metrics.impressions),
                    "clicks":          int(r.metrics.clicks),
                    "ctr":             round(r.metrics.ctr * 100, 4),
                    "leads":           int(conv),
                    "conversions":     float(conv),
                    "cpl":             round(spend / conv, 2) if conv > 0 else None,
                    "currency":        "USD",
                    "spend_native":    round(spend_native, 2),
                    "currency_native": native_cur,
                    "impression_share":     _is(r.metrics.search_impression_share),
                    "top_impression_share": _is(r.metrics.search_top_impression_share),
                    "lost_is_budget":       _is(r.metrics.search_budget_lost_impression_share),
                    "lost_is_rank":         _is(r.metrics.search_rank_lost_impression_share),
                    "updated_at":      now,
                })
                count += 1
        except Exception as e:
            print(f"[google_ads]   account {cid} error: {e}")
        print(f"[google_ads]   account {cid}: {count} rows")

    return upsert_rows("campaigns_daily", rows,
                       key_fields=["date", "channel", "campaign_id"])


# ── Ad Group level → adsets_daily ─────────────────────────────────────────────

def collect_adgroups_and_write(days: int = None, incremental: bool = False):
    """Ad group grain → adsets_daily. Same credentials, same API call."""
    client = _client()
    ga     = client.get_service("GoogleAdsService")
    start, end = _date_window(days, incremental)

    query = f"""
        SELECT
            customer.id,
            customer.currency_code,
            campaign.id,
            campaign.name,
            campaign.tracking_url_template,
            campaign.url_custom_parameters,
            ad_group.id,
            ad_group.name,
            ad_group.tracking_url_template,
            ad_group.url_custom_parameters,
            ad_group.status,
            metrics.cost_micros,
            metrics.conversions,
            metrics.clicks,
            metrics.impressions,
            metrics.ctr,
            segments.date
        FROM ad_group
        WHERE segments.date BETWEEN '{start}' AND '{end}'
          AND campaign.status != 'REMOVED'
          AND ad_group.status != 'REMOVED'
    """

    now  = datetime.now(timezone.utc).isoformat()
    rows = []
    accounts = _customer_ids()
    print(f"[google_ads] adgroups {start} -> {end} | {len(accounts)} account(s)")
    for cid in accounts:
        count = 0
        try:
            for r in ga.search(customer_id=cid, query=query):
                spend_native = r.metrics.cost_micros / 1_000_000
                native_cur   = normalize_currency(r.customer.currency_code)
                spend        = to_usd(spend_native, native_cur)
                conv         = r.metrics.conversions
                # utm_audience: the ad-group-level UTM tag. {_adgroup} in
                # the campaign/ad_group template resolves to ad_group.name
                # at click time, but Google Ads doesn't expose that resolved
                # value on the API. So we resolve it ourselves: merge
                # url_custom_parameters from campaign + ad_group, then fall
                # back to ad_group.name when the template uses {_adgroup}.
                custom_params = _merged_custom_params(r.campaign, r.ad_group)
                # The {_adgroup} placeholder isn't in url_custom_parameters
                # — Google substitutes it from ad_group.name. Emulate that.
                custom_params.setdefault("adgroup", r.ad_group.name or "")
                utm_audience = _extract_utm_param(
                    "audience", custom_params,
                    r.ad_group.tracking_url_template,
                    r.campaign.tracking_url_template,
                )
                rows.append({
                    "date":          str(r.segments.date),
                    "channel":       "google_ads",
                    "account_id":    cid,
                    "campaign_id":   str(r.campaign.id),
                    "campaign_name": r.campaign.name,
                    "adset_id":      str(r.ad_group.id),
                    "adset_name":    r.ad_group.name,
                    "utm_audience":  utm_audience,
                    "status":        r.ad_group.status.name,
                    "spend":         round(spend, 2),
                    "impressions":   int(r.metrics.impressions),
                    "clicks":        int(r.metrics.clicks),
                    "ctr":           round(r.metrics.ctr * 100, 4),
                    "leads":         int(conv),
                    "conversions":   float(conv),
                    "currency":      "USD",
                    "updated_at":    now,
                })
                count += 1
        except Exception as e:
            print(f"[google_ads]   adgroups account {cid} error: {e}")
        print(f"[google_ads]   adgroups account {cid}: {count} rows")

    # PMax asset_groups belong here too — they are the PMax equivalent of an
    # ad_group (both → utm_audience). Merged into the same batch so the
    # shared (date, channel='google_ads') DELETE clause in upsert_rows wipes
    # and re-inserts both consistently.
    try:
        pmax_rows = _build_pmax_asset_group_rows_for_adsets(days, incremental, now)
        if pmax_rows:
            print(f"[google_ads]   pmax asset_groups merged: {len(pmax_rows)}")
            rows.extend(pmax_rows)
    except Exception as e:
        print(f"[google_ads]   pmax asset_groups error (continuing): {e}")

    return upsert_rows("adsets_daily", rows,
                       key_fields=["date", "channel", "adset_id"])


def _fetch_pmax_asset_groups(days, incremental):
    """Single API call that yields (record, custom_params, spend) tuples for
    PMax asset_groups. Used by both adset-level and ad-level builders so we
    only hit the API once."""
    client = _client()
    ga     = client.get_service("GoogleAdsService")
    start, end = _date_window(days, incremental)
    # asset_group.url_custom_parameters is where each asset_group's own
    # _adname (= utm_content), _audience (= utm_audience), etc. live.
    # Campaign-level params are inherited; asset_group-level overrides.
    query = f"""
        SELECT
            customer.id,
            customer.currency_code,
            campaign.id,
            campaign.name,
            campaign.tracking_url_template,
            campaign.url_custom_parameters,
            asset_group.id,
            asset_group.name,
            asset_group.status,
            metrics.cost_micros,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.conversions,
            segments.date
        FROM asset_group
        WHERE segments.date BETWEEN '{start}' AND '{end}'
          AND campaign.advertising_channel_type = 'PERFORMANCE_MAX'
          AND campaign.status != 'REMOVED'
    """
    print(f"[google_ads] pmax-asset-groups {start} -> {end}")
    for cid in _customer_ids():
        try:
            for r in ga.search(customer_id=cid, query=query):
                spend_native = r.metrics.cost_micros / 1_000_000
                native_cur   = normalize_currency(r.customer.currency_code)
                spend        = to_usd(spend_native, native_cur)
                # asset_group.url_custom_parameters isn't queryable as a
                # field in GAQL (confirmed via API error). So we work with
                # campaign-level params + the implicit Google substitutions
                # that happen at click time.
                custom_params = _custom_params_dict(r.campaign)
                # Implicit substitutions Google does at click time when the
                # tracking template uses {_paramname}. For PMax, asset_group
                # plays the role of both "adgroup" and "adname" (asset_group
                # IS the lowest reportable unit and is what gets clicked):
                custom_params.setdefault("adgroup",    r.asset_group.name or "")
                custom_params.setdefault("assetgroup", r.asset_group.name or "")
                custom_params.setdefault("adname",     r.asset_group.name or "")
                yield (r, cid, custom_params, spend)
        except Exception as e:
            print(f"[google_ads]   pmax asset_groups account {cid} error: {e}")


def _build_pmax_asset_group_rows_for_adsets(days, incremental, now: str) -> list[dict]:
    """Build PMax asset_group rows formatted for adsets_daily (utm_audience)."""
    rows = []
    for r, cid, custom_params, spend in _fetch_pmax_asset_groups(days, incremental):
        utm_audience = _extract_utm_param(
            "audience", custom_params, r.campaign.tracking_url_template,
        )
        rows.append({
            "date":          str(r.segments.date),
            "channel":       "google_ads",
            "account_id":    cid,
            "campaign_id":   str(r.campaign.id),
            "campaign_name": r.campaign.name,
            "adset_id":      f"pmax_{r.asset_group.id}",
            "adset_name":    r.asset_group.name,
            "utm_audience":  utm_audience,
            "status":        r.asset_group.status.name,
            "spend":         round(spend, 2),
            "impressions":   int(r.metrics.impressions),
            "clicks":        int(r.metrics.clicks),
            "ctr":           round(r.metrics.ctr * 100, 4),
            "leads":         int(r.metrics.conversions),
            "conversions":   float(r.metrics.conversions),
            "currency":      "USD",
            "updated_at":    now,
        })
    return rows


def _build_pmax_asset_group_rows_for_ads(days, incremental, now: str) -> list[dict]:
    """Build PMax asset_group rows formatted for ads_daily (utm_content).

    Each asset_group becomes one row in ads_daily because PMax has no
    sub-asset_group reportable unit. utm_content is resolved from the
    asset_group's own url_custom_parameters — typically the _adname value.
    """
    rows = []
    for r, cid, custom_params, spend in _fetch_pmax_asset_groups(days, incremental):
        utm_content = _extract_utm_param(
            "content", custom_params, r.campaign.tracking_url_template,
        )
        rows.append({
            "date":          str(r.segments.date),
            "channel":       "google_ads",
            "account_id":    cid,
            "campaign_id":   str(r.campaign.id),
            "campaign_name": r.campaign.name,
            "adset_id":      f"pmax_{r.asset_group.id}",
            "adset_name":    r.asset_group.name,
            "ad_id":         f"pmax_{r.asset_group.id}",
            "ad_name":       r.asset_group.name,
            "utm_content":   utm_content,
            "status":        r.asset_group.status.name,
            "spend":         round(spend, 2),
            "impressions":   int(r.metrics.impressions),
            "clicks":        int(r.metrics.clicks),
            "ctr":           round(r.metrics.ctr * 100, 4),
            "leads":         int(r.metrics.conversions),
            "conversions":   float(r.metrics.conversions),
            "currency":      "USD",
            "final_url":     None,
            "updated_at":    now,
        })
    return rows


# ── Keyword level → keywords_daily ────────────────────────────────────────────

def collect_keywords_and_write(days: int = None, incremental: bool = False):
    """Keyword grain → keywords_daily. Same credentials, same API call."""
    client = _client()
    ga     = client.get_service("GoogleAdsService")
    start, end = _date_window(days, incremental)

    query = f"""
        SELECT
            customer.id,
            customer.currency_code,
            campaign.id,
            campaign.name,
            ad_group.id,
            ad_group.name,
            ad_group_criterion.criterion_id,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            ad_group_criterion.status,
            ad_group_criterion.quality_info.quality_score,
            metrics.cost_micros,
            metrics.conversions,
            metrics.clicks,
            metrics.impressions,
            metrics.ctr,
            metrics.average_cpc,
            segments.date
        FROM keyword_view
        WHERE segments.date BETWEEN '{start}' AND '{end}'
          AND ad_group_criterion.type = 'KEYWORD'
          AND campaign.status != 'REMOVED'
          AND ad_group.status != 'REMOVED'
    """

    now  = datetime.now(timezone.utc).isoformat()
    rows = []
    accounts = _customer_ids()
    print(f"[google_ads] keywords {start} -> {end} | {len(accounts)} account(s)")
    for cid in accounts:
        count = 0
        try:
            for r in ga.search(customer_id=cid, query=query):
                spend_native = r.metrics.cost_micros / 1_000_000
                native_cur   = normalize_currency(r.customer.currency_code)
                spend        = to_usd(spend_native, native_cur)
                avg_cpc_native = r.metrics.average_cpc / 1_000_000
                avg_cpc        = to_usd(avg_cpc_native, native_cur)
                conv           = r.metrics.conversions
                qs             = r.ad_group_criterion.quality_info.quality_score
                rows.append({
                    "date":          str(r.segments.date),
                    "channel":       "google_ads",
                    "account_id":    cid,
                    "campaign_id":   str(r.campaign.id),
                    "campaign_name": r.campaign.name,
                    "adgroup_id":    str(r.ad_group.id),
                    "adgroup_name":  r.ad_group.name,
                    "keyword_id":    str(r.ad_group_criterion.criterion_id),
                    "keyword_text":  r.ad_group_criterion.keyword.text,
                    "match_type":    r.ad_group_criterion.keyword.match_type.name,
                    "status":        r.ad_group_criterion.status.name,
                    "quality_score": int(qs) if qs else None,
                    "spend":         round(spend, 2),
                    "impressions":   int(r.metrics.impressions),
                    "clicks":        int(r.metrics.clicks),
                    "ctr":           round(r.metrics.ctr * 100, 4),
                    "avg_cpc":       round(avg_cpc, 4),
                    "conversions":   float(conv),
                    "currency":      "USD",
                    "updated_at":    now,
                })
                count += 1
        except Exception as e:
            print(f"[google_ads]   keywords account {cid} error: {e}")
        print(f"[google_ads]   keywords account {cid}: {count} rows")

    return upsert_rows("keywords_daily", rows,
                       key_fields=["date", "channel", "adgroup_id", "keyword_id"])


# ── Ad level → ads_daily (with final_url for LP analysis) ─────────────────────

def collect_ads_and_write(days: int = None, incremental: bool = False):
    """Ad grain → ads_daily. Includes final_url so LP type (HubSpot vs WordPress) can be tracked."""
    client = _client()
    ga     = client.get_service("GoogleAdsService")
    start, end = _date_window(days, incremental)

    query = f"""
        SELECT
            customer.id,
            customer.currency_code,
            campaign.id,
            campaign.name,
            campaign.tracking_url_template,
            ad_group.id,
            ad_group.name,
            ad_group.tracking_url_template,
            ad_group_ad.ad.id,
            ad_group_ad.ad.name,
            ad_group_ad.ad.final_urls,
            ad_group_ad.ad.tracking_url_template,
            ad_group_ad.ad.url_custom_parameters,
            ad_group_ad.status,
            metrics.cost_micros,
            metrics.conversions,
            metrics.clicks,
            metrics.impressions,
            metrics.ctr,
            segments.date
        FROM ad_group_ad
        WHERE segments.date BETWEEN '{start}' AND '{end}'
          AND campaign.status != 'REMOVED'
          AND ad_group.status != 'REMOVED'
          AND ad_group_ad.status != 'REMOVED'
    """

    now  = datetime.now(timezone.utc).isoformat()
    rows = []
    accounts = _customer_ids()
    print(f"[google_ads] ads {start} -> {end} | {len(accounts)} account(s)")
    for cid in accounts:
        count = 0
        try:
            for r in ga.search(customer_id=cid, query=query):
                spend_native = r.metrics.cost_micros / 1_000_000
                native_cur   = normalize_currency(r.customer.currency_code)
                spend        = to_usd(spend_native, native_cur)
                conv         = r.metrics.conversions
                # final_urls is a repeated field; take first URL or None
                final_urls   = list(r.ad_group_ad.ad.final_urls)
                final_url    = final_urls[0] if final_urls else None
                # utm_content: parsed from tracking_url_template at
                # ad > ad_group > campaign (lowest-non-empty wins). Resolves
                # {_paramname} placeholders against merged custom params
                # from campaign + ad_group + ad. Plus the implicit
                # {_adname} → ad.name and {_adgroup} → ad_group.name
                # substitutions Google does at click time.
                custom_params = _merged_custom_params(
                    r.campaign, r.ad_group, r.ad_group_ad.ad,
                )
                custom_params.setdefault("adgroup", r.ad_group.name or "")
                custom_params.setdefault("adname", r.ad_group_ad.ad.name or "")
                utm_content = _extract_utm_param(
                    "content", custom_params,
                    r.ad_group_ad.ad.tracking_url_template,
                    r.ad_group.tracking_url_template,
                    r.campaign.tracking_url_template,
                )
                rows.append({
                    "date":          str(r.segments.date),
                    "channel":       "google_ads",
                    "account_id":    cid,
                    "campaign_id":   str(r.campaign.id),
                    "campaign_name": r.campaign.name,
                    "adset_id":      str(r.ad_group.id),
                    "adset_name":    r.ad_group.name,
                    "ad_id":         str(r.ad_group_ad.ad.id),
                    "ad_name":       r.ad_group_ad.ad.name or "",
                    "utm_content":   utm_content,
                    "status":        r.ad_group_ad.status.name,
                    "spend":         round(spend, 2),
                    "impressions":   int(r.metrics.impressions),
                    "clicks":        int(r.metrics.clicks),
                    "ctr":           round(r.metrics.ctr * 100, 4),
                    "leads":         int(conv),
                    "conversions":   float(conv),
                    "currency":      "USD",
                    "final_url":     final_url,
                    "updated_at":    now,
                })
                count += 1
        except Exception as e:
            print(f"[google_ads]   ads account {cid} error: {e}")
        print(f"[google_ads]   ads account {cid}: {count} rows")

    # PMax: each asset_group becomes one ad row. utm_content resolved
    # from asset_group.url_custom_parameters (where _adname lives). Merged
    # into the same batch so the shared (date, channel) DELETE doesn't
    # wipe both buckets.
    try:
        pmax_rows = _build_pmax_asset_group_rows_for_ads(days, incremental, now)
        if pmax_rows:
            print(f"[google_ads]   pmax asset_group ads merged: {len(pmax_rows)}")
            rows.extend(pmax_rows)
    except Exception as e:
        print(f"[google_ads]   pmax ads error (continuing): {e}")

    return upsert_rows("ads_daily", rows,
                       key_fields=["date", "channel", "ad_id"])


# ── PMax Asset Group level → pmax_asset_groups_daily ─────────────────────────

def collect_pmax_asset_groups_and_write(days: int = None, incremental: bool = False):
    """PMax asset-group grain → pmax_asset_groups_daily.

    Queries asset_group_asset for Performance Max campaigns only,
    joining asset and campaign metadata.  One row per
    (date, customer_id, campaign_id, asset_group_id, asset_id).
    """
    from google.cloud import bigquery as bq
    from collectors.bq_writer import get_client

    client = _client()
    ga     = client.get_service("GoogleAdsService")
    start, end = _date_window(days, incremental)

    query = f"""
        SELECT
            asset_group.id,
            asset_group.name,
            asset_group.status,
            asset_group.campaign,
            campaign.id,
            campaign.name,
            asset.id,
            asset.name,
            asset.type,
            asset_group_asset.performance_label,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions,
            segments.date
        FROM asset_group_asset
        WHERE segments.date BETWEEN '{start}' AND '{end}'
          AND campaign.advertising_channel_type = 'PERFORMANCE_MAX'
    """

    now  = datetime.now(timezone.utc).isoformat()
    rows = []
    accounts = _customer_ids()
    print(f"[google_ads] pmax_asset_groups {start} -> {end} | {len(accounts)} account(s)")
    for cid in accounts:
        count = 0
        try:
            for r in ga.search(customer_id=cid, query=query):
                spend = r.metrics.cost_micros / 1_000_000
                rows.append({
                    "date":               str(r.segments.date),
                    "customer_id":        cid,
                    "campaign_id":        str(r.campaign.id),
                    "campaign_name":      r.campaign.name,
                    "asset_group_id":     str(r.asset_group.id),
                    "asset_group_name":   r.asset_group.name,
                    "asset_group_status": r.asset_group.status.name,
                    "asset_id":           str(r.asset.id),
                    "asset_name":         r.asset.name or "",
                    "asset_type":         r.asset.type_.name,
                    "performance_label":  r.asset_group_asset.performance_label.name,
                    "impressions":        int(r.metrics.impressions),
                    "clicks":             int(r.metrics.clicks),
                    "spend":              round(spend, 6),
                    "conversions":        float(r.metrics.conversions),
                    "updated_at":         now,
                })
                count += 1
        except Exception as e:
            print(f"[google_ads]   pmax_asset_groups account {cid} error: {e}")
        print(f"[google_ads]   pmax_asset_groups account {cid}: {count} rows")

    _ensure_pmax_asset_groups_table()
    return upsert_rows("pmax_asset_groups_daily", rows,
                       key_fields=["date", "customer_id", "campaign_id",
                                   "asset_group_id", "asset_id"])


def _ensure_pmax_asset_groups_table():
    from google.cloud import bigquery as bq
    from collectors.bq_writer import get_client

    client   = get_client()
    table_id = f"{os.getenv('BQ_PROJECT_ID')}.{os.getenv('BQ_DATASET')}.pmax_asset_groups_daily"
    schema = [
        bq.SchemaField("date",               "DATE",      mode="REQUIRED"),
        bq.SchemaField("customer_id",         "STRING"),
        bq.SchemaField("campaign_id",         "STRING"),
        bq.SchemaField("campaign_name",       "STRING"),
        bq.SchemaField("asset_group_id",      "STRING"),
        bq.SchemaField("asset_group_name",    "STRING"),
        bq.SchemaField("asset_group_status",  "STRING"),
        bq.SchemaField("asset_id",            "STRING"),
        bq.SchemaField("asset_name",          "STRING"),
        bq.SchemaField("asset_type",          "STRING"),
        bq.SchemaField("performance_label",   "STRING"),
        bq.SchemaField("impressions",         "INT64"),
        bq.SchemaField("clicks",              "INT64"),
        bq.SchemaField("spend",               "FLOAT64"),
        bq.SchemaField("conversions",         "FLOAT64"),
        bq.SchemaField("updated_at",          "TIMESTAMP"),
    ]
    table = bq.Table(table_id, schema=schema)
    table.time_partitioning = bq.TimePartitioning(field="date")
    table.clustering_fields = ["customer_id", "campaign_id", "asset_group_id"]
    client.create_table(table, exists_ok=True)


if __name__ == "__main__":
    import sys
    cmd  = sys.argv[1] if len(sys.argv) > 1 else "all"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else None
    if cmd in ("all", "campaigns"):
        print(f"campaigns:         {collect_and_write(days=days)} rows")
    if cmd in ("all", "adgroups"):
        print(f"adgroups:          {collect_adgroups_and_write(days=days)} rows")
    if cmd in ("all", "keywords"):
        print(f"keywords:          {collect_keywords_and_write(days=days)} rows")
    if cmd in ("all", "ads"):
        print(f"ads:               {collect_ads_and_write(days=days)} rows")
    if cmd in ("all", "pmax_asset_groups"):
        print(f"pmax_asset_groups: {collect_pmax_asset_groups_and_write(days=days)} rows")
