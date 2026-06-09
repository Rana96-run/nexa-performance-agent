---
name: Qoyod Performance Agent
description: Daily AI agent that pulls Google Ads/Meta/HubSpot data, sends to Claude for analysis, posts decisions to Slack for approval, then executes approved actions
type: project
originSessionId: 494a0794-05d3-4caa-bd1b-7c9a7f0a1b58
---
Building a Python performance marketing agent for Qoyod (Saudi B2B cloud accounting SaaS).

**Why:** Automate daily performance checks across Google Ads, Meta, Snapchat, TikTok, and HubSpot — agent proposes actions, humans approve via Slack, then it executes.

**How to apply:** All code lives in D:/Nexa Performance Agent. The 4 MD files in md_files/ are the Claude system prompt (decision rules, thresholds, channel logic). Nothing executes without Slack approval. Asana tasks are always created. KPI thresholds: CPL pause > $30 (4 days), CPQL pause > $80 (4 days). SQL = Contact module only, never Lead module.
