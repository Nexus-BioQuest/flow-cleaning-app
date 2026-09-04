#!/usr/bin/env python3
"""
Merge two exported flow cytometry master Excel files.

This script is intended for the workflow where you have:
1. one master workbook that has your edited Day 0 / Day 7 data and naming/QC changes
2. another master workbook that contains additional columns/rows you want to bring over

It will:
- merge the Day 0 / Day 7 flow sheets by adding extra columns from the second workbook
- merge the name mapping sheet by stacking extra rows from the second workbook
- preserve all other sheets, carrying them over from the base workbook or adding them from the second workbook

Example:
    python merge_master_exports.py \
        --base "edited_master.xlsx" \
        --other "source_master.xlsx" \
        --output "merged_master.xlsx"
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


def _print_dataframe_summary(label: str, df: pd.DataFrame) -> None:
    """Print a compact summary of the dataframe for the user."""
    print(f"[{label}] rows={len(df)} columns={len(df.columns)}")
    if not df.empty:
        sample_cols = [col for col in df.columns if "sample" in col.lower() or "name" in col.lower()]
        print(f"[{label}] sample/name columns detected={len(sample_cols)}")


def _print_overlap_report(label: str, left: pd.DataFrame, right: pd.DataFrame, join_key: str) -> None:
    """Print a simple overlap summary for a merge key."""
    if join_key not in left.columns or join_key not in right.columns:
        print(f"[{label}] join key '{join_key}' missing from one or both dataframes")
        return

    left_values = set(left[join_key].dropna().astype(str))
    right_values = set(right[join_key].dropna().astype(str))
    overlap = sorted(left_values & right_values)
    print(f"[{label}] join key '{join_key}' overlap count={len(overlap)}")


def _find_join_key(df: pd.DataFrame) -> str | None:
    """Find the most likely sample/name column to use as a merge key."""
    candidates = [
        "sample_id",
        "sample",
        "sample_name",
        "sample_name_id",
        "name",
        "subject_id",
        "subject",
        "id",
        "well",
    ]
    normalized = {col.lower(): col for col in df.columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    for col in df.columns:
        if "sample" in col.lower() or "name" in col.lower():
            return col
    return None


def _print_duplicate_summary(label: str, df: pd.DataFrame, join_key: str) -> None:
    """Report duplicate join-key values before merging."""
    if join_key not in df.columns:
        return
    duplicates = df[join_key].dropna().astype(str)
    dup_values = sorted({value for value in duplicates if list(duplicates).count(value) > 1})
    if dup_values:
        print(f"[{label}] duplicate join-key values detected for '{join_key}' count={len(dup_values)}")
    else:
        print(f"[{label}] duplicate join-key values detected for '{join_key}' count=0")


def _deduplicate_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Drop duplicate rows while preserving the last occurrence."""
    if df.empty:
        return df
    return df.drop_duplicates(keep="last").reset_index(drop=True)


FLOW_SHEET_HINTS = ("flow_data", "precision_count")
NAME_MAPPING_SHEET_HINTS = ("name_mapping", "gate_name", "gate_names")


def merge_columns(left: pd.DataFrame, right: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    """Merge two dataframes by aligning on sample identifiers when possible."""
    left_df = left.reset_index(drop=True)
    right_df = right.reset_index(drop=True)

    _print_dataframe_summary(f"{sheet_name} (base)", left_df)
    _print_dataframe_summary(f"{sheet_name} (other)", right_df)

    join_key = _find_join_key(left_df)
    if join_key is None:
        join_key = _find_join_key(right_df)

    if join_key and join_key in right_df.columns:
        _print_duplicate_summary(sheet_name, left_df, join_key)
        _print_duplicate_summary(sheet_name, right_df, join_key)
        _print_overlap_report(sheet_name, left_df, right_df, join_key)
        merged = left_df.merge(right_df, on=join_key, how="outer", suffixes=("", "_other"))
        print(f"[{sheet_name}] merged rows after sample-name join = {len(merged)}")
        print(f"[{sheet_name}] merged columns before dedupe = {len(merged.columns)}")
        return _deduplicate_rows(merged)

    overlap = [col for col in left_df.columns if col in right_df.columns]
    if overlap:
        right_df = right_df.rename(columns={col: f"{col}_other" for col in overlap})

    merged = pd.concat([left_df, right_df], axis=1, ignore_index=False)
    print(f"[{sheet_name}] merged rows after column-wise concat = {len(merged)}")
    print(f"[{sheet_name}] merged columns before dedupe = {len(merged.columns)}")
    return _deduplicate_rows(merged)


def merge_rows(left: pd.DataFrame, right: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    """Stack rows from the second workbook underneath the first."""
    left_df = left.reset_index(drop=True)
    right_df = right.reset_index(drop=True)

    _print_dataframe_summary(f"{sheet_name} (base)", left_df)
    _print_dataframe_summary(f"{sheet_name} (other)", right_df)

    merged = pd.concat([left_df, right_df], axis=0, ignore_index=True)
    print(f"[{sheet_name}] stacked rows before dedupe = {len(merged)}")
    deduped = _deduplicate_rows(merged)
    print(f"[{sheet_name}] stacked rows after dedupe = {len(deduped)}")
    return deduped


def merge_sheet(sheet_name: str, left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    """Merge two sheets using the sheet name to choose a strategy."""
    normalized_name = sheet_name.lower()
    if any(hint in normalized_name for hint in NAME_MAPPING_SHEET_HINTS):
        return merge_rows(left, right, sheet_name)
    if any(hint in normalized_name for hint in FLOW_SHEET_HINTS):
        return merge_columns(left, right, sheet_name)
    return merge_rows(left, right, sheet_name)


def merge_master_files(base_path: str | Path, other_path: str | Path, output_path: str | Path) -> Path:
    """Merge two master Excel files into a new workbook."""
    base_path = Path(base_path)
    other_path = Path(other_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Merging base workbook: {base_path}")
    print(f"Merging other workbook: {other_path}")

    with pd.ExcelFile(base_path) as base_excel, pd.ExcelFile(other_path) as other_excel:
        sheets = sorted(set(base_excel.sheet_names) | set(other_excel.sheet_names))
        merged_sheets: Dict[str, pd.DataFrame] = {}

        for sheet_name in sheets:
            print(f"\nProcessing sheet: {sheet_name}")
            in_base = sheet_name in base_excel.sheet_names
            in_other = sheet_name in other_excel.sheet_names

            if in_base and in_other:
                left_df = pd.read_excel(base_path, sheet_name=sheet_name)
                right_df = pd.read_excel(other_path, sheet_name=sheet_name)
                merged_sheets[sheet_name] = merge_sheet(sheet_name, left_df, right_df)
            elif in_base:
                merged_sheets[sheet_name] = pd.read_excel(base_path, sheet_name=sheet_name)
            else:
                merged_sheets[sheet_name] = pd.read_excel(other_path, sheet_name=sheet_name)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, df in merged_sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    return output_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge two exported flow cytometry master Excel files")
    parser.add_argument("--base", required=True, help="Path to the master file you want to keep as the base")
    parser.add_argument("--other", required=True, help="Path to the second master file to pull in extra columns/rows")
    parser.add_argument("--output", required=True, help="Where to save the merged workbook")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    output_path = merge_master_files(args.base, args.other, args.output)
    print(f"Merged workbook written to: {output_path}")


if __name__ == "__main__":
    main()
