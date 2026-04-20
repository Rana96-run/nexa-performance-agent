"""Inspects a Miro board to understand its structure before cloning."""
import os
import sys
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
TOKEN = os.getenv("MIRO_ACCESS_TOKEN")
BOARD_ID = sys.argv[1] if len(sys.argv) > 1 else "uXjVGk7YbXE="

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
BASE = f"https://api.miro.com/v2/boards/{BOARD_ID}"

print(f"Inspecting board: {BOARD_ID}\n")
info = requests.get(BASE, headers=HEADERS, timeout=30)
print("Board info:", info.status_code)
if info.ok:
    d = info.json()
    print(f"  name: {d.get('name')}")
    print(f"  desc: {d.get('description')}")

for kind in ("items",):
    cursor = None
    total = 0
    types = {}
    samples = []
    while True:
        url = f"{BASE}/{kind}?limit=50" + (f"&cursor={cursor}" if cursor else "")
        r = requests.get(url, headers=HEADERS, timeout=30)
        if not r.ok:
            print(f"  {kind}: {r.status_code} {r.text[:200]}")
            break
        j = r.json()
        for it in j.get("data", []):
            t = it.get("type")
            types[t] = types.get(t, 0) + 1
            total += 1
            if True:
                samples.append({
                    "type": t,
                    "id": it.get("id"),
                    "data": it.get("data"),
                    "style": it.get("style"),
                    "position": it.get("position"),
                    "geometry": it.get("geometry"),
                })
        cursor = j.get("cursor")
        if not cursor:
            break
    out = Path(__file__).parent / "miro_dump.json"
    out.write_text(json.dumps(samples, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nTotal items: {total}")
    print(f"By type: {types}")
    print(f"Wrote {out}")
