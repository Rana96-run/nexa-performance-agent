---
name: verify-pixels-before-signoff
description: No LP sign-off until both pixels are observed firing in Events Manager and UTM passes through on every form field
metadata:
  type: critical
---

Before signing off a deployed LP variant: observe **both** pixels firing in Meta
Events Manager (not "should fire" — observed), and confirm **UTM passthrough on
every form field**.

**Why:** a silently-broken pixel or dropped UTM corrupts the lead→campaign join,
so CPQL goes wrong for weeks before anyone notices. "Done means verified."

**How to apply:** test the live page, watch Events Manager, submit a test lead and
confirm UTMs land in HubSpot, THEN hand back to `cro-specialist`.
