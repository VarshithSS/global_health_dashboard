"""
CS661 Group-5 — Global NCD Care Inequality Dashboard  ·  "MARK 2" UI
=====================================================================

An experimental redesign of the dashboard's front end. Same data, same six
visualization tasks, same linked-filter / cross-filter / animation behaviour
as app.py ("Mark 1") — but a completely new "Observatory" interface:

    - a brand header + live KPI insight strip that summarises the current
      selection in four headline numbers,
    - a sticky command bar for the six shared filters,
    - a left navigation rail (instead of top tabs) that switches between the
      six analytical views,
    - one cohesive dark chart theme with a validated, colour-blind-safe
      categorical palette (dataviz skill: reference dark palette, CVD order)
      and a branded sequential ramp for the choropleth.

Mark 1 (app.py) is left completely untouched. This file only imports the pure
create_*() chart functions and the shared label maps from `visualizations`,
then rebuilds everything above them. Run with:

    python mark2.py
    open http://127.0.0.1:8051/
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, State, callback_context
from dash.exceptions import PreventUpdate

from visualizations.labels import INDICATOR_LABELS, INDICATOR_FAMILY_LABELS
from visualizations.global_map import create_global_map
from visualizations.sex_gap import create_sex_gap_chart
from visualizations.temporal_trend import create_temporal_trend_chart
from visualizations.treatment_control import create_treatment_control_cascade
from visualizations.regional_income import create_regional_income_comparison
from visualizations.age_crude import create_age_standardized_crude_chart


# =============================================================================
# 1. DATA LOADING  (mirrors app.py — the DataFrames are the shared substrate)
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


def _load_csv(name, year_cols=("year",), numeric_cols=()):
    df = pd.read_csv(DATA_DIR / name)
    for col in year_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


map_df = _load_csv("map_data.csv", numeric_cols=["value"])
map_df = map_df.dropna(subset=["year", "indicator_code", "sex", "value"])
map_df["year"] = map_df["year"].astype(int)

sex_gap_df = _load_csv("sex_gap_data.csv", numeric_cols=["Male", "Female", "delta_sex"])
sex_gap_df = sex_gap_df.dropna(
    subset=["country", "year", "indicator_code", "Male", "Female", "delta_sex"]
)
sex_gap_df["year"] = sex_gap_df["year"].astype(int)

trend_country_df = _load_csv("trend_country.csv")
trend_country_df = trend_country_df.dropna(subset=["country", "year", "sex"])
trend_country_df["year"] = trend_country_df["year"].astype(int)

trend_region_df = _load_csv("trend_region.csv")
trend_region_df["year"] = trend_region_df["year"].astype(int)

trend_income_df = _load_csv("trend_income.csv")
trend_income_df["year"] = trend_income_df["year"].astype(int)

cascade_df = _load_csv(
    "cascade_data.csv", numeric_cols=["htn_tx_crude", "htn_ctrl_crude", "delta_leak"]
)
cascade_df = cascade_df.dropna(
    subset=["country", "year", "sex", "htn_tx_crude", "htn_ctrl_crude"]
)
cascade_df["year"] = cascade_df["year"].astype(int)

region_income_df = _load_csv(
    "region_income_summary.csv", numeric_cols=["mean", "median", "std", "count"]
)
region_income_df = region_income_df.dropna(
    subset=["who_region", "income_group", "indicator_code", "year", "mean"]
)
region_income_df["year"] = region_income_df["year"].astype(int)


# =============================================================================
# 2. CONSTANTS
# =============================================================================

INDICATOR_OPTIONS = [
    {"label": label, "value": code} for code, label in INDICATOR_LABELS.items()
]
INDICATOR_FAMILY_OPTIONS = [
    {"label": label, "value": code} for code, label in INDICATOR_FAMILY_LABELS.items()
]

AGE_CRUDE_PAIRS = {
    "diabetes_treatment": ("diab_tx_crude", "diab_tx_std"),
    "hypertension_treatment": ("htn_tx_crude", "htn_tx_std"),
    "hypertension_control": ("htn_ctrl_crude", "htn_ctrl_std"),
}

ALL_COUNTRIES = sorted(map_df["country"].dropna().unique())
COUNTRY_OPTIONS = [{"label": c, "value": c} for c in ALL_COUNTRIES]

ALL_TOKEN = "All"
WHO_REGIONS = sorted(map_df["who_region"].dropna().unique())

_INCOME_LADDER = [
    "Low-income", "Lower-middle-income", "Upper-middle-income",
    "High-income", "Not Classified",
]
_INCOME_PRESENT = set(map_df["income_group"].dropna().unique())
INCOME_GROUPS = [g for g in _INCOME_LADDER if g in _INCOME_PRESENT]
INCOME_GROUPS += [g for g in sorted(_INCOME_PRESENT) if g not in INCOME_GROUPS]

REGION_OPTIONS = (
    [{"label": "All regions", "value": ALL_TOKEN}]
    + [{"label": r, "value": r} for r in WHO_REGIONS]
)
INCOME_OPTIONS = (
    [{"label": "All income groups", "value": ALL_TOKEN}]
    + [{"label": g, "value": g} for g in INCOME_GROUPS]
)

ALL_YEARS = sorted(int(y) for y in map_df["year"].dropna().unique())
YEAR_MIN, YEAR_MAX = min(ALL_YEARS), max(ALL_YEARS)
# Show the endpoints plus every 5th year, but drop any 5-year mark that sits
# within 2 years of the max (e.g. 2020 next to 2022) so the labels don't
# overlap on the slider.
_mark_years = {YEAR_MIN, YEAR_MAX} | {
    y for y in ALL_YEARS if y % 5 == 0 and abs(YEAR_MAX - y) >= 3
}
YEAR_MARKS = {int(y): str(int(y)) for y in sorted(_mark_years)}

DEFAULT_INDICATOR = "diab_tx_std"
DEFAULT_SEX = "Female"
DEFAULT_YEAR = YEAR_MAX
DEFAULT_COUNTRY = "India" if "India" in ALL_COUNTRIES else ALL_COUNTRIES[0]
DEFAULT_REGION = ALL_TOKEN
DEFAULT_INCOME = ALL_TOKEN

PREFERRED_COMPARISON_COUNTRIES = [
    "India", "China", "Brazil", "United States of America", "Japan",
]


# =============================================================================
# 3. DESIGN SYSTEM  (Mark 2 "Observatory" tokens + validated chart palette)
# =============================================================================

# UI surface / ink tokens. Kept in sync with the CSS custom properties below.
C = {
    "bg":        "#080b12",
    "panel":     "#111825",
    "panel2":    "#0d1420",
    "elev":      "#182234",
    "border":    "#22304a",
    "text":      "#eaf0fb",
    "text2":     "#a7b4cc",
    "muted":     "#67748d",
    "accent":    "#2dd4bf",
    "accent2":   "#3b82f6",
}

# Categorical palette — dataviz skill reference dark instance, in its
# CVD-optimised slot order (blue, aqua, yellow, green, violet, red, magenta,
# orange). Validated against surface #131a26: all pass band/chroma/contrast,
# worst adjacent CVD in the 8–12 floor band → always paired with a legend.
CATEGORICAL = [
    "#3987e5", "#199e70", "#c98500", "#008300",
    "#9085e9", "#e66767", "#d55181", "#d95926",
]

# Branded sequential ramp for the choropleth: dark navy (near zero, recedes
# toward the dark surface) → bright blue (high coverage, pops off the map).
MAP_COLORSCALE = [
    [0.00, "#0d366b"], [0.15, "#184f95"], [0.30, "#256abf"],
    [0.45, "#3987e5"], [0.60, "#5598e7"], [0.75, "#86b6ef"],
    [0.90, "#b7d3f6"], [1.00, "#e8f2fe"],
]

# Semantic colours for the treatment→control cascade (state, not identity):
# treatment = neutral, leakage = bad, effective control = good.
CASCADE_COLORS = {
    "Treatment Coverage": "#3b82f6",        # neutral baseline
    "Not Effectively Controlled": "#e5484d",  # leakage — bad
    "Effective Control": "#30c88f",         # good outcome
}

# Sex uses the safest two-hue pair (blue / orange).
SEX_COLORS = {"Female": "#3987e5", "Male": "#e0863f"}

FONT_STACK = ('Inter, system-ui, -apple-system, "Segoe UI", '
              'Roboto, Arial, sans-serif')


# =============================================================================
# 4. SCOPE HELPERS
# =============================================================================

def countries_in_scope(region, income):
    d = map_df
    if region and region != ALL_TOKEN:
        d = d[d["who_region"] == region]
    if income and income != ALL_TOKEN:
        d = d[d["income_group"] == income]
    return sorted(d["country"].dropna().unique())


def pick_scope_country(pool, current):
    if current in pool:
        return current
    for c in PREFERRED_COMPARISON_COUNTRIES:
        if c in pool:
            return c
    return pool[0] if pool else None


def scope_description(region, income):
    bits = [b for b in (
        None if region == ALL_TOKEN else region,
        None if income == ALL_TOKEN else income,
    ) if b]
    return " · ".join(bits) if bits else "Worldwide"


def _nearest_year(years, year):
    """Nearest available year to `year` within a Series/array of years."""
    vals = pd.Series(years).dropna().astype(int)
    if vals.empty:
        return None
    if year in vals.values:
        return int(year)
    return int(min(vals.unique(), key=lambda y: abs(y - year)))


def _age_crude_effective_year(family, year, sex):
    crude_col, std_col = AGE_CRUDE_PAIRS[family]
    years = trend_country_df.loc[
        (trend_country_df["sex"] == sex)
        & trend_country_df[crude_col].notna()
        & trend_country_df[std_col].notna(),
        "year",
    ]
    return _nearest_year(years, year)


# =============================================================================
# 5. CHART THEMING + CACHED BUILDERS  (recolour to the Mark 2 palette)
# =============================================================================

def _recolor_named(fig, mapping):
    """Recolour whole traces by their `name` (bars, marker series)."""
    for tr in fig.data:
        col = mapping.get(getattr(tr, "name", None))
        if not col:
            continue
        if tr.marker is not None:
            tr.marker.color = col
        if getattr(tr, "line", None) is not None and "lines" in (tr.mode or ""):
            tr.line.color = col


def _recolor_by_legendgroup(fig, colors):
    """Assign one palette colour per legend group, in first-seen order."""
    order = {}
    for tr in fig.data:
        lg = getattr(tr, "legendgroup", None)
        if lg is None:
            continue
        if lg not in order:
            order[lg] = colors[len(order) % len(colors)]
        col = order[lg]
        if getattr(tr, "line", None) is not None:
            tr.line.color = col
        if tr.marker is not None:
            tr.marker.color = col


def _fix_footer_overlap(fig):
    """Stop the footer annotations from colliding with the x-axis title.

    The create_*() charts place their footer texts (source line, gap/leakage
    summaries) at negative *paper* y — which is measured in fractions of the
    plot-area height, so on shorter plots they drift up into the x-axis title
    and overlap it. This re-anchors every footer to the plot's bottom edge and
    offsets it in **pixels**, so the clearance below the axis title is fixed
    regardless of plot height, then grows the bottom margin to fit. Applied to
    all charts so the overlap can't occur on any of them.
    """
    # Pin any x-axis title snug against the tick labels so it can't drift down,
    # and note whether the labels are angled (tilted long labels — e.g. Task 5's
    # region names — occupy far more vertical space, pushing the title lower).
    tilted = False
    for ax in fig.select_xaxes():
        if ax.title is not None and ax.title.text:
            ax.title.standoff = 8
        if ax.tickangle:
            tilted = True

    footers = [a for a in fig.layout.annotations
               if a.yref in ("paper", None) and a.y is not None and a.y < 0]
    if not footers:
        return

    # Reserve pixels below the plot before the footer stack starts: enough to
    # clear the tick labels + axis title, more when the labels are tilted.
    AXIS_PX = 120 if tilted else 74
    LINE_PX = 22
    for i, ann in enumerate(sorted(footers, key=lambda a: a.y, reverse=True)):
        ann.update(y=0, yref="paper", yanchor="top",
                   yshift=-(AXIS_PX + i * LINE_PX))

    needed_b = AXIS_PX + (len(footers) - 1) * LINE_PX + 42
    if (fig.layout.margin.b or 0) < needed_b:
        fig.layout.margin.b = needed_b


def _theme(fig, is_map=False):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=CATEGORICAL,
        font=dict(family=FONT_STACK, color=C["text2"], size=13),
        title_font_color=C["text"],
        legend_font_color=C["text2"],
        legend_title_font_color=C["muted"],
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        # NOTE: do NOT override the figure margins here — each create_*() chart
        # tunes its own top/bottom margin to fit its title, horizontal legend
        # and footer annotations. Forcing a small top margin made the title
        # overlap the legend (Mark 2 bug).
    )
    if is_map:
        fig.update_geos(
            bgcolor="rgba(0,0,0,0)",
            landcolor="#172032",
            oceancolor="#0a1018",
            lakecolor="#0a1018",
            coastlinecolor=C["border"],
            countrycolor="#0d1420",
        )
        fig.update_coloraxes(
            colorscale=MAP_COLORSCALE,
            colorbar_tickfont_color=C["text2"],
            colorbar_title_font_color=C["text2"],
            colorbar_outlinecolor="rgba(0,0,0,0)",
        )
    else:
        axis_style = dict(
            gridcolor="#1b2740",
            zerolinecolor="#22304a",
            linecolor="#22304a",
            tickcolor=C["muted"],
            title_font_color=C["muted"],
            tickfont_color=C["muted"],
        )
        fig.update_xaxes(**axis_style)
        fig.update_yaxes(**axis_style)
    _fix_footer_overlap(fig)
    return fig


def empty_selection_placeholder(message, height=500):
    fig = go.Figure()
    fig.update_layout(
        height=height,
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[{
            "text": message, "xref": "paper", "yref": "paper",
            "x": 0.5, "y": 0.5, "showarrow": False,
            "font": {"size": 15, "color": C["muted"], "family": FONT_STACK},
        }],
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


@lru_cache(maxsize=512)
def _fig_map(indicator, year, sex, region, income):
    pool = tuple(countries_in_scope(region, income))
    scoped = map_df[map_df["country"].isin(pool)]
    fig = create_global_map(df=scoped, indicator=indicator, year=year, sex=sex)
    return _theme(fig, is_map=True)


@lru_cache(maxsize=256)
def _fig_sexgap(indicator, country):
    fig = create_sex_gap_chart(df=sex_gap_df, indicator=indicator, country=country)
    _recolor_named(fig, SEX_COLORS)
    return _theme(fig)


@lru_cache(maxsize=256)
def _fig_trend(level, indicator, entities, sex):
    cfg = LEVEL_CONFIG[level]
    fig = create_temporal_trend_chart(
        df=cfg["df"], indicator=indicator, entities=list(entities),
        entity_column=cfg["entity_column"], level_name=cfg["level_name"], sex=sex,
    )
    return _theme(fig)


@lru_cache(maxsize=256)
def _fig_cascade(country, year, sex):
    fig = create_treatment_control_cascade(
        df=cascade_df, country=country, year=year, sex=sex)
    _recolor_named(fig, CASCADE_COLORS)
    return _theme(fig)


@lru_cache(maxsize=256)
def _fig_region(indicator, year):
    fig = create_regional_income_comparison(
        df=region_income_df, indicator=indicator, year=year)
    return _theme(fig)


@lru_cache(maxsize=256)
def _fig_agecrude(family, year, sex, countries):
    fig = create_age_standardized_crude_chart(
        df=trend_country_df, indicator_family=family, year=year, sex=sex,
        countries=list(countries))
    _recolor_by_legendgroup(fig, CATEGORICAL)
    return _theme(fig)


# =============================================================================
# 6. APP + GLOBAL CSS
# =============================================================================

app = Dash(__name__, suppress_callback_exceptions=True)
app.title = "NCD Care Observatory · CS661 Group 5 · Mark 6"
server = app.server

app.index_string = """<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    {%css%}
    <style>
      :root {
        --bg:#080b12; --panel:#111825; --panel2:#0d1420; --elev:#182234;
        --border:#22304a; --border-soft:rgba(255,255,255,0.06);
        --text:#eaf0fb; --text2:#a7b4cc; --muted:#67748d;
        --accent:#2dd4bf; --accent2:#3b82f6;
      }
      * { box-sizing:border-box; }
      html,body { margin:0; padding:0; background:var(--bg); }
      body {
        font-family:Inter, system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
        color:var(--text);
        background:
          radial-gradient(1100px 620px at 82% -8%, rgba(45,212,191,0.10), transparent 60%),
          radial-gradient(1000px 560px at 4% 0%, rgba(59,130,246,0.12), transparent 55%),
          var(--bg);
        -webkit-font-smoothing:antialiased;
      }
      ::-webkit-scrollbar { width:10px; height:10px; }
      ::-webkit-scrollbar-track { background:transparent; }
      ::-webkit-scrollbar-thumb { background:var(--border); border-radius:6px; }
      ::-webkit-scrollbar-thumb:hover { background:var(--muted); }

      .card {
        background:linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0)) , var(--panel);
        border:1px solid var(--border);
        border-radius:16px;
      }

      /* KPI tiles */
      .kpi {
        position:relative; overflow:hidden;
        background:linear-gradient(180deg, rgba(255,255,255,0.025), rgba(255,255,255,0)), var(--panel);
        border:1px solid var(--border); border-radius:16px; padding:18px 20px;
        transition:transform .15s ease, border-color .15s ease;
      }
      .kpi:hover { transform:translateY(-2px); border-color:rgba(45,212,191,0.45); }
      .kpi::before {
        content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
        background:linear-gradient(180deg,var(--accent),var(--accent2));
      }
      .kpi-label { font-size:11px; font-weight:700; letter-spacing:.11em; text-transform:uppercase; color:var(--muted); }
      .kpi-value { font-size:34px; font-weight:800; line-height:1.05; margin-top:8px; color:var(--text); }
      .kpi-value .unit { font-size:16px; font-weight:600; color:var(--text2); margin-left:3px; }
      .kpi-cap { font-size:12.5px; color:var(--text2); margin-top:7px; }

      /* Nav rail */
      .nav-item {
        display:block; width:100%; text-align:left; cursor:pointer;
        background:transparent; border:1px solid transparent; border-radius:12px;
        padding:13px 15px; margin-bottom:8px; color:var(--text2);
        transition:background .14s ease, border-color .14s ease, transform .14s ease;
      }
      .nav-item:hover { background:var(--elev); transform:translateX(2px); }
      .nav-item.active {
        background:linear-gradient(180deg, rgba(45,212,191,0.12), rgba(59,130,246,0.06)), var(--elev);
        border-color:rgba(45,212,191,0.5);
      }
      .nav-num {
        display:inline-flex; align-items:center; justify-content:center;
        width:26px; height:26px; border-radius:8px; font-size:13px; font-weight:800;
        background:var(--panel2); border:1px solid var(--border); color:var(--muted);
        margin-right:11px; flex:0 0 auto;
      }
      .nav-item.active .nav-num { background:var(--accent); color:#04211d; border-color:var(--accent); }
      .nav-title { font-size:14px; font-weight:700; color:var(--text); }
      .nav-item.active .nav-title { color:var(--text); }
      .nav-desc { font-size:11.5px; color:var(--muted); margin-top:3px; line-height:1.35; }

      .chip {
        display:inline-flex; align-items:center; gap:7px; font-size:12px; font-weight:600;
        color:var(--text2); background:var(--panel2); border:1px solid var(--border);
        border-radius:999px; padding:6px 13px;
      }
      .dot { width:8px; height:8px; border-radius:50%; background:var(--accent);
             box-shadow:0 0 0 4px rgba(45,212,191,0.18); }

      .ctl-label { font-size:11px; font-weight:700; letter-spacing:.06em; text-transform:uppercase;
                   color:var(--muted); display:block; margin-bottom:7px; }

      .btn {
        background:var(--panel2); color:var(--text2); border:1px solid var(--border);
        border-radius:9px; padding:9px 15px; font-size:13px; font-weight:600; cursor:pointer;
        font-family:inherit; transition:all .14s ease;
      }
      .btn:hover { border-color:var(--accent); color:var(--text); }
      .btn-accent { color:var(--accent); border-color:rgba(45,212,191,0.5); }
      .btn-accent:hover { background:rgba(45,212,191,0.12); }

      /* Dash 4's Dropdown & Slider are themed entirely through --Dash-* custom
       * properties (the light defaults make the box/text white on our dark
       * bar). Redefining those tokens dark — with !important so they win no
       * matter when Dash injects its own :root — themes every part of both
       * controls at once: trigger box, menu, options, value text, slider
       * track/thumb/marks, and the value tooltip. */
      :root {
        --Dash-Stroke-Strong: #2a3a5a !important;
        --Dash-Stroke-Weak: rgba(255,255,255,0.10) !important;
        --Dash-Fill-Interactive-Strong: var(--accent) !important;
        --Dash-Fill-Interactive-Weak: rgba(45,212,191,0.10) !important;
        --Dash-Fill-Inverse-Strong: var(--panel2) !important;
        --Dash-Text-Primary: var(--text) !important;
        --Dash-Text-Strong: var(--text) !important;
        --Dash-Text-Weak: var(--text2) !important;
        --Dash-Text-Disabled: var(--muted) !important;
        --Dash-Fill-Primary-Hover: rgba(255,255,255,0.06) !important;
        --Dash-Fill-Primary-Active: rgba(45,212,191,0.18) !important;
        --Dash-Fill-Disabled: var(--border) !important;
        --Dash-Shading-Strong: rgba(0,0,0,0.55) !important;
        --Dash-Shading-Weak: rgba(0,0,0,0.40) !important;
        --Dash-Tooltip-Background-Color: var(--accent) !important;
        --Dash-Tooltip-Border-Color: var(--accent) !important;
      }
      /* Class-level fallbacks in case a surface uses a non-token background. */
      .dash-dropdown-trigger, .dash-dropdown-content {
        background: var(--panel2) !important; border-color: var(--border) !important;
      }
      .dash-dropdown-value, .dash-dropdown-value-item,
      .dash-dropdown-value-count { color: var(--text) !important; }
      .dash-dropdown-placeholder { color: var(--muted) !important; }
      .dash-dropdown-option:hover { background: var(--elev) !important; }
      /* Value tooltip (the always-visible year pill). Its background comes
       * from --Dash-Fill-Inverse-Strong — the same token we darken for the
       * dropdown box — so left alone it's dark text on a dark pill (invisible).
       * Style the element directly: teal pill (fill covers the arrow), dark
       * text. */
      .dash-slider-tooltip {
        background-color: var(--accent) !important;
        fill: var(--accent) !important;
        color: #04211d !important;
        font-weight: 700 !important;
      }

      /* RadioItems */
      .radio-row label { margin-right:16px; color:var(--text2); font-size:13.5px; cursor:pointer; }
      .radio-row input { accent-color:var(--accent); margin-right:6px; }

      /* ---- Mark 6 sidebar + page shell ---- */
      .app-shell { display:grid; grid-template-columns:250px 1fr; min-height:100vh; }
      .sidebar {
        background:linear-gradient(180deg, var(--panel2), var(--bg));
        border-right:1px solid var(--border); padding:22px 15px;
        position:sticky; top:0; height:100vh; overflow-y:auto;
        display:flex; flex-direction:column;
      }
      .side-brand { display:flex; align-items:center; gap:12px; padding:4px 8px 18px; }
      .side-logo {
        width:40px; height:40px; border-radius:11px; font-size:21px;
        display:flex; align-items:center; justify-content:center;
        background:linear-gradient(140deg,#2dd4bf,#3b82f6);
        box-shadow:0 6px 18px rgba(45,212,191,0.28);
      }
      .side-brand-name { font-size:14px; font-weight:800; letter-spacing:.03em; color:var(--text); }
      .side-brand-sub { font-size:11px; color:var(--muted); margin-top:1px; }
      .side-nav { display:flex; flex-direction:column; gap:3px; flex:1; margin-top:6px; }
      .side-item {
        display:flex; align-items:center; gap:12px; padding:10px 12px;
        border-radius:11px; cursor:pointer; color:var(--text2);
        border:1px solid transparent; transition:background .14s, border-color .14s, transform .14s;
      }
      .side-item:hover { background:var(--elev); transform:translateX(2px); }
      .side-item.active {
        background:linear-gradient(180deg, rgba(45,212,191,0.13), rgba(59,130,246,0.06)), var(--elev);
        border-color:rgba(45,212,191,0.5);
      }
      .side-emoji { font-size:18px; width:24px; text-align:center; flex:0 0 auto; }
      .side-label { font-size:13.5px; font-weight:700; color:var(--text); line-height:1.15; }
      .side-item:not(.active) .side-label { color:var(--text2); }
      .side-sub { font-size:11px; color:var(--muted); margin-top:1px; }
      .side-foot { border-top:1px solid var(--border); padding:14px 8px 2px; margin-top:12px;
                   font-size:12px; font-weight:600; color:var(--text2); }
      .side-foot-sub { font-size:11px; font-weight:500; color:var(--muted); margin-top:2px; }

      .main { padding:32px 40px 64px; max-width:1520px; }
      .page-head h1 { font-size:24px; font-weight:800; margin:0 0 6px; color:var(--text); }
      .page-head p { margin:0 0 20px; font-size:14px; color:var(--text2); max-width:820px; line-height:1.5; }
      .controls-card { background:linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0)), var(--panel);
                       border:1px solid var(--border); border-radius:14px; padding:16px 20px; margin-bottom:18px; }
      .chart-card { padding:20px 22px; }
      .chart-note { font-size:13px; color:var(--text2); text-align:center; margin-bottom:8px; min-height:18px; }

      /* Home */
      .home-hero { padding:8px 4px 26px; }
      .hero-eyebrow { font-size:12px; font-weight:800; letter-spacing:.14em; color:var(--accent); }
      .hero-title { font-size:34px; font-weight:800; line-height:1.12; margin:12px 0 14px;
                    color:var(--text); max-width:900px; }
      .hero-lead { font-size:15px; line-height:1.6; color:var(--text2); max-width:820px; margin:0 0 18px; }
      .hero-chips { display:flex; gap:10px; flex-wrap:wrap; }
      .home-grid { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:20px; }
      .info-card { padding:22px 24px; }
      .info-card.wide { grid-column:1 / -1; }
      .info-title { font-size:12px; font-weight:800; letter-spacing:.1em; text-transform:uppercase;
                    color:var(--accent); margin-bottom:16px; }
      .info-row { display:flex; justify-content:space-between; gap:20px; padding:9px 0;
                  border-bottom:1px solid var(--border); }
      .info-row:last-child { border-bottom:none; }
      .info-key { font-size:13px; color:var(--muted); font-weight:600; }
      .info-val { font-size:13.5px; color:var(--text); text-align:right; }
      .team-group { padding:12px 0; border-bottom:1px solid var(--border); }
      .team-group:last-child { border-bottom:none; }
      .team-role { font-size:12.5px; font-weight:700; color:var(--text2); margin-bottom:9px; }
      .team-members { display:flex; flex-wrap:wrap; gap:8px; }
      .team-chip { font-size:12.5px; color:var(--text); background:var(--panel2);
                   border:1px solid var(--border); border-radius:8px; padding:6px 11px; }
      .explore-grid { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:14px; }
      .explore-item { display:flex; gap:11px; align-items:flex-start; padding:12px 14px;
                      background:var(--panel2); border:1px solid var(--border); border-radius:11px; }
      .explore-emoji { font-size:20px; }
      .explore-label { font-size:13.5px; font-weight:700; color:var(--text); }
      .explore-desc { font-size:11.5px; color:var(--muted); margin-top:2px; }
      .home-hint { margin:18px 0 0; font-size:13px; color:var(--muted); }
      @media (max-width:1100px){ .home-grid,.explore-grid{ grid-template-columns:1fr; } }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>"""



# =============================================================================
# 7. LAYOUT  —  sidebar (Home + 6 task pages), each page self-contained
# =============================================================================

GRAPH_CONFIG = {"displayModeBar": True, "displaylogo": False, "responsive": True}

LEVEL_CONFIG = {
    "country": dict(df=trend_country_df, entity_column="country", level_name="Country"),
    "region": dict(df=trend_region_df, entity_column="who_region", level_name="WHO Region"),
    "income": dict(df=trend_income_df, entity_column="income_group", level_name="Income Group"),
}

# Sidebar entries: (key, emoji, label, one-line description).
SIDEBAR = [
    ("home", "🏠", "Home", "About this project"),
    ("1", "🗺️", "Global Map", "Coverage by country"),
    ("2", "⚖️", "Sex Gap", "Male vs female disparity"),
    ("3", "📈", "Temporal Trend", "Coverage over time"),
    ("4", "🩸", "Care Cascade", "Treatment → control leakage"),
    ("5", "🌍", "Region & Income", "WHO region × income"),
    ("6", "📐", "Standardized vs Crude", "Age-structure effect"),
]

# The project team (from the proposal, Section 7), grouped by responsibility.
TEAM = [
    ("Data Processing, Cleaning & Analytics",
     ["Stuti Singh (251083)", "Unnati Gangurde (231107)"]),
    ("Backend Development",
     ["Talakola Maha Lakshmi (241082)", "Khasha Meganakshtra (240542)"]),
    ("Visualization Development",
     ["Pyna Hema Lakshmi SatyaSree (240819)", "Sruja BG (240289)",
      "Annadevara Yashvanth Chary (240143)"]),
    ("Frontend Development",
     ["Mavilla Bharadwaja (251110021)", "Singampalli Sri Varshith (251110074)"]),
]


def control(label, comp, flex="1", min_w="170px"):
    return html.Div([html.Label(label, className="ctl-label"), comp],
                    style={"flex": flex, "minWidth": min_w})


def dd(cid, options, value, **kw):
    return dcc.Dropdown(id=cid, options=options, value=value,
                        clearable=False, **kw)


def region_income_controls(prefix):
    """The two scope dropdowns, shared by every country-oriented page."""
    return [
        control("WHO Region", dd(f"{prefix}-region", REGION_OPTIONS, DEFAULT_REGION),
                flex="1.4", min_w="170px"),
        control("Income Group", dd(f"{prefix}-income", INCOME_OPTIONS, DEFAULT_INCOME),
                flex="1.4", min_w="170px"),
    ]


def year_control(cid):
    return control("Year", html.Div(dcc.Slider(
        id=cid, min=YEAR_MIN, max=YEAR_MAX, step=1, value=DEFAULT_YEAR,
        marks=YEAR_MARKS, tooltip={"placement": "top", "always_visible": True},
        updatemode="mouseup"), style={"paddingTop": "14px"}),
        flex="3", min_w="320px")


def controls_card(children):
    return html.Div(className="controls-card", children=[html.Div(
        style={"display": "flex", "gap": "20px", "alignItems": "flex-end",
               "flexWrap": "wrap"}, children=children)])


def chart_card(graph_id, note_id, height):
    return html.Div(className="card chart-card", children=[
        html.Div(id=note_id, className="chart-note"),
        dcc.Loading(type="circle", color=C["accent"], children=[
            dcc.Graph(id=graph_id, config=GRAPH_CONFIG, style={"height": height})]),
    ])


def page(key, title, subtitle, controls, graph_id, note_id, height):
    return html.Div(
        id=f"page-{key}", className="page",
        style={"display": "none"},
        children=[
            html.Div(className="page-head", children=[
                html.H1(title), html.P(subtitle)]),
            controls_card(controls),
            chart_card(graph_id, note_id, height),
        ],
    )


# ---- Home page --------------------------------------------------------------

def info_card(title, rows, wide=False):
    body = []
    for label, value in rows:
        body.append(html.Div(className="info-row", children=[
            html.Span(label, className="info-key"),
            html.Span(value, className="info-val"),
        ]))
    return html.Div(className="card info-card" + (" wide" if wide else ""),
                    children=[html.Div(title, className="info-title")] + body)


def team_card():
    groups = []
    for role, members in TEAM:
        groups.append(html.Div(className="team-group", children=[
            html.Div(role, className="team-role"),
            html.Div(className="team-members", children=[
                html.Span(m, className="team-chip") for m in members]),
        ]))
    return html.Div(className="card info-card wide", children=[
        html.Div("The Team", className="info-title")] + groups)


def home_page():
    return html.Div(
        id="page-home", className="page", style={"display": "block"},
        children=[
            html.Div(className="home-hero", children=[
                html.Div("CS661 · COURSE PROJECT · GROUP 5", className="hero-eyebrow"),
                html.H1("Global Diabetes & Hypertension "
                        "Care Inequality Observatory", className="hero-title"),
                html.P("An interactive visual-analytics system exploring how "
                       "treatment coverage and effective control of two major "
                       "non-communicable diseases vary across countries, WHO "
                       "regions, income groups, sex and three decades — and where "
                       "care systems fail to convert treatment into control.",
                       className="hero-lead"),
                html.Div(className="hero-chips", children=[
                    html.Span([html.Span(className="dot"),
                               "WHO Health Inequality Data Repository"], className="chip"),
                    html.Span("195 countries", className="chip"),
                    html.Span("1990–2022", className="chip"),
                    html.Span("~71k rows", className="chip"),
                ]),
            ]),
            html.Div(className="home-grid", children=[
                info_card("Course", [
                    ("Course", "CS661 — Big Data Visual Analytics"),
                    ("Instructor", "«  add instructor name  »"),
                    ("Group", "Group 5"),
                    ("Deliverable", "Interactive single-page dashboard"),
                ]),
                info_card("Dataset", [
                    ("Source", "WHO Health Inequality Data Repository"),
                    ("Module", "Health Care System & Access"),
                    ("Publisher", "WHO Global Health Observatory"),
                    ("Scope", "6 NCD indicators · 195 countries · 1990–2022"),
                    ("Note", "Hypertension indicators run through 2019"),
                ]),
                team_card(),
                html.Div(className="card info-card wide", children=[
                    html.Div("What you can explore", className="info-title"),
                    html.Div(className="explore-grid", children=[
                        html.Div(className="explore-item", children=[
                            html.Span(emoji, className="explore-emoji"),
                            html.Div([html.Div(label, className="explore-label"),
                                      html.Div(desc, className="explore-desc")]),
                        ]) for key, emoji, label, desc in SIDEBAR if key != "home"
                    ]),
                    html.P("Pick a section from the sidebar to begin.",
                           className="home-hint"),
                ]),
            ]),
        ],
    )


# ---- Task pages -------------------------------------------------------------

def sex_dd(cid):
    return dd(cid, [{"label": "Male", "value": "Male"},
                    {"label": "Female", "value": "Female"}], DEFAULT_SEX)


page_1 = page(
    "1", "Global Coverage Map",
    "Choropleth of a selected indicator by country. Scope to a WHO region or "
    "income group to focus the map.",
    [control("Indicator", dd("t1-indicator", INDICATOR_OPTIONS, DEFAULT_INDICATOR),
             flex="2.4", min_w="250px"),
     control("Sex", sex_dd("t1-sex"), flex="1", min_w="120px"),
     *region_income_controls("t1"),
     year_control("t1-year")],
    "t1-graph", "t1-note", "600px")

page_2 = page(
    "2", "Sex Gap Analysis",
    "Male vs female coverage for one country across years. Region / income "
    "narrow which countries you can pick.",
    [control("Indicator", dd("t2-indicator", INDICATOR_OPTIONS, DEFAULT_INDICATOR),
             flex="2.2", min_w="250px"),
     *region_income_controls("t2"),
     control("Country", dd("t2-country", COUNTRY_OPTIONS, DEFAULT_COUNTRY,
                           searchable=True), flex="1.8", min_w="200px")],
    "t2-graph", "t2-note", "700px")

page_3 = page(
    "3", "Temporal Trend",
    "How coverage has evolved over time for selected countries, WHO regions or "
    "income groups.",
    [control("Indicator", dd("t3-indicator", INDICATOR_OPTIONS, DEFAULT_INDICATOR),
             flex="2", min_w="240px"),
     control("Sex", sex_dd("t3-sex"), flex="1", min_w="120px"),
     control("Compare by", dcc.RadioItems(
         id="t3-level",
         options=[{"label": "Country", "value": "country"},
                  {"label": "WHO Region", "value": "region"},
                  {"label": "Income Group", "value": "income"}],
         value="country", inline=True, className="radio-row"),
         flex="1.4", min_w="260px"),
     *region_income_controls("t3"),
     control("Entities to compare", dcc.Dropdown(id="t3-entities", multi=True),
             flex="2.4", min_w="320px")],
    "t3-graph", "t3-note", "600px")

page_4 = page(
    "4", "Treatment → Control Cascade",
    "The hypertension 'leaky pipeline' for one country: how much treatment "
    "coverage fails to become effective control.",
    [*region_income_controls("t4"),
     control("Country", dd("t4-country", COUNTRY_OPTIONS, DEFAULT_COUNTRY,
                           searchable=True), flex="1.8", min_w="200px"),
     control("Sex", sex_dd("t4-sex"), flex="1", min_w="120px"),
     year_control("t4-year")],
    "t4-graph", "t4-note", "640px")

page_5 = page(
    "5", "Region & Income Comparison",
    "Mean coverage across the six WHO regions and the World Bank income groups, "
    "with ±1 standard-deviation error bars.",
    [control("Indicator", dd("t5-indicator", INDICATOR_OPTIONS, DEFAULT_INDICATOR),
             flex="2.4", min_w="250px"),
     year_control("t5-year")],
    "t5-graph", "t5-note", "680px")

page_6 = page(
    "6", "Age-Standardized vs Crude",
    "How much cross-country variation is explained by population age structure "
    "versus genuine differences in care.",
    [control("Indicator family",
             dd("t6-family", INDICATOR_FAMILY_OPTIONS, "diabetes_treatment"),
             flex="1.6", min_w="240px"),
     control("Sex", sex_dd("t6-sex"), flex="1", min_w="120px"),
     year_control("t6-year"),
     *region_income_controls("t6"),
     control("Countries to compare", dcc.Dropdown(id="t6-countries", multi=True),
             flex="2.4", min_w="320px")],
    "t6-graph", "t6-note", "720px")


def sidebar():
    items = []
    for key, emoji, label, desc in SIDEBAR:
        items.append(html.Div(
            id=f"nav-{key}", n_clicks=0,
            className="side-item active" if key == "home" else "side-item",
            children=[
                html.Span(emoji, className="side-emoji"),
                html.Div([html.Div(label, className="side-label"),
                          html.Div(desc, className="side-sub")]),
            ],
        ))
    return html.Div(className="sidebar", children=[
        html.Div(className="side-brand", children=[
            html.Div("🩺", className="side-logo"),
            html.Div([html.Div("NCD OBSERVATORY", className="side-brand-name"),
                      html.Div("Care Inequality", className="side-brand-sub")]),
        ]),
        html.Div(className="side-nav", children=items),
        html.Div(className="side-foot", children=[
            html.Div("CS661 · Group 5"),
            html.Div("WHO Health Inequality Repository", className="side-foot-sub"),
        ]),
    ])


app.layout = html.Div(className="app-shell", children=[
    dcc.Store(id="active-page", data="home"),
    html.Div(id="resize-sink", style={"display": "none"}),
    sidebar(),
    html.Div(className="main", children=[
        home_page(), page_1, page_2, page_3, page_4, page_5, page_6,
    ]),
])


# =============================================================================
# 8. NAVIGATION
# =============================================================================

_PAGE_KEYS = ["home", "1", "2", "3", "4", "5", "6"]


@app.callback(
    Output("active-page", "data"),
    [Input(f"nav-{k}", "n_clicks") for k in _PAGE_KEYS],
    prevent_initial_call=True,
)
def set_active_page(*_clicks):
    triggered = callback_context.triggered_id
    if not triggered:
        raise PreventUpdate
    return triggered.split("-", 1)[1]


@app.callback(
    [Output(f"page-{k}", "style") for k in _PAGE_KEYS]
    + [Output(f"nav-{k}", "className") for k in _PAGE_KEYS],
    Input("active-page", "data"),
)
def render_active_page(active):
    styles = [{"display": "block" if k == active else "none"} for k in _PAGE_KEYS]
    classes = ["side-item active" if k == active else "side-item" for k in _PAGE_KEYS]
    return styles + classes


# Hidden graphs don't size correctly until a resize fires — nudge Plotly when
# the visible page changes.
app.clientside_callback(
    "function(v){ setTimeout(function(){ "
    "window.dispatchEvent(new Event('resize')); }, 80); return ''; }",
    Output("resize-sink", "children"),
    Input("active-page", "data"),
)


# =============================================================================
# 9. TASK 1 — GLOBAL MAP
# =============================================================================

@app.callback(
    Output("t1-graph", "figure"), Output("t1-note", "children"),
    Input("t1-indicator", "value"), Input("t1-sex", "value"),
    Input("t1-year", "value"), Input("t1-region", "value"), Input("t1-income", "value"),
)
def update_map(indicator, sex, year, region, income):
    pool = countries_in_scope(region, income)
    scoped = map_df[map_df["country"].isin(pool)]
    available = scoped.loc[
        (scoped["indicator_code"] == indicator) & (scoped["sex"] == sex), "year"]
    if available.empty:
        msg = f"No data available for {INDICATOR_LABELS[indicator]} ({sex})."
        return empty_selection_placeholder(msg), msg
    eff = year if year in available.values else int(
        min(available, key=lambda y: abs(y - year)))
    fig = _fig_map(indicator, eff, sex, region, income)
    note = f"{INDICATOR_LABELS[indicator]} · {sex} · {eff}"
    scope = scope_description(region, income)
    if scope != "Worldwide":
        note += f" · scope: {scope}"
    if eff != year:
        note += f" (no {year} data; showing nearest year)"
    return fig, note


# =============================================================================
# 10. TASK 2 — SEX GAP
# =============================================================================

@app.callback(
    Output("t2-country", "options"), Output("t2-country", "value"),
    Input("t2-indicator", "value"), Input("t2-region", "value"),
    Input("t2-income", "value"), State("t2-country", "value"),
)
def t2_country_options(indicator, region, income, current):
    avail = set(sex_gap_df.loc[sex_gap_df["indicator_code"] == indicator, "country"])
    pool = [c for c in countries_in_scope(region, income) if c in avail]
    options = [{"label": c, "value": c} for c in pool]
    return options, pick_scope_country(pool, current)


@app.callback(
    Output("t2-graph", "figure"), Output("t2-note", "children"),
    Input("t2-indicator", "value"), Input("t2-country", "value"),
)
def update_sex_gap(indicator, country):
    avail = sex_gap_df.loc[sex_gap_df["indicator_code"] == indicator, "country"].unique()
    if country is None or len(avail) == 0:
        msg = "No country available for this selection."
        return empty_selection_placeholder(msg, height=560), msg
    if country not in avail:
        country = sorted(avail)[0]
    fig = _fig_sexgap(indicator, country)
    note = f"{INDICATOR_LABELS[indicator]} · {country} · Male vs Female, 1990–latest"
    return fig, note


# =============================================================================
# 11. TASK 3 — TEMPORAL TREND
# =============================================================================

@app.callback(
    Output("t3-entities", "options"), Output("t3-entities", "value"),
    Input("t3-level", "value"), Input("t3-indicator", "value"),
    Input("t3-sex", "value"), Input("t3-region", "value"), Input("t3-income", "value"),
)
def t3_entity_options(level, indicator, sex, region, income):
    cfg = LEVEL_CONFIG[level]
    col, df = cfg["entity_column"], cfg["df"]
    if level == "country":
        subset = df[df["sex"] == sex].dropna(subset=[indicator])
        scope = set(countries_in_scope(region, income))
        subset = subset[subset[col].isin(scope)]
    else:
        subset = df[(df["indicator_code"] == indicator) & df["avg_value"].notna()]
    pool = sorted(subset[col].dropna().unique())
    options = [{"label": o, "value": o} for o in pool]
    if level == "country":
        default = [c for c in PREFERRED_COMPARISON_COUNTRIES if c in pool][:5] or pool[:3]
    else:
        default = pool[:4]
    return options, default


@app.callback(
    Output("t3-graph", "figure"), Output("t3-note", "children"),
    Input("t3-level", "value"), Input("t3-entities", "value"),
    Input("t3-indicator", "value"), Input("t3-sex", "value"),
)
def update_trend(level, entities, indicator, sex):
    cfg = LEVEL_CONFIG[level]
    entities = entities or []
    if not entities:
        note = f"Select at least one {cfg['level_name'].lower()} to compare."
        return empty_selection_placeholder(note, height=460), note
    fig = _fig_trend(level, indicator, tuple(entities),
                     sex if level == "country" else None)
    note = (f"{INDICATOR_LABELS[indicator]} · by {cfg['level_name']} · "
            f"{', '.join(entities)}")
    return fig, note


# =============================================================================
# 12. TASK 4 — CASCADE
# =============================================================================

@app.callback(
    Output("t4-country", "options"), Output("t4-country", "value"),
    Input("t4-region", "value"), Input("t4-income", "value"),
    State("t4-country", "value"),
)
def t4_country_options(region, income, current):
    avail = set(cascade_df["country"].unique())
    pool = [c for c in countries_in_scope(region, income) if c in avail]
    options = [{"label": c, "value": c} for c in pool]
    return options, pick_scope_country(pool, current)


@app.callback(
    Output("t4-graph", "figure"), Output("t4-note", "children"),
    Input("t4-country", "value"), Input("t4-sex", "value"), Input("t4-year", "value"),
)
def update_cascade(country, sex, year):
    if country is None:
        msg = "No country available for this selection."
        return empty_selection_placeholder(msg), msg
    subset = cascade_df[(cascade_df["country"] == country)
                        & (cascade_df["year"] == year)
                        & (cascade_df["sex"] == sex)]
    if subset.empty:
        avail = cascade_df.loc[(cascade_df["country"] == country)
                               & (cascade_df["sex"] == sex), "year"]
        if avail.empty:
            msg = f"No hypertension cascade data for {country}."
            return empty_selection_placeholder(msg), msg
        year = int(avail.max())
    fig = _fig_cascade(country, year, sex)
    row = cascade_df[(cascade_df["country"] == country)
                     & (cascade_df["year"] == year)
                     & (cascade_df["sex"] == sex)].iloc[0]
    note = (f"{country} · {sex} · {year} — Treatment {row['htn_tx_crude']:.1f}% → "
            f"Control {row['htn_ctrl_crude']:.1f}% (leakage {row['delta_leak']:.1f} pp)")
    return fig, note


# =============================================================================
# 13. TASK 5 — REGION & INCOME
# =============================================================================

@app.callback(
    Output("t5-graph", "figure"), Output("t5-note", "children"),
    Input("t5-indicator", "value"), Input("t5-year", "value"),
)
def update_region_income(indicator, year):
    available = region_income_df.loc[
        region_income_df["indicator_code"] == indicator, "year"]
    if available.empty:
        msg = f"No data available for {INDICATOR_LABELS[indicator]}."
        return empty_selection_placeholder(msg), msg
    eff = year if year in available.values else int(
        min(available, key=lambda y: abs(y - year)))
    fig = _fig_region(indicator, eff)
    note = f"{INDICATOR_LABELS[indicator]} · {eff} · WHO Region × World Bank Income Group"
    if eff != year:
        note += f" (no {year} data; showing nearest year)"
    return fig, note


# =============================================================================
# 14. TASK 6 — AGE-STANDARDIZED VS CRUDE
# =============================================================================

@app.callback(
    Output("t6-countries", "options"), Output("t6-countries", "value"),
    Input("t6-family", "value"), Input("t6-sex", "value"), Input("t6-year", "value"),
    Input("t6-region", "value"), Input("t6-income", "value"),
)
def t6_country_options(family, sex, year, region, income):
    crude_col, std_col = AGE_CRUDE_PAIRS[family]
    eff = _age_crude_effective_year(family, year, sex)
    if eff is None:
        return [], []
    subset = trend_country_df[(trend_country_df["year"] == eff)
                              & (trend_country_df["sex"] == sex)
                              ].dropna(subset=[crude_col, std_col])
    scope = set(countries_in_scope(region, income))
    pool = [c for c in sorted(subset["country"].unique()) if c in scope]
    options = [{"label": c, "value": c} for c in pool]
    default = [c for c in PREFERRED_COMPARISON_COUNTRIES if c in pool][:5] or pool[:5]
    return options, default


@app.callback(
    Output("t6-graph", "figure"), Output("t6-note", "children"),
    Input("t6-family", "value"), Input("t6-countries", "value"),
    Input("t6-sex", "value"), Input("t6-year", "value"),
)
def update_age_crude(family, countries, sex, year):
    countries = countries or []
    if not countries:
        note = "Select at least one country to compare."
        return empty_selection_placeholder(note, height=520), note
    eff = _age_crude_effective_year(family, year, sex)
    if eff is None:
        note = f"No data available for {INDICATOR_FAMILY_LABELS[family]} ({sex})."
        return empty_selection_placeholder(note, height=520), note
    crude_col, std_col = AGE_CRUDE_PAIRS[family]
    valid = set(trend_country_df[(trend_country_df["year"] == eff)
                                 & (trend_country_df["sex"] == sex)
                                 ].dropna(subset=[crude_col, std_col])["country"])
    countries = [c for c in countries if c in valid]
    if not countries:
        note = "Select at least one country to compare."
        return empty_selection_placeholder(note, height=520), note
    fig = _fig_agecrude(family, eff, sex, tuple(countries))
    note = (f"{INDICATOR_FAMILY_LABELS[family]} · {sex} · {eff} · "
            f"{', '.join(countries)}")
    if eff != year:
        note += f" (no {year} data; showing nearest year)"
    return fig, note


# =============================================================================
# 15. ENTRYPOINT
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("NCD Care Inequality Observatory — MARK 6 (sidebar layout)")
    print("=" * 70)
    print(f"Countries: {map_df['iso3'].nunique()} | Years: {YEAR_MIN}-{YEAR_MAX}")
    print("Open http://127.0.0.1:8055/ in your browser.")
    app.run(debug=True, port=8055)
