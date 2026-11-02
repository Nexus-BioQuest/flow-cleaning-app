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

Bead concentration, bead volume and sample volume are set in each day's own tab,
so they can differ between days. Bead concentration is entered in beads per mL;
the tab displays beads per µL as a live derived value (`per mL ÷ 1,000`), which is
used in precision-count exports.

The `day_0_precision_count` / `day_7_precision_count` sheets carry the inputs the
QC step needs to convert gated event counts to absolute cells per well:

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
| V_well | total well volume (200 for standard plates) | fixed QC constant | µL |

Days listed in the metadata `day` column (other than 0 and 7) get their tabs
automatically on upload. Use the **Additional days** tab to add any others beyond Day 0 and Day 7.
Each added day gets its own tab for uploading and processing files and
generating optional precision counts. The workbook includes that day's
flow-data sheet and, when generated, its precision-count sheet (for example,
`day_14_flow_data` and `day_14_precision_count`).
Validation checks each processed day for sample-name, frequency, duplicate
column, and precision-count issues, and compares each day's columns with Day 0.

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
