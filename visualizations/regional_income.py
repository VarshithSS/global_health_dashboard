import pandas as pd
import plotly.graph_objects as go


INDICATOR_LABELS = {
    "diab_tx_std":
        "Diabetes Treatment Coverage (Age-Standardized)",

    "diab_tx_crude":
        "Diabetes Treatment Coverage (Crude)",

    "htn_ctrl_std":
        "Hypertension Effective Control (Age-Standardized)",

    "htn_ctrl_crude":
        "Hypertension Effective Control (Crude)",

    "htn_tx_std":
        "Hypertension Treatment Coverage (Age-Standardized)",

    "htn_tx_crude":
        "Hypertension Treatment Coverage (Crude)",
}


def create_regional_income_comparison(
    df: pd.DataFrame,
    indicator: str,
    year: int,
) -> go.Figure:
    """
    Task 5: Regional and Income-Group Comparison.

    Creates a grouped bar chart comparing mean indicator
    values across WHO regions and World Bank income groups.

    Error bars show standard deviation.
    """

    # Required columns from the actual dataset
    required_columns = {
        "who_region",
        "income_group",
        "indicator_code",
        "year",
        "mean",
        "median",
        "std",
        "count",
    }

    # Check for missing columns
    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:
        raise ValueError(
            f"Missing required columns: "
            f"{sorted(missing_columns)}"
        )

    # Work on a copy
    data = df.copy()

    # Convert year to numeric
    data["year"] = pd.to_numeric(
        data["year"],
        errors="coerce"
    )

    # Convert summary statistics to numeric
    data["mean"] = pd.to_numeric(
        data["mean"],
        errors="coerce"
    )

    data["median"] = pd.to_numeric(
        data["median"],
        errors="coerce"
    )

    data["std"] = pd.to_numeric(
        data["std"],
        errors="coerce"
    )

    data["count"] = pd.to_numeric(
        data["count"],
        errors="coerce"
    )

    # Remove rows missing essential values
    data = data.dropna(
        subset=[
            "who_region",
            "income_group",
            "indicator_code",
            "year",
            "mean",
        ]
    )

    # Convert valid years to integers
    data["year"] = (
        data["year"]
        .astype(int)
    )

    # Validate selected indicator
    available_indicators = sorted(
        data["indicator_code"]
        .dropna()
        .astype(str)
        .unique()
    )

    if indicator not in available_indicators:
        raise ValueError(
            f"Invalid indicator '{indicator}'. "
            f"Available indicators: "
            f"{available_indicators}"
        )

    # Filter selected indicator and year
    filtered_df = data[
        (data["indicator_code"] == indicator)
        & (data["year"] == int(year))
    ].copy()

    if filtered_df.empty:
        raise ValueError(
            f"No data found for "
            f"indicator='{indicator}', "
            f"year={year}"
        )

    # Get readable indicator name
    indicator_name = (
        INDICATOR_LABELS.get(
            indicator,
            indicator
        )
    )

    # Get WHO regions
    regions = sorted(
        filtered_df["who_region"]
        .dropna()
        .astype(str)
        .unique()
    )

    # Preferred logical income-group order
    preferred_income_order = [
        "Low-income",
        "Lower-middle-income",
        "Upper-middle-income",
        "High-income",
    ]

    # Get actual income groups
    available_income_groups = list(
        filtered_df["income_group"]
        .dropna()
        .astype(str)
        .unique()
    )

    # Keep preferred order when names match
    income_groups = [
        group
        for group in preferred_income_order
        if group in available_income_groups
    ]

    # Add any unexpected groups
    income_groups += [
        group
        for group in sorted(
            available_income_groups
        )
        if group not in income_groups
    ]

    # Create empty figure
    fig = go.Figure()

    # Add one bar series per income group
    for income_group in income_groups:

        group_df = filtered_df[
            filtered_df["income_group"]
            == income_group
        ].copy()

        # Align every income group to the same region order
        group_df = (
            group_df
            .set_index("who_region")
            .reindex(regions)
            .reset_index()
        )

        # Build hover information
        customdata = group_df[
            [
                "median",
                "std",
                "count",
            ]
        ].to_numpy()

        # Add grouped bars
        fig.add_trace(
            go.Bar(
                x=group_df["who_region"],

                y=group_df["mean"],

                name=str(
                    income_group
                ),

                error_y=dict(
                    type="data",
                    array=group_df["std"],
                    visible=True,
                ),

                customdata=customdata,

                hovertemplate=(
                    "<b>%{x}</b><br>"
                    "Income Group: "
                    + str(income_group)
                    + "<br>"
                    "Mean: %{y:.2f}%<br>"
                    "Median: %{customdata[0]:.2f}%<br>"
                    "Std Dev: %{customdata[1]:.2f}<br>"
                    "Count: %{customdata[2]:.0f}"
                    "<extra></extra>"
                ),
            )
        )

    # Find visible maximum including standard deviation
    upper_values = (
        filtered_df["mean"]
        + filtered_df["std"].fillna(0)
    )

    maximum_value = float(
        upper_values.max()
    )

    # Configure chart layout
    fig.update_layout(
        template="plotly_white",

        title=dict(
            text=(
                f"{indicator_name}"
                "<br>"
                f"<sup>"
                f"WHO Region × Income Group Comparison | "
                f"{year}"
                f"</sup>"
            ),

            x=0.5,
            xanchor="center",

            font=dict(
                size=21
            ),
        ),

        xaxis=dict(
            title="WHO Region",

            tickangle=-20,

            showgrid=False,
        ),

        yaxis=dict(
            title="Mean Coverage (%)",

            range=[
                0,
                min(
                    100,
                    maximum_value * 1.15
                )
            ],

            ticksuffix="%",

            showgrid=True,

            gridcolor=(
                "rgba(180,180,180,0.25)"
            ),

            zeroline=False,
        ),

        barmode="group",

        bargap=0.18,

        bargroupgap=0.06,

        height=720,

        margin=dict(
            l=80,
            r=50,
            t=130,
            b=140,
        ),

        legend=dict(
            title="World Bank Income Group",

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

    # Add explanation of error bars
    fig.add_annotation(
        text=(
            "Bars show mean coverage; "
            "error bars show ±1 standard deviation"
        ),

        x=0.5,
        y=-0.24,

        xref="paper",
        yref="paper",

        showarrow=False,

        font=dict(
            size=12,
            color="dimgray",
        ),
    )

    # Add source
    fig.add_annotation(
        text=(
            "Source: WHO Health Inequality "
            "Data Repository"
        ),

        x=0,
        y=-0.32,

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