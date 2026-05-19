"""Verify the iOS 404 issue Google flagged."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass

import urllib.request, urllib.error

URL = "https://lp.qoyod.com/qawaem/"

UAS = {
    "desktop_chrome":   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "iphone_safari":    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "ipad_safari":      "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "android_chrome":   "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "adsbot_desktop":   "AdsBot-Google (+http://www.google.com/adsbot.html)",
    "adsbot_mobile":    "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2272.96 Mobile Safari/537.36 (compatible; AdsBot-Google-Mobile; +http://www.google.com/mobile/adsbot.html)",
    "googlebot_iphone": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
}

print(f"Probing {URL} with various user agents\n")
for label, ua in UAS.items():
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": ua})
        r = urllib.request.urlopen(req, timeout=10)
        body_preview = r.read(500).decode("utf-8", errors="replace")
        has_qawaem = "قوائم" in body_preview or "qawaem" in body_preview.lower() or "236" in body_preview
        print(f"  [{label:<20}] HTTP {r.status}  content_marker={has_qawaem}")
    except urllib.error.HTTPError as e:
        print(f"  [{label:<20}] HTTP {e.code} {e.reason}   ← BROKEN")
    except urllib.error.URLError as e:
        print(f"  [{label:<20}] URLError: {e.reason}")
