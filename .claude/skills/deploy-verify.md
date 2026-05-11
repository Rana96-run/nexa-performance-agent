# deploy-verify — confirm code is on GitHub and Railway before calling anything done

## Purpose

Before declaring any code change complete, verify the full chain:
1. Local changes committed
2. GitHub has the latest commit
3. Railway deployed FROM that commit (not an older snapshot)
4. Routes / endpoints actually behave as expected

Skipping any of these steps means Railway may be running stale code and the
change is not actually live.

## When to invoke this skill

- After any `git push` + `railway up` before reporting "done" to the user
- Whenever a deployed change isn't behaving as expected
- Before debugging why a fix isn't working (confirm it's even deployed first)

## Steps

### 0. Pull before touching anything (non-negotiable)

```bash
cd "D:\Nexa Performance Agent"
git pull origin main
```

Never make changes on a stale local branch. If there are conflicts, resolve them first.

### 1. Confirm local is clean and pushed

```bash
cd "D:\Nexa Performance Agent"
git status                          # must show "nothing to commit"
git log --oneline -3                # note the latest commit hash
git log --oneline origin/main -1    # must match local HEAD
```

If local is ahead: `git push` first.

### 2. Confirm Railway deployed the latest commit

```bash
railway logs --tail 20 2>&1 | grep -E "Starting Container|Deploying|Build|commit"
```

Look for "Starting Container" AFTER the git push timestamp.
If Railway shows an older startup time, the new deploy hasn't landed yet — wait 60–90s and re-check.

### 3. Health check

```bash
curl -s https://nexa-performance-agent.up.railway.app/health
# Expected: {"status":"ok"}
```

If health fails, check `railway logs --tail 30` for import errors or crashes.

### 4. Smoke-test the specific change

For route changes (redirects, new endpoints):
```bash
curl -sv "https://nexa-performance-agent.up.railway.app/<route>" 2>&1 | grep -E "< HTTP|< [Ll]ocation"
# Expected: 302 Found + correct Location header
```

For env var changes (new secrets, updated URLs):
```bash
railway variables 2>&1 | grep <VAR_NAME>
# Confirm the value matches what you set
```

For code logic changes, check Railway logs after triggering the relevant action:
```bash
railway logs --tail 30 2>&1 | grep -E "<keyword from your change>"
```

### 5. If Railway is still on old code

Railway deploys from GitHub when connected via GitHub integration.
`railway up` uploads a local snapshot — but if Railway is also connected to
GitHub, the GitHub deploy may override it.

Force a clean GitHub-triggered deploy:
```bash
git commit --allow-empty -m "chore: force Railway redeploy"
git push
# Wait 90–120s for build + container swap
```

Then repeat steps 3 and 4.

### 6. Only report "done" after step 4 passes — NEVER before

**Rule: "done" is not a feeling. It is a verified, observed result.**

Before saying "done", "fixed", "numbers are correct", or any equivalent:
1. The code change is committed and pushed ✅
2. The output/data was **actually queried or observed** and matches the target ✅
3. The end-to-end path was tested — not just "the code looks right" ✅

If any of these three are missing, the correct statement is:
- "Running now — will confirm" (not "done")
- "BQ updated — Hex needs a manual refresh" (not "numbers are correct in Hex")
- "Fix deployed — smoke test pending" (not "fixed")

**Never claim a number is correct without having queried it.**
**Never claim Hex shows X without having seen Hex show X.**
**Never say "done" when the verify step is still running or hasn't run.**

This rule exists because on 2026-05-11 the word "done" was said 3 times for
the same fix before it was actually working end-to-end. Each premature "done"
cost debugging time and eroded trust.

Never tell the user a change is live until the smoke-test confirms it.
If the smoke-test fails after two deploy attempts, diagnose before retrying:
- Check if Railway GitHub integration is active (Railway dashboard → Settings → Source)
- Check if the env var is being read at request time vs module load time
- Check if a conflicting `railway up` snapshot is overriding the GitHub deploy

## Example: verifying a redirect route

```bash
# 1. Confirm pushed
git log --oneline origin/main -1
# → 1bf5792 fix: read DASHBOARD_DEST_URL at request time

# 2. Confirm Railway started after push
railway logs --tail 10 | grep "Starting Container"

# 3. Health
curl -s https://nexa-performance-agent.up.railway.app/health
# → {"status":"ok"}

# 4. Smoke-test redirect
curl -sv "https://nexa-performance-agent.up.railway.app/dashboard" 2>&1 | grep "< Location"
# → Location: https://app.hex.tech/019de9f2.../latest  ✅
```
