import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from visualizations.labels import INDICATOR_LABELS


def create_global_map(
    df: pd.DataFrame,
    indicator: str,
    year: int,
    sex: str
) -> go.Figure:
    """
    Create an interactive global choropleth map.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame loaded from map_data.csv.

    indicator : str
        Indicator code, for example:
        - diab_tx_std
        - diab_tx_crude
        - htn_ctrl_std
        - htn_ctrl_crude
        - htn_tx_std
        - htn_tx_crude

    year : int
        Selected year.

    sex : str
        "Male" or "Female"

    Returns
    -------
    plotly.graph_objects.Figure
        Interactive choropleth map.
    """

    required_columns = {
        "iso3",
        "country",
        "year",
        "indicator_code",
        "sex",
        "value",
        "who_region",
        "income_group",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {sorted(missing_columns)}"
        )

    if indicator not in df["indicator_code"].unique():
        raise ValueError(
            f"Invalid indicator '{indicator}'. "
            f"Available indicators: "
            f"{sorted(df['indicator_code'].unique())}"
        )

    filtered_df = df[
        (df["indicator_code"] == indicator)
        & (df["year"] == year)
        & (df["sex"] == sex)
    ].copy()

    if filtered_df.empty:
        raise ValueError(
            f"No data found for indicator={indicator}, "
            f"year={year}, sex={sex}"
        )

    indicator_name = INDICATOR_LABELS.get(
        indicator,
        indicator
    )

    fig = px.choropleth(
        filtered_df,
        locations="iso3",
        locationmode="ISO-3",
        color="value",
        hover_name="country",
        hover_data={
            "iso3": False,
            "value": ":.2f",
            "who_region": True,
            "income_group": True,
        },
        color_continuous_scale="Viridis",
        range_color=(0, 100),
        labels={
            "value": "Coverage (%)",
            "who_region": "WHO Region",
            "income_group": "Income Group",
        },
        title=(
            f"{indicator_name}<br>"
            f"<sup>{sex} | {year}</sup>"
        ),
    )

    fig.update_geos(
        showframe=False,
        showcoastlines=True,
        coastlinecolor="rgba(80,80,80,0.45)",
        showland=True,
        landcolor="rgb(235, 235, 235)",
        showocean=True,
        oceancolor="rgb(245, 249, 252)",
        showcountries=True,
        countrycolor="rgba(255,255,255,0.7)",
        projection_type="natural earth",
    )

    fig.update_coloraxes(
        colorbar=dict(
            title="Coverage (%)",
            thickness=16,
            len=0.75,
            x=1.02,
        )
    )

    fig.update_traces(
        marker_line_color="rgba(255,255,255,0.55)",
        marker_line_width=0.4,
    )

    fig.update_layout(
        template="plotly_white",
        height=650,
        margin=dict(
            l=10,
            r=80,
            t=90,
            b=10
        ),
        title=dict(
            x=0.5,
            xanchor="center",
            font=dict(size=22),
        ),
        geo=dict(
            bgcolor="rgba(0,0,0,0)"
        ),
    )

    return fig