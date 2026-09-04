from io import BytesIO
import json
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT
FIXTURES = Path(__file__).parent / "fixtures" / "flowjo"
sys.path.insert(0, str(APP_DIR))

from flow_cleaning.data_processing import FlowDataCleaner
from flow_cleaning.master_export import build_master_workbook
from flow_cleaning.validation import DataValidator

class UploadedFixture(BytesIO):
    def __init__(self, path: Path):
        super().__init__(path.read_bytes())
        self.name = path.name

def _load(path: Path) -> pd.DataFrame:
    return FlowDataCleaner().load_files([UploadedFixture(path)])[path.name]

def test_manifest_frequency_fixtures_are_preserved_and_profiled():
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    for filename, expected in manifest.items():
        frame = _load(FIXTURES / filename)
        assert frame[expected["column"]].tolist() == expected["raw_values"]
        original = frame.copy(deep=True)
        result = DataValidator.validate_frequency_ranges(frame)
        pd.testing.assert_frame_equal(frame, original)
        assert result["valid"] is expected["valid"]
        assert result["details"][expected["column"]]["input_formats"] == expected["formats"]
        if text := expected.get("warning_contains"):
            assert any(text in warning for warning in result["warnings"])

def test_cleaning_fixture_removes_only_documented_rows_and_duplicate_column():
    path = FIXTURES / "cleaning_edge_cases.csv"
    cleaned, summary = FlowDataCleaner().process_files([UploadedFixture(path)], remove_fmo=True)
    assert cleaned["sample_name"].tolist() == ["S1", "S2", "Mean", "SD"]
    # Mean/SD removal is performed explicitly by the app after the general cleaner.
    assert cleaned.columns.tolist() == ["sample_name", "Population | Count"]
    assert summary["fmo_removed"] == 1

def test_golden_values_survive_master_export():
    day0 = _load(FIXTURES / "mixed_frequency_formats.csv")
    day7 = _load(FIXTURES / "rare_numeric_frequencies.csv")
    workbook = build_master_workbook(day0, day7)
    exported_day0 = pd.read_excel(BytesIO(workbook), sheet_name="day_0_flow_data")
    exported_day7 = pd.read_excel(BytesIO(workbook), sheet_name="day_7_flow_data")
    assert exported_day0.iloc[:3, 1].tolist() == ["4.7%", "0.047", "0.04%"]
    assert exported_day7.iloc[:, 1].tolist() == [0.04, 0.07, 0.2]
