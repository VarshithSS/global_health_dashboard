
import pandas as pd
import plotly.graph_objects as go

from visualizations.labels import INDICATOR_LABELS


# List of supported indicators
VALID_INDICATORS = list(
    INDICATOR_LABELS.keys()
)


def create_temporal_trend_chart(
    df: pd.DataFrame,
    indicator: str,
    entities: list,
    entity_column: str,
    level_name: str,
    sex: str = None,
) -> go.Figure:
    """
    Task 3: Temporal Trend Analysis.

    Creates an interactive multi-line time-series chart.

    Supports:
    - trend_country.csv
    - trend_region.csv
    - trend_income.csv

    Country data is stored in wide format.
    Region and income data are stored in long format.

    Parameters
    ----------
    df : pd.DataFrame
        Trend dataset.

    indicator : str
        Selected indicator code.

    entities : list
        Entities to compare, such as countries,
        WHO regions, or income groups.

    entity_column : str
        Column containing entity names.

    level_name : str
        Human-readable aggregation level.

    sex : str or None
        Male or Female for country-level data.
        Region and income datasets do not require sex.

    Returns
    -------
    go.Figure
        Interactive Plotly time-series chart.
    """

    # Check whether the requested entity column exists
    if entity_column not in df.columns:
        raise ValueError(
            f"Entity column '{entity_column}' not found. "
            f"Available columns: {df.columns.tolist()}"
        )

    # Validate the selected indicator
    if indicator not in VALID_INDICATORS:
        raise ValueError(
            f"Invalid indicator '{indicator}'. "
            f"Available indicators: {VALID_INDICATORS}"
        )

    # At least one entity must be selected
    if not entities:
        raise ValueError(
            "At least one entity must be selected."
        )

    # Work on a copy to avoid modifying the original DataFrame
    data = df.copy()

    # Detect wide-format data
    # Example: trend_country.csv
    # Indicator codes themselves are columns
    is_wide_format = (
        indicator in data.columns
    )

    # Detect long-format data
    # Example: trend_region.csv and trend_income.csv
    is_long_format = (
        "indicator_code" in data.columns
        and "avg_value" in data.columns
    )

    # Reject unsupported dataset structures
    if not is_wide_format and not is_long_format:
        raise ValueError(
            "Unsupported trend dataset structure. "
            f"Columns found: {data.columns.tolist()}"
        )

    # Handle wide-format country data
    if is_wide_format:

        required_columns = {
            entity_column,
            "year",
            indicator,
        }

        missing_columns = (
            required_columns
            - set(data.columns)
        )

        if missing_columns:
            raise ValueError(
                f"Missing required columns: "
                f"{sorted(missing_columns)}"
            )

        # Country-level data contains separate Male/Female rows
        if "sex" in data.columns:

            # Sex is required for country-level trends
            if sex is None:
                raise ValueError(
                    "Sex must be provided for "
                    "country-level trend data."
                )

            # Get valid sex values from the dataset
            available_sexes = sorted(
                data["sex"]
                .dropna()
                .unique()
            )

            # Validate selected sex
            if sex not in available_sexes:
                raise ValueError(
                    f"Invalid sex '{sex}'. "
                    f"Available values: {available_sexes}"
                )

            # Filter data to selected sex
            data = data[
                data["sex"] == sex
            ].copy()

        # Convert selected indicator column into
        # a common internal value column
        data["value"] = pd.to_numeric(
            data[indicator],
            errors="coerce"
        )

    # Handle long-format region and income data
    else:

        required_columns = {
            entity_column,
            "year",
            "indicator_code",
            "avg_value",
        }

        missing_columns = (
            required_columns
            - set(data.columns)
        )

        if missing_columns:
            raise ValueError(
                f"Missing required columns: "
                f"{sorted(missing_columns)}"
            )

        # Keep only the selected indicator
        data = data[
            data["indicator_code"] == indicator
        ].copy()

        # Convert avg_value into a common internal value column
        data["value"] = pd.to_numeric(
            data["avg_value"],
            errors="coerce"
        )

    # Convert year to numeric
    data["year"] = pd.to_numeric(
        data["year"],
        errors="coerce"
    )

    # Remove rows missing essential plotting information
    data = data.dropna(
        subset=[
            entity_column,
            "year",
            "value",
        ]
    )

    # Convert valid years to integers
    data["year"] = (
        data["year"]
        .astype(int)
    )

    # Get all entities available after filtering
    available_entities = set(
        data[entity_column]
        .unique()
    )

    # Identify invalid requested entities
    invalid_entities = [
        entity
        for entity in entities
        if entity not in available_entities
    ]

    # Reject invalid entity selections
    if invalid_entities:
        raise ValueError(
            f"Invalid {level_name} selections: "
            f"{invalid_entities}"
        )

    # Keep only selected countries, regions,
    # or income groups
    filtered_df = data[
        data[entity_column]
        .isin(entities)
    ].copy()

    # Ensure filtered data exists
    if filtered_df.empty:
        raise ValueError(
            "No temporal trend data found for "
            f"{level_name}: {entities}"
        )

    # Sort values chronologically within each entity
    filtered_df = (
        filtered_df
        .sort_values(
            by=[
                entity_column,
                "year",
            ]
        )
        .reset_index(drop=True)
    )

    # Get readable indicator title
    indicator_name = (
        INDICATOR_LABELS.get(
            indicator,
            indicator
        )
    )

    # Find visible year range
    minimum_year = int(
        filtered_df["year"].min()
    )

    maximum_year = int(
        filtered_df["year"].max()
    )

    # Create empty Plotly figure
    fig = go.Figure()

    # Add one temporal line for every selected entity
    for entity in entities:

        # Extract data for one entity
        entity_df = filtered_df[
            filtered_df[entity_column]
            == entity
        ].copy()

        # Skip entities with no remaining data
        if entity_df.empty:
            continue

        # Ensure chronological ordering
        entity_df = (
            entity_df
            .sort_values("year")
        )

        # Add line and point markers
        fig.add_trace(
            go.Scatter(
                x=entity_df["year"],
                y=entity_df["value"],

                mode="lines+markers",

                name=str(entity),

                line=dict(
                    width=3
                ),

                marker=dict(
                    size=6
                ),

                # Carry the entity name on every point so a click on the line
                # can be resolved back to a country/region/income downstream
                # (used by the dashboard's cross-filtering).
                customdata=[str(entity)] * len(entity_df),

                hovertemplate=(
                    f"<b>{entity}</b><br>"
                    "Year: %{x}<br>"
                    "Coverage: %{y:.2f}%"
                    "<extra></extra>"
                ),
            )
        )

    # Find minimum and maximum observed coverage
    minimum_value = float(
        filtered_df["value"].min()
    )

    maximum_value = float(
        filtered_df["value"].max()
    )

    # Calculate observed coverage span
    value_span = (
        maximum_value
        - minimum_value
    )

    # Add padding so lines do not touch chart boundaries
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

    # Ensure enough vertical range for nearly flat series
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

    # Calculate total time span
    year_span = (
        maximum_year
        - minimum_year
    )

    # Choose readable year tick spacing
    if year_span <= 15:
        year_dtick = 1

    elif year_span <= 35:
        year_dtick = 5

    else:
        year_dtick = 10

    # Add sex to subtitle when available
    if sex is not None:

        subtitle = (
            f"Temporal Trend by "
            f"{level_name} | {sex}"
        )

    else:

        subtitle = (
            f"Temporal Trend by "
            f"{level_name}"
        )

    # Configure overall chart layout
    fig.update_layout(
        template="plotly_white",

        title=dict(
            text=(
                f"{indicator_name}"
                f"<br>"
                f"<sup>{subtitle}</sup>"
            ),

            x=0.5,
            xanchor="center",

            font=dict(
                size=21
            ),
        ),

        # Configure time axis
        xaxis=dict(
            title="Year",

            range=[
                minimum_year - 0.5,
                maximum_year + 0.5,
            ],

            tickmode="linear",
            dtick=year_dtick,

            showgrid=True,

            gridcolor=(
                "rgba(180,180,180,0.20)"
            ),

            zeroline=False,
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

        height=700,

        margin=dict(
            l=80,
            r=50,
            t=130,
            b=100,
        ),

        # Place legend horizontally above chart
        legend=dict(
            title=level_name,

            orientation="h",

            yanchor="bottom",
            y=1.02,

            xanchor="center",
            x=0.5,
        ),

        # Show all entity values together for a year
        hovermode="x unified",

        font=dict(
            family="Arial",
            size=13,
        ),
    )

    # Add source information below chart
    fig.add_annotation(
        text=(
            "Source: WHO Health Inequality "
            "Data Repository"
        ),

        x=0,
        y=-0.15,

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
