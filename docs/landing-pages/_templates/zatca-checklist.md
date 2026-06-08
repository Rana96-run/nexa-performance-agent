# LP Compliance Checklist (ZATCA + tracking) — gate before any LP goes live

`developer` confirms every item is observed (not assumed) before sign-off, then
hands the result back to `cro-specialist`.

## ZATCA (non-negotiable)
- [ ] ZATCA compliance badge is **above the fold** on every viewport (desktop + mobile).
- [ ] Badge renders in RTL Arabic layout without breaking.

## Tracking — pixels
- [ ] Qoyod_CRM_PIXEL `1782671302631317` fires on page load (verified in Events Manager).
- [ ] Qoyod_Web_PIXEL `3036579196577051` fires on page load (verified in Events Manager).
- [ ] Lead/submit event fires on form completion (verified in Events Manager).

## Tracking — UTM
- [ ] UTM passthrough wired on **every** form field (utm_source/medium/campaign/content/audience).
- [ ] Test submission lands in HubSpot with all UTMs populated (confirms the lead→campaign join).

## Content
- [ ] Arabic copy is MSA, never colloquial; layout RTL.
- [ ] destination_url matches the brief's test_id.

A single unchecked box = NOT signed off.
