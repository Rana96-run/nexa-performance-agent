"""
sync_railway_env.py — pipe `railway variables --json` into this script
to update the local .env with production Railway credentials.

Usage:
    railway variables --json | python scripts/sync_railway_env.py

Or directly:
    python scripts/sync_railway_env.py           (reads railway_vars.json if present)
"""
import json, re, sys, pathlib

# Keys to pull from Railway into local .env
SYNC_KEYS = [
    "LI_ACCESS_TOKEN", "LI_REFRESH_TOKEN", "LI_AD_ACCOUNT_URN",
    "TIKTOK_ACCESS_TOKEN", "TIKTOK_REFRESH_TOKEN",
    "MS_REFRESH_TOKEN",
    "META_ACCESS_TOKEN",
    "GOOGLE_ADS_REFRESH_TOKEN",
    "SNAP_ACCESS_TOKEN", "SNAP_REFRESH_TOKEN",
]

ENV_PATH = pathlib.Path(__file__).parent.parent / ".env"


def sync(rvars: dict) -> list[str]:
    env_text = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""

    updated = []
    for key in SYNC_KEYS:
        if key not in rvars:
            continue
        val = str(rvars[key])
        pattern     = rf"^{re.escape(key)}=.*$"
        replacement = f"{key}={val}"
        if re.search(pattern, env_text, re.MULTILINE):
            env_text = re.sub(pattern, replacement, env_text, flags=re.MULTILINE)
        else:
            env_text = env_text.rstrip("\n") + f"\n{replacement}\n"
        updated.append(key)

    ENV_PATH.write_text(env_text, encoding="utf-8")
    return updated


def main():
    raw = sys.stdin.read().strip() if not sys.stdin.isatty() else ""
    if not raw:
        # Fallback: read from cached file
        cache = pathlib.Path("/tmp/railway_vars.json")
        if cache.exists():
            raw = cache.read_text()
        else:
            print("[sync-env] No input — pipe `railway variables --json` into this script")
            sys.exit(1)

    try:
        rvars = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[sync-env] JSON parse error: {e}")
        sys.exit(1)

    updated = sync(rvars)
    if updated:
        print(f"[sync-env] ✓ Synced {len(updated)} key(s): {', '.join(updated)}")
    else:
        print("[sync-env] No matching keys found in Railway vars")


if __name__ == "__main__":
    main()
