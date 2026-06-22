# LP Brief Template — 8 sections (owned by cro-specialist)

Copy this to `../briefs/YYYY-MM-DD_<product>_<hypothesis-slug>.md` and fill in.
The brief (including the annotated design spec) is the first artifact in the chain → hands to `developer`.

---
test_id: <YYYY-MM-DD_product_slug>
product: Invoice | Bookkeeping | Qflavours | <season>
channel: Meta | Google | Snapchat | LinkedIn
status: brief | design | build | live | decided
---

## 1. Hypothesis
If we <change>, then <metric> will <direction> because <reason>.

## 2. Current state (live BQ, 14-day window — explicit dates)
Window: YYYY-MM-DD to YYYY-MM-DD · current CPQL: $X · current conversion: X%
destination_url: <the page under test>

## 3. Target audience & OCEAN persona
Segment: <audience> · persona traits driving the copy/design.

## 4. Offer & message
The single promise above the fold; supporting proof points.

## 5. Page structure (sections, order)
Hero → … → CTA. Note where the **ZATCA badge** sits (must be above the fold).

## 6. Form & tracking
Fields required · **UTM passthrough on every field** · both pixels fire.

## 7. Success criteria (the win condition)
Decide ship/kill from: CPQL delta ≥ X over 14 days at confidence Y.

## 8. Risks & kill criterion
What would make us stop early; the pre-approved revert.
