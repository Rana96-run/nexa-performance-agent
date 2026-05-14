-- ─────────────────────────────────────────────────────────────────────────────
-- Agent Activity Heatmap — GitHub-style contribution calendar
-- One row per (day, category). Hex renders this as a heatmap with category
-- on the Y-axis and date on the X-axis, intensity = count.
--
-- Category taxonomy (mirrors the 8 dashboard metrics):
--   Campaigns Created   | campaign_created
--   Keywords Added      | keyword_candidates_queued_for_weekly_review / launch (keyword_management)
--   Keywords Paused     | keywords_paused
--   Negatives Added     | negative_keywords_added
--   Ads Paused          | pause_task_created / junk_leads_task_created / ads_paused
--   Asana Tasks         | asana_task_created
--   Slack Messages      | posted_slack_digest / slack_summary_posted / post_weekly_summary
--   Approvals           | posted_approvals_digest / approval_requested
-- ─────────────────────────────────────────────────────────────────────────────

WITH raw AS (
  SELECT
    DATE(ts, 'Asia/Riyadh') AS day,
    action,
    role,
    COALESCE(rows_affected, 1) AS cnt
  FROM `angular-axle-492812-q4.qoyod_marketing.agent_activity_log`
  WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 91 DAY)
    AND status NOT IN ('failed', 'skipped')
),

categorised AS (
  SELECT
    day,
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
  FROM raw
)

SELECT
  day,
  category,
  SUM(cnt) AS count
FROM categorised
WHERE category IS NOT NULL
GROUP BY day, category
ORDER BY day DESC, category
