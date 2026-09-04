from io import BytesIO
from pathlib import Path
import sys
import pandas as pd
import pandas.testing as pdt

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
from flow_cleaning.data_processing import FlowDataCleaner
from flow_cleaning.validation import DataValidator
from flow_cleaning.master_export import build_master_workbook

class UploadedBytes(BytesIO):
    def __init__(self, content: bytes, name: str):
        super().__init__(content)
        self.name = name

def test_csv_loader_never_rescales_mixed_frequency_values():
    upload = UploadedBytes(b"sample_name,Freq. of Parent\nS1,4.7%\nS2,0.047\nS3,0.04%\n", "flow.csv")
    loaded = FlowDataCleaner().load_files([upload])["flow.csv"]
    assert loaded["Freq. of Parent"].tolist() == ["4.7%", "0.047", "0.04%"]

def test_excel_loader_preserves_numeric_and_percentage_cells(tmp_path):
    source = pd.DataFrame({"sample_name": ["S1", "S2", "S3"], "Frequency": [0.047, "4.7%", 0.04]})
    path = tmp_path / "flow.xlsx"
    source.to_excel(path, index=False)
    upload = UploadedBytes(path.read_bytes(), "flow.xlsx")
    loaded = FlowDataCleaner().load_files([upload])["flow.xlsx"]
    assert loaded["Frequency"].tolist() == [0.047, "4.7%", 0.04]

def test_frequency_validation_is_observational_and_does_not_mutate_values():
    frame = pd.DataFrame({"Freq": ["4.7%", "0.047", "0.04%", None]})
    original = frame.copy(deep=True)
    result = DataValidator.validate_frequency_ranges(frame)
    pdt.assert_frame_equal(frame, original)
    assert result["valid"]
    assert result["details"]["Freq"]["input_formats"] == ["explicit_percent", "plain_numeric"]
    assert result["details"]["Freq"]["explicit_percent_values"] == 2
    assert result["details"]["Freq"]["plain_numeric_values"] == 1
    assert any("mixes explicit % strings" in warning for warning in result["warnings"])

def test_all_values_below_one_are_flagged_as_ambiguous_not_rescaled():
    frame = pd.DataFrame({"Frequency": [0.04, 0.07, 0.2]})
    result = DataValidator.validate_frequency_ranges(frame)
    assert frame["Frequency"].tolist() == [0.04, 0.07, 0.2]
    assert result["valid"]
    assert any("proportions or rare percentages" in warning for warning in result["warnings"])

def test_explicit_percent_column_is_profiled_without_division():
    frame = pd.DataFrame({"Freq": ["0.04%", "4.7 %", "100%"]})
    result = DataValidator.validate_frequency_ranges(frame)
    assert frame["Freq"].tolist() == ["0.04%", "4.7 %", "100%"]
    assert result["valid"]
    assert result["details"]["Freq"]["explicit_percent_values"] == 3

def test_negative_and_over_100_values_still_fail_range_validation():
    result = DataValidator.validate_frequency_ranges(pd.DataFrame({"Freq": ["-0.1%", "100.1%"]}))
    assert not result["valid"]

def test_non_frequency_columns_are_not_profiled():
    result = DataValidator.validate_frequency_ranges(pd.DataFrame({"Count": [0.04], "MFI": [0.5]}))
    assert result["frequency_columns"] == []
    assert result["valid"]

def test_mixed_frequency_values_survive_master_workbook_round_trip():
    day0 = pd.DataFrame({"sample_name": ["S1", "S2", "S3"], "Freq": ["4.7%", 0.047, "0.04%"]})
    day7 = day0.copy()
    workbook = build_master_workbook(day0, day7)
    exported = pd.read_excel(BytesIO(workbook), sheet_name="day_0_flow_data")
    assert exported["Freq"].tolist() == ["4.7%", 0.047, "0.04%"]
