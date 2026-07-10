"""Single source of truth for human-readable indicator labels.

Previously each visualization module and app.py carried its own copy of this
mapping, which had already drifted in wording. Import from here instead.
"""

# The six-way indicator_code taxonomy used by the map, sex-gap, temporal-trend,
# region/income and cascade views.
INDICATOR_LABELS = {
    "diab_tx_std": "Diabetes Treatment Coverage (Age-Standardized)",
    "diab_tx_crude": "Diabetes Treatment Coverage (Crude)",
    "htn_tx_std": "Hypertension Treatment Coverage (Age-Standardized)",
    "htn_tx_crude": "Hypertension Treatment Coverage (Crude)",
    "htn_ctrl_std": "Hypertension Effective Control (Age-Standardized)",
    "htn_ctrl_crude": "Hypertension Effective Control (Crude)",
}

# The three-way "indicator family" taxonomy used only by the age-standardized
# vs. crude view (which pairs the crude/standardized columns of one family).
INDICATOR_FAMILY_LABELS = {
    "diabetes_treatment": "Diabetes Treatment Coverage",
    "hypertension_treatment": "Hypertension Treatment Coverage",
    "hypertension_control": "Hypertension Effective Control",
}
