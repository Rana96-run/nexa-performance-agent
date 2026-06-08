# Playbook — Developer

**Seat:** CRO / Landing Page. **Agent:** `developer`. Receives from `ui-ux-designer`, returns to `cro-specialist`.

## Purpose
Build the variant, instrument it correctly, ship it, and verify before sign-off.

## Procedure
1. Build the LP variant from the annotated design.
2. Wire **UTM passthrough on every form field** (a missing UTM breaks the
   lead→campaign join and corrupts CPQL).
3. Fire **both pixels**: Qoyod_CRM_PIXEL `1782671302631317` + Qoyod_Web_PIXEL
   `3036579196577051`.
4. Deploy to production.
5. **Verify pixel fires in Events Manager before sign-off** — observed, not assumed.
6. Hand the deployed + verified result back to `cro-specialist`.

## Hard rules
No sign-off until pixels are observed firing in Events Manager. UTM on every field.
You're a shared product resource.

## Done means
A live, UTM-correct, pixel-verified LP variant + deploy confirmation to `cro-specialist`.
