# Qoyod Designer Agent — Full Usage Instructions

---

## What Is This?

The **Qoyod Designer Agent** is a complete creative production system for Qoyod and all sub-brands. It handles the full creative pipeline — from market intelligence to production-ready design briefs and AI-generated images — without needing a separate creative director.

---

## File Structure

```
Design Agent/
├── .env                              ← API keys and environment variables
├── system-prompt.md                  ← Agent identity, pipeline, all rules
├── skillset.md                       ← Skills catalog and capability map
├── instructions.md                   ← This file
├── references/
│   ├── brand-identity.md             ← Colors, fonts, layout grid (source of truth)
│   ├── campaign-analysis.md          ← Campaign history + market intelligence
│   ├── design-patterns.md            ← 10 layout templates + AI photo variable system
│   └── prompt-templates.md           ← Production-ready templates (Story/Post/Carousel/Video)
├── Social media design samples/      ← Reference executions — actual Qoyod campaigns
└── Lama_Sans_1641320455652_uo27ge.zip ← Lama Sans font family (all weights)
```

---

## How to Use

### Starting the Agent

Load `system-prompt.md` as the system prompt for the Claude agent. The agent will automatically reference the `references/` folder files for brand data.

### Request Patterns

#### Full Campaign (all 6 stages from scratch)
```
"ابغى حملة جديدة لـ QBookkeeping — ٦ تصاميم ستوري"
```
→ Agent delivers: analysis → ideas → headlines → design prompts → AI image prompts → generated images

#### Competitor Analysis + Response Campaign
```
"حلل لي هالمحتوى من المنافس [+ screenshots]"
```
→ 10-dimension analysis + gap identification + response campaign ideas

#### Design Prompt Only (you already have the idea)
```
"ابغى برومبت تصميم لفكرة 'كم تكلفك الفوضى' — ستوري QBookkeeping"
```
→ Complete designer brief in Arabic with all specs

#### Headlines Only
```
"اكتب لي هيدلاينز لحملة مسك الدفاتر — زاوية الخوف من الغرامات"
```
→ 2–3 variations with font/color annotations

#### AI Image Prompt Only
```
"ابغى برومبت صورة AI لرجل سعودي في مكتب — لحملة QBookkeeping"
```
→ Full 8-block English prompt ready for HiggsField or Midjourney

#### Generate Image Directly (HiggsField)
```
"ولّد لي الصورة هذي مباشرة: [image prompt or brief]"
```
→ Agent writes prompt, calls HiggsField API, returns image

---

## The 6 Brands — At a Glance

| Brand | للعربي | الاستخدام |
|-------|--------|-----------|
| Qoyod | قيود | محاسبة سحابية، فوترة ZATCA |
| QBookkeeping | مسك الدفاتر | خدمة مسك الدفاتر، فريق SOCPA |
| QFlavours | فليفرز | نقاط بيع للمطاعم والكافيهات |
| QTahseel | تحصيل | تحصيل المدفوعات |
| QLend | ليند | تمويل الأعمال |
| QAcademy | أكاديمي | تدريب ودورات محاسبية |

---

## HiggsField API

The agent uses HiggsField for AI image generation. Credentials are in `.env`.

**Do not share the `.env` file publicly.** The API secret in `.env` is the live production key.

**Basic workflow:**
1. Agent assembles the image prompt following the 8-block skeleton
2. Agent calls `POST /v1/images/generate` with the prompt + dimensions
3. API returns the generated image
4. Post-processing: overlay brand logos, pricing numbers, Arabic text using your design tool

**Supported dimensions:**

| Use Case | Width | Height | Ratio |
|----------|-------|--------|-------|
| Instagram Post / Square | 1080 | 1080 | 1:1 |
| Story / Reel / Snapchat | 1080 | 1920 | 9:16 |
| Portrait Post | 1080 | 1350 | 4:5 |
| LinkedIn / Website Banner | 1920 | 1080 | 16:9 |

---

## Typography Setup

The **Lama Sans** font family is in `Lama_Sans_1641320455652_uo27ge.zip`.

Install all weights before any design work:
- Lama Sans Black — main headlines
- Lama Sans Bold — CTAs and stats
- Lama Sans SemiBold — pills and eyebrow text
- Lama Sans Medium — sub-headlines
- Lama Sans Regular — body copy

**Lama Sans is the only font used in all Qoyod designs — Arabic and English.**

---

## Reference Designs

The `Social media design samples/` folder contains actual executed Qoyod campaign designs. Use them as:
- Visual benchmark for quality level
- Color and layout verification
- Template reference for what each of the 10 patterns looks like in production

---

## Key Rules (Never Break These)

1. **Exact hex codes always** — no "orange" or "dark blue" — always `#F26522` or `#021544`
2. **Lama Sans only** — never suggest or use any other Arabic font
3. **Right-align all Arabic** — no exceptions, including inside cards, buttons, or pills
4. **No text inside AI-generated images** — overlay text in your design tool
5. **Logo placement is fixed** — sub-brand logo bottom-right, qoyod.com bottom-left
6. **Gradient direction: 45°** from top-right to bottom-left — always

---

## Quick Troubleshooting

| Problem | Fix |
|---------|-----|
| AI image has broken Arabic letters | Add negative block: "broken Arabic letters, disconnected characters, left-to-right Arabic" |
| Design looks off-brand | Check hex codes in the design prompt — load `references/brand-identity.md` |
| Headline doesn't feel Saudi | Add لهجة سعودية variant, reference the headline bank in system-prompt.md Stage 4 |
| HiggsField API error | Check `.env` credentials — verify `HIGGSFIELD_API_KEY_ID` and `HIGGSFIELD_API_KEY_SECRET` |
| Wrong template selected | Use the template selection guide in system-prompt.md Stage 5 |
