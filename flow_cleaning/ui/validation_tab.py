"""Compact, action-oriented validation interface for wide flow datasets."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from flow_cleaning.validation import DataValidator


def run_checks(day_0, day_7, metadata=None, precision_0=None, precision_7=None) -> dict:
    validator = DataValidator()
    results = {
        "column": validator.validate_column_consistency(day_0, day_7),
        "day_0_samples": validator.validate_sample_names(day_0, metadata),
        "day_7_samples": validator.validate_sample_names(day_7, metadata),
        "day_0_frequency": validator.validate_frequency_ranges(day_0),
        "day_7_frequency": validator.validate_frequency_ranges(day_7),
        "day_0_duplicate_columns": validator.validate_duplicate_columns(day_0, ["sample_name"]),
        "day_7_duplicate_columns": validator.validate_duplicate_columns(day_7, ["sample_name"]),
    }
    if precision_0 is not None:
        results["day_0_precision"] = validator.validate_precision_counts(precision_0)
    if precision_7 is not None:
        results["day_7_precision"] = validator.validate_precision_counts(precision_7)
    return results


def _add(rows, severity, check, dataset, summary, action, affected):
    rows.append({"Priority": severity, "Check": check, "Dataset": dataset,
                 "Finding": summary, "Recommended action": action, "Affected": affected})


def build_findings(results: dict) -> pd.DataFrame:
    """Reduce hundreds of column-level messages to one row per actionable category."""
    rows = []
    columns = results["column"]
    missing_0, missing_7 = columns.get("only_in_day_0", set()), columns.get("only_in_day_7", set())
    if missing_0 or missing_7:
        _add(rows, "Action required", "Column structure", "Day 0 vs Day 7",
             f"{len(missing_0)} columns occur only in Day 0; {len(missing_7)} only in Day 7.",
             "Compare the FlowJo gates and export settings before export.", len(missing_0) + len(missing_7))
    case_count = len(columns.get("case_mismatches", {}))
    if case_count:
        _add(rows, "Automatically resolved", "Column names", "Day 7", f"{case_count} capitalization differences found.",
             "No action needed; names are standardized to Day 0.", case_count)

    for day in ("day_0", "day_7"):
        label = day.replace("_", " ").title()
        sample = results[f"{day}_samples"]
        if sample.get("issues"):
            _add(rows, "Action required", "Sample names", label,
                 f"{len(sample['issues'])} sample-name issue categories found.",
                 "Review duplicates, controls, extensions and metadata matches in Details.", len(sample["issues"]))

        frequency = results[f"{day}_frequency"]
        details = frequency.get("details", {})
        invalid = [name for name, item in details.items()
                   if (item.get("min") is not None and item["min"] < 0) or
                      (item.get("max") is not None and item["max"] > 100)]
        non_numeric = sum(item.get("non_numeric_values", 0) > 0 for item in details.values())
        mixed = [name for name, item in details.items() if {"explicit_percent", "plain_numeric"}.issubset(item.get("input_formats", []))]
        if invalid or non_numeric:
            _add(rows, "Action required", "Frequency values", label,
                 f"{len(invalid)} out-of-range columns; {non_numeric} columns contain non-numeric values.",
                 "Inspect the named columns and correct the source export. Values were not changed.", len(set(invalid)) + non_numeric)
        if mixed:
            _add(rows, "Review", "Frequency scale", label,
                 f"{len(mixed)} columns mix explicit percentages and plain numbers.",
                 "Confirm that each column uses one intended representation. Values were not changed.", len(mixed))
        if frequency.get("all_plain_numeric_between_zero_and_one"):
            _add(rows, "Review", "Frequency scale", label,
                 "Every frequency value in every frequency column is between 0 and 1.",
                 "Confirm whether this export uses proportions or percentages. No scale was inferred.", len(details))

        duplicates = results[f"{day}_duplicate_columns"].get("duplicate_groups", [])
        if duplicates:
            _add(rows, "Review", "Identical columns", label,
                 f"{len(duplicates)} groups have identical values in every sample.",
                 "Confirm that the gates are genuinely distinct and the FlowJo export is correct.", len(duplicates))

        precision = results.get(f"{day}_precision")
        if precision and (precision.get("issues") or precision.get("warnings")):
            severity = "Action required" if precision.get("issues") else "Review"
            _add(rows, severity, "Precision counts", label,
                 f"{len(precision.get('issues', []))} errors and {len(precision.get('warnings', []))} warnings.",
                 "Review missing, non-positive or unusually low/high bead counts.",
                 len(precision.get("issues", [])) + len(precision.get("warnings", [])))

    return pd.DataFrame(rows, columns=["Priority", "Check", "Dataset", "Finding", "Recommended action", "Affected"])


def _frequency_detail(results: dict, day: str) -> pd.DataFrame:
    records = []
    for column, detail in results[f"{day}_frequency"].get("details", {}).items():
        formats = set(detail.get("input_formats", []))
        if ("non_numeric" in formats or
                (detail.get("min") is not None and detail["min"] < 0) or
                (detail.get("max") is not None and detail["max"] > 100)):
            status = "Action required"
        elif {"explicit_percent", "plain_numeric"}.issubset(formats):
            status = "Review"
        else:
            status = "No issue"
        records.append({"Status": status, "Column": column, "Minimum": detail["min"],
                        "Maximum": detail["max"], "Input format": ", ".join(sorted(formats)),
                        "Missing": detail.get("missing_values", 0)})
    return pd.DataFrame(records)


def render_details(results: dict) -> None:
    with st.expander("Detailed results", expanded=False):
        detail_type = st.selectbox("Show", ["Frequency columns", "Column differences", "Sample names", "Identical columns", "Precision counts"])
        if detail_type == "Frequency columns":
            day = st.radio("Dataset", ["Day 0", "Day 7"], horizontal=True, key="frequency_detail_day")
            detail = _frequency_detail(results, day.lower().replace(" ", "_"))
            statuses = st.multiselect("Status", ["Action required", "Review", "No issue"], default=["Action required", "Review"])
            search = st.text_input("Find a column", placeholder="Marker, gate or fluorophore")
            if statuses:
                detail = detail[detail["Status"].isin(statuses)]
            if search:
                detail = detail[detail["Column"].str.contains(search, case=False, regex=False)]
            st.dataframe(detail, use_container_width=True, hide_index=True, height=360)
            st.caption(f"Showing {len(detail):,} columns. Source values are never rescaled by validation.")
        elif detail_type == "Column differences":
            col = results["column"]
            records = ([{"Dataset": "Day 0 only", "Column": x} for x in sorted(col.get("only_in_day_0", []))] +
                       [{"Dataset": "Day 7 only", "Column": x} for x in sorted(col.get("only_in_day_7", []))])
            st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True, height=360)
        elif detail_type == "Sample names":
            for day in ("day_0", "day_7"):
                st.markdown(f"**{day.replace('_', ' ').title()}**")
                for issue in results[f"{day}_samples"].get("issues", []): st.write(issue)
        elif detail_type == "Identical columns":
            for day in ("day_0", "day_7"):
                groups = results[f"{day}_duplicate_columns"].get("duplicate_groups", [])
                st.markdown(f"**{day.replace('_', ' ').title()} — {len(groups)} groups**")
                st.dataframe(pd.DataFrame({"Columns in identical group": [" | ".join(g) for g in groups]}), hide_index=True, use_container_width=True)
        else:
            for day in ("day_0", "day_7"):
                result = results.get(f"{day}_precision")
                if result:
                    st.markdown(f"**{day.replace('_', ' ').title()}**")
                    for message in result.get("issues", []) + result.get("warnings", []): st.write(message)


def render(results: dict) -> None:
    findings = build_findings(results)
    required = int((findings["Priority"] == "Action required").sum()) if not findings.empty else 0
    review = int((findings["Priority"] == "Review").sum()) if not findings.empty else 0
    resolved = int((findings["Priority"] == "Automatically resolved").sum()) if not findings.empty else 0
    a, b, c = st.columns(3)
    a.metric("Action required", required)
    b.metric("Review", review)
    c.metric("Automatically resolved", resolved)
    if required:
        st.error("Resolve the items marked Action required before relying on the export.")
    elif review:
        st.warning("No blocking errors were found. Review the flagged patterns in their scientific context.")
    else:
        st.success("No validation issues were found.")
    if not findings.empty:
        priority = st.multiselect("Filter findings", ["Action required", "Review", "Automatically resolved"],
                                  default=["Action required", "Review"])
        visible = findings[findings["Priority"].isin(priority)] if priority else findings.iloc[0:0]
        st.dataframe(visible, use_container_width=True, hide_index=True,
                     column_config={"Affected": st.column_config.NumberColumn(format="%d")})
    render_details(results)
