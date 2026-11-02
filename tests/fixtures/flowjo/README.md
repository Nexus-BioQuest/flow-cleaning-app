# FlowJo golden fixtures

These anonymized fixtures represent FlowJo export structures associated with
production issues. They are minimal, immutable regression inputs.

- `mixed_frequency_formats.csv` combines explicit percentages and plain numbers.
- `rare_numeric_frequencies.csv` contains only values below 1; their unit is
  intentionally unknown and must never be inferred from magnitude.
- `cleaning_edge_cases.csv` contains `.fcs`, FMO, Mean/SD rows, and a duplicated
  export column.
- `invalid_frequency_values.csv` contains out-of-range and non-numeric values.

Add anonymized exports to this directory and record their expected properties
in `manifest.json`. Preserve source values in golden inputs; do not replace
incorrect values with corrected values.
