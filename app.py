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

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, State, callback_context

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

INDICATOR_LABELS = {
    "diab_tx_std": "Diabetes Treatment Coverage (Age-Standardized)",
    "diab_tx_crude": "Diabetes Treatment Coverage (Crude)",
    "htn_tx_std": "Hypertension Treatment Coverage (Age-Standardized)",
    "htn_tx_crude": "Hypertension Treatment Coverage (Crude)",
    "htn_ctrl_std": "Hypertension Effective Control (Age-Standardized)",
    "htn_ctrl_crude": "Hypertension Effective Control (Crude)",
}

INDICATOR_OPTIONS = [
    {"label": label, "value": code} for code, label in INDICATOR_LABELS.items()
]

INDICATOR_FAMILY_LABELS = {
    "diabetes_treatment": "Diabetes Treatment Coverage",
    "hypertension_treatment": "Hypertension Treatment Coverage",
    "hypertension_control": "Hypertension Effective Control",
}
INDICATOR_FAMILY_OPTIONS = [
    {"label": label, "value": code} for code, label in INDICATOR_FAMILY_LABELS.items()
]

ALL_COUNTRIES = sorted(map_df["country"].dropna().unique())
COUNTRY_OPTIONS = [{"label": c, "value": c} for c in ALL_COUNTRIES]

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

PREFERRED_COMPARISON_COUNTRIES = [
    "India", "China", "Brazil", "United States of America", "Japan",
]

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
                    control_label(f"Year: {DEFAULT_YEAR}"),
                    dcc.Slider(
                        id="f-year",
                        min=YEAR_MIN,
                        max=YEAR_MAX,
                        step=1,
                        value=DEFAULT_YEAR,
                        marks=YEAR_MARKS,
                        tooltip={"placement": "bottom", "always_visible": False},
                        updatemode="mouseup",
                    ),
                ],
                style={"flex": "3", "minWidth": "320px", "paddingTop": "2px"},
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
                    "WHO Health Inequality Data Repository · 1990–2022 · "
                    "treatment coverage, effective control, and the gaps between them",
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
# 4. GLOBAL FILTER STATE
# =============================================================================
# Every control writes into one dcc.Store. Individual tab callbacks read
# from this store, so a change made anywhere (including a map click)
# is visible to every other tab immediately.

@app.callback(
    Output("global-filters", "data"),
    Output("f-country", "value"),
    Input("f-indicator", "value"),
    Input("f-sex", "value"),
    Input("f-country", "value"),
    Input("f-year", "value"),
    Input("map-graph", "clickData"),
    State("global-filters", "data"),
)
def sync_global_filters(indicator, sex, country, year, map_click, current):
    triggered = callback_context.triggered_id

    # A click on the choropleth map overrides the Country dropdown.
    if triggered == "map-graph" and map_click and map_click.get("points"):
        point = map_click["points"][0]
        clicked_iso3 = point.get("location")
        match = map_df.loc[map_df["iso3"] == clicked_iso3, "country"]
        if not match.empty:
            country = match.iloc[0]

    new_state = {
        "indicator": indicator,
        "sex": sex,
        "country": country,
        "year": int(year),
    }
    return new_state, country


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

    # Not every indicator is reported through the same final year (e.g.
    # hypertension indicators currently end in 2019 while diabetes ones run
    # through 2022, but the year slider spans the full 1990-2022 range across
    # all indicators). Fall back to the nearest available year for this
    # indicator/sex instead of letting create_global_map raise ValueError.
    available_years = map_df.loc[
        (map_df["indicator_code"] == indicator) & (map_df["sex"] == sex), "year"
    ]
    if available_years.empty:
        msg = f"No data available for {INDICATOR_LABELS[indicator]} ({sex})."
        return empty_selection_placeholder(msg), msg

    if year not in available_years.values:
        year = int(min(available_years, key=lambda y: abs(y - year)))

    fig = create_global_map(
        df=map_df,
        indicator=indicator,
        year=year,
        sex=sex,
    )
    note = (f"{INDICATOR_LABELS[indicator]} · {sex} · "
            f"{year} — click a country to select it everywhere below")
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
    fig = create_sex_gap_chart(df=sex_gap_df, indicator=indicator, country=country)
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
)
def update_trend_entity_options(level, filters):
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
    else:
        subset = df[
            (df["indicator_code"] == indicator) & df["avg_value"].notna()
        ]

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

    fig = create_temporal_trend_chart(
        df=cfg["df"],
        indicator=filters["indicator"],
        entities=entities,
        entity_column=cfg["entity_column"],
        level_name=cfg["level_name"],
        sex=filters["sex"] if level == "country" else None,
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
            return {}, f"No hypertension cascade data for {country}."
        year = int(available_years.max())

    fig = create_treatment_control_cascade(
        df=cascade_df, country=country, year=year, sex=sex,
    )
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
    if available_years.empty:
        msg = f"No data available for {INDICATOR_LABELS[indicator]}."
        return empty_selection_placeholder(msg), msg

    if year not in available_years.values:
        year = int(min(available_years, key=lambda y: abs(y - year)))

    fig = create_regional_income_comparison(
        df=region_income_df, indicator=indicator, year=year,
    )
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
)
def update_age_crude_options(family, filters):
    cfg = {
        "diabetes_treatment": ("diab_tx_crude", "diab_tx_std"),
        "hypertension_treatment": ("htn_tx_crude", "htn_tx_std"),
        "hypertension_control": ("htn_ctrl_crude", "htn_ctrl_std"),
    }[family]
    crude_col, std_col = cfg
    subset = trend_country_df[
        (trend_country_df["year"] == filters["year"])
        & (trend_country_df["sex"] == filters["sex"])
    ].dropna(subset=[crude_col, std_col])
    pool = sorted(subset["country"].unique())
    options = [{"label": c, "value": c} for c in pool]

    default = [c for c in PREFERRED_COMPARISON_COUNTRIES if c in pool]
    if filters["country"] not in default and filters["country"] in pool:
        default = [filters["country"]] + default
    default = default[:5] or pool[:5]
    return options, default


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

    fig = create_age_standardized_crude_chart(
        df=trend_country_df,
        indicator_family=family,
        year=filters["year"],
        sex=filters["sex"],
        countries=countries,
    )
    note = (f"{INDICATOR_FAMILY_LABELS[family]} · {filters['sex']} · {filters['year']} · "
            f"{', '.join(countries)}")
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