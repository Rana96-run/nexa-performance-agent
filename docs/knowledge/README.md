# Knowledge Base

Technical reference extracted from resolved issues, sessions, and code reviews.
This is NOT behavioral memory — it is the searchable record of what was discovered and why.

## Structure

```
docs/knowledge/
  findings/      API traps, schema facts, data anomalies, bug root causes
  learnings/     What worked / didn't on tasks; generalizable patterns
  actions/       Executed decisions with expected + actual outcomes
  project_*.md   Project context files (architecture overviews, credentials layout)
```

## How to use

- **Before wiring a new API call**: grep `findings/` for the platform name
- **Before recommending a campaign action**: check `learnings/` for regression vs drain patterns
- **Before rerunning a collector**: check `actions/` for prior backfill outcomes
- **Auto-memory (`memory/feedback_*.md`)** holds behavior rules only — read those for HOW to act, read here for WHAT is true about the system

## How to add a new item

Follow the naming and frontmatter from any existing file in the matching subfolder.
Update this README only if the folder structure changes.
