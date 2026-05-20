"""Upload RSA via raw Bulk CSV file. Bypasses the bingads SDK suds layer
entirely — the SOAP enum serialization issue is in the SDK, not the
underlying HTTP/CSV pipeline. MS docs for the CSV format:
https://learn.microsoft.com/en-us/advertising/bulk-service/responsive-search-ad
"""
import sys, os, json, tempfile, csv
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

from bingads.v13.bulk import (
    BulkServiceManager, FileUploadParameters,
)
from executors.microsoft_ads import _auth

AG_ID  = "1238051567759836"
LP_URL = "https://lp.qoyod.com/qawaem/"

HEADLINES = [
    "تجنب غرامة قرار 236", "أودع قوائمك المالية في دقائق",
    "موعد الإيداع: 30 يونيو 2026", "غرامة شخصية تصل 20,000 ريال",
    "متوافق مع منصة قوائم", "تصدير XBRL بنقرة واحدة",
    "أكثر من 50,000 شركة سعودية", "متوافق ZATCA + قوائم",
    "تجربة 14 يوم بدون بطاقة", "إعداد في 14 دقيقة",
    "أنت مسؤول شخصياً عن الإيداع", "احم المدير من غرامة 236",
    "احسب غرامة شركتك مجاناً", "ابدأ الإيداع في دقائق",
    "أودع قوائمك من 120 ريال/شهر",
]
DESCRIPTIONS = [
    "تجنب غرامة قرار 236 الشخصية. قيود يصدر قوائمك ويرفعها لمنصة قوائم في دقائق. ابدأ مجاناً.",
    "أكثر من 50,000 شركة سعودية تستخدم قيود. تجربة 14 يوم بدون بطاقة. ابدأ الآن.",
    "موعد إيداع قوائم 2025 ينتهي 30 يونيو 2026. غرامة شخصية تصل 20,000 ريال للمدير.",
    "موعد الإيداع 30 يونيو 2026. قيود يصدر قوائمك جاهزة لمنصة قوائم. سجل مجاناً الآن.",
]

# Build the headlines/descriptions JSON arrays
headlines_json = json.dumps(
    [{"text": h} for h in HEADLINES], ensure_ascii=False, separators=(",", ":")
)
descriptions_json = json.dumps(
    [{"text": d} for d in DESCRIPTIONS], ensure_ascii=False, separators=(",", ":")
)

# CSV columns per MS Bulk schema for Responsive Search Ad
# Minimum required: Type, Status, Parent Id (= ad group id), Headline, Description, Final Url
out_dir = os.path.normpath(tempfile.gettempdir())
csv_path = os.path.join(out_dir, "qawaem_rsa_upload.csv")

with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.writer(fh)
    # Header row — Format Version line first
    w.writerow(["Format Version"])
    w.writerow(["6.0"])
    w.writerow([])
    # RSA columns
    w.writerow([
        "Type", "Status", "Parent Id", "Campaign", "Ad Group",
        "Title Part 1", "Title Part 2", "Title Part 3",   # legacy required even for RSA
        "Headline",
        "Text",                                            # legacy required
        "Description",
        "Final Url",
        "Path 1", "Path 2",
        "Ad Format Preference",
        "Editorial Status",
    ])
    w.writerow([
        "Responsive Search Ad",  # Type
        "Active",                # Status
        AG_ID,                   # Parent Id (ad group)
        "",                      # Campaign (optional when parent ID given)
        "",                      # Ad Group (optional when parent ID given)
        HEADLINES[0][:30], HEADLINES[1][:30], HEADLINES[2][:30],
        headlines_json,
        DESCRIPTIONS[0][:90],
        descriptions_json,
        LP_URL,
        "", "",                  # paths empty
        "",                      # ad format pref
        "",                      # editorial status (read-only on input)
    ])

print(f"  CSV written: {csv_path}")
print(f"  Headline JSON sample: {headlines_json[:150]}...")
print(f"  Descriptions JSON sample: {descriptions_json[:150]}...")

# Upload
auth = _auth()
mgr = BulkServiceManager(
    authorization_data=auth,
    poll_interval_in_milliseconds=5000,
    environment="production",
)
params = FileUploadParameters(
    result_file_directory=out_dir,
    result_file_name="qawaem_rsa_upload_result.csv",
    overwrite_result_file=True,
    upload_file_path=csv_path,
    response_mode="ErrorsAndResults",
)

print("\n  Uploading...")
try:
    result_file = mgr.upload_file(params)
    print(f"  ✅ result file: {result_file}")
    if result_file and os.path.exists(result_file):
        with open(result_file, "r", encoding="utf-8-sig") as fh:
            print(fh.read()[:4000])
except Exception as e:
    print(f"  ❌ {type(e).__name__}: {str(e)[:400]}")
