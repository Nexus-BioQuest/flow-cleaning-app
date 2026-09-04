"""Rule-based gate mapping used by the cleaning app.

This module makes the existing automated naming behaviour reusable and testable.
It does not call an AI service: names and classifications come from fixed lookup
tables and regular-expression rules in the existing naming modules.
"""
from __future__ import annotations
import pandas as pd
from flow_cleaning.gate_naming_rules import create_gate_name_mapping

OUTPUT_COLUMNS = ["gating_name", "metric", "plot_name", "for_graphing"]

def generate_gate_mapping(day_0: pd.DataFrame, day_7: pd.DataFrame) -> pd.DataFrame:
    """Generate the same editable mapping as the original inline implementation."""
    columns_by_case = {}
    for column in list(day_0.columns) + list(day_7.columns):
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
