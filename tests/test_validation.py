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
    frame = pd.DataFrame({"sample_name": ["S1", "S2"], "A": [1, np.nan], "B": [1, np.nan], "C": [1, 2]})
    result = DataValidator.validate_duplicate_columns(frame, ignore_columns=["sample_name"])
    assert not result["valid"]
    assert result["duplicate_groups"] == [["A", "B"]]

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
    result = DataValidator.validate_precision_counts(pd.DataFrame({"precision_count_beads": [1000, 50000, 100000]}))
    assert result == {"valid": True, "issues": [], "warnings": []}

def test_precision_counts_reject_non_positive_missing_and_text_values():
    result = DataValidator.validate_precision_counts(pd.DataFrame({"precision_count_beads": [0, -1, None, "bad"]}))
    assert not result["valid"]
    assert any("missing or non-numeric" in issue for issue in result["issues"])
    assert any("zero or negative" in issue for issue in result["issues"])

def test_precision_counts_warn_at_low_and_high_thresholds_without_failing():
    result = DataValidator.validate_precision_counts(pd.DataFrame({"precision_count_beads": [999, 100001]}))
    assert result["valid"]
    assert len(result["warnings"]) == 2

def test_validation_report_reflects_failure():
    report = DataValidator.create_validation_report(day_0_val={"valid": False, "total_samples": 1, "issues": ["bad sample"]})
    assert "Validation issues detected" in report
    assert "bad sample" in report
