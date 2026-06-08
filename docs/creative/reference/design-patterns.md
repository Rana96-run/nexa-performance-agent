# Design Patterns & AI Image Prompt System

Visual patterns extracted from Qoyod campaigns + structured prompt system for AI image generation.

---

## 1. Approved Background Patterns

### Pattern A: Navy Solid + Concentric Circles
- Base: Navy `#021544` solid fill
- Concentric circles: centered or offset, ~15% opacity, lighter blue/cyan
- Q watermark: 50% opacity soft light, positioned off-center
- Used in: Campaign-05, Campaign-21, Campaign-04, Campaign-19
- **Best for:** Bold headlines, person photos, dark mood

### Pattern B: Light Gradient (Cyan → White)
- Base: Gradient from light cyan/turquoise to white
- Direction: 45° top-right to bottom-left
- Concentric circles: subtle, same opacity
- Used in: Campaign-08, Campaign-22, Campaign-07, Campaign-15
- **Best for:** Clean layouts, device mockups, educational content

### Pattern C: Split Screen
- Left half: one background treatment
- Right half: contrasting treatment
- Vertical divider: thin line or torn-edge effect
- **Best for:** Before/after comparisons, contrast messaging

### Pattern D: Photo Background with Overlay
- Full-bleed photo (restaurant interior, office, kitchen)
- Dark navy overlay at 60-80% opacity
- Text reads over the overlay
- Used in: Campaign-04, Campaign-19
- **Best for:** Atmospheric, immersive, restaurant context

### Pattern E: Minimal Clean
- Mostly white/very light background
- Minimal graphic elements
- Product/device as the hero element
- Used in: إدارة أعمالك design
- **Best for:** Product showcases, feature highlights

---

## 2. Visual Element Types

### Type 1: Device Mockups
- Desktop monitor, laptop, iPad/tablet, iPhone/phone
- Always showing Qoyod interface/dashboard
- Positioned in middle-to-bottom of design
- Can include keyboard, stylus for context
- **Overused in current campaigns — use sparingly in new work**

### Type 2: Person Photography
- Saudi person(s) in authentic attire
- Positive expression: confident, relaxed, smiling
- Often interacting with device or looking at camera
- Positioned in bottom half of design
- **Underused — prioritize in new campaigns**

### Type 3: Hands + Device
- Hands holding tablet or phone
- Screen showing Qoyod interface
- More intimate, user-perspective feel
- Used in: Campaign-08, Campaign-11

### Type 4: Icons + Stats
- Large numbers (statistics)
- Simple flat icons (checkmarks, shields, clocks)
- Feature lists with icon bullets
- **Good for educational/value content**

### Type 5: Contextual Objects
- Delivery bags (for QFlavours)
- Receipt/invoice coming from device
- Calculator, notebook, coffee
- **Add storytelling and context**

---

## 3. AI Image Generation — Variable System

Use this system to build consistent, high-quality photography prompts.

### Variable [A] — Camera & Composition

| Code | Description |
|------|-------------|
| A1 | Medium-wide shot, eye level, front three-quarter, showing environment |
| A2 | Close-up, slightly below eye level, subject fills 60% of frame |
| A3 | Wide establishing shot, camera slightly above, showing full scene |
| A4 | Over-the-shoulder, focus on screen/device subject is using |
| A5 | Straight-on portrait, centered, shallow DOF |

### Variable [B] — Subject

| Code | Description |
|------|-------------|
| B1 | Saudi man, well-groomed beard, clean modern appearance |
| B2 | Saudi woman wearing hijab, confident professional |
| B3 | Two professionals (male + female), collaborative scene |
| B4 | Hands only — interacting with device or document |
| B5 | Group of 2-3 professionals, meeting/discussion |

### Variable [C] — Expression & Gesture

| Code | Description |
|------|-------------|
| C1 | Smiling naturally, looking at device screen, hand approaching touchscreen |
| C2 | Thoughtful, looking at documents/reports, hand on chin |
| C3 | Looking directly at camera, confident open smile, relaxed hands |
| C4 | Engaged in conversation, gesturing while explaining |
| C5 | Relaxed and relieved, leaning back, satisfied expression |

### Variable [D] — Outfit

| Code | Description |
|------|-------------|
| D1 | White thobe with red/white shemagh (traditional Saudi male) |
| D2 | Business suit, modern professional |
| D3 | Chef whites / restaurant uniform |
| D4 | Navy/dark abaya with minimal accessories |
| D5 | Smart casual — polo or button-down shirt |

### Variable [E] — Environment

| Code | Description |
|------|-------------|
| E1 | Modern restaurant interior, cashier counter, POS screen |
| E2 | Professional office, clean desk, laptop, minimal décor |
| E3 | Co-working space, glass walls, modern furniture |
| E4 | Home office, comfortable setup, natural light |
| E5 | Café/coffee shop, casual meeting setting |

### Locked Constants (always include)

```
Dominant brand color: deep navy blue applied to walls, signage, lighting accents.
Color harmony centered around navy blue branding.
Balanced warm-cool contrast: warm skin tones against cool navy environment.
Lighting: soft natural daylight, large diffused window light. Warm highlights on skin.
Subtle soft fill light. Gentle back rim light separating subject from background.
Cinematic soft shadows. Realistic light falloff.
Shot on full-frame camera, 35mm lens, f/2.8 depth of field.
Ultra-realistic photography. Commercial advertising style.
Clean polished surfaces. Soft reflections on screens.
Color grading: premium advertising tone, slightly warm highlights, cool navy midtones.
Photorealistic, 8K quality. No distortion, no artificial look, no exaggerated HDR.
No visible text on any screen or surface.
```

### Aspect Ratios
| Format | Ratio | Use |
|--------|-------|-----|
| Story | 9:16 | Instagram/Snapchat stories |
| Post | 1:1 | Instagram feed |
| Landscape | 3:2 | LinkedIn, website |
| Reel cover | 9:16 | TikTok/Reels |

### Variation Strategy
Change only one variable at a time:
- Same scene, different angle → swap [A]
- Same person, different expression → swap [C]
- Same shot, different location → swap [E]
- Full recast → swap [B] + [D] together

### Critical Rules
1. **Never ask AI to add text, UI elements, or overlays** — those are added in design tools
2. **Saudi authenticity required** — features, attire, environment must look Saudi
3. **Brand color integration** — navy blue in environment (walls, signage, accents)
4. **Always specify:** no text on surfaces, realistic proportions, no deformation
5. **Run 2-3 generations per combination** and select the strongest

---

## 4. QBookkeeping-Specific Patterns

### Color Application
- **Navy `#021544`:** Primary backgrounds, headline color on light backgrounds
- **Orange:** Highlighted words in headlines, CTA buttons, checkmarks, icons, stats
- **White:** Body text on dark backgrounds, card backgrounds
- **Light cyan/cream:** Light background option

### Recurring Trust Elements
- "فريق مختص ومعتمد من SOCPA" — appears as badge or subtitle
- Checkmark lists (✓) in orange for feature/benefit lists
- SOCPA mention in at least one design per campaign set

### Footer Pattern
```
[qoyod.com]                    [مسك الدفاتر BOOKKEEPING Q. | QOYOD]
(bottom-left)                  (bottom-right)
```

---

## 5. QFlavours-Specific Patterns

### Color Application
- **Navy/dark blue:** Primary backgrounds, especially with restaurant context
- **Bright cyan/turquoise:** Headlines, highlighted text, accent elements
- **Light blue:** Light background option
- **White:** Text on dark backgrounds

### F&B Visual Context
- Kitchen interiors, restaurant settings
- Food delivery bags, digital menus
- Order management screens, kitchen display systems
- Chef/restaurant staff imagery

### Footer Pattern
```
[qoyod.com]                    [فليفرز Flavours Q. | QOYOD]
(bottom-left)                  (bottom-right)
```
