---
name: Meta campaign tracking setup
description: Always select both Qoyod pixels when setting up Meta campaigns
type: project
originSessionId: 98abfa4b-165c-4f94-9eed-fbd113d7e8d2
---
When creating or configuring any Meta campaign, always enable both conversion tracking sources under the Tracking step:

1. **CRM events** — `Qoyod_CRM_PIXEL`  (Pixel ID: `1782671302631317`)
2. **Website events** — `Qoyod_Web_PIXEL`  (Pixel ID: `3036579196577051`)

**Why:** These are the two data sources Qoyod uses to track qualified leads (CRM) and site behaviour (web). Missing either breaks conversion attribution.

**Instagram profile:** Always select `qoyod` as the Instagram account under Ad Setup → Instagram profile.

**How to apply:** Any time a Meta campaign is created via executor or manual setup instructions, confirm both pixels are selected and Instagram profile is set to `qoyod` before publishing.
