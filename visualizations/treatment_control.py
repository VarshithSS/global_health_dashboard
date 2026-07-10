# Treatment-to-Control Cascade visualization
import pandas as pd
import plotly.graph_objects as go


def create_treatment_control_cascade(
    df: pd.DataFrame,
    country: str,
    year: int,
    sex: str,
) -> go.Figure:
    """
    Task 4: Treatment-to-Control Cascade.

    Compares hypertension treatment coverage against
    effective control coverage for the same country,
    year, and sex.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame loaded from cascade_data.csv.

    country : str
        Selected country.

    year : int
        Selected year.

    sex : str
        Selected sex, such as Male or Female.

    Returns
    -------
    go.Figure
        Interactive Plotly cascade visualization.
    """

    # Required columns for Task 4
    required_columns = {
        "iso3",
        "country",
        "year",
        "sex",
        "who_region",
        "income_group",
        "htn_ctrl_crude",
        "htn_tx_crude",
        "delta_leak",
    }

    # Check whether required columns exist
    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:
        raise ValueError(
            f"Missing required columns: "
            f"{sorted(missing_columns)}"
        )

    # Work on a copy of the original dataset
    data = df.copy()

    # Convert year to numeric
    data["year"] = pd.to_numeric(
        data["year"],
        errors="coerce"
    )

    # Convert treatment coverage to numeric
    data["htn_tx_crude"] = pd.to_numeric(
        data["htn_tx_crude"],
        errors="coerce"
    )

    # Convert control coverage to numeric
    data["htn_ctrl_crude"] = pd.to_numeric(
        data["htn_ctrl_crude"],
        errors="coerce"
    )

    # Convert leakage gap to numeric
    data["delta_leak"] = pd.to_numeric(
        data["delta_leak"],
        errors="coerce"
    )

    # Remove rows missing essential values
    data = data.dropna(
        subset=[
            "country",
            "year",
            "sex",
            "htn_tx_crude",
            "htn_ctrl_crude",
        ]
    )

    # Convert valid years to integers
    data["year"] = (
        data["year"]
        .astype(int)
    )

    # Validate selected country
    available_countries = sorted(
        data["country"]
        .dropna()
        .astype(str)
        .unique()
    )

    if country not in available_countries:
        raise ValueError(
            f"Invalid country '{country}'."
        )

    # Validate selected sex
    available_sexes = sorted(
        data["sex"]
        .dropna()
        .astype(str)
        .unique()
    )

    if sex not in available_sexes:
        raise ValueError(
            f"Invalid sex '{sex}'. "
            f"Available values: {available_sexes}"
        )

    # Filter the exact country, year, and sex
    filtered_df = data[
        (data["country"] == country)
        & (data["year"] == int(year))
        & (data["sex"] == sex)
    ].copy()

    # Ensure data exists for the selection
    if filtered_df.empty:
        raise ValueError(
            f"No cascade data found for "
            f"country='{country}', "
            f"year={year}, "
            f"sex='{sex}'"
        )

    # Use the selected country-year-sex row
    row = filtered_df.iloc[0]

    # Extract treatment coverage
    treatment = float(
        row["htn_tx_crude"]
    )

    # Extract effective control coverage
    control = float(
        row["htn_ctrl_crude"]
    )

    # Calculate leakage directly from treatment minus control
    leakage = (
        treatment
        - control
    )

    # Calculate share of treated coverage that reaches control
    if treatment > 0:
        conversion_rate = (
            control
            / treatment
        ) * 100

    else:
        conversion_rate = 0.0

    # Calculate leakage as a share of treatment coverage
    if treatment > 0:
        leakage_rate = (
            leakage
            / treatment
        ) * 100

    else:
        leakage_rate = 0.0

    # Read metadata for title and hover information
    who_region = str(
        row["who_region"]
    )

    income_group = str(
        row["income_group"]
    )

    # Create the figure
    fig = go.Figure()

    # Add treatment coverage bar
    fig.add_trace(
        go.Bar(
            x=[treatment],

            y=["Treatment Coverage"],

            orientation="h",

            name="Treatment Coverage",

            text=[
                f"{treatment:.1f}%"
            ],

            textposition="inside",

            customdata=[
                [
                    who_region,
                    income_group,
                    year,
                    sex,
                ]
            ],

            hovertemplate=(
                "<b>Treatment Coverage</b><br>"
                "Coverage: %{x:.2f}%<br>"
                "Country: " + country + "<br>"
                "Year: %{customdata[2]}<br>"
                "Sex: %{customdata[3]}<br>"
                "WHO Region: %{customdata[0]}<br>"
                "Income Group: %{customdata[1]}"
                "<extra></extra>"
            ),
        )
    )

    # Add leakage bar
    fig.add_trace(
        go.Bar(
            x=[leakage],

            y=["Pipeline Leakage"],

            orientation="h",

            name="Not Effectively Controlled",

            text=[
                f"{leakage:.1f} pp"
            ],

            textposition="inside",

            customdata=[
                [
                    treatment,
                    control,
                    leakage_rate,
                ]
            ],

            hovertemplate=(
                "<b>Pipeline Leakage</b><br>"
                "Treatment: %{customdata[0]:.2f}%<br>"
                "Effective Control: %{customdata[1]:.2f}%<br>"
                "Leakage: %{x:.2f} pp<br>"
                "Share of treatment lost: "
                "%{customdata[2]:.1f}%"
                "<extra></extra>"
            ),
        )
    )

    # Add effective control bar
    fig.add_trace(
        go.Bar(
            x=[control],

            y=["Effective Control"],

            orientation="h",

            name="Effective Control",

            text=[
                f"{control:.1f}%"
            ],

            textposition="inside",

            customdata=[
                [
                    treatment,
                    conversion_rate,
                ]
            ],

            hovertemplate=(
                "<b>Effective Control</b><br>"
                "Coverage: %{x:.2f}%<br>"
                "Treatment Coverage: "
                "%{customdata[0]:.2f}%<br>"
                "Treatment-to-Control Conversion: "
                "%{customdata[1]:.1f}%"
                "<extra></extra>"
            ),
        )
    )

    # Configure chart layout
    fig.update_layout(
        template="plotly_white",

        title=dict(
            text=(
                "Hypertension Treatment-to-Control Cascade"
                "<br>"
                f"<sup>"
                f"{country} | "
                f"{sex} | "
                f"{year} | "
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

        xaxis=dict(
            title=dict(
                text="Coverage / Gap (%)",
                standoff=20,
            ),

            range=[
                0,
                max(
                    treatment * 1.15,
                    10
                )
            ],

            ticksuffix="%",

            showgrid=True,

            gridcolor=(
                "rgba(180,180,180,0.25)"
            ),

            zeroline=False,
        ),

        yaxis=dict(
            title="",

            categoryorder="array",

            categoryarray=[
                "Effective Control",
                "Pipeline Leakage",
                "Treatment Coverage",
            ],
        ),

        height=640,

        margin=dict(
            l=170,
            r=70,
            t=130,
            b=210,
        ),

        showlegend=False,

        hovermode="closest",

        font=dict(
            family="Arial",
            size=13,
        ),
    )

    # Add treatment-to-control conversion summary
    fig.add_annotation(
        text=(
            f"<b>Treatment → Control Conversion:</b> "
            f"{conversion_rate:.1f}%"
        ),

        x=0.5,
        y=-0.26,

        xref="paper",
        yref="paper",

        showarrow=False,

        font=dict(
            size=13,
        ),
    )

    # Add leakage summary
    fig.add_annotation(
        text=(
            f"<b>Systemic Care Pipeline Leakage:</b> "
            f"{leakage:.2f} percentage points"
        ),

        x=0.5,
        y=-0.34,

        xref="paper",
        yref="paper",

        showarrow=False,

        font=dict(
            size=13,
        ),
    )

    # Add interpretation
    fig.add_annotation(
        text=(
            f"{leakage_rate:.1f}% of treatment coverage "
            f"does not translate into effective control"
        ),

        x=0.5,
        y=-0.42,

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
        y=-0.50,

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


