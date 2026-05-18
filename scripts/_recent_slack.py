import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from config import SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, SLACK_CHANNEL_NOTIFY, SLACK_CHANNEL_APPROVAL
from slack_sdk import WebClient
c = WebClient(token=SLACK_BOT_TOKEN)

for ch_name, ch_id in [("notify", SLACK_CHANNEL_NOTIFY),
                        ("approval", SLACK_CHANNEL_APPROVAL),
                        ("main", SLACK_CHANNEL_ID)]:
    if not ch_id:
        print(f"--- {ch_name}: (not configured) ---\n")
        continue
    print(f"=== {ch_name} ({ch_id}) ===")
    try:
        h = c.conversations_history(channel=ch_id, limit=2)
        for m in h["messages"]:
            text = m.get("text") or ""
            print(f"\nts={m['ts']}  bot={m.get('bot_id', '-')}  length={len(text)} chars")
            print("-" * 60)
            print(text[:2000])
            print("-" * 60)
    except Exception as e:
        print(f"  error: {str(e)[:200]}")
    print()
