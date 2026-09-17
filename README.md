# Flow Cytometry Data Preparation

A standalone Streamlit application for cleaning and validating FlowJo exports,
generating precision-count tables and gate mappings, and exporting an
analysis-ready master workbook.

## Install

```bash
cd ~/Documents/flow-cleaning-app
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

## Test

```bash
python -m pip install -r requirements-test.txt
python -m pytest
```

The application never rescales frequency values automatically. FlowJo values
are preserved as supplied and frequency columns are profiled for explicit
percentages, plain numbers, mixed representations, invalid values, and
ambiguous all-below-1 inputs.

The interface follows the operating-system light or dark appearance setting.
Its custom styling uses paired theme tokens rather than fixed foreground and
background colours.

## Precision counts and the absolute-count formula

Bead concentration is entered once in beads per mL. The sidebar displays beads
per µL as a live derived value (`per mL ÷ 1,000`), and the same derived value is
used in precision-count exports.

The `day_0_precision_count` / `day_7_precision_count` sheets carry the inputs the
QC step needs to convert Day 7 gated event counts to absolute cells per well:

```
absolute count [cells/well] = (N_events × V_bead) / (N_beads × V_sample) × C_beads × V_well
```

| Symbol | Meaning | Column | Units |
|---|---|---|---|
| N_events | raw gated event count | `<gate> \| Count` (flow-data sheet) | events |
| V_bead | bead suspension volume added | `bead_volume_ul` | µL |
| N_beads | precision-count beads recorded | `recorded_bead_count` | events |
| V_sample | sample volume acquired | `sample_volume_ul` | µL |
| C_beads | precision-count bead concentration | `bead_concentration_per_ul` | beads/µL |
| V_well | total well volume (200 for standard plates) | QC sidebar constant | µL |

`expected_bead_count` (= `bead_concentration_per_ul` × `bead_volume_ul`) and
`bead_concentration_per_ml` are written for audit only; nothing computes with
them. Older workbooks using the previous column names
(`beads_per_microlitre`, `bead_vol_microlitre`, `cell_vol_microlitre`,
`precision_count_beads`, `bead_count`, `bead_conc_per_ml`) are still accepted by
the QC step.

## Structure

- `app.py` - minimal Streamlit launcher
- `flow_cleaning/` - application source package
- `flow_cleaning/streamlit_app.py` - workflow orchestration
- `flow_cleaning/data_processing.py` - loading, cleaning, and merging
- `flow_cleaning/validation.py` - validation rules and reports
- `flow_cleaning/gate_mapping.py` - mapping workflow and stable schema
- `flow_cleaning/gate_naming_rules.py` - deterministic naming rules
- `flow_cleaning/cell_classification_rules.py` - deterministic classification rules
- `flow_cleaning/precision_counts.py` - precision-count calculations
- `flow_cleaning/master_export.py` - master workbook construction
- `flow_cleaning/ui/` - interface modules
- `tests/` - unit, contract, and golden-file regression tests
