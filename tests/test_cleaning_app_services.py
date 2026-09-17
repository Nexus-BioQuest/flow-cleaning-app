from io import BytesIO
from pathlib import Path
import sys
import pandas as pd
import openpyxl

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from flow_cleaning.gate_mapping import OUTPUT_COLUMNS, generate_gate_mapping
from flow_cleaning.master_export import build_master_workbook
from flow_cleaning.precision_counts import (PrecisionCountSettings, concentration_per_microlitre,
                                             create_precision_count_table, detect_bead_count_column)

def test_gate_mapping_preserves_export_schema_and_case_deduplication():
    gate = "Singlets/Scatter/Live/CD4-/Total_B_Cells | Freq. of Parent"
    day_0 = pd.DataFrame({"sample_name": ["S1"], gate: [0.2]})
    day_7 = pd.DataFrame({"sample_name": ["S2"], gate.upper(): [0.3]})
    mapping = generate_gate_mapping(day_0, day_7)
    assert list(mapping.columns) == OUTPUT_COLUMNS
    assert len(mapping) == 1
    assert mapping.loc[0, "metric"] == "Freq. of Parent"
    assert bool(mapping.loc[0, "for_graphing"])

def test_master_workbook_preserves_required_tabs_and_columns():
    day_0 = pd.DataFrame({"sample_name": ["S1"], "value": [1]})
    day_7 = pd.DataFrame({"sample_name": ["S1"], "value": [2]})
    precision = pd.DataFrame({"sample_name": ["S1"], "recorded_bead_count": [100]})
    metadata = pd.DataFrame({"sample_name": ["S1"], "donor": ["D1"]})
    mapping = pd.DataFrame([{column: value for column, value in zip(OUTPUT_COLUMNS, [
        "Singlets/Scatter/Live/CD4-/Total_B_Cells | Count", "Count", "Total B Count",
        True])}])
    workbook = build_master_workbook(day_0, day_7, precision, precision, mapping, metadata)
    excel = pd.ExcelFile(BytesIO(workbook))
    for sheet in ("day_0_flow_data", "day_7_flow_data", "day_0_precision_count",
                  "day_7_precision_count", "name_mapping", "metadata"):
        assert sheet in excel.sheet_names
    assert list(pd.read_excel(BytesIO(workbook), sheet_name="name_mapping").columns) == OUTPUT_COLUMNS
    exported_book = openpyxl.load_workbook(BytesIO(workbook))
    assert "name_mapping_tree" not in exported_book.sheetnames

def test_precision_count_schema_matches_the_normalisation_formula_symbols():
    flow = pd.DataFrame({"sample_name": ["S1"], "Precision Bead Count": [123.0]})
    assert detect_bead_count_column(flow) == "Precision Bead Count"
    table = create_precision_count_table(flow, "Precision Bead Count", PrecisionCountSettings(1e6, 1e3, 50, 150))
    assert list(table.columns) == ["sample_name", "bead_concentration_per_ml", "bead_concentration_per_ul",
        "bead_volume_ul", "expected_bead_count", "sample_volume_ul", "recorded_bead_count"]
    assert table.loc[0, "expected_bead_count"] == 50000  # C_beads x V_bead

def test_bead_concentration_per_ul_is_derived_from_per_ml_concentration():
    assert concentration_per_microlitre(1_000_000) == 1_000
    assert concentration_per_microlitre(2_500_000) == 2_500
