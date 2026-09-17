"""Build the master workbook consumed by the analysis application."""
from io import BytesIO

import pandas as pd


def build_master_workbook(day_0: pd.DataFrame, day_7: pd.DataFrame, day_0_precision=None,
                          day_7_precision=None, gate_names=None, metadata=None) -> bytes:
    """Return the same workbook sheets produced by the original Streamlit block."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        day_0.to_excel(writer, index=False, sheet_name="day_0_flow_data")
        day_7.to_excel(writer, index=False, sheet_name="day_7_flow_data")
        if day_0_precision is not None: day_0_precision.to_excel(writer, index=False, sheet_name="day_0_precision_count")
        if day_7_precision is not None: day_7_precision.to_excel(writer, index=False, sheet_name="day_7_precision_count")
        if gate_names is not None:
            gate_names.to_excel(writer, index=False, sheet_name="name_mapping")
        if metadata is not None: metadata.to_excel(writer, index=False, sheet_name="metadata")
    return output.getvalue()
