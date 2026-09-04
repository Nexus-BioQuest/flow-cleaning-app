from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flow_cleaning.workbook_merge import merge_master_files


def test_merge_master_files_combines_flow_and_name_mapping_sheets(tmp_path):
    base_path = tmp_path / "base_master.xlsx"
    other_path = tmp_path / "other_master.xlsx"
    output_path = tmp_path / "merged_master.xlsx"

    base_day0 = pd.DataFrame({
        "sample_id": ["sample_a", "sample_b"],
        "day_0_value": [10, 20],
    })
    other_day0 = pd.DataFrame({
        "sample_id": ["sample_b", "sample_c"],
        "qc_flag": ["pass", "pass"],
        "extra_col": [99, 100],
    })

    base_mapping = pd.DataFrame({
        "gating_name": ["CD19+", "CD3+"],
        "plot_name": ["B cells", "T cells"],
    })
    other_mapping = pd.DataFrame({
        "gating_name": ["CD3+", "CD4+"],
        "plot_name": ["T cells", "Helper T cells"],
    })

    with pd.ExcelWriter(base_path) as writer:
        base_day0.to_excel(writer, sheet_name="day_0_flow_data", index=False)
        base_mapping.to_excel(writer, sheet_name="name_mapping", index=False)

    with pd.ExcelWriter(other_path) as writer:
        other_day0.to_excel(writer, sheet_name="day_0_flow_data", index=False)
        other_mapping.to_excel(writer, sheet_name="name_mapping", index=False)

    merged_path = merge_master_files(base_path, other_path, output_path)

    assert merged_path == output_path

    with pd.ExcelFile(output_path) as xl:
        assert "day_0_flow_data" in xl.sheet_names
        assert "name_mapping" in xl.sheet_names

        merged_day0 = pd.read_excel(output_path, sheet_name="day_0_flow_data")
        merged_mapping = pd.read_excel(output_path, sheet_name="name_mapping")

    assert "day_0_value" in merged_day0.columns
    assert "qc_flag" in merged_day0.columns
    assert "extra_col" in merged_day0.columns
    assert set(merged_day0["sample_id"]) == {"sample_a", "sample_b", "sample_c"}
    assert len(merged_mapping) == 3
    assert set(merged_mapping["gating_name"]) == {"CD19+", "CD3+", "CD4+"}
