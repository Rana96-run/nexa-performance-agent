# hex-sql-cells — Add/update SQL cells in Hex programmatically

## Principle

**Always prefer programmatic cell manipulation over clicking through the Hex UI.**
Clicking is slow, error-prone across virtual-rendered notebooks, and breaks on
layout changes. JavaScript + Monaco editor is reliable and fast.

## The two scenarios

### A — Update content of an existing cell (most common)

Use this when the cell already exists (e.g. clearing Windsor placeholders,
updating a query that already has a cell label you can target).

```javascript
async () => {
  const scroller = document.querySelector('.LogicViewContents__OLContainer-sc-47481b60-0');
  
  // 1. Scroll to the cell by its label text
  const targetLabel = 'Google Ads — Ad Groups placeholder';  // adjust per cell
  let targetPos = null;
  
  // Scan in steps to find the cell
  for (let pos = 0; pos <= scroller.scrollHeight; pos += 800) {
    scroller.scrollTop = pos;
    await new Promise(r => setTimeout(r, 300));
    const labels = document.querySelectorAll('[class*="CellLabel"], [class*="cellLabel"]');
    for (const l of labels) {
      if (l.innerText.trim() === targetLabel) { targetPos = pos; break; }
    }
    if (targetPos !== null) break;
  }
  if (targetPos === null) return 'cell not found';
  
  // 2. Find the Monaco editor for this cell and replace its content
  // (cell must be in viewport — targetPos scroll is already set)
  const editors = document.querySelectorAll('.monaco-editor');
  // Identify the right editor by proximity to the label (editors render in DOM order)
  // Use the Monaco editor API to replace content
  const editorIndex = 0;  // adjust if multiple editors visible
  const model = monaco.editor.getModels()[editorIndex];
  if (!model) return 'no model';
  
  const newSQL = `-- your SQL here`;
  model.setValue(newSQL);
  return 'updated';
}
```

### B — Add a brand-new SQL cell after an existing cell (harder)

Hex uses virtual rendering + React. The most reliable programmatic approach
is to interact with Hex's internal dispatch mechanism. Try this order:

**Step 1 — Try keyboard shortcut after selecting the cell:**
```javascript
async () => {
  const scroller = document.querySelector('.LogicViewContents__OLContainer-sc-47481b60-0');
  // Scroll to the target cell
  scroller.scrollTop = TARGET_POSITION;
  await new Promise(r => setTimeout(r, 400));
  
  // Click on the cell's Monaco editor to select it
  const editors = document.querySelectorAll('.monaco-editor');
  editors[TARGET_INDEX].querySelector('.inputarea').focus();
  
  // In Hex, pressing Escape to exit edit mode, then 'b' adds a cell below
  // (similar to Jupyter). Try this keyboard sequence:
  document.activeElement.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}));
  await new Promise(r => setTimeout(r, 100));
  document.activeElement.dispatchEvent(new KeyboardEvent('keydown', {key:'b', bubbles:true}));
  return 'attempted keyboard shortcut';
}
```

**Step 2 — If keyboard shortcut fails, use the "+" button between cells:**
```javascript
async () => {
  // Hex shows a "+" insert button when hovering between cells
  // Find it via the accessibility tree or by looking for [aria-label*="Add"]
  const addBtns = Array.from(document.querySelectorAll('button, [role="button"]'))
    .filter(b => (b.getAttribute('aria-label') || b.innerText || '').toLowerCase().includes('add'));
  return addBtns.map(b => ({label: b.getAttribute('aria-label'), text: b.innerText.substring(0,40)}));
}
```
Then use `mcp__plugin_chrome-devtools-mcp_chrome-devtools__click` with the
uid from `take_snapshot` to click the "+" button.

**Step 3 — Use Hex's React internal dispatch (advanced):**
```javascript
() => {
  // Find the React fiber on a known element
  const el = document.querySelector('[class*="NotebookCell"], [class*="CellWrapper"]');
  if (!el) return 'no cell element';
  const fiberKey = Object.keys(el).find(k => k.startsWith('__reactFiber'));
  if (!fiberKey) return 'no fiber';
  
  // Walk up to find the store dispatch
  let fiber = el[fiberKey];
  let dispatch = null;
  while (fiber && !dispatch) {
    const props = fiber.memoizedProps || {};
    if (props.dispatch) { dispatch = props.dispatch; break; }
    if (fiber.stateNode && fiber.stateNode.dispatch) { dispatch = fiber.stateNode.dispatch; break; }
    fiber = fiber.return;
  }
  if (!dispatch) return 'no dispatch found';
  
  // Try dispatching an INSERT_CELL action
  dispatch({ type: 'INSERT_CELL_AFTER', payload: { cellType: 'SQL' } });
  return 'dispatched';
}
```

## Reliable Monaco content replacement

This is the proven approach from previous sessions (works consistently):

```javascript
async (cellLabel, newContent) => {
  const scroller = document.querySelector('.LogicViewContents__OLContainer-sc-47481b60-0');
  
  // Find scroll position of cell
  for (let pos = 0; pos <= scroller.scrollHeight; pos += 800) {
    scroller.scrollTop = pos;
    await new Promise(r => setTimeout(r, 350));
    
    const labels = document.querySelectorAll('[class*="CellLabel"], [class*="cellLabel"]');
    for (const lbl of labels) {
      if (lbl.innerText.trim() !== cellLabel) continue;
      
      // Found cell — find its Monaco editor
      // Walk up to the cell container, then find the .inputarea
      let cellEl = lbl;
      while (cellEl && !cellEl.querySelector('.monaco-editor')) {
        cellEl = cellEl.parentElement;
      }
      if (!cellEl) continue;
      
      const ta = cellEl.querySelector('textarea.inputarea');
      if (!ta) continue;
      
      // Click to focus, Ctrl+A to select all, type replacement
      ta.focus();
      await new Promise(r => setTimeout(r, 100));
      ta.dispatchEvent(new KeyboardEvent('keydown', {
        key:'a', code:'KeyA', ctrlKey:true, keyCode:65, which:65,
        bubbles:true, cancelable:true, composed:true
      }));
      await new Promise(r => setTimeout(r, 100));
      
      // Type the new content
      document.execCommand('insertText', false, newContent);
      return { found: true, label: cellLabel };
    }
  }
  return { found: false };
}
```

## Hex scroll container selector

```javascript
const scroller = document.querySelector('.LogicViewContents__OLContainer-sc-47481b60-0');
```
This class may change with Hex deploys. If it fails, fall back to:
```javascript
const scroller = document.querySelector('[class*="OLContainer"]') || 
                 document.querySelector('[class*="LogicViewContents"]');
```

## Known cell positions (as of 2026-05-04, scrollHeight=26819)

| Cell label | approx scrollTop |
|---|---|
| Google Ads header | 6400 |
| Google Ads KPIs | 7200 |
| Google Ads Campaigns | 8000 |
| Google Ads — Ad Groups placeholder | 8800 |
| Google Ads — Ads placeholder | 8800 |
| Google Ads — Keywords placeholder | 9600 |
| Google Ads — Recommendations | 9600 |
| Meta Ads header | 9600 |
| Meta Ads Campaigns | 11200 |
| Meta Ads — Ad Groups placeholder | 12000 |
| Meta Ads — Ads placeholder | 12000 |
| Meta Ads — Keywords placeholder | 12000 |
| Snapchat Ads Campaigns | 13600 |
| Snapchat Ads — Ad Groups placeholder | 15200 |
| Snapchat Ads — Ads placeholder | 15200 |
| Snapchat Ads — Keywords placeholder | 15200 |
| TikTok Ads Campaigns | 16800 |
| TikTok Ads — Ad Groups placeholder | 17600 |
| TikTok Ads — Ads placeholder | 17600 |
| TikTok Ads — Keywords placeholder | 18400 |
| LinkedIn Ads Campaigns | 20000 |
| LinkedIn Ads — Ad Groups placeholder | 20800 |
| LinkedIn Ads — Ads placeholder | 20800 |
| LinkedIn Ads — Keywords placeholder | 20800 |
| Organic Search header | 21600 |

## SQL patterns for sub-campaign cells

### Adsets (utm_audience level)
Joins `adsets_daily.adset_name` ↔ `hubspot_leads_module_daily.lead_utm_audience`.

```sql
-- {Channel} Ad Sets: adsets_daily LEFT JOIN HubSpot on utm_audience
WITH hs AS (
  SELECT lower(lead_utm_audience) as adset_key,
         sum(leads_total) as leads,
         sum(leads_qualified) as sqls
  FROM qoyod_marketing.hubspot_leads_module_daily
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND lead_utm_audience IS NOT NULL
  GROUP BY 1
),
adsets AS (
  SELECT adset_name, campaign_name,
         any_value(status) as status,
         sum(spend) as spend,
         sum(impressions) as impressions,
         sum(clicks) as clicks
  FROM qoyod_marketing.adsets_daily
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND channel = '{CHANNEL}'
  GROUP BY adset_name, campaign_name
)
SELECT
  a.campaign_name, a.adset_name, a.status,
  a.spend, a.impressions, a.clicks,
  round(safe_divide(a.clicks, nullif(a.impressions,0)) * 100, 4) as ctr,
  coalesce(hs.leads, 0) as leads,
  coalesce(hs.sqls, 0) as sqls,
  safe_divide(a.spend, nullif(hs.leads, 0)) as cpl,
  safe_divide(a.spend, nullif(hs.sqls, 0)) as cpql
FROM adsets a
LEFT JOIN hs ON lower(a.adset_name) = hs.adset_key
ORDER BY a.spend DESC
```

### Ads (utm_content level)
Joins `ads_daily.ad_name` ↔ `hubspot_leads_module_daily.lead_utm_content`.

```sql
-- {Channel} Ads: ads_daily LEFT JOIN HubSpot on utm_content
WITH hs AS (
  SELECT lower(lead_utm_content) as ad_key,
         sum(leads_total) as leads,
         sum(leads_qualified) as sqls
  FROM qoyod_marketing.hubspot_leads_module_daily
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND lead_utm_content IS NOT NULL
  GROUP BY 1
),
ads AS (
  SELECT ad_name, adset_name, campaign_name,
         any_value(status) as status,
         sum(spend) as spend,
         sum(impressions) as impressions,
         sum(clicks) as clicks
  FROM qoyod_marketing.ads_daily
  WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
    AND channel = '{CHANNEL}'
  GROUP BY ad_name, adset_name, campaign_name
)
SELECT
  a.campaign_name, a.adset_name, a.ad_name, a.status,
  a.spend, a.impressions, a.clicks,
  round(safe_divide(a.clicks, nullif(a.impressions,0)) * 100, 4) as ctr,
  coalesce(hs.leads, 0) as leads,
  coalesce(hs.sqls, 0) as sqls,
  safe_divide(a.spend, nullif(hs.leads, 0)) as cpl,
  safe_divide(a.spend, nullif(hs.sqls, 0)) as cpql
FROM ads a
LEFT JOIN hs ON lower(a.ad_name) = hs.ad_key
ORDER BY a.spend DESC
```

### Keywords (utm_term level, Google Ads only)
```sql
-- Google Ads Keywords: keywords_daily
SELECT
  campaign_name, adgroup_name, keyword_text, match_type,
  avg(quality_score) as quality_score,
  sum(spend) as spend,
  sum(impressions) as impressions,
  sum(clicks) as clicks,
  round(safe_divide(sum(clicks), nullif(sum(impressions),0)) * 100, 4) as ctr,
  safe_divide(sum(spend), nullif(sum(clicks),0)) as avg_cpc,
  sum(conversions) as conversions
FROM qoyod_marketing.keywords_daily
WHERE date BETWEEN {{ start_date }} AND {{ end_date }}
  AND channel = 'google_ads'
GROUP BY campaign_name, adgroup_name, keyword_text, match_type
ORDER BY spend DESC
```

## Notes

- Google Ads keywords live in `keywords_daily` only — no ad-level keyword join.
- Snapchat / TikTok / LinkedIn don't have `keywords_daily` data.
- Snapchat adset = "Ad Squad"; LinkedIn adset = "Campaign" (utm_audience level).
- Always pre-aggregate HubSpot before joining — never join raw rows (fan-out risk).
- `lead_utm_audience` and `lead_utm_content` may be sparse if UTM params aren't
  set on all landing pages. Zero leads ≠ bad campaign; check UTM coverage first.
