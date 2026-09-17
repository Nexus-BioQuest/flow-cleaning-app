"""
Data Validation Module - FIXED VERSION

CRITICAL FIXES:
1. All column comparisons are case-insensitive
2. Day 0 columns are the canonical reference
3. Recommendations guide users to standardize to Day 0 casing
"""

import numpy as np
import pandas as pd
import streamlit as st
from typing import Dict, List, Optional, Tuple


class DataValidator:
    """Handles validation of flow cytometry data with case-insensitive operations."""
    
    @staticmethod
    def validate_individual_files(file_dfs: List[Tuple[str, pd.DataFrame, pd.DataFrame]], 
                                  day_label: str = "Day") -> Dict:
        """
        Validate individual files within a day before merging.
        Checks for:
        1. Column consistency across files
        2. Sample name consistency  
        3. Sample names lost during cleaning
        
        Args:
            file_dfs: List of tuples (filename, raw_df, cleaned_df)
            day_label: Label for the day (e.g., "Day 0", "Day 7")
            
        Returns:
            Dict with validation results
        """
        validation = {
            "valid": True,
            "day": day_label,
            "file_count": len(file_dfs),
            "column_consistency": {},
            "sample_name_consistency": {},
            "cleaning_effects": {},
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        if not file_dfs:
            validation["valid"] = False
            validation["issues"].append(f"No files provided for {day_label}")
            return validation
        
        # === 1. CHECK COLUMN CONSISTENCY ACROSS FILES ===
        col_validation = DataValidator._validate_columns_across_files(file_dfs, day_label)
        validation["column_consistency"] = col_validation
        
        if not col_validation["consistent"]:
            validation["valid"] = False
            validation["issues"].extend(col_validation["issues"])
        
        validation["warnings"].extend(col_validation["warnings"])
        validation["recommendations"].extend(col_validation["recommendations"])
        
        # === 2. CHECK SAMPLE NAME CONSISTENCY ===
        sample_validation = DataValidator._validate_sample_names_across_files(file_dfs, day_label)
        validation["sample_name_consistency"] = sample_validation
        
        if not sample_validation["consistent"]:
            validation["warnings"].extend(sample_validation["warnings"])
        
        validation["recommendations"].extend(sample_validation["recommendations"])
        
        # === 3. CHECK CLEANING EFFECTS ===
        cleaning_validation = DataValidator._validate_cleaning_effects(file_dfs, day_label)
        validation["cleaning_effects"] = cleaning_validation
        
        if cleaning_validation["samples_lost"] > 0:
            validation["warnings"].append(
                f"{cleaning_validation['samples_lost']} total samples removed during cleaning in {day_label}"
            )
        
        validation["recommendations"].extend(cleaning_validation["recommendations"])
        
        return validation
    
    @staticmethod
    def _validate_columns_across_files(file_dfs: List[Tuple[str, pd.DataFrame, pd.DataFrame]], 
                                      day_label: str) -> Dict:
        """Check if all files have the same column structure (case-insensitive)."""
        result = {
            "consistent": True,
            "reference_file": None,
            "reference_columns": set(),
            "file_columns": {},
            "common_columns": set(),
            "column_differences": {},
            "case_differences": {},
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        if not file_dfs:
            return result
        
        # Use first file as reference
        ref_filename, _, ref_cleaned_df = file_dfs[0]
        result["reference_file"] = ref_filename
        result["reference_columns"] = set(ref_cleaned_df.columns)
        
        # Create case-insensitive mapping for reference
        ref_lower_map = {col.lower(): col for col in ref_cleaned_df.columns}
        ref_lower_set = set(ref_lower_map.keys())
        
        # Check each file against reference
        all_consistent = True
        common_lower = ref_lower_set.copy()
        
        for filename, _, cleaned_df in file_dfs:
            file_cols = set(cleaned_df.columns)
            result["file_columns"][filename] = file_cols
            
            # Case-insensitive comparison
            file_lower_map = {col.lower(): col for col in cleaned_df.columns}
            file_lower_set = set(file_lower_map.keys())
            
            # Find common columns (case-insensitive)
            common_lower &= file_lower_set
            
            # Find differences
            only_in_ref = ref_lower_set - file_lower_set
            only_in_file = file_lower_set - ref_lower_set
            
            if only_in_ref or only_in_file:
                all_consistent = False
                result["consistent"] = False
                
                result["column_differences"][filename] = {
                    "only_in_reference": {ref_lower_map[col] for col in only_in_ref},
                    "only_in_this_file": {file_lower_map[col] for col in only_in_file}
                }
                
                result["issues"].append(
                    f"Column mismatch in '{filename}': "
                    f"{len(only_in_ref)} missing, {len(only_in_file)} extra"
                )
            
            # Check for case differences in common columns
            for col_lower in file_lower_set & ref_lower_set:
                ref_col = ref_lower_map[col_lower]
                file_col = file_lower_map[col_lower]
                
                if ref_col != file_col:
                    if filename not in result["case_differences"]:
                        result["case_differences"][filename] = []
                    
                    result["case_differences"][filename].append({
                        "reference": ref_col,
                        "this_file": file_col
                    })
        
        result["common_columns"] = common_lower
        
        # Generate recommendations
        if result["consistent"] and not result["case_differences"]:
            result["recommendations"].append(
                f"All {len(file_dfs)} files in {day_label} have identical columns"
            )
        elif result["consistent"] and result["case_differences"]:
            result["recommendations"].append(
                f"All {len(file_dfs)} files in {day_label} have matching columns (case-insensitive)"
            )
            result["warnings"].append(
                f"{len(result['case_differences'])} files have case differences that will be standardized"
            )
        else:
            result["recommendations"].append(
                f"Files in {day_label} have different column structures. "
                f"Check your FlowJo gating and export settings."
            )
        
        return result
    
    @staticmethod
    def _is_frequency_column(column_name: str) -> bool:
        """Return True for frequency-like column names."""
        column_name = str(column_name).lower()
        return 'freq' in column_name or 'frequency' in column_name

    @staticmethod
    def find_duplicate_value_columns(df: pd.DataFrame,
                                     ignore_columns: Optional[List[str]] = None) -> List[List[str]]:
        """Find groups of columns whose full row-by-row value signature is identical."""
        if ignore_columns is None:
            ignore_columns = []

        columns = [col for col in df.columns if col not in ignore_columns]
        if len(columns) <= 1:
            return []

        def normalize_col_values(series: pd.Series):
            populated = series.notna()
            if populated.sum() < 2 or not populated.all():
                return None
            normalized_values = []
            for value in series.tolist():
                normalized_values.append((type(value).__name__, value))
            return tuple(normalized_values)

        signature_map = {}
        for col in columns:
            signature = normalize_col_values(df[col])
            if signature is not None:
                signature_map.setdefault(signature, []).append(col)

        duplicate_groups = [sorted(cols) for cols in signature_map.values() if len(cols) > 1]
        return sorted(duplicate_groups, key=lambda group: (len(group), group))

    @staticmethod
    def validate_frequency_ranges(df: pd.DataFrame,
                                  frequency_columns: Optional[List[str]] = None) -> Dict:
        """Profile frequency representations without converting the source data."""
        if frequency_columns is None:
            frequency_columns = [col for col in df.columns if DataValidator._is_frequency_column(col)]

        result = {
            "valid": True,
            "frequency_columns": frequency_columns,
            "all_plain_numeric_between_zero_and_one": False,
            "issues": [],
            "warnings": [],
            "recommendations": [],
            "details": {}
        }

        if not frequency_columns:
            result["recommendations"].append("No frequency-like columns were detected.")
            return result

        for col in frequency_columns:
            series = df[col]
            text = series.astype('string').str.strip()
            explicit_percent = text.str.endswith('%', na=False)
            numeric_text = text.str.replace(',', '', regex=False).str.rstrip('%').str.strip()
            numeric = pd.to_numeric(numeric_text, errors='coerce')
            non_numeric = series.notna() & numeric.isna()
            plain_numeric = series.notna() & ~explicit_percent & numeric.notna()

            formats = []
            if explicit_percent.any():
                formats.append('explicit_percent')
            if plain_numeric.any():
                formats.append('plain_numeric')
            if non_numeric.any():
                formats.append('non_numeric')
            if non_numeric.any():
                result["valid"] = False
                result["issues"].append(
                    f"Column '{col}' contains {int(non_numeric.sum())} non-numeric frequency values."
                )

            col_min = numeric.min(skipna=True)
            col_max = numeric.max(skipna=True)
            result["details"][col] = {
                "min": float(col_min) if pd.notna(col_min) else None,
                "max": float(col_max) if pd.notna(col_max) else None,
                "input_formats": formats,
                "explicit_percent_values": int(explicit_percent.sum()),
                "plain_numeric_values": int(plain_numeric.sum()),
                "non_numeric_values": int(non_numeric.sum()),
                "missing_values": int(series.isna().sum()),
            }

            if numeric.dropna().empty:
                continue

            if explicit_percent.any() and plain_numeric.any():
                result["warnings"].append(
                    f"Column '{col}' mixes explicit % strings and plain numbers. Values were preserved unchanged; confirm the intended scale."
                )
            elif explicit_percent.any():
                result["warnings"].append(
                    f"Column '{col}' uses explicit % strings. Values were preserved unchanged."
                )
            elif col_max > 1:
                result["warnings"].append(
                    f"Column '{col}' uses plain numeric values spanning up to {col_max:g}. Values were preserved unchanged."
                )

            if col_min < 0 or col_max > 100:
                result["valid"] = False
                result["issues"].append(
                    f"Column '{col}' has values outside the allowed frequency range 0-100: {col_min}..{col_max}."
                )
                continue

        populated_details = [item for item in result["details"].values()
                             if item.get("min") is not None and item.get("max") is not None]
        all_frequency_values_are_small_plain_numbers = bool(populated_details) and all(
            item.get("input_formats") == ["plain_numeric"]
            and item["min"] >= 0
            and item["max"] <= 1
            for item in populated_details
        ) and len(populated_details) == len(frequency_columns)
        result["all_plain_numeric_between_zero_and_one"] = all_frequency_values_are_small_plain_numbers
        if all_frequency_values_are_small_plain_numbers:
            result["warnings"].append(
                "Every non-missing frequency value across the dataset is a plain number between 0 and 1. "
                "Confirm whether the export uses proportions or percentages; no values were changed."
            )

        if result["issues"]:
            result["valid"] = False
        return result

    @staticmethod
    def validate_duplicate_columns(df: pd.DataFrame,
                                   ignore_columns: Optional[List[str]] = None) -> Dict:
        """Validate that no columns contain identical full-column value signatures row-by-row."""
        duplicate_groups = DataValidator.find_duplicate_value_columns(df, ignore_columns)
        duplicate_details = []
        for group in duplicate_groups:
            sample_values = []
            for row_index in df.index[:2]:
                row_values = {str(column): df.at[row_index, column] for column in group}
                sample_values.append({
                    "row": int(row_index) if isinstance(row_index, (int, np.integer)) else str(row_index),
                    "values": row_values,
                })
            duplicate_details.append({"columns": group, "rows": sample_values})
        validation = {
            "valid": True,
            "issues": [],
            "warnings": [],
            "duplicate_groups": duplicate_groups,
            "duplicate_details": duplicate_details,
            "rows_checked": len(df),
            "columns_checked": len(df.columns) - len(ignore_columns or []),
        }

        if duplicate_groups:
            validation["valid"] = False
            validation["issues"].append(
                f"{len(duplicate_groups)} identical full-column value group(s) detected: "
                + "; ".join([", ".join(group) for group in duplicate_groups[:5]])
            )
            if len(duplicate_groups) > 5:
                validation["warnings"].append(
                    f"...and {len(duplicate_groups) - 5} more duplicate column groups"
                )
        else:
            validation["warnings"].append("No duplicate-value columns were detected.")

        return validation

    @staticmethod
    def _validate_sample_names_across_files(file_dfs: List[Tuple[str, pd.DataFrame, pd.DataFrame]], 
                                           day_label: str) -> Dict:
        """Check for duplicate or overlapping sample names across files."""
        result = {
            "consistent": True,
            "file_samples": {},
            "duplicate_samples": {},
            "unique_samples_per_file": {},
            "total_unique_samples": 0,
            "warnings": [],
            "recommendations": []
        }
        
        all_samples = []
        
        for filename, _, cleaned_df in file_dfs:
            if 'sample_name' not in cleaned_df.columns:
                result["warnings"].append(f"No 'sample_name' column in '{filename}'")
                continue
            
            samples = cleaned_df['sample_name'].dropna().astype(str).tolist()
            result["file_samples"][filename] = set(samples)
            all_samples.extend(samples)
        
        # Check for duplicates across files
        from collections import Counter
        sample_counts = Counter(all_samples)
        duplicates = {sample: count for sample, count in sample_counts.items() if count > 1}
        
        if duplicates:
            result["consistent"] = False
            result["duplicate_samples"] = duplicates
            
            # Find which files have the duplicates
            for sample, count in list(duplicates.items())[:5]:  # Show first 5
                files_with_sample = [
                    filename for filename, samples in result["file_samples"].items() 
                    if sample in samples
                ]
                result["warnings"].append(
                    f"Sample '{sample}' appears in {count} files: {', '.join(files_with_sample)}"
                )
            
            if len(duplicates) > 5:
                result["warnings"].append(f"...and {len(duplicates) - 5} more duplicates")
            
            result["recommendations"].append(
                f"{len(duplicates)} samples appear in multiple files in {day_label}. "
                "This may cause issues during merging. Ensure each sample is only in one file."
            )
        
        # Calculate unique samples per file
        for filename, samples in result["file_samples"].items():
            result["unique_samples_per_file"][filename] = len(samples)
        
        result["total_unique_samples"] = len(set(all_samples))
        
        if result["consistent"]:
            result["recommendations"].append(
                f"No duplicate samples across {len(file_dfs)} files in {day_label} "
                f"({result['total_unique_samples']} unique samples)"
            )
        
        return result
    
    @staticmethod
    def _validate_cleaning_effects(file_dfs: List[Tuple[str, pd.DataFrame, pd.DataFrame]], 
                                  day_label: str) -> Dict:
        """Check what samples/rows were lost during cleaning."""
        result = {
            "file_effects": {},
            "samples_lost": 0,
            "rows_lost": 0,
            "lost_samples_list": [],
            "recommendations": []
        }
        
        for filename, raw_df, cleaned_df in file_dfs:
            effect = {
                "raw_rows": len(raw_df),
                "cleaned_rows": len(cleaned_df),
                "rows_lost": len(raw_df) - len(cleaned_df)
            }
            
            # Check sample names if column exists
            if 'sample_name' in raw_df.columns and 'sample_name' in cleaned_df.columns:
                raw_samples = set(raw_df['sample_name'].dropna().astype(str))
                cleaned_samples = set(cleaned_df['sample_name'].dropna().astype(str))
                
                lost_samples = raw_samples - cleaned_samples
                
                effect["raw_samples"] = len(raw_samples)
                effect["cleaned_samples"] = len(cleaned_samples)
                effect["samples_lost"] = len(lost_samples)
                effect["lost_sample_names"] = list(lost_samples)
                
                result["samples_lost"] += len(lost_samples)
                result["lost_samples_list"].extend(lost_samples)
                
                if lost_samples:
                    result["recommendations"].append(
                        f"'{filename}': {len(lost_samples)} samples removed during cleaning: "
                        f"{', '.join(list(lost_samples)[:3])}" + 
                        (f"... and {len(lost_samples)-3} more" if len(lost_samples) > 3 else "")
                    )
            
            result["rows_lost"] += effect["rows_lost"]
            result["file_effects"][filename] = effect
        
        # Summary recommendation
        if result["samples_lost"] == 0:
            result["recommendations"].append(
                f"No samples lost during cleaning in {day_label}"
            )
        else:
            result["recommendations"].append(
                f"Total samples removed in {day_label}: {result['samples_lost']} "
                f"(check if these are expected FMO/control samples)"
            )
        
        return result
    
    @staticmethod
    def display_pre_merge_validation(validation: Dict):
        """Display pre-merge validation results in Streamlit."""
        day = validation.get("day", "Unknown")
        
        st.subheader(f"Pre-Merge Validation: {day}")
        st.caption(f"Checking {validation.get('file_count', 0)} individual files before merging")
        
        # Overall status
        if validation.get("valid", False):
            st.success(f"All files in {day} are ready to merge")
        else:
            st.error(f"Issues detected in {day} files")
        
        # Create tabs for different checks
        tab1, tab2, tab3 = st.tabs(["Column Structure", "Sample Names", "Cleaning Effects"])
        
        with tab1:
            col_val = validation.get("column_consistency", {})
            
            if col_val.get("consistent", True):
                st.success(f"All columns match across files")
            else:
                st.error(f"Column structure varies between files")
            
            st.metric("Common Columns", len(col_val.get("common_columns", [])))
            
            # Show column differences
            if col_val.get("column_differences"):
                st.warning("**Column Differences Detected:**")
                for filename, diffs in col_val["column_differences"].items():
                    with st.expander(f"{filename}"):
                        if diffs["only_in_reference"]:
                            st.write("**Missing columns:**", ", ".join(sorted(diffs["only_in_reference"])))
                        if diffs["only_in_this_file"]:
                            st.write("**Extra columns:**", ", ".join(sorted(diffs["only_in_this_file"])))
            
            # Show case differences
            if col_val.get("case_differences"):
                with st.expander(f"Case Differences ({len(col_val['case_differences'])} files)"):
                    for filename, cases in col_val["case_differences"].items():
                        st.write(f"**{filename}:**")
                        for case in cases[:5]:  # Show first 5
                            st.text(f"  Reference: {case['reference']} | This file: {case['this_file']}")
        
        with tab2:
            sample_val = validation.get("sample_name_consistency", {})
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Unique Samples", sample_val.get("total_unique_samples", 0))
            with col2:
                st.metric("Duplicate Samples", len(sample_val.get("duplicate_samples", {})))
            
            # Show samples per file
            if sample_val.get("unique_samples_per_file"):
                st.write("**Samples per file:**")
                for filename, count in sample_val["unique_samples_per_file"].items():
                    st.text(f"  {filename}: {count} samples")
            
            # Show duplicates
            if sample_val.get("duplicate_samples"):
                st.error("**Duplicate Samples Found:**")
                for sample, count in list(sample_val["duplicate_samples"].items())[:10]:
                    st.text(f"  '{sample}' appears {count} times")
        
        with tab3:
            clean_val = validation.get("cleaning_effects", {})
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Samples Lost", clean_val.get("samples_lost", 0))
            with col2:
                st.metric("Rows Lost", clean_val.get("rows_lost", 0))
            
            # Show per-file effects
            if clean_val.get("file_effects"):
                st.write("**Cleaning effects per file:**")
                for filename, effect in clean_val["file_effects"].items():
                    with st.expander(f"{filename}"):
                        st.write(f"Raw rows: {effect['raw_rows']} → Cleaned rows: {effect['cleaned_rows']}")
                        if 'samples_lost' in effect and effect['samples_lost'] > 0:
                            st.warning(f"**{effect['samples_lost']} samples removed:**")
                            st.write(", ".join(effect['lost_sample_names'][:10]))
                            if len(effect['lost_sample_names']) > 10:
                                st.write(f"...and {len(effect['lost_sample_names'])-10} more")
        
        # Show all recommendations
        if validation.get("recommendations"):
            st.info("**📌 Recommendations:**")
            for rec in validation["recommendations"]:
                st.markdown(f"- {rec}")
    
    @staticmethod
    def validate_column_consistency(day_0_df: pd.DataFrame, 
                                    day_7_df: pd.DataFrame) -> Dict:
        """
        Validate column consistency between Day 0 and Day 7 data with CASE-INSENSITIVE comparison.
        Day 0 column names are the canonical reference.
        
        Returns detailed comparison including case mismatches.
        """
        validation = {
            "valid": True,
            "day_0_columns": set(day_0_df.columns),
            "day_7_columns": set(day_7_df.columns),
            "common_columns_ci": set(),  # Case-insensitive common columns
            "only_in_day_0": set(),
            "only_in_day_7": set(),
            "case_mismatches": {},
            "canonical_map": {},  # Maps lowercase -> Day 0 canonical case
            "recommendations": []
        }
        
        # Create case-insensitive mappings
        day_0_lower = {col.lower(): col for col in day_0_df.columns}
        day_7_lower = {col.lower(): col for col in day_7_df.columns}
        
        day_0_keys = set(day_0_lower.keys())
        day_7_keys = set(day_7_lower.keys())
        
        # Find common and unique columns (case-insensitive)
        common_lower = day_0_keys & day_7_keys
        validation["common_columns_ci"] = common_lower
        
        # Columns only in one dataset (case-insensitive)
        only_in_day_0_lower = day_0_keys - day_7_keys
        only_in_day_7_lower = day_7_keys - day_0_keys
        
        validation["only_in_day_0"] = {day_0_lower[k] for k in only_in_day_0_lower}
        validation["only_in_day_7"] = {day_7_lower[k] for k in only_in_day_7_lower}
        
        # Build canonical mapping (lowercase -> Day 0 case)
        for col_lower in common_lower:
            validation["canonical_map"][col_lower] = day_0_lower[col_lower]
        
        # Find case mismatches in common columns
        for col_lower in common_lower:
            day_0_col = day_0_lower[col_lower]
            day_7_col = day_7_lower[col_lower]
            if day_0_col != day_7_col:
                validation["case_mismatches"][col_lower] = {
                    "day_0": day_0_col,
                    "day_7": day_7_col,
                    "canonical": day_0_col  # Day 0 is canonical
                }
        
        # Determine if valid
        if validation["only_in_day_0"] or validation["only_in_day_7"]:
            validation["valid"] = False
            validation["recommendations"].append(
                "Column names don't match between Day 0 and Day 7 (case-insensitive). "
                "Check your FlowJo exports for consistent gating."
            )
            
            if validation["only_in_day_0"]:
                validation["recommendations"].append(
                    f"{len(validation['only_in_day_0'])} columns only in Day 0: "
                    f"{', '.join(sorted(list(validation['only_in_day_0'])[:3]))}..."
                )
            
            if validation["only_in_day_7"]:
                validation["recommendations"].append(
                    f"{len(validation['only_in_day_7'])} columns only in Day 7: "
                    f"{', '.join(sorted(list(validation['only_in_day_7'])[:3]))}..."
                )
        
        if validation["case_mismatches"]:
            validation["recommendations"].append(
                f"{len(validation['case_mismatches'])} columns have different capitalization. "
                "These will be standardized to Day 0 casing in the merged export."
            )
        
        # Success message
        if validation["valid"] and not validation["case_mismatches"]:
            validation["recommendations"].append(
                "All columns are identical, including letter case."
            )
        elif validation["valid"] and validation["case_mismatches"]:
            validation["recommendations"].append(
                "All columns match (case-insensitive). Minor case differences will be auto-corrected."
            )
        
        return validation
    
    @staticmethod
    def standardize_day_7_to_day_0(day_7_df: pd.DataFrame, 
                                   canonical_map: Dict[str, str]) -> pd.DataFrame:
        """
        Standardize Day 7 column names to match Day 0 (canonical) casing.
        
        Args:
            day_7_df: Day 7 DataFrame
            canonical_map: Dict mapping lowercase -> Day 0 canonical case
            
        Returns:
            Day 7 DataFrame with standardized column names
        """
        day_7_standardized = day_7_df.copy()
        
        # Build rename mapping
        rename_map = {}
        for col in day_7_standardized.columns:
            col_lower = col.lower()
            if col_lower in canonical_map:
                canonical_col = canonical_map[col_lower]
                if col != canonical_col:
                    rename_map[col] = canonical_col
        
        if rename_map:
            day_7_standardized = day_7_standardized.rename(columns=rename_map)
            st.info(f"Standardized {len(rename_map)} Day 7 column names to match Day 0 casing")
        
        return day_7_standardized
    
    @staticmethod
    def validate_sample_names(df: pd.DataFrame, 
                            metadata_df: Optional[pd.DataFrame] = None) -> Dict:
        """
        Validate sample names for common issues.
        """
        validation = {
            "valid": True,
            "total_samples": 0,
            "issues": [],
            "metadata_match": None
        }
        
        if 'sample_name' not in df.columns:
            validation["valid"] = False
            validation["issues"].append("No sample_name column found")
            return validation
        
        raw_samples = df['sample_name']
        missing_count = int(raw_samples.isna().sum())
        samples = raw_samples.dropna().astype(str).str.strip()
        validation["total_samples"] = len(raw_samples)
        
        # Check for empty sample names
        empty_count = int(samples.str.casefold().isin({'', 'nan', 'none'}).sum()) + missing_count
        if empty_count:
            validation["issues"].append(f"{empty_count} empty sample names found")
            validation["valid"] = False
        
        # Check for duplicates
        duplicates = samples[samples.duplicated()].unique()
        if len(duplicates) > 0:
            # Get count for each duplicate
            duplicate_counts = samples[samples.isin(duplicates)].value_counts()
            
            # Create detailed message
            duplicate_details = []
            for name, count in duplicate_counts.items():
                duplicate_details.append(f"'{name}' (appears {count} times)")
            
            validation["issues"].append(
                f"{len(duplicates)} duplicate sample names found: " + 
                ", ".join(duplicate_details)
            )
            validation["valid"] = False
        
        # Check for FMO samples
        fmo_samples = samples[samples.str.contains('fmo', case=False, na=False)]
        if len(fmo_samples) > 0:
            fmo_list = "', '".join(fmo_samples.unique()[:10])  # Show first 10
            more_text = f" (and {len(fmo_samples.unique()) - 10} more)" if len(fmo_samples.unique()) > 10 else ""
            validation["issues"].append(
                f"{len(fmo_samples)} FMO samples detected: '{fmo_list}'{more_text}"
            )
            validation["valid"] = False
        
        # Check for .fcs extensions
        fcs_samples = samples[samples.str.contains(r'\.fcs', case=False, na=False)]
        if len(fcs_samples) > 0:
            fcs_list = "', '".join(fcs_samples.unique()[:10])  # Show first 10
            more_text = f" (and {len(fcs_samples.unique()) - 10} more)" if len(fcs_samples.unique()) > 10 else ""
            validation["issues"].append(
                f"{len(fcs_samples)} samples have .fcs extensions: '{fcs_list}'{more_text}"
            )
            validation["valid"] = False
        
        # Validate against metadata if provided
        if metadata_df is not None and 'sample_name' in metadata_df.columns:
            flow_samples = set(samples.unique())
            meta_samples = set(metadata_df['sample_name'].dropna().astype(str).unique())
            
            matching = flow_samples & meta_samples
            in_flow_not_meta = flow_samples - meta_samples
            in_meta_not_flow = meta_samples - flow_samples
            
            validation["metadata_match"] = {
                "matching": matching,
                "in_flow_not_metadata": in_flow_not_meta,
                "in_metadata_not_flow": in_meta_not_flow,
                "match_percentage": len(matching) / len(flow_samples) * 100 if flow_samples else 0
            }
            
            if in_flow_not_meta:
                validation["valid"] = False
                sample_list = "', '".join(sorted(list(in_flow_not_meta))[:10])  # Show first 10
                more_text = f" (and {len(in_flow_not_meta) - 10} more)" if len(in_flow_not_meta) > 10 else ""
                validation["issues"].append(
                    f"{len(in_flow_not_meta)} samples in flow data not found in metadata: '{sample_list}'{more_text}"
                )
        
        return validation
    
    @staticmethod
    def validate_precision_counts(df: pd.DataFrame) -> Dict:
        """
        Validate precision count data for anomalies.
        """
        validation = {
            "valid": True,
            "issues": [],
            "warnings": []
        }
        
        count_column = next(
            (c for c in ('recorded_bead_count', 'precision_count_beads') if c in df.columns),
            None,
        )
        if count_column is None:
            validation["valid"] = False
            validation["issues"].append("No recorded_bead_count column found")
            return validation

        counts = pd.to_numeric(df[count_column], errors='coerce')
        missing = counts.isna()
        if missing.any():
            validation["valid"] = False
            validation["issues"].append(f"{int(missing.sum())} samples have missing or non-numeric bead counts")

        non_positive = counts.notna() & counts.le(0)
        if non_positive.any():
            validation["valid"] = False
            validation["issues"].append(f"{int(non_positive.sum())} samples have zero or negative bead counts")
        
        # Check for unusually low counts (< 1000)
        low_counts = counts.gt(0) & counts.lt(1000)
        if low_counts.any():
            validation["warnings"].append(
                f"{int(low_counts.sum())} samples have very low bead counts (< 1000)"
            )
        
        # Check for unusually high counts (> 100000)
        high_counts = counts.gt(100000)
        if high_counts.any():
            validation["warnings"].append(
                f"{int(high_counts.sum())} samples have unusually high bead counts (> 100000)"
            )
        
        return validation
    
    @staticmethod
    def display_validation_results(validation: Dict, title: str = "Validation Results"):
        """
        Display validation results in Streamlit with formatting.
        """
        st.subheader(title)
        
        if validation.get("valid", False):
            st.success("All validation checks passed.")
        else:
            st.error("Validation issues detected")
        
        # Display issues
        if validation.get("issues"):
            st.error("**Issues:**")
            for issue in validation["issues"]:
                st.markdown(f"- {issue}")
        
        # Display warnings
        if validation.get("warnings"):
            st.warning("**Warnings:**")
            for warning in validation["warnings"]:
                st.markdown(f"- {warning}")
        
        return validation.get("valid", False)
    
    @staticmethod
    def create_validation_report(day_0_val: Dict = None,
                                day_7_val: Dict = None,
                                column_val: Dict = None) -> str:
        """
        Create a comprehensive validation report.
        """
        report_lines = [
            "# Flow Cytometry Data Validation Report",
            f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Summary",
        ]
        
        # Overall status
        all_valid = True
        if day_0_val and not day_0_val.get("valid", True):
            all_valid = False
        if day_7_val and not day_7_val.get("valid", True):
            all_valid = False
        if column_val and not column_val.get("valid", True):
            all_valid = False
        
        if all_valid:
            report_lines.append("**All validation checks passed.**")
        else:
            report_lines.append("**Validation issues detected - see details below**")
        
        report_lines.append("")
        
        # Day 0 validation
        if day_0_val:
            report_lines.append("## Day 0 Data Validation")
            report_lines.append(f"- Total samples: {day_0_val.get('total_samples', 'N/A')}")
            
            if day_0_val.get("issues"):
                report_lines.append("- **Issues:**")
                for issue in day_0_val["issues"]:
                    report_lines.append(f"  - {issue}")
            
            if day_0_val.get("warnings"):
                report_lines.append("- **Warnings:**")
                for warning in day_0_val["warnings"]:
                    report_lines.append(f"  - {warning}")
            
            report_lines.append("")
        
        # Day 7 validation
        if day_7_val:
            report_lines.append("## Day 7 Data Validation")
            report_lines.append(f"- Total samples: {day_7_val.get('total_samples', 'N/A')}")
            
            if day_7_val.get("issues"):
                report_lines.append("- **Issues:**")
                for issue in day_7_val["issues"]:
                    report_lines.append(f"  - {issue}")
            
            if day_7_val.get("warnings"):
                report_lines.append("- **Warnings:**")
                for warning in day_7_val["warnings"]:
                    report_lines.append(f"  - {warning}")
            
            report_lines.append("")
        
        # Column validation
        if column_val:
            report_lines.append("## Column Consistency Check (Case-Insensitive)")
            report_lines.append(f"- Day 0 columns: {len(column_val.get('day_0_columns', []))}")
            report_lines.append(f"- Day 7 columns: {len(column_val.get('day_7_columns', []))}")
            report_lines.append(f"- Common columns (case-insensitive): {len(column_val.get('common_columns_ci', []))}")
            
            if column_val.get("only_in_day_0"):
                report_lines.append(f"\n**Columns only in Day 0** ({len(column_val['only_in_day_0'])}):")
                for col in sorted(column_val["only_in_day_0"]):
                    report_lines.append(f"- {col}")
            
            if column_val.get("only_in_day_7"):
                report_lines.append(f"\n**Columns only in Day 7** ({len(column_val['only_in_day_7'])}):")
                for col in sorted(column_val["only_in_day_7"]):
                    report_lines.append(f"- {col}")
            
            if column_val.get("case_mismatches"):
                report_lines.append(f"\n**Case Mismatches** ({len(column_val['case_mismatches'])}) - Will be standardized to Day 0:")
                for col_lower, cases in column_val["case_mismatches"].items():
                    report_lines.append(f"- Day 0 (canonical): `{cases['day_0']}` | Day 7: `{cases['day_7']}`")
            
            if column_val.get("recommendations"):
                report_lines.append("\n**Recommendations:**")
                for rec in column_val["recommendations"]:
                    report_lines.append(f"- {rec}")
        
        return "\n".join(report_lines)
