from pathlib import Path
import sys
import numpy as np
import pandas as pd

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
from flow_cleaning.validation import DataValidator

def test_column_consistency_is_case_insensitive_and_day0_is_canonical():
    day0 = pd.DataFrame(columns=["sample_name", "CD4 | Count"])
    day7 = pd.DataFrame(columns=["SAMPLE_NAME", "cd4 | count"])
    result = DataValidator.validate_column_consistency(day0, day7)
    assert result["valid"]
    assert result["canonical_map"]["cd4 | count"] == "CD4 | Count"
    assert len(result["case_mismatches"]) == 2

def test_column_consistency_rejects_missing_or_extra_columns():
    result = DataValidator.validate_column_consistency(
        pd.DataFrame(columns=["sample_name", "A"]), pd.DataFrame(columns=["sample_name", "B"]))
    assert not result["valid"]
    assert result["only_in_day_0"] == {"A"}
    assert result["only_in_day_7"] == {"B"}

def test_frequency_validation_accepts_both_supported_scales():
    proportions = DataValidator.validate_frequency_ranges(pd.DataFrame({"Freq parent": [0, .25, 1]}))
    percentages = DataValidator.validate_frequency_ranges(pd.DataFrame({"Frequency": [0, 25, 100]}))
    assert proportions["valid"] and percentages["valid"]

def test_frequency_validation_rejects_values_outside_zero_to_100():
    result = DataValidator.validate_frequency_ranges(pd.DataFrame({"Freq": [-.1, 101]}))
    assert not result["valid"]
    assert result["issues"]

def test_frequency_validation_rejects_non_numeric_values():
    result = DataValidator.validate_frequency_ranges(pd.DataFrame({"Freq": [0.2, "not measured"]}))
    assert not result["valid"]
    assert "non-numeric" in result["issues"][0]

def test_duplicate_value_columns_ignores_sample_identifier():
    frame = pd.DataFrame({"sample_name": ["S1", "S2"], "A": [1, 2], "B": [1, 2], "C": [1, 3]})
    result = DataValidator.validate_duplicate_columns(frame, ignore_columns=["sample_name"])
    assert not result["valid"]
    assert result["duplicate_groups"] == [["A", "B"]]
    assert result["duplicate_details"][0]["rows"][0]["values"] == {"A": 1, "B": 1}
    assert result["duplicate_details"][0]["rows"][1]["values"] == {"A": 2, "B": 2}

def test_duplicate_value_columns_ignore_sparse_columns_with_shared_values():
    frame = pd.DataFrame({"A": [1, np.nan, np.nan], "B": [1, np.nan, np.nan], "C": [1, 2, 3]})
    result = DataValidator.validate_duplicate_columns(frame)
    assert result["valid"]
    assert result["duplicate_groups"] == []

def test_duplicate_value_columns_require_at_least_two_populated_rows():
    frame = pd.DataFrame({"A": [1, np.nan], "B": [1, np.nan], "C": [2, 3]})
    result = DataValidator.validate_duplicate_columns(frame)
    assert result["valid"]
    assert result["duplicate_groups"] == []

def test_reported_count_columns_are_not_identical():
    frame = pd.DataFrame({
        "GC count": [1, 2433, 0, 2262, 1727, 1138, 1879, 44, 1915, 1830, 1856, 1853, 2033, 2029, 4, 0, 4, 1, 2, 1, 1, 1, 2, 1, 2, 1, 2, 1, 0, 725, 959],
        "CD8 proliferated count": [5156, 9206, 9269, 10163, 7788, 8169, 4260, 12691, 2503, 9002, 9543, 9103, 9651, 9629, 4530, 4743, 6376, 4610, 5745, np.nan, 7455, 2356, 4733, 4560, 4650, 4774, 4394, 4743, 5294, np.nan, np.nan],
    })
    result = DataValidator.validate_duplicate_columns(frame)
    assert result["duplicate_groups"] == []

def test_duplicate_value_columns_require_every_row_to_match():
    frame = pd.DataFrame({"A": [1, 2], "B": [1, 3], "C": [9, 8]})
    result = DataValidator.validate_duplicate_columns(frame)
    assert result["valid"]
    assert result["duplicate_groups"] == []

def test_duplicate_value_columns_do_not_stop_after_first_two_rows():
    frame = pd.DataFrame({"A": [6347, 10, 9355], "B": [6347, 11, 9355]})
    result = DataValidator.validate_duplicate_columns(frame)
    assert result["valid"]
    assert result["duplicate_groups"] == []

def test_sample_validation_rejects_missing_duplicates_fmo_and_extensions():
    frame = pd.DataFrame({"sample_name": ["S1", " S1 ", None, " ", "FMO_CD4", "S2.fcs"]})
    result = DataValidator.validate_sample_names(frame)
    assert not result["valid"]
    assert any("duplicate" in issue for issue in result["issues"])
    assert any("empty" in issue for issue in result["issues"])
    assert any("FMO" in issue for issue in result["issues"])
    assert any(".fcs" in issue for issue in result["issues"])

def test_sample_validation_reports_metadata_mismatch():
    flow = pd.DataFrame({"sample_name": ["S1", "S2"]})
    metadata = pd.DataFrame({"sample_name": ["S1", "S3"]})
    result = DataValidator.validate_sample_names(flow, metadata)
    assert not result["valid"]
    assert result["metadata_match"]["in_flow_not_metadata"] == {"S2"}
    assert result["metadata_match"]["in_metadata_not_flow"] == {"S3"}

def test_precision_counts_accept_normal_range():
    result = DataValidator.validate_precision_counts(pd.DataFrame({"recorded_bead_count": [1000, 50000, 100000]}))
    assert result == {"valid": True, "issues": [], "warnings": []}

def test_precision_counts_accept_the_legacy_column_name():
    result = DataValidator.validate_precision_counts(pd.DataFrame({"precision_count_beads": [1000, 50000, 100000]}))
    assert result == {"valid": True, "issues": [], "warnings": []}

def test_precision_counts_reject_non_positive_missing_and_text_values():
    result = DataValidator.validate_precision_counts(pd.DataFrame({"recorded_bead_count": [0, -1, None, "bad"]}))
    assert not result["valid"]
    assert any("missing or non-numeric" in issue for issue in result["issues"])
    assert any("zero or negative" in issue for issue in result["issues"])

def test_precision_counts_warn_at_low_and_high_thresholds_without_failing():
    result = DataValidator.validate_precision_counts(pd.DataFrame({"recorded_bead_count": [999, 100001]}))
    assert result["valid"]
    assert len(result["warnings"]) == 2

def test_validation_report_reflects_failure():
    report = DataValidator.create_validation_report(day_0_val={"valid": False, "total_samples": 1, "issues": ["bad sample"]})
    assert "Validation issues detected" in report
    assert "bad sample" in report
