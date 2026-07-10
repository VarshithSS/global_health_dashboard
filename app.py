"""
CS661 Group-5 — Global Diabetes & Hypertension Care Inequality Dashboard
=========================================================================

Single-page Dash app that merges all six visualization tasks into one
linked dashboard, per Section 5 of the project proposal:

    "Selections made in one view (e.g., clicking a country on the map)
    will update the other linked views, enabling users to drill down
    from a global overview to country-level detail."

Architecture
------------
- ONE Dash app, ONE server, ONE layout (tabs, not separate scripts).
- A global filter bar (Indicator, Sex, Year, Country) sits above the tabs.
  Its state lives in a dcc.Store ("global-filters") that every tab reads.
- Clicking a country on the Task 1 map updates the global Country
  dropdown, which cascades into Tasks 2, 3, 4, and 6 automatically.
- Task 6 keeps a local "indicator family" control because it uses a
  different taxonomy (paired crude/std columns) than the other tabs'
  6-way indicator_code scheme.
- Task 5 has no sex breakdown in its source data (region_income_summary.csv
  is pre-aggregated across sex), so it only listens to Indicator + Year.

Run with:  python app.py
Then open: http://127.0.0.1:8050/
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
# 1. PATHS & DATA LOADING
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

sex_gap_df = _load_csv(
    "sex_gap_data.csv", numeric_cols=["Male", "Female", "delta_sex"]
)
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
# 2. SHARED LABELS / CONSTANTS
# =============================================================================

# INDICATOR_LABELS / INDICATOR_FAMILY_LABELS are imported from
# visualizations.labels so the app and every chart share one definition.
INDICATOR_OPTIONS = [
    {"label": label, "value": code} for code, label in INDICATOR_LABELS.items()
]

INDICATOR_FAMILY_OPTIONS = [
    {"label": label, "value": code} for code, label in INDICATOR_FAMILY_LABELS.items()
]

# Crude/standardized column pair for each indicator family (Task 6).
AGE_CRUDE_PAIRS = {
    "diabetes_treatment": ("diab_tx_crude", "diab_tx_std"),
    "hypertension_treatment": ("htn_tx_crude", "htn_tx_std"),
    "hypertension_control": ("htn_ctrl_crude", "htn_ctrl_std"),
}

ALL_COUNTRIES = sorted(map_df["country"].dropna().unique())
COUNTRY_OPTIONS = [{"label": c, "value": c} for c in ALL_COUNTRIES]

# WHO region and World Bank income-group filters scope the *country universe*:
# selecting one narrows the Country dropdown, the map, and the multi-select
# comparison tabs to matching countries. ALL_TOKEN is the "no filter" sentinel.
ALL_TOKEN = "All"

WHO_REGIONS = sorted(map_df["who_region"].dropna().unique())

# World Bank income groups in their natural ladder, not alphabetical.
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

# IMPORTANT: cast every year to a native Python int. pandas.unique() returns
# numpy.int64 values, and Dash's dcc.Slider serializes `marks` to JSON via
# Flask's jsonify, which chokes on numpy int64 dict keys ("keys must be str,
# int, float, bool or None, not numpy.int64"). Casting here, once, avoids
# needing to remember to do it in every callback that touches years.
ALL_YEARS = sorted(int(y) for y in map_df["year"].dropna().unique())
YEAR_MIN, YEAR_MAX = min(ALL_YEARS), max(ALL_YEARS)
YEAR_MARKS = {
    int(y): str(int(y)) for y in ALL_YEARS if y in (YEAR_MIN, YEAR_MAX) or y % 5 == 0
}

DEFAULT_INDICATOR = "diab_tx_std"
DEFAULT_SEX = "Female"
DEFAULT_YEAR = YEAR_MAX
DEFAULT_COUNTRY = "India" if "India" in ALL_COUNTRIES else ALL_COUNTRIES[0]
DEFAULT_REGION = ALL_TOKEN
DEFAULT_INCOME = ALL_TOKEN


def nearest_available_year(available_years, year):
    """
    Given a pandas Series/array of years that actually have data for some
    indicator (+sex) slice, return the closest year to the requested one.
    Returns None if no years are available at all.

    Several indicator families are only reported through an earlier year
    than others (hypertension currently ends in 2019, diabetes in 2022),
    but the global year slider spans the full combined range. This keeps
    every tab from crashing/going blank when that mismatch is hit.
    """
    if len(available_years) == 0:
        return None
    if year in set(available_years):
        return int(year)
    return int(min(available_years, key=lambda y: abs(y - year)))

PREFERRED_COMPARISON_COUNTRIES = [
    "India", "China", "Brazil", "United States of America", "Japan",
]


def countries_in_scope(region, income):
    """Countries matching the current WHO-region / income-group scope.

    Both default to ALL_TOKEN ("no filter"). The membership is derived from
    map_df, which carries who_region and income_group for every country.
    """
    d = map_df
    if region and region != ALL_TOKEN:
        d = d[d["who_region"] == region]
    if income and income != ALL_TOKEN:
        d = d[d["income_group"] == income]
    return sorted(d["country"].dropna().unique())


def pick_scope_country(pool, current):
    """Keep the current country if it's still in scope, else fall back to a
    sensible in-scope default (a preferred comparison country, or the first)."""
    if current in pool:
        return current
    for c in PREFERRED_COMPARISON_COUNTRIES:
        if c in pool:
            return c
    return pool[0] if pool else None

COLORS = {
    "bg": "#0f1420",
    "panel": "#161d2e",
    "accent": "#4fd1c5",
    "text": "#e6e9f0",
    "muted": "#8892a6",
    "border": "#26304a",
}


# =============================================================================
# 3. APP
# =============================================================================

app = Dash(__name__, suppress_callback_exceptions=True)
app.title = "Global NCD Care Inequality Dashboard"
server = app.server  # for deployment (gunicorn etc.)


def empty_selection_placeholder(message, height=500):
    """
    A blank figure with a centered message, shown instead of crashing when
    a required multi-select (e.g. "Countries to compare") is emptied out.
    Both create_temporal_trend_chart and create_age_standardized_crude_chart
    raise ValueError on an empty entity/country list, so callbacks check
    for that before calling them rather than letting the exception surface
    as a 500 in the browser.
    """
    fig = go.Figure()
    fig.update_layout(
        height=height,
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[{
            "text": message,
            "xref": "paper", "yref": "paper",
            "x": 0.5, "y": 0.5,
            "showarrow": False,
            "font": {"size": 15, "color": COLORS["muted"]},
        }],
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def control_label(text):
    return html.Label(
        text,
        style={
            "fontWeight": "600",
            "fontSize": "12px",
            "letterSpacing": "0.05em",
            "textTransform": "uppercase",
            "color": COLORS["muted"],
            "display": "block",
            "marginBottom": "6px",
        },
    )


def filter_bar():
    """Global filter bar shared across every tab."""
    return html.Div(
        children=[
            html.Div(
                [
                    control_label("Indicator"),
                    dcc.Dropdown(
                        id="f-indicator",
                        options=INDICATOR_OPTIONS,
                        value=DEFAULT_INDICATOR,
                        clearable=False,
                    ),
                ],
                style={"flex": "2", "minWidth": "260px"},
            ),
            html.Div(
                [
                    control_label("Sex"),
                    dcc.Dropdown(
                        id="f-sex",
                        options=[{"label": "Male", "value": "Male"},
                                 {"label": "Female", "value": "Female"}],
                        value=DEFAULT_SEX,
                        clearable=False,
                    ),
                ],
                style={"flex": "1", "minWidth": "140px"},
            ),
            html.Div(
                [
                    control_label("WHO Region"),
                    dcc.Dropdown(
                        id="f-region",
                        options=REGION_OPTIONS,
                        value=DEFAULT_REGION,
                        clearable=False,
                    ),
                ],
                style={"flex": "2", "minWidth": "190px"},
            ),
            html.Div(
                [
                    control_label("Income Group"),
                    dcc.Dropdown(
                        id="f-income",
                        options=INCOME_OPTIONS,
                        value=DEFAULT_INCOME,
                        clearable=False,
                    ),
                ],
                style={"flex": "2", "minWidth": "190px"},
            ),
            html.Div(
                [
                    control_label("Country"),
                    dcc.Dropdown(
                        id="f-country",
                        options=COUNTRY_OPTIONS,
                        value=DEFAULT_COUNTRY,
                        clearable=False,
                        searchable=True,
                    ),
                ],
                style={"flex": "2", "minWidth": "220px"},
            ),
            html.Div(
                [
                    control_label("Year"),
                    html.Div(
                        [
                            html.Button(
                                "▶ Play",
                                id="year-play",
                                n_clicks=0,
                                style={
                                    "background": COLORS["panel"],
                                    "color": COLORS["accent"],
                                    "border": f"1px solid {COLORS['accent']}",
                                    "borderRadius": "6px",
                                    "padding": "6px 12px",
                                    "fontSize": "13px",
                                    "fontWeight": "600",
                                    "cursor": "pointer",
                                    "whiteSpace": "nowrap",
                                },
                            ),
                            html.Div(
                                dcc.Slider(
                                    id="f-year",
                                    min=YEAR_MIN,
                                    max=YEAR_MAX,
                                    step=1,
                                    value=DEFAULT_YEAR,
                                    marks=YEAR_MARKS,
                                    tooltip={"placement": "bottom",
                                             "always_visible": True},
                                    updatemode="mouseup",
                                ),
                                style={"flex": "1"},
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center",
                               "gap": "14px"},
                    ),
                    # Drives the year forward while "Play" is active (A3).
                    dcc.Interval(id="year-interval", interval=1100,
                                 n_intervals=0, disabled=True),
                ],
                style={"flex": "3", "minWidth": "360px", "paddingTop": "2px"},
            ),
            html.Div(
                [
                    control_label(" "),  # spacer to align button with dropdowns
                    html.Button(
                        "↺ Reset",
                        id="f-reset",
                        n_clicks=0,
                        style={
                            "background": COLORS["panel"],
                            "color": COLORS["muted"],
                            "border": f"1px solid {COLORS['border']}",
                            "borderRadius": "6px",
                            "padding": "7px 14px",
                            "fontSize": "13px",
                            "fontWeight": "600",
                            "cursor": "pointer",
                            "whiteSpace": "nowrap",
                        },
                    ),
                ],
                style={"flex": "0 0 auto", "minWidth": "100px"},
            ),
        ],
        style={
            "display": "flex",
            "gap": "24px",
            "alignItems": "flex-start",
            "flexWrap": "wrap",
            "background": COLORS["panel"],
            "border": f"1px solid {COLORS['border']}",
            "borderRadius": "10px",
            "padding": "18px 22px",
            "marginBottom": "18px",
        },
    )


def graph_card(graph_id, note_id=None, height="640px", extra_controls=None):
    children = []
    if extra_controls is not None:
        children.append(extra_controls)
    if note_id is not None:
        children.append(
            html.Div(
                id=note_id,
                style={
                    "textAlign": "center",
                    "fontSize": "13px",
                    "color": COLORS["muted"],
                    "marginBottom": "8px",
                },
            )
        )
    children.append(
        dcc.Loading(
            type="circle",
            color=COLORS["accent"],
            children=[
                dcc.Graph(
                    id=graph_id,
                    config={"displayModeBar": True, "displaylogo": False,
                            "responsive": True},
                    style={"height": height},
                )
            ],
        )
    )
    return html.Div(
        children=children,
        style={
            "background": COLORS["panel"],
            "border": f"1px solid {COLORS['border']}",
            "borderRadius": "10px",
            "padding": "16px 20px",
        },
    )


# =============================================================================
# 3b. TAB LAYOUTS
# =============================================================================
# Defined here (before app.layout) because app.layout now calls these
# directly to build each dcc.Tab's children, instead of a callback that
# lazily swapped content into a shared Div.

def tab1_layout():
    return graph_card("map-graph", note_id="map-note", height="640px")


def tab2_layout():
    return graph_card("sexgap-graph", note_id="sexgap-note", height="720px")


def tab3_layout():
    controls = html.Div(
        [
            html.Div(
                [
                    control_label("Compare by"),
                    dcc.RadioItems(
                        id="trend-level",
                        options=[
                            {"label": "Country", "value": "country"},
                            {"label": "WHO Region", "value": "region"},
                            {"label": "Income Group", "value": "income"},
                        ],
                        value="country",
                        inline=True,
                        style={"color": COLORS["text"]},
                    ),
                ],
                style={"flex": "1", "minWidth": "260px"},
            ),
            html.Div(
                [
                    control_label("Entities to compare"),
                    dcc.Dropdown(id="trend-entities", multi=True),
                ],
                style={"flex": "2", "minWidth": "320px"},
            ),
        ],
        style={"display": "flex", "gap": "24px", "flexWrap": "wrap",
               "marginBottom": "14px"},
    )
    return graph_card("trend-graph", note_id="trend-note", height="640px",
                       extra_controls=controls)


def tab4_layout():
    return graph_card("cascade-graph", note_id="cascade-note", height="640px")


def tab5_layout():
    return graph_card("region-income-graph", note_id="region-income-note",
                       height="700px")


def tab6_layout():
    controls = html.Div(
        [
            html.Div(
                [
                    control_label("Indicator family"),
                    dcc.Dropdown(
                        id="age-crude-family",
                        options=INDICATOR_FAMILY_OPTIONS,
                        value="diabetes_treatment",
                        clearable=False,
                    ),
                ],
                style={"flex": "1", "minWidth": "260px"},
            ),
            html.Div(
                [
                    control_label("Countries to compare"),
                    dcc.Dropdown(id="age-crude-countries", multi=True),
                ],
                style={"flex": "2", "minWidth": "320px"},
            ),
        ],
        style={"display": "flex", "gap": "24px", "flexWrap": "wrap",
               "marginBottom": "14px"},
    )
    return graph_card("age-crude-graph", note_id="age-crude-note", height="760px",
                       extra_controls=controls)


app.layout = html.Div(
    style={
        "background": COLORS["bg"],
        "minHeight": "100vh",
        "fontFamily": "'Inter', 'Segoe UI', Arial, sans-serif",
        "color": COLORS["text"],
        "padding": "26px 32px 60px",
    },
    children=[
        # ---- shared state ------------------------------------------------
        dcc.Store(id="global-filters", data={
            "indicator": DEFAULT_INDICATOR,
            "sex": DEFAULT_SEX,
            "region": DEFAULT_REGION,
            "income": DEFAULT_INCOME,
            "country": DEFAULT_COUNTRY,
            "year": DEFAULT_YEAR,
        }),

        # ---- header --------------------------------------------------------
        html.Div(
            [
                html.H1(
                    "Global Diabetes & Hypertension Care Inequality",
                    style={"margin": "0 0 4px", "fontSize": "26px"},
                ),
                html.P(
                    "WHO Health Inequality Data Repository · diabetes 1990–2022, "
                    "hypertension 1990–2019 · treatment coverage, effective "
                    "control, and the gaps between them",
                    style={"margin": 0, "color": COLORS["muted"], "fontSize": "14px"},
                ),
            ],
            style={"marginBottom": "20px"},
        ),

        # ---- global filter bar --------------------------------------------
        filter_bar(),

        # ---- tabs -----------------------------------------------------------
        # NOTE: tab content is passed directly as `children` of each dcc.Tab
        # (not swapped in/out via a callback into a shared Div). This keeps
        # every graph's id permanently present in the layout — Dash's Tabs
        # component just hides the inactive panels with CSS. That matters
        # because callbacks like `sync_global_filters` depend on
        # Input("map-graph", "clickData") at all times; if map-graph were
        # only mounted while Tab 1 is open, Dash would throw "nonexistent
        # object used in Input" the moment you switched to another tab.
        dcc.Tabs(
            id="tabs",
            value="tab-1",
            children=[
                dcc.Tab(label="1 · Global Map", value="tab-1",
                        children=[tab1_layout()]),
                dcc.Tab(label="2 · Sex Gap", value="tab-2",
                        children=[tab2_layout()]),
                dcc.Tab(label="3 · Temporal Trend", value="tab-3",
                        children=[tab3_layout()]),
                dcc.Tab(label="4 · Treatment→Control Cascade", value="tab-4",
                        children=[tab4_layout()]),
                dcc.Tab(label="5 · Region & Income", value="tab-5",
                        children=[tab5_layout()]),
                dcc.Tab(label="6 · Age-Standardized vs Crude", value="tab-6",
                        children=[tab6_layout()]),
            ],
            style={"marginBottom": "16px"},
        ),
    ],
)


# =============================================================================
# 3c. THEMING + CACHED FIGURE BUILDERS
# =============================================================================
# The create_*() chart functions render on a light "plotly_white" template.
# _theme() recolors a finished figure to sit on the dark app shell (see the
# README's dark-theme note) without rewriting any chart's internals.
#
# Each chart is also wrapped in an lru_cache keyed on its scalar arguments, so
# revisiting the same selection — most visibly while the year animation loops —
# reuses the built figure instead of re-filtering the in-memory DataFrame and
# rebuilding the trace list every time.

def _theme(fig, is_map=False):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color=COLORS["text"],
        title_font_color=COLORS["text"],
        legend_font_color=COLORS["text"],
        legend_title_font_color=COLORS["muted"],
    )
    if is_map:
        fig.update_geos(
            bgcolor="rgba(0,0,0,0)",
            landcolor="#1b2334",
            oceancolor="#0c111c",
            lakecolor="#0c111c",
            coastlinecolor=COLORS["border"],
            countrycolor=COLORS["bg"],
        )
        fig.update_coloraxes(
            colorbar_tickfont_color=COLORS["text"],
            colorbar_title_font_color=COLORS["text"],
        )
    else:
        axis_style = dict(
            gridcolor=COLORS["border"],
            zerolinecolor=COLORS["border"],
            linecolor=COLORS["border"],
            tickcolor=COLORS["muted"],
            title_font_color=COLORS["muted"],
            tickfont_color=COLORS["muted"],
        )
        fig.update_xaxes(**axis_style)
        fig.update_yaxes(**axis_style)
    return fig


def _age_crude_effective_year(family, year, sex):
    """Nearest year that actually has data for this family/sex (Task 6).

    Diabetes runs 1990-2022 but hypertension stops at 2019, while the global
    year slider spans the full range — so at year=2022 a hypertension family
    would otherwise have zero rows. Mirrors the fallback used by Tasks 1/4/5.
    """
    crude_col, std_col = AGE_CRUDE_PAIRS[family]
    years = trend_country_df.loc[
        (trend_country_df["sex"] == sex)
        & trend_country_df[crude_col].notna()
        & trend_country_df[std_col].notna(),
        "year",
    ]
    if years.empty:
        return None
    if year in years.values:
        return year
    return int(min(years.unique(), key=lambda y: abs(y - year)))


@lru_cache(maxsize=512)
def _fig_map(indicator, year, sex, region, income):
    pool = tuple(countries_in_scope(region, income))
    scoped = map_df[map_df["country"].isin(pool)]
    return _theme(
        create_global_map(df=scoped, indicator=indicator, year=year, sex=sex),
        is_map=True,
    )


@lru_cache(maxsize=256)
def _fig_sexgap(indicator, country):
    return _theme(
        create_sex_gap_chart(df=sex_gap_df, indicator=indicator, country=country)
    )


@lru_cache(maxsize=256)
def _fig_trend(level, indicator, entities, sex):
    cfg = LEVEL_CONFIG[level]
    return _theme(create_temporal_trend_chart(
        df=cfg["df"],
        indicator=indicator,
        entities=list(entities),
        entity_column=cfg["entity_column"],
        level_name=cfg["level_name"],
        sex=sex,
    ))


@lru_cache(maxsize=256)
def _fig_cascade(country, year, sex):
    return _theme(create_treatment_control_cascade(
        df=cascade_df, country=country, year=year, sex=sex,
    ))


@lru_cache(maxsize=256)
def _fig_region(indicator, year):
    return _theme(create_regional_income_comparison(
        df=region_income_df, indicator=indicator, year=year,
    ))


@lru_cache(maxsize=256)
def _fig_agecrude(family, year, sex, countries):
    return _theme(create_age_standardized_crude_chart(
        df=trend_country_df,
        indicator_family=family,
        year=year,
        sex=sex,
        countries=list(countries),
    ))


# =============================================================================
# 4. GLOBAL FILTER STATE
# =============================================================================
# Every control writes into one dcc.Store. Individual tab callbacks read
# from this store, so a change made anywhere (including a map click)
# is visible to every other tab immediately.

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
    Input("year-interval", "n_intervals"),
    State("trend-level", "value"),
    State("global-filters", "data"),
)
def sync_global_filters(indicator, sex, region, income, country, year,
                        map_click, trend_click, agecrude_click, sexgap_click,
                        regincome_click, n_intervals, trend_level, current):
    """Single reducer for all shared filter state.

    Every control and every cross-filterable chart click funnels through here
    and writes one dcc.Store, so a change made anywhere is visible to every
    tab. `f-country`, `f-region`, `f-income` and `f-year` are both Inputs and
    Outputs of this one callback — Dash permits that self-reference (it does
    not re-trigger the callback from its own outputs), which is what lets a
    chart click push a new value back into a control.
    """
    triggered = callback_context.triggered_id
    region = region or ALL_TOKEN
    income = income or ALL_TOKEN

    # --- Tab 5 bar click -> set WHO region + income scope (A5) --------------
    # x is the WHO region; the income group rides in customdata[3] (added in
    # regional_income.py so the trace's group survives the round-trip).
    if (triggered == "region-income-graph"
            and regincome_click and regincome_click.get("points")):
        point = regincome_click["points"][0]
        clicked_region = point.get("x")
        custom = point.get("customdata")
        if clicked_region in WHO_REGIONS:
            region = clicked_region
        if custom and len(custom) >= 4 and custom[3] in INCOME_GROUPS:
            income = custom[3]

    # --- Map click -> set country (A5, pre-existing) ------------------------
    if triggered == "map-graph" and map_click and map_click.get("points"):
        clicked_iso3 = map_click["points"][0].get("location")
        match = map_df.loc[map_df["iso3"] == clicked_iso3, "country"]
        if not match.empty:
            country = match.iloc[0]

    # --- Age-standardized vs crude marker click -> set country (A5) ---------
    # markers carry customdata[0] = country name.
    if (triggered == "age-crude-graph"
            and agecrude_click and agecrude_click.get("points")):
        custom = agecrude_click["points"][0].get("customdata")
        if custom:
            country = custom[0]

    # --- Temporal trend point click -> set year, and country if country-level
    if (triggered == "trend-graph"
            and trend_click and trend_click.get("points")):
        point = trend_click["points"][0]
        if point.get("x") is not None:
            year = point["x"]
        if trend_level == "country":
            custom = point.get("customdata")
            if custom:
                # customdata is the entity name (added in temporal_trend.py).
                country = custom if isinstance(custom, str) else custom[0]

    # --- Sex-gap point click -> set year (its y-axis is year) (A5) ----------
    if (triggered == "sexgap-graph"
            and sexgap_click and sexgap_click.get("points")):
        clicked_year = sexgap_click["points"][0].get("y")
        if clicked_year is not None:
            year = clicked_year

    # --- Animation tick -> advance to next year, looping (A3) --------------
    if triggered == "year-interval":
        if year in ALL_YEARS:
            year = ALL_YEARS[(ALL_YEARS.index(year) + 1) % len(ALL_YEARS)]
        else:
            year = ALL_YEARS[0]

    # --- Apply region/income scope to the country universe (A1) ------------
    pool = countries_in_scope(region, income)
    country_options = [{"label": c, "value": c} for c in pool]
    country = pick_scope_country(pool, country)

    new_state = {
        "indicator": indicator,
        "sex": sex,
        "region": region,
        "income": income,
        "country": country,
        "year": int(year),
    }
    return new_state, country, country_options, region, income, int(year)


# --- A3: Play/Pause toggle for the year animation --------------------------
@app.callback(
    Output("year-interval", "disabled"),
    Output("year-play", "children"),
    Input("year-play", "n_clicks"),
    State("year-interval", "disabled"),
)
def toggle_year_animation(n_clicks, currently_disabled):
    if not n_clicks:
        raise PreventUpdate
    now_disabled = not currently_disabled
    return now_disabled, ("▶ Play" if now_disabled else "⏸ Pause")


# --- D: Reset every filter back to its default ------------------------------
# f-region/f-income/f-country/f-year are also outputs of the reducer above, so
# they need allow_duplicate. Writing the controls re-triggers the reducer,
# which reconciles the store and rescopes the country list.
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
# 6. TASK 1 — GLOBAL MAP  (indicator, sex, year)
# =============================================================================

@app.callback(
    Output("map-graph", "figure"),
    Output("map-note", "children"),
    Input("global-filters", "data"),
)
def update_map(filters):
    indicator, sex, year = filters["indicator"], filters["sex"], filters["year"]

    # Region/income scope restricts which countries the choropleth colours (A1).
    pool = countries_in_scope(
        filters.get("region", ALL_TOKEN), filters.get("income", ALL_TOKEN)
    )
    scoped = map_df[map_df["country"].isin(pool)]

    # Not every indicator is reported through the same final year (e.g.
    # hypertension indicators currently end in 2019 while diabetes ones run
    # through 2022, but the year slider spans the full 1990-2022 range across
    # all indicators). Fall back to the nearest available year for this
    # indicator/sex instead of letting create_global_map raise ValueError.
    available_years = scoped.loc[
        (scoped["indicator_code"] == indicator) & (scoped["sex"] == sex), "year"
    ]
    resolved_year = nearest_available_year(available_years, year)
    if resolved_year is None:
        msg = f"No data available for {INDICATOR_LABELS[indicator]} ({sex})."
        return empty_selection_placeholder(msg), msg
    year = resolved_year

    fig = _fig_map(
        indicator, year, sex,
        filters.get("region", ALL_TOKEN), filters.get("income", ALL_TOKEN),
    )
    scope_bits = [b for b in (
        None if filters.get("region", ALL_TOKEN) == ALL_TOKEN else filters["region"],
        None if filters.get("income", ALL_TOKEN) == ALL_TOKEN else filters["income"],
    ) if b]
    note = (f"{INDICATOR_LABELS[indicator]} · {sex} · "
            f"{year} — click a country to select it everywhere below")
    if scope_bits:
        note += f" · scope: {' + '.join(scope_bits)}"
    if year != filters["year"]:
        note += f" (no {filters['year']} data for this indicator; showing nearest year)"
    return fig, note


# =============================================================================
# 7. TASK 2 — SEX GAP  (indicator, country)
# =============================================================================

@app.callback(
    Output("sexgap-graph", "figure"),
    Output("sexgap-note", "children"),
    Input("global-filters", "data"),
)
def update_sex_gap(filters):
    country = filters["country"]
    indicator = filters["indicator"]
    available = sex_gap_df.loc[
        sex_gap_df["indicator_code"] == indicator, "country"
    ].unique()
    if country not in available:
        country = sorted(available)[0]
    fig = _fig_sexgap(indicator, country)
    note = f"{INDICATOR_LABELS[indicator]} · {country} · Male vs Female, 1990–latest"
    return fig, note


# =============================================================================
# 8. TASK 3 — TEMPORAL TREND  (indicator, sex, level, entities)
# =============================================================================

LEVEL_CONFIG = {
    "country": dict(df=trend_country_df, entity_column="country", level_name="Country"),
    "region": dict(df=trend_region_df, entity_column="who_region", level_name="WHO Region"),
    "income": dict(df=trend_income_df, entity_column="income_group", level_name="Income Group"),
}


@app.callback(
    Output("trend-entities", "options"),
    Output("trend-entities", "value"),
    Input("trend-level", "value"),
    Input("global-filters", "data"),
    State("trend-entities", "value"),
)
def update_trend_entity_options(level, filters, current_selection):
    cfg = LEVEL_CONFIG[level]
    col = cfg["entity_column"]
    df = cfg["df"]
    indicator = filters["indicator"]

    # The dropdown must only offer entities that actually have data for the
    # currently selected indicator (and sex, for country-level wide-format
    # data) — otherwise "Select All" can pull in an entity like Tokelau that
    # exists in the file but is null for that specific indicator column,
    # which create_temporal_trend_chart then rejects as an invalid selection.
    if level == "country":
        subset = df[df["sex"] == filters["sex"]].dropna(subset=[indicator])
        # Region/income scope narrows the selectable countries (A1).
        scope = set(countries_in_scope(
            filters.get("region", ALL_TOKEN), filters.get("income", ALL_TOKEN)
        ))
        subset = subset[subset[col].isin(scope)]
    else:
        subset = df[
            (df["indicator_code"] == indicator) & df["avg_value"].notna()
        ]

    options_pool = sorted(subset[col].dropna().unique())
    options = [{"label": o, "value": o} for o in options_pool]

    def default_selection():
        if level == "country":
            picks = [c for c in PREFERRED_COMPARISON_COUNTRIES if c in options_pool]
            if filters["country"] in options_pool and filters["country"] not in picks:
                picks = [filters["country"]] + picks
            return picks[:5] or options_pool[:3]
        return options_pool[:4]

    # Only reset to the default list when the comparison level itself
    # changes (or on first load, where there's no prior selection yet).
    # A change to year/indicator/sex via the global filter bar should
    # preserve what the user already picked, dropping only entities that
    # are no longer valid for the new selection rather than wiping it out.
    triggered = callback_context.triggered_id
    if triggered == "trend-level" or not current_selection:
        selection = default_selection()
    else:
        selection = [e for e in current_selection if e in options_pool]
        if not selection:
            selection = default_selection()

    return options, selection


@app.callback(
    Output("trend-graph", "figure"),
    Output("trend-note", "children"),
    Input("trend-level", "value"),
    Input("trend-entities", "value"),
    Input("global-filters", "data"),
)
def update_trend(level, entities, filters):
    cfg = LEVEL_CONFIG[level]
    entities = entities or []

    if not entities:
        note = f"Select at least one {cfg['level_name'].lower()} to compare."
        return empty_selection_placeholder(note, height=500), note

    fig = _fig_trend(
        level,
        filters["indicator"],
        tuple(entities),
        filters["sex"] if level == "country" else None,
    )
    note = (f"{INDICATOR_LABELS[filters['indicator']]} · by {cfg['level_name']} · "
            f"{', '.join(entities)}")
    return fig, note


# =============================================================================
# 9. TASK 4 — TREATMENT→CONTROL CASCADE  (country, year, sex)
# =============================================================================

@app.callback(
    Output("cascade-graph", "figure"),
    Output("cascade-note", "children"),
    Input("global-filters", "data"),
)
def update_cascade(filters):
    country, year, sex = filters["country"], filters["year"], filters["sex"]
    subset = cascade_df[
        (cascade_df["country"] == country)
        & (cascade_df["year"] == year)
        & (cascade_df["sex"] == sex)
    ]
    if subset.empty:
        # fall back to nearest available year for this country/sex
        available_years = cascade_df.loc[
            (cascade_df["country"] == country) & (cascade_df["sex"] == sex), "year"
        ]
        if available_years.empty:
            msg = f"No hypertension cascade data for {country}."
            return empty_selection_placeholder(msg), msg
        year = int(available_years.max())

    fig = _fig_cascade(country, year, sex)
    row = cascade_df[
        (cascade_df["country"] == country)
        & (cascade_df["year"] == year)
        & (cascade_df["sex"] == sex)
    ].iloc[0]
    note = (f"{country} · {sex} · {year} — Treatment {row['htn_tx_crude']:.1f}% → "
            f"Control {row['htn_ctrl_crude']:.1f}% "
            f"(leakage {row['delta_leak']:.1f} pp)")
    return fig, note


# =============================================================================
# 10. TASK 5 — REGION & INCOME COMPARISON  (indicator, year)
# =============================================================================

@app.callback(
    Output("region-income-graph", "figure"),
    Output("region-income-note", "children"),
    Input("global-filters", "data"),
)
def update_region_income(filters):
    indicator, year = filters["indicator"], filters["year"]

    # Same cross-indicator year mismatch as Task 1: hypertension indicators
    # in region_income_summary.csv currently end in 2019 while diabetes ones
    # run through 2022, but the global year slider spans the full range.
    # Fall back to the nearest available year for this indicator.
    available_years = region_income_df.loc[
        region_income_df["indicator_code"] == indicator, "year"
    ]
    resolved_year = nearest_available_year(available_years, year)
    if resolved_year is None:
        msg = f"No data available for {INDICATOR_LABELS[indicator]}."
        return empty_selection_placeholder(msg), msg
    year = resolved_year

    fig = _fig_region(indicator, year)
    note = f"{INDICATOR_LABELS[indicator]} · {year} · WHO Region × World Bank Income Group"
    if year != filters["year"]:
        note += f" (no {filters['year']} data for this indicator; showing nearest year)"
    return fig, note


# =============================================================================
# 11. TASK 6 — AGE-STANDARDIZED VS CRUDE  (family, year, sex, countries)
# =============================================================================

@app.callback(
    Output("age-crude-countries", "options"),
    Output("age-crude-countries", "value"),
    Input("age-crude-family", "value"),
    Input("global-filters", "data"),
    State("age-crude-countries", "value"),
)
def update_age_crude_options(family, filters, current_selection):
    crude_col, std_col = AGE_CRUDE_PAIRS[family]
    # Fall back to the nearest year with data (hypertension stops at 2019
    # while the slider reaches 2022); otherwise the pool would be empty (B1).
    eff_year = _age_crude_effective_year(family, filters["year"], filters["sex"])
    if eff_year is None:
        return [], []
    subset = trend_country_df[
        (trend_country_df["year"] == eff_year)
        & (trend_country_df["sex"] == filters["sex"])
    ].dropna(subset=[crude_col, std_col])
    # Region/income scope narrows the selectable countries (A1).
    scope = set(countries_in_scope(
        filters.get("region", ALL_TOKEN), filters.get("income", ALL_TOKEN)
    ))
    pool = [c for c in sorted(subset["country"].unique()) if c in scope]
    options = [{"label": c, "value": c} for c in pool]

    def default_selection():
        picks = [c for c in PREFERRED_COMPARISON_COUNTRIES if c in pool]
        if filters["country"] not in picks and filters["country"] in pool:
            picks = [filters["country"]] + picks
        return picks[:5] or pool[:5]

    # Countries stay countries no matter which indicator family is picked,
    # so preserve the user's existing selection across a family change too
    # (dropping only countries with no data for the new family). Only fall
    # back to the default list on first load, when there's nothing to keep.
    if not current_selection:
        selection = default_selection()
    else:
        selection = [c for c in current_selection if c in pool]
        if not selection:
            selection = default_selection()

    return options, selection


@app.callback(
    Output("age-crude-graph", "figure"),
    Output("age-crude-note", "children"),
    Input("age-crude-family", "value"),
    Input("age-crude-countries", "value"),
    Input("global-filters", "data"),
)
def update_age_crude(family, countries, filters):
    countries = countries or []

    if not countries:
        note = "Select at least one country to compare."
        return empty_selection_placeholder(note, height=560), note

    # Same nearest-year fallback as the options callback (B1).
    eff_year = _age_crude_effective_year(family, filters["year"], filters["sex"])
    if eff_year is None:
        note = (f"No data available for {INDICATOR_FAMILY_LABELS[family]} "
                f"({filters['sex']}).")
        return empty_selection_placeholder(note, height=560), note

    # Drop any countries that lack data for this family/year/sex, so a stale
    # selection left over from a previous family can't reach the chart (which
    # would otherwise raise ValueError).
    crude_col, std_col = AGE_CRUDE_PAIRS[family]
    valid = set(trend_country_df[
        (trend_country_df["year"] == eff_year)
        & (trend_country_df["sex"] == filters["sex"])
    ].dropna(subset=[crude_col, std_col])["country"])
    countries = [c for c in countries if c in valid]
    if not countries:
        note = "Select at least one country to compare."
        return empty_selection_placeholder(note, height=560), note

    fig = _fig_agecrude(family, eff_year, filters["sex"], tuple(countries))
    note = (f"{INDICATOR_FAMILY_LABELS[family]} · {filters['sex']} · {eff_year} · "
            f"{', '.join(countries)}")
    if eff_year != filters["year"]:
        note += (f" (no {filters['year']} data for this indicator; "
                 f"showing nearest year)")
    return fig, note


# =============================================================================
# 12. ENTRYPOINT
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Global Diabetes & Hypertension Care Inequality Dashboard")
    print("=" * 70)
    print(f"Countries: {map_df['iso3'].nunique()} | Years: {YEAR_MIN}-{YEAR_MAX}")
    print("Open http://127.0.0.1:8050/ in your browser.")
    app.run(debug=True)