"""Test how lp.qoyod.com/qawaem/ responds to different user agents.
AdsBot-Google has its own user-agent string. If the LP responds differently
to AdsBot vs a regular browser, that explains DESTINATION_NOT_WORKING."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

import urllib.request, urllib.error

URL = "https://lp.qoyod.com/qawaem/"

UAS = {
    "regular_browser": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "adsbot_google":   "AdsBot-Google (+http://www.google.com/adsbot.html)",
    "googlebot":       "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "no_ua":           "",
}

print(f"Probing {URL}\n")
for label, ua in UAS.items():
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": ua} if ua else {})
        r = urllib.request.urlopen(req, timeout=10)
        body = r.read(2000).decode("utf-8", errors="replace")
        status = r.status
        ct = r.headers.get("content-type", "?")
        size = len(body)
        # Cheap content signal — does the body contain Decision 236 markers?
        has_qawaem  = "قوائم" in body or "Qawaem" in body or "qawaem" in body
        has_236     = "236" in body
        has_cf_challenge = "Just a moment" in body or "cloudflare" in body.lower()
        print(f"  [{label:<20}] HTTP {status}  ct={ct[:30]}  size={size}b")
        print(f"     qawaem_text={has_qawaem}  236_text={has_236}  cf_challenge={has_cf_challenge}")
    except urllib.error.HTTPError as e:
        print(f"  [{label:<20}] HTTPError {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        print(f"  [{label:<20}] URLError: {e.reason}")
    except Exception as e:
        print(f"  [{label:<20}] {type(e).__name__}: {e}")
