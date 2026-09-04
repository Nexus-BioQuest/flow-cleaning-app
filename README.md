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

## Structure

- `app.py` — minimal Streamlit launcher
- `flow_cleaning/` — application source package
- `flow_cleaning/streamlit_app.py` — workflow orchestration
- `flow_cleaning/data_processing.py` — loading, cleaning, and merging
- `flow_cleaning/validation.py` — validation rules and reports
- `flow_cleaning/gate_mapping.py` — mapping workflow and stable schema
- `flow_cleaning/gate_naming_rules.py` — deterministic naming rules
- `flow_cleaning/cell_classification_rules.py` — deterministic classification rules
- `flow_cleaning/precision_counts.py` — precision-count calculations
- `flow_cleaning/master_export.py` — master workbook construction
- `flow_cleaning/ui/` — interface modules
- `tests/` — unit, contract, and golden-file regression tests
