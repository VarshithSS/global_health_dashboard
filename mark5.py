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
app.title = "NCD Care Observatory · CS661 Group 5 · Mark 5"
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

      .view-title { font-size:19px; font-weight:800; color:var(--text); margin:0; }
      .view-note { font-size:13px; color:var(--text2); margin-top:5px; min-height:18px; }
    </style>
</head>
<body>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>"""


# =============================================================================
# 7. UI BUILDERS
# =============================================================================

NAV = [
    ("1", "Global Map", "Coverage choropleth by country"),
    ("2", "Sex Gap", "Male vs female disparity over time"),
    ("3", "Temporal Trend", "Coverage trajectories, 1990–2022"),
    ("4", "Care Cascade", "Treatment → effective control leakage"),
    ("5", "Region & Income", "WHO region × World Bank income"),
    ("6", "Standardized vs Crude", "How age structure skews raw burden"),
]

GRAPH_CONFIG = {"displayModeBar": True, "displaylogo": False, "responsive": True}


def kpi_tile(idx):
    return html.Div(
        className="kpi",
        children=[
            html.Div(id=f"kpi-{idx}-label", className="kpi-label"),
            html.Div(id=f"kpi-{idx}-value", className="kpi-value"),
            html.Div(id=f"kpi-{idx}-cap", className="kpi-cap"),
        ],
    )


def control(label, comp, flex="1", min_w="150px"):
    return html.Div([html.Label(label, className="ctl-label"), comp],
                    style={"flex": flex, "minWidth": min_w})


def nav_rail():
    items = []
    for i, (num, title, desc) in enumerate(NAV, start=1):
        items.append(html.Div(
            id=f"nav-{i}", n_clicks=0,
            className="nav-item active" if i == 1 else "nav-item",
            children=[
                html.Div(style={"display": "flex", "alignItems": "flex-start"}, children=[
                    html.Span(num, className="nav-num"),
                    html.Div([
                        html.Div(title, className="nav-title"),
                        html.Div(desc, className="nav-desc"),
                    ]),
                ]),
            ],
        ))
    # height:100% + the grid's stretch alignment makes the rail match the
    # content panel's height (issue #2).
    return html.Div(items, className="card", style={
        "padding": "14px", "height": "100%",
    })


def view_panel(index, graph_id, note_id, height, extra_controls=None):
    inner = []
    inner.append(html.Div([
        html.H2(NAV[index - 1][1], className="view-title"),
        html.Div(id=note_id, className="view-note"),
    ], style={"marginBottom": "14px"}))
    if extra_controls is not None:
        inner.append(extra_controls)
    inner.append(dcc.Loading(
        type="circle", color=C["accent"],
        children=[dcc.Graph(id=graph_id, config=GRAPH_CONFIG,
                            style={"height": height})],
    ))
    return html.Div(
        id=f"panel-{index}", className="card",
        style={"padding": "22px 24px",
               "display": "block" if index == 1 else "none"},
        children=inner,
    )


def trend_controls():
    return html.Div(
        style={"display": "flex", "gap": "22px", "flexWrap": "wrap",
               "marginBottom": "16px"},
        children=[
            control("Compare by", dcc.RadioItems(
                id="trend-level",
                options=[{"label": "Country", "value": "country"},
                         {"label": "WHO Region", "value": "region"},
                         {"label": "Income Group", "value": "income"}],
                value="country", inline=True, className="radio-row",
            ), flex="1", min_w="260px"),
            control("Entities to compare",
                    dcc.Dropdown(id="trend-entities", multi=True),
                    flex="2", min_w="320px"),
        ],
    )


def agecrude_controls():
    return html.Div(
        style={"display": "flex", "gap": "22px", "flexWrap": "wrap",
               "marginBottom": "16px"},
        children=[
            control("Indicator family", dcc.Dropdown(
                id="age-crude-family", options=INDICATOR_FAMILY_OPTIONS,
                value="diabetes_treatment", clearable=False),
                flex="1", min_w="260px"),
            control("Countries to compare",
                    dcc.Dropdown(id="age-crude-countries", multi=True),
                    flex="2", min_w="320px"),
        ],
    )


def command_bar():
    return html.Div(
        className="card",
        style={"padding": "16px 20px", "marginBottom": "18px",
               "position": "sticky", "top": "12px", "zIndex": "50",
               "backdropFilter": "blur(6px)"},
        children=[html.Div(
            style={"display": "flex", "gap": "20px", "alignItems": "flex-end",
                   "flexWrap": "wrap"},
            children=[
                control("Indicator", dcc.Dropdown(
                    id="f-indicator", options=INDICATOR_OPTIONS,
                    value=DEFAULT_INDICATOR, clearable=False),
                    flex="2.4", min_w="250px"),
                control("Sex", dcc.Dropdown(
                    id="f-sex",
                    options=[{"label": "Male", "value": "Male"},
                             {"label": "Female", "value": "Female"}],
                    value=DEFAULT_SEX, clearable=False), flex="1", min_w="120px"),
                control("WHO Region", dcc.Dropdown(
                    id="f-region", options=REGION_OPTIONS,
                    value=DEFAULT_REGION, clearable=False), flex="1.6", min_w="170px"),
                control("Income Group", dcc.Dropdown(
                    id="f-income", options=INCOME_OPTIONS,
                    value=DEFAULT_INCOME, clearable=False), flex="1.6", min_w="170px"),
                control("Country", dcc.Dropdown(
                    id="f-country", options=COUNTRY_OPTIONS, value=DEFAULT_COUNTRY,
                    clearable=False, searchable=True), flex="1.8", min_w="190px"),
                control("Year", html.Div(dcc.Slider(
                    id="f-year", min=YEAR_MIN, max=YEAR_MAX, step=1,
                    value=DEFAULT_YEAR, marks=YEAR_MARKS,
                    tooltip={"placement": "top", "always_visible": True},
                    updatemode="mouseup"),
                    style={"paddingTop": "14px"}), flex="3", min_w="330px"),
                html.Div([html.Label(" ", className="ctl-label"),
                          html.Button("↺ Reset", id="f-reset", n_clicks=0,
                                      className="btn")],
                         style={"flex": "0 0 auto"}),
            ],
        )],
    )


def header():
    return html.Div(
        style={"display": "flex", "justifyContent": "space-between",
               "alignItems": "center", "flexWrap": "wrap", "gap": "16px",
               "marginBottom": "20px"},
        children=[
            html.Div(style={"display": "flex", "alignItems": "center", "gap": "16px"},
                     children=[
                html.Div(style={
                    "width": "46px", "height": "46px", "borderRadius": "13px",
                    "background": "linear-gradient(140deg,#2dd4bf,#3b82f6)",
                    "display": "flex", "alignItems": "center",
                    "justifyContent": "center", "fontSize": "24px",
                    "boxShadow": "0 8px 24px rgba(45,212,191,0.28)"}, children="🩺"),
                html.Div([
                    html.Div("NCD CARE INEQUALITY OBSERVATORY", style={
                        "fontSize": "19px", "fontWeight": "800",
                        "letterSpacing": "0.02em", "color": C["text"]}),
                    html.Div("Diabetes & hypertension: who gets treated, "
                             "who gets controlled — and the gap between",
                             style={"fontSize": "13px", "color": C["text2"],
                                    "marginTop": "2px"}),
                ]),
            ]),
            html.Div(style={"display": "flex", "gap": "10px", "flexWrap": "wrap"},
                     children=[
                html.Span([html.Span(className="dot"),
                           "WHO Health Inequality Repository"], className="chip"),
                html.Span("diabetes 1990–2022 · hypertension 1990–2019",
                          className="chip"),
                html.Span("CS661 · Group 5", className="chip"),
            ]),
        ],
    )


app.layout = html.Div(
    style={"minHeight": "100vh", "padding": "26px 34px 56px",
           "maxWidth": "1680px", "margin": "0 auto"},
    children=[
        dcc.Store(id="global-filters", data={
            "indicator": DEFAULT_INDICATOR, "sex": DEFAULT_SEX,
            "region": DEFAULT_REGION, "income": DEFAULT_INCOME,
            "country": DEFAULT_COUNTRY, "year": DEFAULT_YEAR,
        }),
        dcc.Store(id="active-view", data=1),
        html.Div(id="resize-sink", style={"display": "none"}),

        header(),

        # KPI insight strip
        html.Div(
            style={"display": "grid",
                   "gridTemplateColumns": "repeat(4, minmax(0, 1fr))",
                   "gap": "16px", "marginBottom": "18px"},
            children=[kpi_tile(i) for i in range(1, 5)],
        ),

        command_bar(),

        # Nav rail + content
        html.Div(
            style={"display": "grid", "gridTemplateColumns": "268px 1fr",
                   "gap": "20px", "alignItems": "stretch"},
            children=[
                nav_rail(),
                html.Div(children=[
                    view_panel(1, "map-graph", "map-note", "600px"),
                    view_panel(2, "sexgap-graph", "sexgap-note", "700px"),
                    view_panel(3, "trend-graph", "trend-note", "600px",
                               extra_controls=trend_controls()),
                    view_panel(4, "cascade-graph", "cascade-note", "640px"),
                    view_panel(5, "region-income-graph", "region-income-note", "680px"),
                    view_panel(6, "age-crude-graph", "age-crude-note", "720px",
                               extra_controls=agecrude_controls()),
                ]),
            ],
        ),

        html.Div(
            "WHO Health Inequality Data Repository (Health Care System & Access "
            "module) · six NCD indicators, ~71k rows · Mark 5 UI · "
            "CS661 Group 5",
            style={"marginTop": "26px", "textAlign": "center",
                   "fontSize": "12px", "color": C["muted"]},
        ),
    ],
)


# =============================================================================
# 8. FILTER REDUCER  (identical linked-state logic to Mark 1)
# =============================================================================

@app.callback(
    Output("global-filters", "data"),
    Output("f-country", "value"),
    Output("f-country", "options"),
    Output("f-region", "value"),
    Output("f-income", "value"),
    Output("f-year", "value"),
    Input("f-indicator", "value"),
    Input("f-sex", "value"),
    Input("f-region", "value"),
    Input("f-income", "value"),
    Input("f-country", "value"),
    Input("f-year", "value"),
    Input("map-graph", "clickData"),
    Input("trend-graph", "clickData"),
    Input("age-crude-graph", "clickData"),
    Input("sexgap-graph", "clickData"),
    Input("region-income-graph", "clickData"),
    State("trend-level", "value"),
    State("global-filters", "data"),
)
def sync_global_filters(indicator, sex, region, income, country, year,
                        map_click, trend_click, agecrude_click, sexgap_click,
                        regincome_click, trend_level, current):
    triggered = callback_context.triggered_id
    region = region or ALL_TOKEN
    income = income or ALL_TOKEN

    if (triggered == "region-income-graph"
            and regincome_click and regincome_click.get("points")):
        point = regincome_click["points"][0]
        clicked_region = point.get("x")
        custom = point.get("customdata")
        if clicked_region in WHO_REGIONS:
            region = clicked_region
        if custom and len(custom) >= 4 and custom[3] in INCOME_GROUPS:
            income = custom[3]

    if triggered == "map-graph" and map_click and map_click.get("points"):
        clicked_iso3 = map_click["points"][0].get("location")
        match = map_df.loc[map_df["iso3"] == clicked_iso3, "country"]
        if not match.empty:
            country = match.iloc[0]

    if (triggered == "age-crude-graph"
            and agecrude_click and agecrude_click.get("points")):
        custom = agecrude_click["points"][0].get("customdata")
        if custom:
            country = custom[0]

    if (triggered == "trend-graph"
            and trend_click and trend_click.get("points")):
        point = trend_click["points"][0]
        if point.get("x") is not None:
            year = point["x"]
        if trend_level == "country":
            custom = point.get("customdata")
            if custom:
                country = custom if isinstance(custom, str) else custom[0]

    if (triggered == "sexgap-graph"
            and sexgap_click and sexgap_click.get("points")):
        clicked_year = sexgap_click["points"][0].get("y")
        if clicked_year is not None:
            year = clicked_year

    pool = countries_in_scope(region, income)
    country_options = [{"label": c, "value": c} for c in pool]
    country = pick_scope_country(pool, country)

    new_state = {
        "indicator": indicator, "sex": sex, "region": region, "income": income,
        "country": country, "year": int(year),
    }
    return new_state, country, country_options, region, income, int(year)


@app.callback(
    Output("f-indicator", "value"),
    Output("f-sex", "value"),
    Output("f-region", "value", allow_duplicate=True),
    Output("f-income", "value", allow_duplicate=True),
    Output("f-country", "value", allow_duplicate=True),
    Output("f-year", "value", allow_duplicate=True),
    Input("f-reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_filters(n_clicks):
    if not n_clicks:
        raise PreventUpdate
    return (DEFAULT_INDICATOR, DEFAULT_SEX, DEFAULT_REGION,
            DEFAULT_INCOME, DEFAULT_COUNTRY, DEFAULT_YEAR)


# =============================================================================
# 9. NAVIGATION  (rail -> active view, toggle panels, nudge Plotly to resize)
# =============================================================================

@app.callback(
    Output("active-view", "data"),
    [Input(f"nav-{i}", "n_clicks") for i in range(1, 7)],
    prevent_initial_call=True,
)
def set_active_view(*_clicks):
    triggered = callback_context.triggered_id
    if not triggered:
        raise PreventUpdate
    return int(triggered.split("-")[1])


@app.callback(
    [Output(f"panel-{i}", "style") for i in range(1, 7)]
    + [Output(f"nav-{i}", "className") for i in range(1, 7)],
    Input("active-view", "data"),
)
def render_active_view(active):
    styles, classes = [], []
    for i in range(1, 7):
        styles.append({"padding": "22px 24px",
                       "display": "block" if i == active else "none"})
        classes.append("nav-item active" if i == active else "nav-item")
    return styles + classes


# Hidden graphs don't resize until a resize event fires — dispatch one when the
# active view changes so Plotly repaints the newly shown panel at full width.
app.clientside_callback(
    "function(v){ setTimeout(function(){ "
    "window.dispatchEvent(new Event('resize')); }, 80); return ''; }",
    Output("resize-sink", "children"),
    Input("active-view", "data"),
)


# =============================================================================
# 10. KPI INSIGHT STRIP
# =============================================================================

@app.callback(
    Output("kpi-1-label", "children"), Output("kpi-1-value", "children"),
    Output("kpi-1-cap", "children"),
    Output("kpi-2-label", "children"), Output("kpi-2-value", "children"),
    Output("kpi-2-cap", "children"),
    Output("kpi-3-label", "children"), Output("kpi-3-value", "children"),
    Output("kpi-3-cap", "children"),
    Output("kpi-4-label", "children"), Output("kpi-4-value", "children"),
    Output("kpi-4-cap", "children"),
    Input("global-filters", "data"),
)
def update_kpis(f):
    indicator, sex, year = f["indicator"], f["sex"], f["year"]
    region, income = f.get("region", ALL_TOKEN), f.get("income", ALL_TOKEN)
    pool = countries_in_scope(region, income)
    pool_set = set(pool)
    dash = html.Span("—", style={"color": C["muted"]})

    def val(num, unit):
        return [f"{num:.1f}", html.Span(unit, className="unit")]

    # Tile 1 — mean coverage across in-scope countries.
    m = map_df[(map_df["indicator_code"] == indicator)
               & (map_df["sex"] == sex)
               & (map_df["country"].isin(pool_set))]
    eff1 = _nearest_year(m["year"], year)
    if eff1 is None:
        k1v, k1c = dash, "no data for this selection"
    else:
        mean_cov = m[m["year"] == eff1]["value"].mean()
        k1v = val(mean_cov, "%")
        k1c = f"{sex} · {eff1}" + ("" if eff1 == year else f" (nearest to {year})")

    # Tile 2 — countries in view.
    k2v = [f"{len(pool)}"]
    k2c = scope_description(region, income)

    # Tile 3 — widest sex gap among in-scope countries.
    sg = sex_gap_df[(sex_gap_df["indicator_code"] == indicator)
                    & (sex_gap_df["country"].isin(pool_set))]
    eff3 = _nearest_year(sg["year"], year)
    if eff3 is None or sg.empty:
        k3v, k3c = dash, "no data for this selection"
    else:
        row = sg[sg["year"] == eff3]
        idx = row["delta_sex"].abs().idxmax()
        gap = float(row.loc[idx, "delta_sex"])
        who = "M" if gap > 0 else "F"
        k3v = [f"{gap:+.1f}", html.Span("pp", className="unit")]
        k3c = f"{row.loc[idx, 'country']} · {eff3} · favours {who}"

    # Tile 4 — mean hypertension treatment→control leakage.
    cas = cascade_df[(cascade_df["sex"] == sex)
                     & (cascade_df["country"].isin(pool_set))]
    eff4 = _nearest_year(cas["year"], year)
    if eff4 is None or cas.empty:
        k4v, k4c = dash, "no data for this selection"
    else:
        leak = cas[cas["year"] == eff4]["delta_leak"].mean()
        k4v = [f"{leak:.1f}", html.Span("pp", className="unit")]
        k4c = f"Hypertension · {sex} · {eff4}"

    return (
        "Mean coverage", k1v, k1c,
        "Countries in view", k2v, k2c,
        "Widest sex gap", k3v, k3c,
        "Avg care leakage", k4v, k4c,
    )


# =============================================================================
# 11. VIEW CALLBACKS  (same logic as Mark 1, Mark 2 themed builders)
# =============================================================================

@app.callback(
    Output("map-graph", "figure"), Output("map-note", "children"),
    Input("global-filters", "data"),
)
def update_map(filters):
    indicator, sex, year = filters["indicator"], filters["sex"], filters["year"]
    region, income = filters.get("region", ALL_TOKEN), filters.get("income", ALL_TOKEN)
    pool = countries_in_scope(region, income)
    scoped = map_df[map_df["country"].isin(pool)]

    available_years = scoped.loc[
        (scoped["indicator_code"] == indicator) & (scoped["sex"] == sex), "year"]
    if available_years.empty:
        msg = f"No data available for {INDICATOR_LABELS[indicator]} ({sex})."
        return empty_selection_placeholder(msg), msg
    if year not in available_years.values:
        year = int(min(available_years, key=lambda y: abs(y - year)))

    fig = _fig_map(indicator, year, sex, region, income)
    note = (f"{INDICATOR_LABELS[indicator]} · {sex} · {year} — "
            f"click a country to select it everywhere")
    scope_bits = scope_description(region, income)
    if scope_bits != "Worldwide":
        note += f" · scope: {scope_bits}"
    if year != filters["year"]:
        note += f" (no {filters['year']} data; showing nearest year)"
    return fig, note


@app.callback(
    Output("sexgap-graph", "figure"), Output("sexgap-note", "children"),
    Input("global-filters", "data"),
)
def update_sex_gap(filters):
    country, indicator = filters["country"], filters["indicator"]
    available = sex_gap_df.loc[
        sex_gap_df["indicator_code"] == indicator, "country"].unique()
    if country not in available:
        country = sorted(available)[0]
    fig = _fig_sexgap(indicator, country)
    note = f"{INDICATOR_LABELS[indicator]} · {country} · Male vs Female, 1990–latest"
    return fig, note


LEVEL_CONFIG = {
    "country": dict(df=trend_country_df, entity_column="country", level_name="Country"),
    "region": dict(df=trend_region_df, entity_column="who_region", level_name="WHO Region"),
    "income": dict(df=trend_income_df, entity_column="income_group", level_name="Income Group"),
}


@app.callback(
    Output("trend-entities", "options"), Output("trend-entities", "value"),
    Input("trend-level", "value"), Input("global-filters", "data"),
)
def update_trend_entity_options(level, filters):
    cfg = LEVEL_CONFIG[level]
    col, df = cfg["entity_column"], cfg["df"]
    indicator = filters["indicator"]

    if level == "country":
        subset = df[df["sex"] == filters["sex"]].dropna(subset=[indicator])
        scope = set(countries_in_scope(
            filters.get("region", ALL_TOKEN), filters.get("income", ALL_TOKEN)))
        subset = subset[subset[col].isin(scope)]
    else:
        subset = df[(df["indicator_code"] == indicator) & df["avg_value"].notna()]

    options_pool = sorted(subset[col].dropna().unique())
    options = [{"label": o, "value": o} for o in options_pool]

    if level == "country":
        default = [c for c in PREFERRED_COMPARISON_COUNTRIES if c in options_pool]
        if filters["country"] in options_pool and filters["country"] not in default:
            default = [filters["country"]] + default
        default = default[:5] or options_pool[:3]
    else:
        default = options_pool[:4]
    return options, default


@app.callback(
    Output("trend-graph", "figure"), Output("trend-note", "children"),
    Input("trend-level", "value"), Input("trend-entities", "value"),
    Input("global-filters", "data"),
)
def update_trend(level, entities, filters):
    cfg = LEVEL_CONFIG[level]
    entities = entities or []
    if not entities:
        note = f"Select at least one {cfg['level_name'].lower()} to compare."
        return empty_selection_placeholder(note, height=460), note
    fig = _fig_trend(level, filters["indicator"], tuple(entities),
                     filters["sex"] if level == "country" else None)
    note = (f"{INDICATOR_LABELS[filters['indicator']]} · by {cfg['level_name']} · "
            f"{', '.join(entities)}")
    return fig, note


@app.callback(
    Output("cascade-graph", "figure"), Output("cascade-note", "children"),
    Input("global-filters", "data"),
)
def update_cascade(filters):
    country, year, sex = filters["country"], filters["year"], filters["sex"]
    subset = cascade_df[(cascade_df["country"] == country)
                        & (cascade_df["year"] == year)
                        & (cascade_df["sex"] == sex)]
    if subset.empty:
        available_years = cascade_df.loc[
            (cascade_df["country"] == country) & (cascade_df["sex"] == sex), "year"]
        if available_years.empty:
            msg = f"No hypertension cascade data for {country}."
            return empty_selection_placeholder(msg), msg
        year = int(available_years.max())

    fig = _fig_cascade(country, year, sex)
    row = cascade_df[(cascade_df["country"] == country)
                     & (cascade_df["year"] == year)
                     & (cascade_df["sex"] == sex)].iloc[0]
    note = (f"{country} · {sex} · {year} — Treatment {row['htn_tx_crude']:.1f}% → "
            f"Control {row['htn_ctrl_crude']:.1f}% "
            f"(leakage {row['delta_leak']:.1f} pp)")
    return fig, note


@app.callback(
    Output("region-income-graph", "figure"),
    Output("region-income-note", "children"),
    Input("global-filters", "data"),
)
def update_region_income(filters):
    indicator, year = filters["indicator"], filters["year"]
    available_years = region_income_df.loc[
        region_income_df["indicator_code"] == indicator, "year"]
    if available_years.empty:
        msg = f"No data available for {INDICATOR_LABELS[indicator]}."
        return empty_selection_placeholder(msg), msg
    if year not in available_years.values:
        year = int(min(available_years, key=lambda y: abs(y - year)))

    fig = _fig_region(indicator, year)
    note = f"{INDICATOR_LABELS[indicator]} · {year} · WHO Region × World Bank Income Group"
    if year != filters["year"]:
        note += f" (no {filters['year']} data; showing nearest year)"
    return fig, note


@app.callback(
    Output("age-crude-countries", "options"), Output("age-crude-countries", "value"),
    Input("age-crude-family", "value"), Input("global-filters", "data"),
)
def update_age_crude_options(family, filters):
    crude_col, std_col = AGE_CRUDE_PAIRS[family]
    eff_year = _age_crude_effective_year(family, filters["year"], filters["sex"])
    if eff_year is None:
        return [], []
    subset = trend_country_df[(trend_country_df["year"] == eff_year)
                              & (trend_country_df["sex"] == filters["sex"])
                              ].dropna(subset=[crude_col, std_col])
    scope = set(countries_in_scope(
        filters.get("region", ALL_TOKEN), filters.get("income", ALL_TOKEN)))
    pool = [c for c in sorted(subset["country"].unique()) if c in scope]
    options = [{"label": c, "value": c} for c in pool]

    default = [c for c in PREFERRED_COMPARISON_COUNTRIES if c in pool]
    if filters["country"] not in default and filters["country"] in pool:
        default = [filters["country"]] + default
    default = default[:5] or pool[:5]
    return options, default


@app.callback(
    Output("age-crude-graph", "figure"), Output("age-crude-note", "children"),
    Input("age-crude-family", "value"), Input("age-crude-countries", "value"),
    Input("global-filters", "data"),
)
def update_age_crude(family, countries, filters):
    countries = countries or []
    if not countries:
        note = "Select at least one country to compare."
        return empty_selection_placeholder(note, height=520), note

    eff_year = _age_crude_effective_year(family, filters["year"], filters["sex"])
    if eff_year is None:
        note = (f"No data available for {INDICATOR_FAMILY_LABELS[family]} "
                f"({filters['sex']}).")
        return empty_selection_placeholder(note, height=520), note

    crude_col, std_col = AGE_CRUDE_PAIRS[family]
    valid = set(trend_country_df[(trend_country_df["year"] == eff_year)
                                 & (trend_country_df["sex"] == filters["sex"])
                                 ].dropna(subset=[crude_col, std_col])["country"])
    countries = [c for c in countries if c in valid]
    if not countries:
        note = "Select at least one country to compare."
        return empty_selection_placeholder(note, height=520), note

    fig = _fig_agecrude(family, eff_year, filters["sex"], tuple(countries))
    note = (f"{INDICATOR_FAMILY_LABELS[family]} · {filters['sex']} · {eff_year} · "
            f"{', '.join(countries)}")
    if eff_year != filters["year"]:
        note += f" (no {filters['year']} data; showing nearest year)"
    return fig, note


# =============================================================================
# 12. ENTRYPOINT
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("NCD Care Inequality Observatory — MARK 5 UI")
    print("=" * 70)
    print(f"Countries: {map_df['iso3'].nunique()} | Years: {YEAR_MIN}-{YEAR_MAX}")
    print("Open http://127.0.0.1:8054/ in your browser.")
    app.run(debug=True, port=8054)
