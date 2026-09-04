# FlowJo golden fixtures

These files are deliberately small and anonymised. They represent export shapes
that have caused production problems and are treated as immutable inputs.

- `mixed_frequency_formats.csv` combines explicit percentages and plain numbers.
- `rare_numeric_frequencies.csv` contains only values below 1; their unit is
  intentionally unknown and must never be inferred from magnitude.
- `cleaning_edge_cases.csv` contains `.fcs`, FMO, Mean/SD rows, and a duplicated
  export column.
- `invalid_frequency_values.csv` contains out-of-range and non-numeric values.

Add anonymised real exports alongside these files and register their expected
properties in `manifest.json`. Never replace a source value with a corrected
value inside a golden input; the purpose is to preserve the original failure.
