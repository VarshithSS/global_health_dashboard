import pandas as pd
import plotly.graph_objects as go

from visualizations.labels import INDICATOR_LABELS


# TASK 2: SEX GAP ANALYSIS

def create_sex_gap_chart(
    df: pd.DataFrame,
    indicator: str,
    country: str,
) -> go.Figure:
    """
    Task 2: Sex Gap Analysis

    Creates an interactive dumbbell chart comparing
    Male and Female coverage across years for one
    selected country and indicator.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame loaded from sex_gap_data.csv.

    indicator : str
        Selected indicator code.

    country : str
        Selected country name.

    Returns
    -------
    plotly.graph_objects.Figure
        Interactive Plotly dumbbell chart.
    """

    
    # 1. VALIDATE REQUIRED COLUMNS

    required_columns = {
        "iso3",
        "country",
        "year",
        "indicator_code",
        "who_region",
        "income_group",
        "Male",
        "Female",
        "delta_sex",
    }

    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:

        raise ValueError(
            "Missing required columns: "
            f"{sorted(missing_columns)}"
        )


    
    # 2. WORK ON COPY

    data = df.copy()


    # 3. CONVERT NUMERIC COLUMNS

    data["year"] = pd.to_numeric(
        data["year"],
        errors="coerce"
    )

    data["Male"] = pd.to_numeric(
        data["Male"],
        errors="coerce"
    )

    data["Female"] = pd.to_numeric(
        data["Female"],
        errors="coerce"
    )

    data["delta_sex"] = pd.to_numeric(
        data["delta_sex"],
        errors="coerce"
    )


    # 4. REMOVE INVALID ROWS

    data = data.dropna(
        subset=[
            "country",
            "year",
            "indicator_code",
            "Male",
            "Female",
            "delta_sex",
        ]
    )

    data["year"] = (
        data["year"]
        .astype(int)
    )


    
    # 5. VALIDATE INDICATOR

    available_indicators = sorted(
        data["indicator_code"]
        .unique()
    )

    if indicator not in available_indicators:

        raise ValueError(
            f"Invalid indicator '{indicator}'. "
            f"Available indicators: "
            f"{available_indicators}"
        )


    # 6. VALIDATE COUNTRY

    available_countries = sorted(
        data["country"]
        .unique()
    )

    if country not in available_countries:

        raise ValueError(
            f"Invalid country '{country}'."
        )


    # 7. FILTER SELECTED INDICATOR + COUNTRY

    filtered_df = data[

        (
            data["indicator_code"]
            == indicator
        )

        &

        (
            data["country"]
            == country
        )

    ].copy()


    if filtered_df.empty:

        raise ValueError(
            f"No data found for "
            f"indicator='{indicator}', "
            f"country='{country}'"
        )


    # 8. SORT BY YEAR

    filtered_df = (

        filtered_df
        .sort_values("year")
        .reset_index(drop=True)

    )


    # 9. CLEAN METADATA

    filtered_df["who_region"] = (

        filtered_df["who_region"]
        .fillna("Not available")

    )

    filtered_df["income_group"] = (

        filtered_df["income_group"]
        .fillna("Not available")

    )


    
    # 10. INDICATOR NAME

    indicator_name = (

        INDICATOR_LABELS.get(
            indicator,
            indicator
        )

    )


    # 11. COUNTRY METADATA

    who_region = str(
        filtered_df["who_region"]
        .iloc[0]
    )

    income_group = str(
        filtered_df["income_group"]
        .iloc[0]
    )


    # 12. YEAR RANGE

    minimum_year = int(
        filtered_df["year"].min()
    )

    maximum_year = int(
        filtered_df["year"].max()
    )


    # 13. DYNAMIC X-AXIS RANGE
    #
    # Instead of forcing 0-100, zoom around actual
    # Male/Female values so the sex gap is visible.
    

    all_values = pd.concat(

        [
            filtered_df["Male"],
            filtered_df["Female"],
        ],

        ignore_index=True
    )


    minimum_value = float(
        all_values.min()
    )

    maximum_value = float(
        all_values.max()
    )


    value_span = (
        maximum_value
        - minimum_value
    )


    # At least 3 percentage points padding.
    # Otherwise use 20% of observed span.
    padding = max(
        3.0,
        value_span * 0.20
    )


    x_min = max(
        0.0,
        minimum_value - padding
    )

    x_max = min(
        100.0,
        maximum_value + padding
    )


    # Safety for nearly identical values
    if x_max - x_min < 8:

        midpoint = (
            x_min + x_max
        ) / 2

        x_min = max(
            0,
            midpoint - 4
        )

        x_max = min(
            100,
            midpoint + 4
        )


    # 14. GAP STATISTICS

    mean_gap = float(
        filtered_df["delta_sex"]
        .mean()
    )

    max_abs_gap_index = (

        filtered_df["delta_sex"]
        .abs()
        .idxmax()

    )

    largest_gap_row = (

        filtered_df
        .loc[max_abs_gap_index]

    )

    largest_gap = float(
        largest_gap_row["delta_sex"]
    )

    largest_gap_year = int(
        largest_gap_row["year"]
    )


    # 15. INTERPRET AVERAGE GAP

    if mean_gap > 0:

        average_gap_summary = (
            f"Average gap: {mean_gap:+.2f} pp "
            f"(higher male coverage)"
        )

    elif mean_gap < 0:

        average_gap_summary = (
            f"Average gap: {mean_gap:+.2f} pp "
            f"(higher female coverage)"
        )

    else:

        average_gap_summary = (
            "Average gap: 0.00 pp "
            "(equal coverage)"
        )


    # 16. INTERPRET LARGEST GAP

    if largest_gap > 0:

        largest_gap_summary = (
            f"Largest gap: {largest_gap:+.2f} pp "
            f"in {largest_gap_year} "
            f"(higher male coverage)"
        )

    elif largest_gap < 0:

        largest_gap_summary = (
            f"Largest gap: {largest_gap:+.2f} pp "
            f"in {largest_gap_year} "
            f"(higher female coverage)"
        )

    else:

        largest_gap_summary = (
            f"Largest gap: 0.00 pp "
            f"in {largest_gap_year}"
        )


    # 17. CREATE FIGURE

    fig = go.Figure()


    # 18. CONNECTOR LINES
    #
    # Each horizontal line connects Female and Male
    # coverage for the same year.
    

    for _, row in filtered_df.iterrows():

        gap = float(
            row["delta_sex"]
        )

        fig.add_trace(

            go.Scatter(

                x=[
                    row["Female"],
                    row["Male"],
                ],

                y=[
                    row["year"],
                    row["year"],
                ],

                mode="lines",

                line=dict(
                    color="rgba(110,110,110,0.45)",
                    width=2,
                ),

                customdata=[
                    [gap],
                    [gap],
                ],

                hovertemplate=(
                    f"<b>{int(row['year'])}</b><br>"
                    f"Female: {row['Female']:.2f}%<br>"
                    f"Male: {row['Male']:.2f}%<br>"
                    f"Gap: {gap:+.2f} pp"
                    "<extra></extra>"
                ),

                showlegend=False,
            )
        )



    # 19. FEMALE MARKERS

    fig.add_trace(

        go.Scatter(

            x=filtered_df["Female"],

            y=filtered_df["year"],

            mode="markers",

            name="Female",

            marker=dict(
                size=11,
                symbol="circle",
            ),

            customdata=filtered_df[
                [
                    "Male",
                    "delta_sex",
                    "who_region",
                    "income_group",
                ]
            ].to_numpy(),

            hovertemplate=(

                "<b>Year: %{y}</b><br>"

                "Female Coverage: "
                "%{x:.2f}%<br>"

                "Male Coverage: "
                "%{customdata[0]:.2f}%<br>"

                "Male - Female Gap: "
                "%{customdata[1]:+.2f} pp<br>"

                "WHO Region: "
                "%{customdata[2]}<br>"

                "Income Group: "
                "%{customdata[3]}"

                "<extra></extra>"
            ),
        )
    )


    # 20. MALE MARKERS

    fig.add_trace(

        go.Scatter(

            x=filtered_df["Male"],

            y=filtered_df["year"],

            mode="markers",

            name="Male",

            marker=dict(
                size=11,
                symbol="diamond",
            ),

            customdata=filtered_df[
                [
                    "Female",
                    "delta_sex",
                    "who_region",
                    "income_group",
                ]
            ].to_numpy(),

            hovertemplate=(

                "<b>Year: %{y}</b><br>"

                "Male Coverage: "
                "%{x:.2f}%<br>"

                "Female Coverage: "
                "%{customdata[0]:.2f}%<br>"

                "Male - Female Gap: "
                "%{customdata[1]:+.2f} pp<br>"

                "WHO Region: "
                "%{customdata[2]}<br>"

                "Income Group: "
                "%{customdata[3]}"

                "<extra></extra>"
            ),
        )
    )


    # 21. X-AXIS TICK SPACING

    visible_span = (
        x_max - x_min
    )

    if visible_span <= 15:

        x_dtick = 2

    elif visible_span <= 30:

        x_dtick = 5

    else:

        x_dtick = 10


    # 22. Y-AXIS TICK SPACING
    

    year_span = (
        maximum_year
        - minimum_year
    )

    if year_span <= 15:

        year_dtick = 1

    else:

        year_dtick = 2


    # 23. LAYOUT
    

    fig.update_layout(

        template="plotly_white",

        title=dict(

            text=(

                f"{indicator_name}"

                f"<br>"

                f"<sup>"
                f"{country} | "
                f"{who_region} | "
                f"{income_group}"
                f"</sup>"
            ),

            x=0.5,

            xanchor="center",

            font=dict(
                size=21
            ),
        ),


        
        # Dynamic coverage axis

        xaxis=dict(

            title="Coverage (%)",

            range=[
                x_min,
                x_max
            ],

            ticksuffix="%",

            dtick=x_dtick,

            showgrid=True,

            gridcolor=(
                "rgba(180,180,180,0.25)"
            ),

            zeroline=False,

            fixedrange=False,
        ),


        # Exact year range

        yaxis=dict(

            title="Year",

            range=[
                minimum_year - 0.7,
                maximum_year + 0.7
            ],

            tickmode="linear",

            dtick=year_dtick,

            showgrid=False,

            fixedrange=False,
        ),


        height=720,


        margin=dict(
            l=80,
            r=50,
            t=120,
            b=130,
        ),


        legend=dict(

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


    
    # 24. AVERAGE GAP ANNOTATION

    fig.add_annotation(

        text=average_gap_summary,

        x=0.5,

        y=-0.13,

        xref="paper",

        yref="paper",

        showarrow=False,

        xanchor="center",

        font=dict(
            size=13,
        ),
    )


    # 25. LARGEST GAP ANNOTATION

    fig.add_annotation(

        text=largest_gap_summary,

        x=0.5,

        y=-0.19,

        xref="paper",

        yref="paper",

        showarrow=False,

        xanchor="center",

        font=dict(
            size=12,
            color="dimgray",
        ),
    )


    # 26. SOURCE ANNOTATION

    fig.add_annotation(

        text=(
            "Source: WHO Health Inequality "
            "Data Repository"
        ),

        x=0,

        y=-0.26,

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