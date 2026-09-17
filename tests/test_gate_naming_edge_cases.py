import pandas as pd
import pytest

from flow_cleaning.gate_mapping import OUTPUT_COLUMNS, generate_gate_mapping
from flow_cleaning.gate_naming_rules import SmartGateNamer


@pytest.mark.parametrize("gate, expected", [
    ("CD86+", "CD86+"),
    ("cd86_pos", "CD86+"),
    ("CD86 positive", "CD86+"),
    ("CD86⁺", "CD86+"),
    ("PD_1 negative", "PD-1-"),
    ("HLA-DRneg", "HLA-DR-"),
    ("CXCR5 POS", "CXCR5+"),
    ("IgD_neg", "IgD-"),
    ("NewMarker_pos", "NewMarker+"),
])
def test_marker_spelling_and_status_variants(gate, expected):
    assert SmartGateNamer()._get_marker_status_display(gate) == expected

def test_compact_double_negative_marker_names_are_readable():
    assert SmartGateNamer()._get_marker_status_display("CD4negCD8neg") == "CD4-CD8-"

def test_compact_ctla4_pd1_marker_combinations_keep_both_statuses():
    namer = SmartGateNamer()
    assert namer._get_marker_status_display("CTLA4_neg_PD1_pos") == "CTLA4-PD-1+"
    assert namer._get_marker_status_display("CTLA4_pos_PD1_neg") == "CTLA4+PD-1-"
    assert namer._get_marker_status_display("CTLA4_pos_PD1_pos") == "CTLA4+PD-1+"

def test_total_marker_labels_keep_readable_spacing():
    namer = SmartGateNamer()
    assert namer._get_marker_status_display("Total_PD1+") == "Total PD-1+"
    assert namer._get_marker_status_display("Total_CTLA4+") == "Total CTLA4+"

def test_root_gate_metrics_are_explicitly_not_applicable():
    name = SmartGateNamer().generate_name("Singlets", "Freq. of Parent")
    assert name == "Not Applicable"


@pytest.mark.parametrize("metric", [
    "Freq. of Parent", "Frequency of Parent", "frequency_of_parent",
    "Freq of parent (%)", "  FREQ OF PARENT  ",
])
def test_frequency_metric_variants(metric):
    name = SmartGateNamer().generate_name("Live/CD86_pos", metric)
    assert name == "CD86+ % (of Viable)"

@pytest.mark.parametrize("metric", [
    "Freq. of Total_CD4_T_Cells", "Frequency of Total CD4 T Cells",
    "Freq. of Total_CD8_T_Cells",
])
def test_total_t_cell_denominators_are_named(metric):
    name = SmartGateNamer().generate_name("Live/CD4pos/Tregs", metric)
    assert "Unknown Metric" not in name
    assert "%" in name


@pytest.mark.parametrize(("channel", "marker"), [
    ("Comp-BV605_CD86-A", "CD86"),
    ("BV605 / CD86-A", "CD86"),
    ("CD86 BV605-H", "CD86"),
    ("PE-Cy7_PD_1-A", "PD-1"),
    ("BUV395 HLA-DR-A", "HLA-DR"),
    ("AF488_IgD-H", "IgD"),
])
def test_mfi_extracts_marker_despite_channel_naming_variation(channel, marker):
    name = SmartGateNamer().generate_name("Live/Total_B_Cells", f"Median ({channel})")
    assert name.startswith(f"{marker} MFI")


def test_unknown_dye_is_retained_and_not_given_an_invented_marker():
    name = SmartGateNamer().generate_name("Live/Total_B_Cells", "Median (Comp-FITC-A)")
    assert name.startswith("FITC-A MFI")


def test_new_marker_is_named_generically_without_failure():
    name = SmartGateNamer().generate_name("Live/NewMarker_pos", "Frequency of Parent")
    assert name == "NewMarker+ % (of Viable)"


def test_gate_mapping_has_only_user_facing_columns_and_handles_empty_frames():
    empty = generate_gate_mapping(pd.DataFrame(), pd.DataFrame())
    assert list(empty.columns) == OUTPUT_COLUMNS
    assert OUTPUT_COLUMNS == ["gating_name", "metric", "plot_name", "for_graphing"]


def test_case_variants_are_deduplicated_across_days():
    day_0 = pd.DataFrame({"sample_name": ["S1"], "Live/CD86_pos | Frequency of Parent": [0.1]})
    day_7 = pd.DataFrame({"sample_name": ["S2"], "live/cd86_POS | Frequency of Parent": [0.2]})
    mapping = generate_gate_mapping(day_0, day_7)
    assert len(mapping) == 1
    assert mapping.loc[0, "plot_name"] == "CD86+ % (of Viable)"

def test_distinct_gates_with_same_generated_name_remain_unambiguous():
    day_0 = pd.DataFrame({
        "Live/CD86_pos | Frequency of Parent": [0.1],
        "Live/CD86_pos/Memory | Frequency of Parent": [0.2],
    })
    mapping = generate_gate_mapping(day_0, pd.DataFrame())
    assert len(mapping) == 2
    assert mapping["plot_name"].nunique() == 2
    assert any("Memory" in name for name in mapping["plot_name"])
    assert not any(name.endswith(" 2)") for name in mapping["plot_name"])

def test_same_gate_equivalent_metrics_do_not_get_artificial_suffixes():
    day_0 = pd.DataFrame({
        "Live/CD4pos/Total_CD4_T_Cells/Tregs | Frequency of Parent": [0.1],
        "Live/CD4pos/Total_CD4_T_Cells/Tregs | Freq. of Total_CD4_T_Cells": [0.1],
    })
    mapping = generate_gate_mapping(day_0, pd.DataFrame())
    assert mapping["plot_name"].tolist() == ["Tregs % (of Total CD4 T Cells)", "Tregs % (of Total CD4 T Cells)"]


def test_trailing_slashes_and_whitespace_do_not_change_name():
    namer = SmartGateNamer()
    expected = namer.generate_name("Live/CD86_pos", "Freq. of Parent")
    assert namer.generate_name(" /Live/CD86_pos/ ", " Frequency of Parent ") == expected
