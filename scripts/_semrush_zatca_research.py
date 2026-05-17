"""Direct Semrush API pull — competitor paid keywords + keyword gaps +
ad copy + related-keyword expansion. Targeted at ZATCA Phase 2 research."""
import os
import csv
import io
import json
import sys
from pathlib import Path
from dotenv import load_dotenv
import httpx

load_dotenv()

KEY = os.getenv("SEMRUSH_API_KEY", "")
BASE = "https://api.semrush.com/"
DB   = "sa"  # Saudi Arabia
OUT  = Path(__file__).parent / "_semrush_zatca"
OUT.mkdir(exist_ok=True)


def parse_csv(text: str) -> list[dict]:
    if not text or text.startswith("ERROR"):
        return [{"error": text.strip()}]
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def call(label: str, params: dict, save: bool = True) -> list[dict]:
    params["key"] = KEY
    print(f"\n--- {label} ---")
    r = httpx.get(BASE, params=params, timeout=30)
    rows = parse_csv(r.text)
    if rows and "error" in rows[0]:
        print(f"  ERROR: {rows[0]['error']}")
        return rows
    print(f"  got {len(rows)} rows")
    if save and rows:
        (OUT / f"{label}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
    # Print first 5 as preview
    for r in rows[:5]:
        print(f"  {json.dumps(r, ensure_ascii=False)}")
    if len(rows) > 5:
        print(f"  ... +{len(rows)-5} more")
    return rows


# ── 1. Domain overview for each competitor in Saudi market ─────────────────
print("=" * 78)
print("1. DOMAIN OVERVIEW — Saudi paid+organic scale")
print("=" * 78)
for d in ["qoyod.com", "wafeq.com", "daftra.com", "rewaa.com"]:
    call(f"01_overview_{d.replace('.', '_')}", {
        "type": "domain_ranks",
        "domain": d,
        "database": DB,
        "export_columns": "Db,Dn,Rk,Or,Ot,Oc,Ad,At,Ac",
    })

# ── 2. Domain PAID keywords for each competitor (top 50 by traffic) ────────
print("\n" + "=" * 78)
print("2. PAID KEYWORDS — what each competitor BIDS on in Saudi")
print("=" * 78)
for d in ["wafeq.com", "daftra.com", "rewaa.com"]:
    call(f"02_paid_keywords_{d.replace('.', '_')}", {
        "type": "domain_adwords",
        "domain": d,
        "database": DB,
        "display_limit": 100,
        "display_sort": "tr_desc",  # by paid traffic descending
        "export_columns": "Ph,Po,Nq,Cp,Ur,Tr,Tc,Co,Nr,Td,Tg",
    })

# ── 3. Keyword gap — direct qoyod vs competitor analysis ──────────────────
print("\n" + "=" * 78)
print("3. KEYWORD GAP — qoyod vs Wafeq / Daftra / Rewaa (paid)")
print("=" * 78)
# 0 = qoyod, 1 = competitor, intent = paid
for comp in ["wafeq.com", "daftra.com", "rewaa.com"]:
    call(f"03_gap_qoyod_vs_{comp.replace('.', '_')}", {
        "type": "domain_domains",
        "domains": f"+|*|*|qoyod.com|+|*|*|{comp}",  # both have | absent = missing
        "database": DB,
        "display_limit": 100,
        "export_columns": "Ph,Nq,Cp,P0,P1",
    })

# ── 4. Related-keyword expansion from ZATCA Phase 2 seeds ─────────────────
print("\n" + "=" * 78)
print("4. RELATED KEYWORDS — expand from ZATCA seeds (volume + CPC)")
print("=" * 78)
seeds = [
    "zatca phase 2",
    "المرحلة الثانية للفاتورة الإلكترونية",
    "ربط الفاتورة الإلكترونية",
    "فاتورة إلكترونية",
    "هيئة الزكاة",
    "fatoora",
]
for seed in seeds:
    safe = seed.replace(" ", "_")[:40]
    call(f"04_related_{safe}", {
        "type": "phrase_related",
        "phrase": seed,
        "database": DB,
        "display_limit": 30,
        "export_columns": "Ph,Nq,Cp,Co,Kd",
    })

# ── 5. Keyword overview — volume + CPC for our priority adds list ─────────
print("\n" + "=" * 78)
print("5. KEYWORD OVERVIEW — volume + CPC for top-30 priority adds")
print("=" * 78)
priority = [
    "منصة فاتورة",
    "fatoora portal",
    "zatca phase 2",
    "zatca phase 2 integration",
    "zatca phase 2 requirements",
    "البرامج المحاسبية المعتمدة من هيئة الزكاة",
    "أفضل برنامج فاتورة إلكترونية للسعودية",
    "غرامة الفاتورة الإلكترونية",
    "تكامل المرحلة الثانية",
    "ربط هيئة الزكاة",
    "zatca integration",
    "zatca sdk",
    "REST API الفاتورة الإلكترونية",
    "كيف أربط الفاتورة الإلكترونية",
    "الفرق بين المرحلة الأولى والثانية",
    "فاتورة إلكترونية مطاعم",
    "فاتورة إلكترونية مقاولات",
    "wafeq",
    "daftra",
    "zoho saudi",
]
# batch-fetch — phrase_this supports semicolon-delim multi
joined = ";".join(priority)
call("05_priority_keyword_overview", {
    "type": "phrase_this",
    "phrase": joined,
    "database": DB,
    "export_columns": "Ph,Nq,Cp,Co,Kd",
})

# ── 6. Ad copies — what Wafeq + Daftra actually run ────────────────────────
print("\n" + "=" * 78)
print("6. AD COPIES — actual ad creative from Wafeq + Daftra")
print("=" * 78)
for d in ["wafeq.com", "daftra.com"]:
    call(f"06_ad_copies_{d.replace('.', '_')}", {
        "type": "domain_adwords_unique",
        "domain": d,
        "database": DB,
        "display_limit": 30,
        "export_columns": "Tt,Ds,Vu,Mt",
    })

print()
print("=" * 78)
print(f"All output files saved to: {OUT}")
print("=" * 78)
