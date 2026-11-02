"""Build editable gate mappings from the app's fixed naming rules."""
from __future__ import annotations
import pandas as pd
from flow_cleaning.gate_naming_rules import create_gate_name_mapping

OUTPUT_COLUMNS = ["gating_name", "metric", "plot_name", "for_graphing"]

def generate_gate_mapping(day_0: pd.DataFrame, day_7: pd.DataFrame,
                          additional_days: list[pd.DataFrame] | None = None) -> pd.DataFrame:
    """Build editable gate mappings from all processed-day columns."""
    columns_by_case = {}
    day_columns = [day_0.columns, day_7.columns]
    day_columns.extend(day.columns for day in (additional_days or []))
    for column in (column for columns in day_columns for column in columns):
        if column != "sample_name": columns_by_case.setdefault(str(column).casefold(), column)
    rows = []
    for column in sorted(columns_by_case.values()):
        gate, separator, metric = str(column).partition(" | ")
        rows.append({"gate_path": gate.strip(), "metric": metric.strip() if separator else "Count",
                     "original_column": column})
    if not rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    mapping = create_gate_name_mapping(pd.DataFrame(rows), gate_col="gate_path", metric_col="metric")
    mapping["for_graphing"] = True
    return mapping.rename(columns={"original_name": "gating_name"})[OUTPUT_COLUMNS]
