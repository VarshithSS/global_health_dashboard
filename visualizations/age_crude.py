import pandas as pd
import plotly.graph_objects as go


# Configuration for crude and age-standardized indicator pairs
PAIR_CONFIG = {
    "diabetes_treatment": {
        "crude": "diab_tx_crude",
        "standardized": "diab_tx_std",
        "label": "Diabetes Treatment Coverage",
    },

    "hypertension_treatment": {
        "crude": "htn_tx_crude",
        "standardized": "htn_tx_std",
        "label": "Hypertension Treatment Coverage",
    },

    "hypertension_control": {
        "crude": "htn_ctrl_crude",
        "standardized": "htn_ctrl_std",
        "label": "Hypertension Effective Control",
    },
}


# Country colors used consistently across all traces
COUNTRY_COLORS = [
    "#EF553B",
    "#FFA15A",
    "#00CC96",
    "#636EFA",
    "#AB63FA",
    "#19D3F3",
    "#FF6692",
    "#B6E880",
    "#FF97FF",
    "#FECB52",
]


def create_age_standardized_crude_chart(
    df: pd.DataFrame,
    indicator_family: str,
    year: int,
    sex: str,
    countries: list,
) -> go.Figure:
    """
    Task 6: Age-Standardized vs. Crude Rate Comparison.

    Creates a paired slope chart comparing crude and
    age-standardized rates for selected countries.

    Difference metric:

        delta_age = crude - age_standardized

    Parameters
    ----------
    df : pd.DataFrame
        Country-level dataset containing crude and
        age-standardized indicator columns.

    indicator_family : str
        One of:
        - diabetes_treatment
        - hypertension_treatment
        - hypertension_control

    year : int
        Selected year.

    sex : str
        Selected sex.

    countries : list
        Countries to compare.

    Returns
    -------
    go.Figure
        Interactive paired slope chart.
    """

    # Validate indicator family
    if indicator_family not in PAIR_CONFIG:
        raise ValueError(
            f"Invalid indicator family "
            f"'{indicator_family}'. "
            f"Available values: "
            f"{list(PAIR_CONFIG.keys())}"
        )

    # Get paired indicator configuration
    config = PAIR_CONFIG[
        indicator_family
    ]

    crude_column = (
        config["crude"]
    )

    standardized_column = (
        config["standardized"]
    )

    indicator_label = (
        config["label"]
    )

    # Required columns
    required_columns = {
        "country",
        "year",
        "sex",
        crude_column,
        standardized_column,
    }

    # Check missing columns
    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:
        raise ValueError(
            f"Missing required columns: "
            f"{sorted(missing_columns)}"
        )

    # Require at least one selected country
    if not countries:
        raise ValueError(
            "At least one country must be selected."
        )

    # Work on a copy
    data = df.copy()

    # Convert year to numeric
    data["year"] = pd.to_numeric(
        data["year"],
        errors="coerce"
    )

    # Convert crude rate to numeric
    data[crude_column] = pd.to_numeric(
        data[crude_column],
        errors="coerce"
    )

    # Convert standardized rate to numeric
    data[standardized_column] = pd.to_numeric(
        data[standardized_column],
        errors="coerce"
    )

    # Remove rows missing essential values
    data = data.dropna(
        subset=[
            "country",
            "year",
            "sex",
            crude_column,
            standardized_column,
        ]
    )

    # Convert valid years to integers
    data["year"] = (
        data["year"]
        .astype(int)
    )

    # Get available sex values
    available_sexes = sorted(
        data["sex"]
        .dropna()
        .astype(str)
        .unique()
    )

    # Validate selected sex
    if sex not in available_sexes:
        raise ValueError(
            f"Invalid sex '{sex}'. "
            f"Available values: "
            f"{available_sexes}"
        )

    # Get available countries
    available_countries = set(
        data["country"]
        .dropna()
        .astype(str)
        .unique()
    )

    # Find invalid country selections
    invalid_countries = [
        country
        for country in countries
        if country not in available_countries
    ]

    # Reject invalid countries
    if invalid_countries:
        raise ValueError(
            f"Invalid countries: "
            f"{invalid_countries}"
        )

    # Filter selected year, sex, and countries
    filtered_df = data[
        (data["year"] == int(year))
        & (data["sex"] == sex)
        & (data["country"].isin(countries))
    ].copy()

    # Ensure data exists
    if filtered_df.empty:
        raise ValueError(
            f"No data found for "
            f"year={year}, "
            f"sex='{sex}', "
            f"countries={countries}"
        )

    # Calculate age-standardization difference
    filtered_df["delta_age"] = (
        filtered_df[crude_column]
        - filtered_df[standardized_column]
    )

    # Preserve selected country order
    country_order = {
        country: index
        for index, country
        in enumerate(countries)
    }

    filtered_df["country_order"] = (
        filtered_df["country"]
        .map(country_order)
    )

    # Sort countries using selection order
    filtered_df = (
        filtered_df
        .sort_values("country_order")
        .reset_index(drop=True)
    )

    # Create empty Plotly figure
    fig = go.Figure()

    # Add one paired slope for every country
    for index, row in filtered_df.iterrows():

        # Extract country name
        country = str(
            row["country"]
        )

        # Assign one consistent country color
        country_color = (
            COUNTRY_COLORS[
                index % len(COUNTRY_COLORS)
            ]
        )

        # Extract crude rate
        crude_value = float(
            row[crude_column]
        )

        # Extract standardized rate
        standardized_value = float(
            row[standardized_column]
        )

        # Extract age difference
        delta_age = float(
            row["delta_age"]
        )

        # Add connector line
        fig.add_trace(
            go.Scatter(
                x=[
                    "Crude Rate",
                    "Age-Standardized Rate",
                ],

                y=[
                    crude_value,
                    standardized_value,
                ],

                mode="lines",

                line=dict(
                    width=2.5,
                    color=country_color,
                ),

                name=country,

                legendgroup=country,

                showlegend=False,

                hoverinfo="skip",
            )
        )

        # Add crude-rate marker
        fig.add_trace(
            go.Scatter(
                x=[
                    "Crude Rate"
                ],

                y=[
                    crude_value
                ],

                mode="markers",

                name=country,

                legendgroup=country,

                showlegend=True,

                marker=dict(
                    size=12,
                    symbol="circle",
                    color=country_color,
                ),

                customdata=[
                    [
                        country,
                        delta_age,
                        standardized_value,
                    ]
                ],

                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Rate Type: Crude<br>"
                    "Crude Coverage: %{y:.2f}%<br>"
                    "Age-Standardized Coverage: "
                    "%{customdata[2]:.2f}%<br>"
                    "ΔAge: %{customdata[1]:+.2f} pp"
                    "<extra></extra>"
                ),
            )
        )

        # Add age-standardized marker
        fig.add_trace(
            go.Scatter(
                x=[
                    "Age-Standardized Rate"
                ],

                y=[
                    standardized_value
                ],

                mode="markers",

                name=country,

                legendgroup=country,

                showlegend=False,

                marker=dict(
                    size=12,
                    symbol="diamond",
                    color=country_color,
                ),

                customdata=[
                    [
                        country,
                        delta_age,
                        crude_value,
                    ]
                ],

                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Rate Type: Age-Standardized<br>"
                    "Age-Standardized Coverage: "
                    "%{y:.2f}%<br>"
                    "Crude Coverage: "
                    "%{customdata[2]:.2f}%<br>"
                    "ΔAge: %{customdata[1]:+.2f} pp"
                    "<extra></extra>"
                ),
            )
        )

    # Combine crude and standardized values
    all_values = pd.concat(
        [
            filtered_df[crude_column],
            filtered_df[standardized_column],
        ],
        ignore_index=True,
    )

    # Find minimum visible value
    minimum_value = float(
        all_values.min()
    )

    # Find maximum visible value
    maximum_value = float(
        all_values.max()
    )

    # Calculate visible value span
    value_span = (
        maximum_value
        - minimum_value
    )

    # Add dynamic axis padding
    padding = max(
        3.0,
        value_span * 0.15
    )

    # Calculate lower y-axis boundary
    y_min = max(
        0.0,
        minimum_value - padding
    )

    # Calculate upper y-axis boundary
    y_max = min(
        100.0,
        maximum_value + padding
    )

    # Ensure enough vertical space
    if y_max - y_min < 10:

        midpoint = (
            y_min + y_max
        ) / 2

        y_min = max(
            0,
            midpoint - 5
        )

        y_max = min(
            100,
            midpoint + 5
        )

    # Calculate average age-standardization offset
    average_delta = float(
        filtered_df["delta_age"]
        .mean()
    )

    # Find largest absolute age offset
    largest_index = (
        filtered_df["delta_age"]
        .abs()
        .idxmax()
    )

    # Get row with largest absolute offset
    largest_row = (
        filtered_df
        .loc[largest_index]
    )

    # Extract country with largest offset
    largest_country = str(
        largest_row["country"]
    )

    # Extract signed largest offset
    largest_delta = float(
        largest_row["delta_age"]
    )

    # Configure chart layout
    fig.update_layout(
        template="plotly_white",

        title=dict(
            text=(
                f"{indicator_label}"
                "<br>"
                f"<sup>"
                f"Crude vs. Age-Standardized | "
                f"{sex} | {year}"
                f"</sup>"
            ),

            x=0.5,
            xanchor="center",

            font=dict(
                size=21
            ),
        ),

        # Configure rate-type axis
        # NOTE: standoff reserves explicit space for the "Rate Type" title
        # so it doesn't collide with the summary annotations below it.
        xaxis=dict(
            title=dict(
                text="Rate Type",
                standoff=20,
            ),

            categoryorder="array",

            categoryarray=[
                "Crude Rate",
                "Age-Standardized Rate",
            ],

            showgrid=False,
        ),

        # Configure coverage axis
        yaxis=dict(
            title="Coverage (%)",

            range=[
                y_min,
                y_max,
            ],

            ticksuffix="%",

            showgrid=True,

            gridcolor=(
                "rgba(180,180,180,0.25)"
            ),

            zeroline=False,
        ),

        height=760,

        margin=dict(
            l=80,
            r=60,
            t=140,
            b=250,
        ),

        # Place country legend above chart
        legend=dict(
            title="Country",

            orientation="h",

            yanchor="bottom",
            y=1.02,

            xanchor="center",
            x=0.5,
        ),

        hovermode="closest",

        font=dict(
            family="Arial",
            size=13,
        ),
    )

    # Add average offset summary
    fig.add_annotation(
        text=(
            f"<b>Average ΔAge:</b> "
            f"{average_delta:+.2f} pp"
        ),

        x=0.5,
        y=-0.24,

        xref="paper",
        yref="paper",

        showarrow=False,

        font=dict(
            size=13
        ),
    )

    # Add largest absolute offset summary
    fig.add_annotation(
        text=(
            f"<b>Largest absolute ΔAge:</b> "
            f"{largest_country} "
            f"({largest_delta:+.2f} pp)"
        ),

        x=0.5,
        y=-0.31,

        xref="paper",
        yref="paper",

        showarrow=False,

        font=dict(
            size=13
        ),
    )

    # Explain the delta metric
    fig.add_annotation(
        text=(
            "ΔAge = Crude Rate − "
            "Age-Standardized Rate"
        ),

        x=0.5,
        y=-0.38,

        xref="paper",
        yref="paper",

        showarrow=False,

        font=dict(
            size=12,
            color="dimgray",
        ),
    )

    # Add source information
    fig.add_annotation(
        text=(
            "Source: WHO Health Inequality "
            "Data Repository"
        ),

        x=0,
        y=-0.45,

        xref="paper",
        yref="paper",

        showarrow=False,

        xanchor="left",

        font=dict(
            size=11,
            color="gray",
        ),
    )

    return fig
