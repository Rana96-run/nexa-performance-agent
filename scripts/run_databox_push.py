"""
Temporary runner: writes Railway's GOOGLE_APPLICATION_CREDENTIALS_JSON to a
temp file so the BQ client uses the correct service account, then runs
push_custom_metrics(). Run via: railway run python scripts/_databox_push_runner.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── Fix BQ credentials ────────────────────────────────────────────────────────
creds_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON", "")
if creds_json:
    tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tf.write(creds_json)
    tf.close()
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tf.name
    print(f"[runner] Using Railway SA: {tf.name[:30]}…", flush=True)
else:
    print("[runner] GOOGLE_APPLICATION_CREDENTIALS_JSON not set — using local cert", flush=True)

print(f"[runner] DATABOX_TOKEN present: {bool(os.environ.get('DATABOX_TOKEN'))}", flush=True)

# ── Run push ──────────────────────────────────────────────────────────────────
from collectors.databox_pusher import push_custom_metrics  # noqa: E402

days = int(sys.argv[1]) if len(sys.argv) > 1 else 90
print(f"[runner] Pushing {days} days…", flush=True)
n = push_custom_metrics(days=days)
print(f"[runner] Done — {n:,} total metric values pushed", flush=True)
