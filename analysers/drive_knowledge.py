"""
analysers/drive_knowledge.py
=============================
Lets the agent LEARN from files shared in Google Drive — not just list them.

The drive_reader gives raw access; this module turns Drive content into
context the Claude roles can reason over:

  1. `index_shared_drive()` — walks the entire visible tree, captures
     {path, id, mimeType, modifiedTime, size} into memory/_drive_index.json.
     Run nightly so role prompts always reference the latest assets.

  2. `read_text_files(folder_id)` — pulls plain-text content from Google
     Docs / .txt / .md / .csv inside a folder so it can be appended to a
     role prompt as reference material.

  3. `summarise_for_role(role_name)` — returns a short markdown bullet
     list of relevant assets for a given role (e.g. the strategist gets
     creative briefs + brand guidelines; the analyst gets benchmark CSVs).

Used by:
  - claude/reporter.py — adds Drive index summary to the daily report
  - claude/manager.py — appends relevant assets to each role's system prompt
  - main.run_cadence — refreshes the index once per night before role calls
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from collectors.drive_reader import (
    DEFAULT_FOLDER_ID, list_folder, walk, read_text,
)

INDEX_PATH = Path(__file__).parent.parent / "memory" / "_drive_index.json"

# File types we can extract text from (everything else stays as a reference link)
TEXT_LIKE_MIMES = {
    "application/vnd.google-apps.document",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/vnd.google-apps.spreadsheet",
}

# Maximum text we'll inline per file before truncating (token budget)
MAX_TEXT_CHARS = 6000

# Folders categorised by which role they help most.  Folder names matched
# loosely (case-insensitive substring).  Update as the team adds new folders.
ROLE_FOLDER_HINTS: dict[str, list[str]] = {
    "media_buyer": [
        "campaign", "ad spend", "budget", "performance",
        "qflavours", "qbookkeeping", "e-invoice",
    ],
    "paid_media_analyst": [
        "analysis", "benchmark", "competitor", "looker", "report",
        "social media analysis",
    ],
    "paid_media_strategist": [
        "media planning", "brand", "branding", "playbook", "voice",
        "logo", "qoyod banding", "creative",
    ],
    "creative_brief_writer": [
        "ai creative", "ready to publish", "under review", "logos",
    ],
}


def _flatten(parents_chain: list[str], name: str) -> str:
    return "/".join(parents_chain + [name])


def index_shared_drive(root_folder_id: str = DEFAULT_FOLDER_ID,
                       max_items: int = 5000) -> dict:
    """
    Walk every folder visible to the service account and write an index file
    so role prompts can cheaply reference Drive assets without re-querying
    the API on every run.
    """
    items: list[dict] = []
    folders_seen = 0

    # Walk top-level visible items rather than only one folder, so files
    # shared individually with the service account are included.
    from collectors.drive_reader import _client
    svc = _client()

    cursor = None
    while True:
        kwargs = dict(
            q="trashed = false",
            fields="nextPageToken, files(id,name,mimeType,modifiedTime,size,parents)",
            pageSize=200,
            orderBy="modifiedTime desc",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        if cursor:
            kwargs["pageToken"] = cursor
        resp = svc.files().list(**kwargs).execute()
        for f in resp.get("files", []):
            if f["mimeType"] == "application/vnd.google-apps.folder":
                folders_seen += 1
            items.append({
                "id":           f["id"],
                "name":         f["name"],
                "mime":         f["mimeType"],
                "modified":     f.get("modifiedTime", ""),
                "size":         f.get("size"),
                "parents":      f.get("parents") or [],
            })
            if len(items) >= max_items:
                break
        cursor = resp.get("nextPageToken")
        if not cursor or len(items) >= max_items:
            break

    # Build a parent→children map so we can resolve breadcrumb paths
    by_id = {it["id"]: it for it in items}
    def path_for(it: dict, depth: int = 0) -> str:
        if depth > 8 or not it.get("parents"):
            return it["name"]
        parent_id = it["parents"][0]
        parent = by_id.get(parent_id)
        if not parent:
            return it["name"]
        return path_for(parent, depth + 1) + "/" + it["name"]
    for it in items:
        it["path"] = path_for(it)

    index = {
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "root":       root_folder_id,
        "items":      items,
        "totals":     {
            "items":   len(items),
            "folders": folders_seen,
            "files":   len(items) - folders_seen,
        },
    }

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(f"[drive-knowledge] Indexed {len(items)} items "
          f"({folders_seen} folders, {len(items) - folders_seen} files) "
          f"-> {INDEX_PATH.name}")
    return index


def load_index() -> Optional[dict]:
    """Return the cached index, or None if it hasn't been built yet."""
    if not INDEX_PATH.exists():
        return None
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


# ─── Role-targeted views ─────────────────────────────────────────────────────

def _matches_any(name: str, hints: Iterable[str]) -> bool:
    n = (name or "").lower()
    return any(h.lower() in n for h in hints)


def assets_for_role(role: str, limit: int = 25) -> list[dict]:
    """
    Return Drive items relevant to a given role, ranked by recency.
    Hints come from ROLE_FOLDER_HINTS — the asset's path is matched against
    the role's keyword list.
    """
    idx = load_index()
    if not idx:
        return []
    hints = ROLE_FOLDER_HINTS.get(role, [])
    if not hints:
        return []
    matched = [
        it for it in idx["items"]
        if it["mime"] != "application/vnd.google-apps.folder"
        and _matches_any(it.get("path", ""), hints)
    ]
    matched.sort(key=lambda it: it.get("modified", ""), reverse=True)
    return matched[:limit]


def summarise_for_role(role: str) -> str:
    """Short markdown summary of Drive assets pertinent to a role.
    Plug the output into the role's system prompt so Claude knows what's
    available and references it by name.
    """
    items = assets_for_role(role)
    if not items:
        return ""
    lines = [
        f"## Drive context (auto-indexed; {len(items)} most-recent relevant files)",
        "",
        "These assets are visible to you via Google Drive. Reference them by name when relevant:",
        "",
    ]
    for it in items:
        kind = it["mime"].split(".")[-1].split("/")[-1][:14]
        date = (it.get("modified") or "")[:10]
        lines.append(f"- `{kind}` · {date} · **{it['name']}**  — `{it.get('path', '')}`")
    return "\n".join(lines)


# ─── Text extraction (for deep-context use cases) ─────────────────────────────

def read_text_files_under(folder_path_substring: str, max_files: int = 5) -> list[dict]:
    """
    Find the most recent text-extractable files whose path matches the given
    substring, then pull each file's content (truncated to MAX_TEXT_CHARS).
    Useful when the strategist needs to actually read a brief.
    """
    idx = load_index()
    if not idx:
        return []
    candidates = [
        it for it in idx["items"]
        if it["mime"] in TEXT_LIKE_MIMES
        and folder_path_substring.lower() in (it.get("path") or "").lower()
    ]
    candidates.sort(key=lambda it: it.get("modified", ""), reverse=True)
    out = []
    for it in candidates[:max_files]:
        try:
            text = read_text(it["id"])
            out.append({
                "name": it["name"],
                "path": it["path"],
                "modified": it["modified"],
                "text": text[:MAX_TEXT_CHARS],
                "truncated": len(text) > MAX_TEXT_CHARS,
            })
        except Exception as e:
            print(f"[drive-knowledge] read failed for {it['name']}: {e}")
    return out


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "index"
    if cmd == "index":
        index = index_shared_drive()
        print(f"  totals: {index['totals']}")
    elif cmd == "summary":
        role = sys.argv[2] if len(sys.argv) > 2 else "media_buyer"
        print(summarise_for_role(role) or f"(no Drive context for role={role})")
    elif cmd == "search":
        sub = sys.argv[2] if len(sys.argv) > 2 else "campaign"
        idx = load_index()
        if not idx:
            print("Index not built yet. Run: python analysers/drive_knowledge.py index")
            sys.exit(1)
        for it in idx["items"][:200]:
            if sub.lower() in (it.get("path") or "").lower():
                print(f"  {it['mime'].split('/')[-1]:24s}  {it['path']}")
    else:
        print("Usage: python analysers/drive_knowledge.py [index|summary <role>|search <substring>]")
