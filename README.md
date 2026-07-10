# Global NCD Care Inequality Dashboard — Frontend Integration

Single-page Dash app merging all 6 CS661 Group-5 visualization tasks
(map, sex gap, temporal trend, cascade, region/income, age-standardized
vs crude) into one linked dashboard, per Section 5 of the proposal.

## Run it

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:8050/

## How linking works

- A global filter bar (Indicator, Sex, Country, Year) sits above the tabs
  and writes into one `dcc.Store` ("global-filters").
- Every tab's callback reads from that store, so changing a filter in the
  bar updates every tab that uses it.
- Clicking a country on the Task 1 map updates the global Country filter,
  which cascades into Tasks 2, 3, 4, and 6 automatically.
- Task 5 (region/income) has no sex breakdown in its source data, so it
  only listens to Indicator + Year.
- Task 6 keeps a local "indicator family" dropdown (different taxonomy —
  paired crude/standardized columns) but still uses the shared Sex/Year/Country.

## File layout

```
app.py                 <- the merged single-page app (run this)
data/                   <- the same 8 CSVs from the original zip, unchanged
visualizations/         <- the same 6 create_*() chart functions, unchanged
```

No visualization logic was rewritten — this only adds the missing
integration layer (shared state, tab layout, cross-filtering) on top of
the existing, working chart functions.

## Known gaps to fill next

- Task 5 currently has no country-level drill-down (it's pre-aggregated
  by region/income in `region_income_summary.csv`); clicking a bar doesn't
  yet set the global country filter.
- No dark/light theme toggle (dashboard defaults to dark to match the
  portfolio aesthetic — swap `COLORS` dict in app.py if you want light mode).
- No loading-state caching — every callback re-filters from the in-memory
  DataFrame each time. Fine at this data size (~71k rows total), but worth
  moving to the SQLite backend once Backend Dev's DB layer is ready.
