-- ─────────────────────────────────────────────────────────────────────────────
-- Agent Activity — Contributions by Category (bar chart per category)
-- Shows total count + breakdown for each of the 8 metrics.
-- Hex: Table or Bar Chart. One row per category.
-- ─────────────────────────────────────────────────────────────────────────────

WITH base AS (
  SELECT
    action,
    role,
    status,
    channel,
    COALESCE(rows_affected, 1) AS cnt,
    DATE(ts, 'Asia/Riyadh')    AS day
  FROM `angular-axle-492812-q4.qoyod_marketing.agent_activity_log`
  WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
    AND status NOT IN ('failed', 'skipped')
),

categorised AS (
  SELECT
    day,
    channel,
    CASE
      WHEN action = 'campaign_created'
        THEN 'Campaigns Created'
      WHEN action IN ('launch', 'keyword_candidates_queued_for_weekly_review')
           AND role = 'keyword_management'
        THEN 'Keywords Added'
      WHEN action = 'keywords_paused'
        THEN 'Keywords Paused'
      WHEN action = 'negative_keywords_added'
        THEN 'Negatives Added'
      WHEN action IN ('pause_task_created', 'junk_leads_task_created', 'ads_paused')
        THEN 'Ads Paused'
      WHEN action = 'asana_task_created'
        THEN 'Asana Tasks'
      WHEN action IN ('posted_slack_digest', 'slack_summary_posted', 'post_weekly_summary',
                      'nightly_audit_complete')
        THEN 'Slack Messages'
      WHEN action IN ('posted_approvals_digest', 'approval_requested')
        THEN 'Approvals'
    END AS category,
    cnt
  FROM base
)

SELECT
  category,
  SUM(cnt)                                                       AS total_90d,
  SUM(CASE WHEN day >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 30 DAY)
               THEN cnt ELSE 0 END)                              AS total_30d,
  SUM(CASE WHEN day >= DATE_SUB(CURRENT_DATE('Asia/Riyadh'), INTERVAL 7 DAY)
               THEN cnt ELSE 0 END)                              AS total_7d,
  COUNT(DISTINCT day)                                            AS active_days_90d
FROM categorised
WHERE category IS NOT NULL
GROUP BY category
ORDER BY total_90d DESC
