# Flow Cytometry Data Preparation

A standalone Streamlit application for cleaning and validating FlowJo exports,
generating precision-count tables and gate mappings, and exporting an
analysis-ready master workbook.

## Windows PowerShell setup

Install Python 3.10 or newer, then run these commands from the project folder:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-test.txt
```

## Run

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest
```

These commands use the project-local environment; activation and
PowerShell execution-policy changes are not required.

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
