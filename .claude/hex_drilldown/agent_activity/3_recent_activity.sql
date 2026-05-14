-- ─────────────────────────────────────────────────────────────────────────────
-- Agent Activity — Recent Activity Feed
-- Last 100 meaningful agent actions, newest first.
-- Hex: Table with Date, Category, Channel, Campaign, Detail, Count, Status columns.
-- ─────────────────────────────────────────────────────────────────────────────

SELECT
  FORMAT_TIMESTAMP('%Y-%m-%d %H:%M', ts, 'Asia/Riyadh') AS ts_riyadh,
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
    ELSE role || '/' || action
  END                                        AS category,
  COALESCE(channel, '—')                     AS channel,
  COALESCE(campaign_name, '—')               AS campaign,
  action                                     AS raw_action,
  COALESCE(rows_affected, 1)                 AS count,
  status,
  ROUND(COALESCE(duration_s, 0), 1)          AS duration_s
FROM `angular-axle-492812-q4.qoyod_marketing.agent_activity_log`
WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
  AND status NOT IN ('failed', 'skipped')
  AND action NOT IN (
    -- exclude noisy infra-only actions
    'bq_cache_loaded', 'refresh_views', 'refresh_complete',
    'cadence_started', 'cadence_skipped_already_ran_today',
    'cadence_complete', 'refresh_hex_notebooks', 'data_quality_autoheal'
  )
ORDER BY ts DESC
LIMIT 115
