"""
analysers/campaign_health.py
=============================
Cross-channel CPQL/CPL health check — the primary analyst investigation.

Measurement rules (from CLAUDE.md):
  - Cost:  campaigns_daily.spend  (channel source, always USD)
  - Leads: hubspot_leads_module_daily  (Lead Module, NOT contact lifecycle)
  - Evaluation order: CPQL first, then CPL
  - Minimum window: 14 days (DAYS_FOR_PAUSE_DECISION)
  - HubSpot pre-aggregated by CTE before joining to avoid spend fan-out

Called from:
  - analysers/campaign_health_tasks.py  (creates Asana tasks + executes actions)
  - main.py daily loop
  - Manual: python -m analysers.campaign_health
"""
from __future__ import annotations

from datetime import date, timedelta

from dotenv import load_dotenv

load_dotenv(override=True)

from collectors.bq_writer import get_client, PROJECT_ID, DATASET
from config import (
    CPL_SCALE, CPL_ACCEPTABLE, CPL_WARNING,
    CPQL_SCALE, CPQL_ACCEPTABLE, CPQL_WARNING,
    QUAL_RATE_TARGET, DAYS_FOR_PAUSE_DECISION,
    ROAS_GOOD, AWARENESS_PATTERNS,
    CHANNEL_CPQL_ACCEPTABLE, MIN_DAYS_SINCE_EDIT, QFLAVOURS_PIPELINE_CHECK,
    SCALE_REQUIRES_ROAS, DRILL_DOWN_CPQL, DRILL_DOWN_CPL, DRILL_DOWN_DAYS,
    SOCIAL_CHANNELS, SEARCH_CHANNELS,
)


# Search channels use keyword-based optimization (the keyword IS the targeting).
# Pausing an ad in a search campaign when the issue is a bad keyword or broken
# LP is the wrong surgery. Ad-level precedence ONLY applies to social.
SOCIAL_PAUSE_CHANNELS = {"meta", "snapchat", "tiktok"}
SEARCH_PAUSE_CHANNELS = {"google_ads", "microsoft_ads"}


def _campaigns_with_ad_pause_candidates(days: int = 14) -> dict[str, list[dict]]:
    """Return {campaign_id: [{ad_id, ad_name, reason, spend, cpl, days_active}, ...]}
    for every SOCIAL-channel campaign that has at least one ad meeting AD-level
    pause criteria.

    Pause precedence rule (CLAUDE.md, confirmed 2026-05-17):
      A campaign-level pause is FORBIDDEN as long as any ad inside it qualifies
      for an ad-level pause. First pause the bad ads; re-evaluate next cycle.

    Channel routing (corrected 2026-05-17):
      - Social (meta, snapchat, tiktok): ad-level pauses run first.
      - Search (google_ads, microsoft_ads): keywords + landing page are the
        first investigation surface, NOT ads. See _campaigns_with_keyword_pause_candidates.

    Rules (mirrors scripts/bulk_ads.py):
      - zero_conv: spend > $70, 7+ days, 0 platform conversions
      - high_cpl:  CPL > $50,  10+ days
      - junk_lead: 10+ days, hs_leads ≥ 5, disq_rate ≥ 60%
    """
    from config import (
        AD_CPL_PAUSE,                 # $50 — high-CPL ad threshold
    )
    ZERO_CONV_SPEND = 70.0
    ZERO_CONV_DAYS  = 7
    HIGH_CPL_DAYS   = 10
    JUNK_LEAD_DAYS  = 10
    JUNK_LEAD_MIN   = 5
    JUNK_LEAD_RATE  = 0.60

    client = get_client()
    sql = f"""
    WITH ad_perf AS (
      SELECT campaign_id, channel, ad_id,
             ANY_VALUE(ad_name)    AS ad_name,
             SUM(spend)            AS total_spend,
             SUM(conversions)      AS total_conv,
             COUNT(DISTINCT date)  AS days_active
      FROM `{PROJECT_ID}.{DATASET}.ads_daily`
      WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {days} DAY)
        AND status IN ('ENABLED', 'ACTIVE')           -- only enabled ads count as candidates
        AND channel IN ('meta', 'snapchat', 'tiktok') -- SOCIAL only; search uses keywords
      GROUP BY campaign_id, channel, ad_id            -- one row per ad
    ),
    hs AS (
      SELECT LOWER(lead_utm_content) AS ad_key,
             SUM(leads_total)        AS hs_leads,
             SUM(leads_disqualified) AS hs_disq
      FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
      WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {days} DAY)
        AND lead_utm_content IS NOT NULL
      GROUP BY 1
    )
    SELECT a.campaign_id, a.channel, a.ad_id, a.ad_name,
           a.total_spend, a.total_conv, a.days_active,
           COALESCE(hs.hs_leads, 0) AS hs_leads,
           COALESCE(hs.hs_disq,  0) AS hs_disq,
           SAFE_DIVIDE(hs.hs_disq, NULLIF(hs.hs_leads, 0))   AS disq_rate,
           SAFE_DIVIDE(a.total_spend, NULLIF(hs.hs_leads, 0)) AS cpl
    FROM ad_perf a
    LEFT JOIN hs ON LOWER(a.ad_name) = hs.ad_key
    WHERE a.total_spend > 20                          -- skip dust
    """
    candidates: dict[str, list[dict]] = {}
    for r in client.query(sql).result():
        reasons = []
        spend = float(r.total_spend or 0)
        conv  = float(r.total_conv  or 0)
        days_a = int(r.days_active or 0)
        cpl   = float(r.cpl) if r.cpl is not None else None
        dr    = float(r.disq_rate) if r.disq_rate is not None else None
        if spend > ZERO_CONV_SPEND and days_a >= ZERO_CONV_DAYS and conv == 0:
            reasons.append("zero_conv")
        if cpl is not None and cpl > AD_CPL_PAUSE and days_a >= HIGH_CPL_DAYS:
            reasons.append("high_cpl")
        if (days_a >= JUNK_LEAD_DAYS and int(r.hs_leads or 0) >= JUNK_LEAD_MIN
                and dr is not None and dr >= JUNK_LEAD_RATE):
            reasons.append("junk_lead")
        if reasons:
            candidates.setdefault(str(r.campaign_id), []).append({
                "ad_id":   str(r.ad_id),
                "ad_name": r.ad_name,
                "reasons": reasons,
                "spend":   round(spend, 2),
                "cpl":     round(cpl, 2) if cpl is not None else None,
                "days":    days_a,
            })
    return candidates


def _campaigns_with_keyword_pause_candidates(days: int = 14) -> dict[str, list[dict]]:
    """Return {campaign_id: [{keyword, ad_group, reason, spend, cpl, days_active}, ...]}
    for SEARCH-channel campaigns (google_ads + microsoft_ads) that have at
    least one keyword meeting keyword-level pause criteria.

    Pause precedence for search (corrected 2026-05-17):
      Keywords are the targeting surface for search; campaign-pause is forbidden
      while any keyword qualifies for keyword-level pause AND any ad's landing
      page hasn't been reviewed. The keyword audit handles surgical cleanup;
      this helper just flags presence so campaign-pause is blocked.

    Rules (mirrors executors/keyword_policy.py + scripts/audit.py keywords):
      - zero_conv:  spend > $35, 14+ days, 0 conversions
      - high_cpl:   CPL > $80, 14+ days, 1+ conversions
      - never delete a converting keyword (this helper only flags pause-worthy)
    """
    client = get_client()
    sql = f"""
    WITH kw_perf AS (
      SELECT campaign_id, channel, adgroup_id, keyword_id,
             ANY_VALUE(keyword_text)  AS keyword_text,
             ANY_VALUE(adgroup_name)  AS adgroup_name,
             SUM(spend)               AS total_spend,
             SUM(conversions)         AS total_conv,
             COUNT(DISTINCT date)     AS days_active
      FROM `{PROJECT_ID}.{DATASET}.keywords_daily`
      WHERE date >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL {days} DAY)
        AND status IN ('ENABLED', 'ACTIVE')
        AND channel IN ('google_ads', 'microsoft_ads')
      GROUP BY campaign_id, channel, adgroup_id, keyword_id
    )
    SELECT campaign_id, channel, keyword_text AS keyword,
           adgroup_name, keyword_id,
           total_spend, total_conv, days_active,
           SAFE_DIVIDE(total_spend, NULLIF(total_conv, 0)) AS cpl
    FROM kw_perf
    WHERE total_spend > 5
    """
    candidates: dict[str, list[dict]] = {}
    try:
        rows = list(client.query(sql).result())
    except Exception as e:
        print(f"[health] keyword candidates query failed: {e}")
        return {}
    for r in rows:
        reasons = []
        spend  = float(r.total_spend or 0)
        conv   = float(r.total_conv or 0)
        days_a = int(r.days_active or 0)
        cpl    = float(r.cpl) if r.cpl is not None else None
        if spend > 35 and days_a >= 14 and conv == 0:
            reasons.append("zero_conv")
        if cpl is not None and cpl > 80 and days_a >= 14 and conv >= 1:
            reasons.append("high_cpl")
        if reasons:
            candidates.setdefault(str(r.campaign_id), []).append({
                "keyword":   r.keyword,
                "adgroup":   r.adgroup_name,
                "reasons":   reasons,
                "spend":     round(spend, 2),
                "cpl":       round(cpl, 2) if cpl is not None else None,
                "days":      days_a,
            })
    return candidates


def _is_awareness(campaign_name: str) -> bool:
    """
    Returns True if the campaign is an awareness/traffic/reach campaign.
    These are evaluated on impression share (IS ≥ 25% = healthy), NOT on leads.
    """
    name_lower = campaign_name.lower().replace("-", "").replace(" ", "")
    return any(p in name_lower for p in AWARENESS_PATTERNS)


# ── KPI primacy ──────────────────────────────────────────────────────────────
# CPQL is the canonical pause/scale signal. CPL zone is consulted only as a
# tie-breaker or supplemental context — never as the primary decision metric.
# See config.py for the rationale (May 2026 incident: CPL gave a green light
# while CPQL was alarming, team kept scaling).

def _cpql_zone(val: float | None) -> str:
    """PRIMARY pause/scale signal. Drives the decision tree below."""
    if val is None:        return "no_data"
    if val < CPQL_SCALE:   return "scale"
    if val <= CPQL_ACCEPTABLE: return "ok"
    if val <= CPQL_WARNING:    return "warning"
    return "pause"


def _cpl_zone(val: float | None) -> str:
    """SECONDARY support signal — used only as tie-breaker. Do not pause/scale
    on CPL alone."""
    if val is None:       return "no_data"
    if val < CPL_SCALE:   return "scale"
    if val <= CPL_ACCEPTABLE: return "ok"
    if val <= CPL_WARNING:    return "warning"
    return "pause"


def audit_campaign_health(
    days: int = DAYS_FOR_PAUSE_DECISION,
    min_spend: float = 70.0,
    channels: list[str] | None = None,
) -> list[dict]:
    """
    Return one health record per campaign with CPQL zone, CPL zone, and
    a recommended action.

    Measurement:
      - Cost from campaigns_daily (channel source)
      - Leads/SQLs from hubspot_leads_module_daily (Lead Module)
      - HubSpot pre-aggregated by CTE to prevent spend fan-out
    """
    client = get_client()

    today = date.today()
    since = (today - timedelta(days=days)).isoformat()
    channel_filter = ""
    channel_filter_bare = ""   # no table alias, for use inside cd CTE
    if channels:
        ch_list = ", ".join(f"'{c}'" for c in channels)
        channel_filter      = f"AND c.channel IN ({ch_list})"
        channel_filter_bare = f"AND channel IN ({ch_list})"

    # Lag-aware CPQL — exclude days where open_leads/leads_total > 30% from
    # CPQL/qual_rate math so pause/scale decisions aren't made on SDR backlog.
    # The 30% threshold matches config.LAG_OPEN_PCT_THRESHOLD; if you tune
    # that constant, update the SQL literal below in hs.day_lag_ok too.
    sql = f"""
        WITH cd AS (
          -- Pre-aggregate campaigns_daily to exactly one row per (date, channel,
          -- campaign_name). Guards against duplicate writes from the collector
          -- (e.g. Snapchat, Bing) which produce fan-out when joined to HS.
          SELECT
            date,
            channel,
            campaign_name,
            ANY_VALUE(account_id) AS account_id,
            ANY_VALUE(status)     AS status,
            SUM(spend)            AS spend,
            MAX(updated_at)       AS updated_at
          FROM `{PROJECT_ID}.{DATASET}.campaigns_daily`
          WHERE date >= '{since}'
            {channel_filter_bare}
          GROUP BY date, channel, campaign_name
        ),
        hs AS (
          -- Include qoyod_source so the JOIN can match HS leads to the right
          -- channel. Without this, a campaign name shared between Google and
          -- Bing (e.g. "Search_AR_Brand_v2") would blend leads from both
          -- channels into whichever cd row is evaluated.
          SELECT
            date,
            lead_utm_campaign,
            -- Map qoyod_source → channel slug so we can join on channel too.
            CASE qoyod_source
              WHEN 'Google Ads'    THEN 'google_ads'
              WHEN 'Meta Ads'      THEN 'meta'
              WHEN 'Snapchat Ads'  THEN 'snapchat'
              WHEN 'Tiktok Ads'    THEN 'tiktok'
              WHEN 'Microsoft Ads' THEN 'microsoft_ads'
              WHEN 'LinkedIn Ads'  THEN 'linkedin'
              ELSE NULL
            END                  AS hs_channel,
            SUM(leads_total)     AS leads,
            SUM(leads_qualified) AS sqls,
            -- Day-level lag flag: TRUE when SDR backlog <= 30% of leads.
            SAFE_DIVIDE(SUM(COALESCE(leads_open, 0)), NULLIF(SUM(leads_total), 0))
                <= 0.30
              OR SUM(leads_total) = 0          AS day_lag_ok
          FROM `{PROJECT_ID}.{DATASET}.hubspot_leads_module_daily`
          GROUP BY date, lead_utm_campaign, qoyod_source
        ),
        deals AS (
          SELECT
            deal_utm_campaign,
            SUM(amount_won) AS revenue_won
          FROM `{PROJECT_ID}.{DATASET}.hubspot_deals_daily`
          WHERE date >= '{since}'
          GROUP BY deal_utm_campaign
        )
        SELECT
          c.channel,
          c.campaign_name,
          MAX(c.account_id)                                                     AS account_id,
          MAX(c.status)                                                         AS status,
          SUM(c.spend)                                                         AS spend,
          SUM(hs.leads)                                                        AS hs_leads,
          SUM(hs.sqls)                                                         AS sqls,
          SAFE_DIVIDE(SUM(c.spend), NULLIF(SUM(hs.leads), 0))                  AS cpl,
          SAFE_DIVIDE(
            SUM(IF(hs.day_lag_ok, c.spend, 0)),
            NULLIF(SUM(IF(hs.day_lag_ok, hs.sqls, 0)), 0)
          )                                                                    AS cpql,
          SAFE_DIVIDE(
            SUM(IF(hs.day_lag_ok, hs.sqls,  0)),
            NULLIF(SUM(IF(hs.day_lag_ok, hs.leads, 0)), 0)
          )                                                                    AS qual_rate,
          MAX(d.revenue_won)                                                    AS revenue_won,
          SAFE_DIVIDE(MAX(d.revenue_won), NULLIF(SUM(c.spend), 0))             AS roas,
          MAX(c.updated_at)                                                     AS last_updated
        FROM cd c
        LEFT JOIN hs
          ON  c.date = hs.date
          AND LOWER(c.campaign_name) = LOWER(hs.lead_utm_campaign)
          AND (hs.hs_channel IS NULL OR hs.hs_channel = c.channel)
        LEFT JOIN deals d
          ON  LOWER(c.campaign_name) = LOWER(d.deal_utm_campaign)
        GROUP BY c.channel, c.campaign_name
        HAVING SUM(c.spend) >= {min_spend}
        ORDER BY cpql ASC NULLS LAST
    """

    rows = list(client.query(sql).result())

    # Pre-fetch IS data from Google Ads API once — used to route awareness campaigns.
    # Keyed by lowercase campaign name. Non-Google channels won't appear here.
    _is_cache: dict = {}
    try:
        from analysers.google_ads_audit import audit_impression_share
        for f in audit_impression_share(days=days):
            _is_cache[f["campaign"].lower()] = f
    except Exception as _e:
        print(f"[health] IS cache fetch skipped: {_e}")

    # Pre-fetch pause-precedence candidates per campaign. Used below to block
    # campaign-level pause when surgical cleanup hasn't happened yet.
    # - Social channels → ad-level candidates (the ad IS the targeting)
    # - Search channels → keyword-level candidates (the keyword IS the targeting)
    try:
        _ad_candidates = _campaigns_with_ad_pause_candidates(days=days)
    except Exception as _e:
        print(f"[health] ad-pause-candidates query skipped: {_e}")
        _ad_candidates = {}
    try:
        _kw_candidates = _campaigns_with_keyword_pause_candidates(days=days)
    except Exception as _e:
        print(f"[health] keyword-pause-candidates query skipped: {_e}")
        _kw_candidates = {}

    findings = []
    for r in rows:
        cpql_z = _cpql_zone(r.cpql)
        cpl_z  = _cpl_zone(r.cpl)
        qr     = (r.qual_rate or 0) * 100
        roas   = float(r.roas or 0)
        is_awareness = _is_awareness(r.campaign_name)

        # Days since last campaign edit
        last_updated = r.last_updated
        if last_updated:
            # last_updated is a datetime (UTC) from BQ
            if hasattr(last_updated, "date"):
                last_updated_date = last_updated.date()
            else:
                last_updated_date = last_updated
            days_since_edit = (today - last_updated_date).days
        else:
            days_since_edit = 999  # unknown → treat as stale, allow action

        # Channel-specific CPQL acceptable threshold override
        ch_cpql_ok = CHANNEL_CPQL_ACCEPTABLE.get(r.channel, CPQL_ACCEPTABLE)
        if r.cpql and r.cpql <= ch_cpql_ok and cpql_z in ("warning",):
            cpql_z = "ok"  # downgrade: within channel-specific acceptable range

        # Qflavours flag — needs HubSpot pipeline verification
        is_qflavours = "qflavours" in r.campaign_name.lower()

        # ── Awareness / traffic / reach campaigns ─────────────────────────────
        # Primary KPI: Search Impression Share + Lost IS metrics, not leads.
        # Route: Lost-IS-Budget high → scale | Lost-IS-Rank high → optimize
        #        IS healthy (no finding) → monitor | non-Google → optimize (manual check)
        if is_awareness:
            is_rec = _is_cache.get(r.campaign_name.lower())
            if is_rec:
                if is_rec["verdict"] == "scale-budget-candidate":
                    action = "scale"
                    note   = (
                        f"Lost IS (Budget) = {is_rec['is_lost_budget']*100:.0f}% — "
                        f"campaign is ranking but budget-capped. "
                        f"Raise daily budget to capture more impressions."
                    )
                else:
                    action = "optimize"
                    note   = is_rec["action"]
            elif r.channel == "google_ads":
                action = "monitor"
                note   = "Awareness campaign — IS healthy, no budget/rank loss detected."
            else:
                action = "optimize"
                note   = (
                    "Awareness/traffic campaign — check platform-native reach/IS metrics. "
                    "Target: impression share ≥ 25%, frequency ≤ 3. CPQL/CPL not applicable."
                )
            if action == "monitor":
                continue   # healthy awareness — no task needed
            findings.append({
                "channel":         r.channel,
                "campaign":        r.campaign_name,
                "account_id":      r.account_id,
                "status":          r.status,
                "days":            days,
                "date_from":       since,
                "date_to":         today.isoformat(),
                "last_updated":    "awareness",
                "days_since_edit": 999,
                "spend":           round(r.spend or 0, 2),
                "hs_leads":        int(r.hs_leads or 0),
                "sqls":            int(r.sqls or 0),
                "cpl":             None,
                "cpql":            None,
                "qual_rate":       0.0,
                "roas":            round(roas, 2),
                "cpql_zone":       "awareness",
                "cpl_zone":        "awareness",
                "junk_leads":      False,
                "is_awareness":    True,
                "is_qflavours":    False,
                "roas_override":   False,
                "action":          action,
                "note":            note,
                "is_share":        is_rec.get("is_share") if is_rec else None,
                "is_lost_budget":  is_rec.get("is_lost_budget") if is_rec else None,
                "is_lost_rank":    is_rec.get("is_lost_rank") if is_rec else None,
            })
            continue

        # ── ROAS override ─────────────────────────────────────────────────────
        roas_override = roas >= ROAS_GOOD and roas > 0

        # ── Drill-down trigger ─────────────────────────────────────────────────
        # CPQL > $130 AND CPL > $32 for >= 10 days
        needs_drilldown = (
            (r.cpql or 0) > DRILL_DOWN_CPQL
            and (r.cpl  or 0) > DRILL_DOWN_CPL
            and days >= DRILL_DOWN_DAYS
        )
        drilldown_channel_type = (
            "search" if r.channel in SEARCH_CHANNELS else
            "social" if r.channel in SOCIAL_CHANNELS else
            "unknown"
        )

        # Junk-leads flag: low CPL looks like scale but CPQL says pause/warning.
        junk_leads = (
            cpl_z in ("scale", "ok")
            and cpql_z in ("pause", "warning")
            and qr < QUAL_RATE_TARGET * 100
            and not roas_override
        )

        # ── Action recommendation — CPQL-first, then CPL ──────────────────────
        if needs_drilldown:
            action = "drilldown"
            if drilldown_channel_type == "search":
                note = (
                    f"CPQL ${r.cpql:.2f} + CPL ${r.cpl:.2f} above threshold for {days} days. "
                    f"Google Ads drill-down order: "
                    f"1) Keywords — pause if: spend >$35 + 0 HubSpot leads (14d), OR CPL >$80 + 1+ HubSpot leads (14d). "
                    f"2) Ad Groups — if >=50% of keywords flagged, pause the group. "
                    f"3) Campaign — pause only if all ad groups are underperforming."
                )
            elif drilldown_channel_type == "social":
                note = (
                    f"CPQL ${r.cpql:.2f} + CPL ${r.cpl:.2f} above threshold for {days} days. "
                    f"Social drill-down order: "
                    f"1) Ads — identify highest-CPL / zero-lead ads and pause them. "
                    f"2) Ad Sets — if majority of ads in an ad set are bad, pause the ad set. "
                    f"3) Campaign — pause only if all ad sets are underperforming."
                )
            else:
                note = (
                    f"CPQL ${r.cpql:.2f} + CPL ${r.cpl:.2f} above threshold for {days} days. "
                    f"Analyse at ad/placement level before touching campaign."
                )

        elif roas_override and cpql_z in ("warning", "pause"):
            action = "optimize"
            note   = (f"ROAS {roas:.2f} >= {ROAS_GOOD} — revenue covering spend. "
                      f"CPQL ${r.cpql:.2f} above target but justified. "
                      f"Optimize qual rate to improve further.")

        elif cpql_z in ("scale", "ok") and cpl_z in ("scale", "ok"):
            # Scale: CPQL ≤ $95 AND ROAS > 0.8 (both required)
            if SCALE_REQUIRES_ROAS and roas == 0:
                action = "monitor"
                note   = (f"CPQL ${r.cpql:.2f} acceptable but no deal revenue attributed yet. "
                          f"Scale once ROAS > {ROAS_GOOD} is confirmed.")
            elif SCALE_REQUIRES_ROAS and not roas_override:
                action = "monitor"
                note   = (f"CPQL ${r.cpql:.2f} acceptable but ROAS {roas:.2f} < {ROAS_GOOD}. "
                          f"Do not scale until revenue covers spend.")
            else:
                action = "scale"
                note   = (f"CPQL ${r.cpql:.2f} <= $95 and ROAS {roas:.2f} > {ROAS_GOOD}. "
                          f"Scale: raise budget 25%.")

        elif cpql_z in ("scale", "ok") and cpl_z in ("scale", "ok", "warning"):
            action = "monitor"
            note   = f"CPQL ${r.cpql:.2f} acceptable. Monitor CPL ${r.cpl:.2f}."

        elif cpql_z == "warning":
            action = "optimize"
            note   = (f"CPQL ${r.cpql:.2f} in warning zone (>${CPQL_ACCEPTABLE}). "
                      f"Qual rate {qr:.1f}% (target {QUAL_RATE_TARGET*100:.0f}%). "
                      f"Investigate audience/keyword quality before scaling.")

        elif cpql_z == "pause":
            if r.cpql and r.cpql > CPQL_WARNING * 3:
                action = "pause"
                note   = (f"CPQL ${r.cpql:.2f} is {r.cpql/CPQL_WARNING:.1f}x the warning threshold. "
                          f"Qual rate {qr:.1f}%. Pause and investigate.")
            else:
                action = "optimize"
                note   = (f"CPQL ${r.cpql:.2f} in pause zone. Qual rate {qr:.1f}%. "
                          f"Review audience, creatives, and landing page before pausing.")

        elif cpql_z == "no_data":
            if cpl_z == "pause":
                action = "optimize"
                note   = f"No qualified leads yet. CPL ${r.cpl:.2f} in pause zone — check HubSpot attribution."
            else:
                action = "monitor"
                note   = "No qualified leads yet — check HubSpot UTM attribution for this campaign."
        else:
            action = "monitor"
            note   = f"CPQL {cpql_z}, CPL {cpl_z}."

        if junk_leads:
            note += (f" WARNING: CPL ${r.cpl:.2f} looks like scale but qual rate is only "
                     f"{qr:.1f}% — leads are junk. Do not scale on CPL alone.")

        if roas_override:
            note += f" (ROAS {roas:.2f} — revenue covering spend)"

        # ── Pause-precedence guard ─────────────────────────────────────────────
        # Confirmed rule (2026-05-17): campaign-level PAUSE is forbidden as long
        # as surgical cleanup hasn't happened first. The surgical surface is
        # CHANNEL-DEPENDENT:
        #   - Social (meta, snapchat, tiktok): pause bad ADS first
        #   - Search (google_ads, microsoft_ads): pause bad KEYWORDS + review LP
        if action == "pause":
            camp_id = str(getattr(r, "campaign_id", "") or "")
            channel = (getattr(r, "channel", "") or "").lower()

            if channel in ("meta", "snapchat", "tiktok"):
                bad_ads = _ad_candidates.get(camp_id, [])
                if bad_ads:
                    bad_ads = sorted(
                        bad_ads,
                        key=lambda a: (
                            0 if "zero_conv" in a["reasons"] else
                            1 if "high_cpl"  in a["reasons"] else 2,
                            -a["spend"],
                        ),
                    )[:5]
                    ad_list = "; ".join(
                        f"{a['ad_name'][:40]} (${a['spend']:.0f} spend, "
                        f"{'+'.join(a['reasons'])}, {a['days']}d)"
                        for a in bad_ads
                    )
                    note = (f"[PAUSE BLOCKED — ad-level cleanup first] "
                            f"Campaign hit pause zone but has {len(_ad_candidates[camp_id])} "
                            f"ad(s) eligible for ad-level pause. Pause these first, "
                            f"then re-evaluate: {ad_list}")
                    action = "drilldown"

            elif channel in ("google_ads", "microsoft_ads"):
                bad_kws = _kw_candidates.get(camp_id, [])
                # Even with no flagged keywords, the LP review is mandatory before
                # campaign-pause on search channels — block and route to drilldown.
                if bad_kws:
                    bad_kws = sorted(
                        bad_kws,
                        key=lambda k: (
                            0 if "zero_conv" in k["reasons"] else 1,
                            -k["spend"],
                        ),
                    )[:5]
                    kw_list = "; ".join(
                        f"{k['keyword'][:35]} in {k['adgroup'][:25]} "
                        f"(${k['spend']:.0f}, {'+'.join(k['reasons'])}, {k['days']}d)"
                        for k in bad_kws
                    )
                    note = (f"[PAUSE BLOCKED — keyword cleanup first] "
                            f"Search campaign hit pause zone but has {len(_kw_candidates[camp_id])} "
                            f"keyword(s) eligible for pause. Pause these AND review "
                            f"the destination LP before campaign-pause: {kw_list}")
                else:
                    note = (f"[PAUSE BLOCKED — LP review required] "
                            f"Search campaign hit pause zone with no keyword-level "
                            f"candidates flagged. Before campaign-pause, manually "
                            f"visit the destination landing page: confirm it loads, "
                            f"form submits, message matches keyword intent. LP issue "
                            f"≠ campaign issue.")
                action = "drilldown"

        # Edit-age guard: if last edit < MIN_DAYS_SINCE_EDIT, too early to act
        if action in ("optimize", "pause") and days_since_edit < MIN_DAYS_SINCE_EDIT:
            note = (f"[HOLD — edited {days_since_edit}d ago, need ≥{MIN_DAYS_SINCE_EDIT}d] " + note)
            action = "monitor"  # downgrade; recheck once edit has had time to show results

        # ── Alternatives considered ────────────────────────────────────────────
        # For pause candidates: compute whether a budget reduction would bring
        # CPQL into the acceptable range instead of a full pause.
        # For scale candidates: validate the campaign has spending momentum.
        alt_budget_cut_pct: int | None = None
        alt_recommendation: str | None = None

        if action == "pause" and r.sqls and r.sqls > 0 and r.cpql and r.spend:
            # How much spend reduction would get CPQL to CPQL_ACCEPTABLE?
            # Assumes same SQL count at lower spend (conservative).
            target_spend  = CPQL_ACCEPTABLE * int(r.sqls)
            cut_pct       = round((1 - target_spend / float(r.spend)) * 100)
            if 10 <= cut_pct <= 55:
                alt_budget_cut_pct = cut_pct
                alt_recommendation = (
                    f"Budget reduction of -{cut_pct}% (${float(r.spend):.0f} → "
                    f"${target_spend:.0f} total over window) could bring CPQL to "
                    f"~${CPQL_ACCEPTABLE} if SQL count holds. "
                    f"Recommended: cut budget first, pause only if CPQL doesn't improve."
                )
            else:
                alt_recommendation = (
                    f"Budget cut alone won't fix this (would require >{55}% reduction). "
                    f"Root cause is likely audience/creative quality. Full pause recommended."
                )

        if action == "scale":
            # Flag if qual rate is solid — scale with confidence note
            if qr >= QUAL_RATE_TARGET * 100:
                alt_recommendation = (
                    f"Qual rate {qr:.0f}% ≥ target — scale is well-supported. "
                    f"+25% budget raise likely to compound qualified leads."
                )
            else:
                alt_recommendation = (
                    f"Qual rate {qr:.0f}% is below target ({QUAL_RATE_TARGET*100:.0f}%). "
                    f"Scale cautiously — CPQL is good but lead quality may slip under more volume."
                )

        # Qflavours note
        if is_qflavours and QFLAVOURS_PIPELINE_CHECK:
            note += " Verify Qflavours leads pipeline in HubSpot has data for this campaign."

        findings.append({
            "channel":        r.channel,
            "campaign":       r.campaign_name,
            "account_id":     r.account_id,
            "status":         r.status,
            "days":           days,
            "date_from":      since,
            "date_to":        today.isoformat(),
            "last_updated":   last_updated_date.isoformat() if last_updated else "unknown",
            "days_since_edit": days_since_edit,
            "spend":          round(r.spend or 0, 2),
            "hs_leads":       int(r.hs_leads or 0),
            "sqls":           int(r.sqls or 0),
            "cpl":            round(r.cpl, 2) if r.cpl else None,
            "cpql":           round(r.cpql, 2) if r.cpql else None,
            "qual_rate":      round(qr, 1),
            "roas":           round(roas, 2),
            "cpql_zone":      cpql_z,
            "cpl_zone":       cpl_z,
            "junk_leads":           junk_leads,
            "is_awareness":         False,
            "is_qflavours":         is_qflavours,
            "roas_override":        roas_override,
            "needs_drilldown":        needs_drilldown,
            "drilldown_channel_type": drilldown_channel_type,
            "action":                 action,
            "note":                   note,
            "alt_budget_cut_pct":     alt_budget_cut_pct,
            "alt_recommendation":     alt_recommendation,
        })

    return findings


def print_health_report(findings: list[dict]) -> None:
    """Pretty-print a health report to stdout."""
    ZONE_ICON   = {"scale": "[SCALE]", "ok": "[OK]", "warning": "[WARN]",
                   "pause": "[PAUSE]", "no_data": "[N/A]"}
    ACTION_ICON = {"scale": "^", "monitor": "~", "optimize": "!", "pause": "X"}
    for f in findings:
        cpql_s = f"${f['cpql']:.2f}" if f["cpql"] else "N/A"
        cpl_s  = f"${f['cpl']:.2f}"  if f["cpl"]  else "N/A"
        print(
            f"{ACTION_ICON.get(f['action'], '?')} [{f['action'].upper():8s}] "
            f"{f['channel']:<12} | {f['campaign'][:45]:<45} | "
            f"spend=${f['spend']:>8.0f} | leads={f['hs_leads']:>4} sqls={f['sqls']:>3} | "
            f"CPQL={cpql_s:>8} {ZONE_ICON.get(f['cpql_zone'],''):8s} | "
            f"CPL={cpl_s:>7} {ZONE_ICON.get(f['cpl_zone'],''):8s} | "
            f"qual={f['qual_rate']:>5.1f}%"
        )


if __name__ == "__main__":
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else DAYS_FOR_PAUSE_DECISION
    findings = audit_campaign_health(days=days)
    print(f"\nCampaign health — last {days} days "
          f"(cost: channel | leads: HubSpot Lead Module)\n{'='*120}")
    print_health_report(findings)
    print(f"\n{len(findings)} campaigns evaluated.")
    scale   = [f for f in findings if f["action"] == "scale"]
    pause   = [f for f in findings if f["action"] == "pause"]
    opt     = [f for f in findings if f["action"] == "optimize"]
    print(f"  Scale: {len(scale)}  |  Optimize: {len(opt)}  |  Pause: {len(pause)}")
