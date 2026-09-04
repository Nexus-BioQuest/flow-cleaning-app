import numpy as np
import pandas as pd

from flow_cleaning.data_processing import FlowDataCleaner


def reconcile(files):
    return FlowDataCleaner().merge_random_chunks(files)


def test_disjoint_samples_same_columns_stack_without_duplicates():
    merged, conflicts = reconcile({
        "a.csv": pd.DataFrame({"sample_name": ["S1"], "CD4 | Count": [10]}),
        "b.csv": pd.DataFrame({"sample_name": ["S2"], "CD4 | Count": [20]}),
    })
    assert merged.to_dict("records") == [
        {"sample_name": "S1", "CD4 | Count": 10},
        {"sample_name": "S2", "CD4 | Count": 20},
    ]
    assert conflicts == []


def test_same_samples_disjoint_columns_join_wide():
    merged, conflicts = reconcile({
        "counts.csv": pd.DataFrame({"sample_name": ["S1", "S2"], "CD4 | Count": [10, 20]}),
        "freq.csv": pd.DataFrame({"sample_name": ["S1", "S2"], "CD4 | Frequency": [1.2, 2.3]}),
    })
    assert merged.shape == (2, 3)
    assert merged.loc[1, "CD4 | Frequency"] == 2.3
    assert conflicts == []


def test_arbitrary_partial_overlap_reconciles_without_thresholds():
    merged, conflicts = reconcile({
        "a.csv": pd.DataFrame({"sample_name": ["S1", "S2"], "A": [1, 2]}),
        "b.csv": pd.DataFrame({"sample_name": ["S2", "S3"], "B": [20, 30]}),
        "c.csv": pd.DataFrame({"sample_name": ["S3", "S4"], "C": [300, 400]}),
    })
    assert merged["sample_name"].tolist() == ["S1", "S2", "S3", "S4"]
    assert merged.loc[merged.sample_name == "S2", "B"].item() == 20
    assert merged.loc[merged.sample_name == "S3", "C"].item() == 300
    assert conflicts == []


def test_identical_repeated_cells_and_rows_are_deduplicated():
    frame = pd.DataFrame({"sample_name": ["S1", "S1"], "A": [1.0, 1.0]})
    merged, conflicts = reconcile({"a.csv": frame, "copy.csv": frame.copy()})
    assert len(merged) == 1
    assert merged.loc[0, "A"] == 1
    assert conflicts == []


def test_missing_cells_are_coalesced_from_other_chunks():
    merged, conflicts = reconcile({
        "a.csv": pd.DataFrame({"sample_name": ["S1"], "A": [np.nan], "B": [2]}),
        "b.csv": pd.DataFrame({"sample_name": ["S1"], "A": [1], "B": [np.nan]}),
    })
    assert merged.loc[0, ["A", "B"]].tolist() == [1, 2]
    assert conflicts == []


def test_case_and_spacing_variants_of_columns_are_one_column():
    merged, conflicts = reconcile({
        "a.csv": pd.DataFrame({"sample_name": ["S1"], "CD4 | Count": [1]}),
        "b.csv": pd.DataFrame({"Sample_Name": ["S2"], " cd4  |  count ": [2]}),
    })
    assert merged.columns.tolist() == ["sample_name", "CD4 | Count"]
    assert merged["CD4 | Count"].tolist() == [1, 2]
    assert conflicts == []


def test_case_variant_columns_within_one_file_are_reconciled_not_dropped():
    frame = pd.DataFrame([["S1", 1, 1], ["S2", np.nan, 2]],
                         columns=["sample_name", "CD4 | Count", "cd4 | count"])
    merged, conflicts = reconcile({"a.csv": frame})
    assert merged.columns.tolist() == ["sample_name", "CD4 | Count"]
    assert merged["CD4 | Count"].tolist() == [1, 2]
    assert conflicts == []


def test_case_variant_columns_within_one_file_report_conflicting_values():
    frame = pd.DataFrame([["S1", 1, 2]],
                         columns=["sample_name", "CD4 | Count", "cd4 | count"])
    merged, conflicts = reconcile({"a.csv": frame})
    assert merged.loc[0, "CD4 | Count"] == 1
    assert len(conflicts) == 1


def test_conflicting_repeated_measurement_is_never_silent():
    merged, conflicts = reconcile({
        "first.csv": pd.DataFrame({"sample_name": ["S1"], "A": [1]}),
        "second.csv": pd.DataFrame({"sample_name": ["S1"], "A": [2]}),
    })
    assert merged.loc[0, "A"] == 1
    assert len(conflicts) == 1
    assert [entry["value"] for entry in conflicts[0]["values"]] == [1, 2]
    assert conflicts[0]["resolution"] == "First value retained pending review"


def test_sample_names_are_trimmed_but_not_case_folded():
    merged, conflicts = reconcile({
        "a.csv": pd.DataFrame({"sample_name": [" S1 ", "s1"], "A": [1, 2]})
    })
    assert merged["sample_name"].tolist() == ["S1", "s1"]
    assert conflicts == []
