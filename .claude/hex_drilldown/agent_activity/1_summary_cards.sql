-- ─────────────────────────────────────────────────────────────────────────────
-- Agent Activity — Summary Cards (30d + 7d totals for each of the 8 metrics)
-- Returns a single row. Hex renders each column as a KPI metric card.
--
-- Hex: use "Metric" display type, one column per card.
-- ─────────────────────────────────────────────────────────────────────────────

WITH base AS (
  SELECT
    action,
    role,
    status,
    COALESCE(rows_affected, 1) AS cnt,
    DATE(ts, 'Asia/Riyadh')    AS day
  FROM `angular-axle-492812-q4.qoyod_marketing.agent_activity_log`
  WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
    AND status NOT IN ('failed', 'skipped')
)

SELECT
  -- Campaigns Created
  SUM(CASE WHEN action = 'campaign_created' THEN cnt ELSE 0 END)
    AS campaigns_created_30d,

  -- Keywords Added (expansion candidates queued or approved for addition)
  SUM(CASE WHEN action IN ('launch', 'keyword_candidates_queued_for_weekly_review')
                AND role = 'keyword_management' THEN cnt ELSE 0 END)
    AS keywords_added_30d,

  -- Keywords Paused (auto-paused non-converting)
  SUM(CASE WHEN action = 'keywords_paused' THEN cnt ELSE 0 END)
    AS keywords_paused_30d,

  -- Negatives Added (direct-executed, no approval)
  SUM(CASE WHEN action = 'negative_keywords_added' THEN cnt ELSE 0 END)
    AS negatives_added_30d,

  -- Ads / Campaigns Paused (pending approval or executed)
  SUM(CASE WHEN action IN ('pause_task_created', 'junk_leads_task_created', 'ads_paused')
                THEN cnt ELSE 0 END)
    AS ads_paused_30d,

  -- Asana Tasks Created
  SUM(CASE WHEN action = 'asana_task_created' THEN 1 ELSE 0 END)
    AS asana_tasks_30d,

  -- Slack Messages Sent (daily digest + weekly summary)
  SUM(CASE WHEN action IN ('posted_slack_digest', 'slack_summary_posted',
                            'post_weekly_summary', 'nightly_audit_complete')
                THEN 1 ELSE 0 END)
    AS slack_messages_30d,

  -- Slack Approval Messages
  SUM(CASE WHEN action IN ('posted_approvals_digest', 'approval_requested')
                THEN 1 ELSE 0 END)
    AS slack_approvals_30d

FROM base
