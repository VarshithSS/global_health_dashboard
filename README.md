# Global NCD Care Inequality Dashboard — CS661 Group 5

A single-page Dash app merging all 6 CS661 Group-5 visualization tasks
(map, sex gap, temporal trend, cascade, region/income, age-standardized
vs crude) into one linked dashboard, per Section 5 of the proposal.

Data: WHO Health Inequality Data Repository (Health Care System & Access
module) — six NCD indicators, 195 countries, 72,420 estimates, no missing
values. Diabetes runs 1990–2022; hypertension 1990–2019.

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:8054/

## The interface

- **KPI strip** — four headline numbers (mean coverage, countries in view,
  widest sex gap, average care leakage), recomputed from the current scope.
- **Command bar** — the six shared filters, plus a Reset button.
- **Left nav rail** — switches between the six analytical views.

## How linking works

- A global filter bar (Indicator, Sex, WHO Region, Income Group, Country,
  Year) sits above the nav rail and writes into one `dcc.Store`
  ("global-filters"). A single reducer callback owns that store.
- Every view's callback reads from that store, so changing a filter in the
  bar updates every view that uses it.
- **Region + Income act as a scope**: they narrow the pool of countries the
  rest of the dashboard considers. The Country dropdown re-populates, and if
  the selected country falls outside the new scope it is swapped for a valid
  in-scope one.
- **Cross-filtering** (chart clicks write back into the store):
  - Task 1 map — click a country → sets the global Country. Tasks 2, 4 and 6
    re-render for it directly; Task 3 uses it to seed its default comparison set.
  - Task 5 region/income — click a bar → sets both WHO Region and Income Group.
  - Task 3 trend — click a point → sets the Year (and, at country level, the Country).
  - Task 2 sex gap — click a year → sets the Year.
- **Nearest-year fallback**: diabetes runs to 2022 but hypertension only to
  2019, so selecting 2022 with a hypertension indicator would otherwise blank
  the view. Instead it snaps to the nearest available year and says so in the
  view's subtitle.
- Task 5 (region/income) has no sex breakdown in its source data, so it
  only listens to Indicator + Year.
- Task 6 keeps a local "indicator family" dropdown (different taxonomy —
  paired crude/standardized columns) but still uses the shared Sex/Year/Country.

## File layout

```
app.py                  <- the merged single-page app (run this)
data/                   <- the 8 prepared CSVs
visualizations/         <- the 6 pure create_*() chart functions (no Dash)
report/                 <- the project report + figures + build script
old_code/               <- earlier UI iterations, kept for reference
```

No visualization logic was rewritten — `app.py` only adds the integration
layer (shared state, layout, cross-filtering, theming) on top of the
existing, working chart functions.

## Report

`report/CS661_Group5_Project_Report.pdf` is the final report. To rebuild it:

```bash
pip install weasyprint kaleido        # + playwright, for the UI screenshots
python report/build_report.py
```

The six chart figures are rendered by importing the app's own theme and
`create_*()` functions, so the report's figures match what the dashboard shows.

## Known gaps

- Task 5 has no country-level drill-down (it's pre-aggregated by region/income
  in `region_income_summary.csv`); clicking a bar sets the region/income scope
  but can't reveal the individual countries inside a cell.
- No dark/light theme toggle (the dashboard is dark-only — swap the `C` dict
  and the CSS custom properties in `app.py` if you want light mode).
- Data is held in memory and re-filtered per callback, with an `lru_cache` in
  front of the six figure builders. Fine at this size (~72k rows); a larger
  scope would want SQLite or DuckDB behind it.
