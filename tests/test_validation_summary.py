import pandas as pd

from flow_cleaning.ui.validation_tab import build_findings, run_checks


def test_wide_dataset_is_summarized_not_expanded_per_column():
    data_0 = {"sample_name": ["S1", "S2"]}
    data_7 = {"sample_name": ["S1", "S2"]}
    for index in range(450):
        column = f"Gate {index} | Freq. of Parent"
        data_0[column] = [0.01, 0.04]
        data_7[column] = [0.02, 0.03]
    findings = build_findings(run_checks(pd.DataFrame(data_0), pd.DataFrame(data_7)))
    frequency = findings[findings["Check"] == "Frequency scale"]
    assert len(frequency) == 2
    assert frequency["Affected"].tolist() == [450, 450]


def test_one_rare_frequency_column_is_not_flagged_when_dataset_contains_values_above_one():
    frame = pd.DataFrame({
        "sample_name": ["S1", "S2"],
        "Rare | Freq. of Parent": [0.01, 0.04],
        "Common | Freq. of Parent": [12.0, 25.0],
    })
    results = run_checks(frame, frame.copy())
    assert not results["day_0_frequency"]["all_plain_numeric_between_zero_and_one"]
    findings = build_findings(results)
    assert findings[findings["Check"] == "Frequency scale"].empty


def test_dataset_wide_zero_to_one_pattern_is_flagged_once_per_day():
    frame = pd.DataFrame({
        "sample_name": ["S1", "S2"],
        "Rare | Frequency": [0.001, 0.04],
        "Common | Frequency": [0.4, 1.0],
    })
    results = run_checks(frame, frame.copy())
    assert results["day_0_frequency"]["all_plain_numeric_between_zero_and_one"]
    findings = build_findings(results)
    scale = findings[findings["Check"] == "Frequency scale"]
    assert len(scale) == 2
    assert scale["Affected"].tolist() == [2, 2]


def test_explicit_percent_values_do_not_trigger_proportion_review():
    frame = pd.DataFrame({"sample_name": ["S1", "S2"], "Rare | Frequency": ["0.01%", "0.04%"]})
    results = run_checks(frame, frame.copy())
    assert not results["day_0_frequency"]["all_plain_numeric_between_zero_and_one"]


def test_frequency_categories_are_actionable_and_values_are_unchanged():
    day_0 = pd.DataFrame({
        "sample_name": ["S1", "S2", "S3"],
        "Rare | Frequency": [0.01, 0.02, 0.04],
        "Mixed | Frequency": ["4.7%", "0.047", "0.04%"],
        "Bad | Frequency": [-1, 20, 101],
        "Text | Frequency": ["error", "0.2", "0.3"],
    })
    original = day_0.copy(deep=True)
    results = run_checks(day_0, day_0.copy())
    findings = build_findings(results)
    assert (findings["Priority"] == "Action required").any()
    assert (findings["Priority"] == "Review").any()
    pd.testing.assert_frame_equal(day_0, original)


def test_column_mismatch_is_one_summary_row_even_when_many_columns_differ():
    day_0 = pd.DataFrame({"sample_name": ["S1"], **{f"A{i}": [i] for i in range(300)}})
    day_7 = pd.DataFrame({"sample_name": ["S1"], **{f"B{i}": [i] for i in range(300)}})
    findings = build_findings(run_checks(day_0, day_7))
    mismatch = findings[findings["Check"] == "Column structure"]
    assert len(mismatch) == 1
    assert mismatch.iloc[0]["Affected"] == 600
