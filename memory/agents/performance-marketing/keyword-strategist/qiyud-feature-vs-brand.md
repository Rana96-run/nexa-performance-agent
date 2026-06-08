---
name: qiyud-feature-vs-brand
description: قيود plus an accounting modifier (محاسبية/المحاسبة/يومية) is the accounting noun, not the Qoyod brand — route as normal, not brand-only
metadata:
  type: critical
---

"قيود" alone is the brand (Qoyod) → BRAND_ONLY, allowed only in `Brand` campaigns.
BUT "قيود" + an accounting modifier (محاسبية / المحاسبة / يومية / اليومية) is the
accounting noun "journal entries" — a feature keyword, route as `normal`.

**Why:** treating `قيود محاسبية` as brand wrongly drops a high-intent feature term
from non-brand campaigns.

**How to apply:** check `keyword_policy.QIYUD_FEATURE_MODIFIERS` before classifying
any قيود term. The disambiguation list is the source of truth, not intuition.
