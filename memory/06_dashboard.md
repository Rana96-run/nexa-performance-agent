# Dashboard (Streamlit)

Location: `dashboard/`  ·  Host: Replit (separate repl from agent)

## Structure

```
dashboard/
├── app.py                          # landing + cache controls
├── bq.py                           # shared BQ client + @st.cache_data
├── .streamlit/config.toml          # theme: Qoyod navy #003DA5
├── requirements.txt                # deps
├── README.md                       # deploy instructions
└── pages/
    ├── 1_Live_Campaigns.py         # real-time KPIs, time series, pause candidates
    ├── 2_Growth_Overview.py        # monthly rollup, funnel, channel mix
    └── 3_Channels_Performance.py   # per-channel deep dive
```

## Planned pages (in 09_open_tasks.md, not built yet)

- `1_Paid_Overview.py` (split from current Live Campaigns)
- `2_Organic_Overview.py` (FB+IG+YT+LinkedIn organic together)
- `3_Channel_Deep_Dive.py` (campaign/adset/ad tables, creative types)
- `4_Leads_Funnel.py` (disqual reasons + sub-reasons)
- `5_Insights_Recommendations.py` (rules-based recs per channel)

## Conventions

- **Every page** starts with:
  ```python
  import sys, os
  sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
  from bq import query, fq
  ```
- **BQ queries** via `query(sql: str) -> pd.DataFrame`, already cached 1h
- **Table refs** via `fq("table_name")` → `\`project.dataset.table\``
- **Filter pattern:** top `st.columns(3)` row with date window + channel multiselect

## Theming

- Primary: `#003DA5` (Qoyod navy)
- Bg: white · secondary bg: `#F5F7FA`
- Use Plotly for charts; pass `use_container_width=True`
- Color-coded CPL zones: 🟢 scale (<20) / 🟡 ok (20-28) / 🟠 warn (28-30) / 🔴 pause (>30)
- Color-coded CPQL zones: 🟢 <40 / 🟡 40-65 / 🟠 65-80 / 🔴 >80

## Cache strategy

- `@st.cache_data(ttl=3600)` on `query()` in `bq.py`
- 6h data refresh + 1h UI cache = worst-case 7h staleness — acceptable
- "Force refresh cache" button on landing page calls `st.cache_data.clear()`

## Local run

```bash
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
# opens http://localhost:8501
```

## Replit run

Inside dashboard/ as its own repl:
```toml
# dashboard/.replit
run = "streamlit run app.py --server.port=$PORT --server.address=0.0.0.0"
```
Required Replit Secrets: `BQ_PROJECT_ID`, `BQ_DATASET`, `BQ_LOCATION`,
`GOOGLE_APPLICATION_CREDENTIALS_JSON` (paste JSON key contents, NOT a path).
