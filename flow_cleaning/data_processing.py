"""
Flow Cytometry Data Cleaning Module - FIXED VERSION

CRITICAL FIXES:
1. All column operations are case-insensitive
2. Day 0 column names are the canonical reference
3. All merges standardize to Day 0 casing
4. Duplicate columns (differing only in case) are eliminated
5. Duplicate columns with .1, .2 suffixes are removed immediately after loading
"""

import pandas as pd
import numpy as np
import re
from typing import Dict, List, Tuple, Optional, Union
from pathlib import Path
import streamlit as st


class FlowDataCleaner:
    """Handles cleaning and merging of flow cytometry data files with case-insensitive operations."""
    
    def __init__(self):
        self.loaded_files = {}
        self.merge_key = 'sample_name'
        self.canonical_column_map = {}  # Maps lowercase -> canonical case
    
    @staticmethod
    def remove_duplicate_columns(df: pd.DataFrame, filename: str = "") -> pd.DataFrame:
        """
        Remove duplicate columns with .1, .2, .3 suffixes immediately after loading file.
        Only removes if values match the base column.
        
        Args:
            df: DataFrame just loaded from file
            filename: Name of file (for logging)
            
        Returns:
            DataFrame with duplicate columns removed
        """
        suffix_pattern = re.compile(r'\.\d+$')
        
        # Group columns by base name
        groups = {}
        for col in df.columns:
            if col == 'sample_name':
                continue
            base = suffix_pattern.sub('', col)
            if base not in groups:
                groups[base] = []
            groups[base].append(col)
        
        # Find duplicates and check values
        to_remove = []
        removed_info = []
        
        for base, cols in groups.items():
            if len(cols) > 1:
                # Sort so base (no suffix) comes first
                cols_sorted = sorted(cols, key=lambda x: (suffix_pattern.search(x) is not None, x))
                base_col = cols_sorted[0]
                
                for dup_col in cols_sorted[1:]:
                    # Check if values match
                    try:
                        values_match = False
                        if df[base_col].equals(df[dup_col]):
                            values_match = True
                        elif pd.api.types.is_numeric_dtype(df[base_col]) and pd.api.types.is_numeric_dtype(df[dup_col]):
                            # For numeric, use close comparison
                            if np.allclose(df[base_col].fillna(0), df[dup_col].fillna(0), rtol=1e-9, equal_nan=True):
                                values_match = True
                        
                        if values_match:
                            to_remove.append(dup_col)
                            removed_info.append((base_col, dup_col))
                    except:
                        pass  # If comparison fails, don't remove
        
        # Remove duplicates
        if to_remove:
            df = df.drop(columns=to_remove)
            
            file_msg = f" in {filename}" if filename else ""
            st.warning(f"⚠️ Removed {len(to_remove)} duplicate column(s) with matching values{file_msg}")
            
            with st.expander(f"📋 View {len(removed_info)} removed column(s)"):
                for base_col, dup_col in removed_info:
                    st.text(f"✓ Kept: {base_col}")
                    st.text(f"  ✗ Removed: {dup_col}")
        
        return df
        
    def standardize_columns_to_canonical(self, df: pd.DataFrame, 
                                         canonical_map: Dict[str, str]) -> pd.DataFrame:
        """
        Standardize all column names to match the canonical casing.
        
        Args:
            df: DataFrame to standardize
            canonical_map: Dict mapping lowercase column name to canonical case
            
        Returns:
            DataFrame with standardized column names
        """
        df = df.copy()
        
        # Create rename mapping
        rename_map = {}
        for col in df.columns:
            col_lower = col.lower()
            if col_lower in canonical_map:
                canonical_col = canonical_map[col_lower]
                if col != canonical_col:
                    rename_map[col] = canonical_col
        
        if rename_map:
            df = df.rename(columns=rename_map)
            st.info(f"   🔤 Standardized {len(rename_map)} column names to canonical casing")
        
        return df
    
    def build_canonical_column_map(self, reference_df: pd.DataFrame) -> Dict[str, str]:
        """
        Build canonical column mapping from a reference DataFrame (typically Day 0).
        
        Args:
            reference_df: The reference DataFrame (Day 0)
            
        Returns:
            Dict mapping lowercase column names to the canonical case
        """
        canonical_map = {}
        for col in reference_df.columns:
            col_lower = col.lower()
            canonical_map[col_lower] = col
        
        return canonical_map
    
    def load_files(self, uploaded_files: List) -> Dict[str, pd.DataFrame]:
        """
        Load uploaded files without changing measurement values or units.

        FlowJo may export frequencies as explicit percentage strings or plain
        numbers. Their scale cannot be inferred safely from magnitude, so this
        loader deliberately performs no percentage conversion.
        
        Args:
            uploaded_files: List of Streamlit uploaded file objects
            
        Returns:
            Dictionary mapping filenames to DataFrames
        """
        dfs = {}

        for uploaded_file in uploaded_files:
            try:
                file_extension = uploaded_file.name.split('.')[-1].lower()

                if file_extension == 'xlsx':
                    df = pd.read_excel(uploaded_file, engine='openpyxl')
                elif file_extension == 'xls':
                    df = pd.read_excel(uploaded_file, engine='xlrd')
                elif file_extension == 'csv':
                    df = pd.read_csv(uploaded_file)
                else:
                    st.warning(f"Unsupported file type: {uploaded_file.name}")
                    continue

                # === NEW: Remove duplicate columns immediately after loading ===
                df = self.remove_duplicate_columns(df, filename=uploaded_file.name)
                
                dfs[uploaded_file.name] = df
                st.success(f"✓ Loaded {uploaded_file.name}: {df.shape[0]} rows, {df.shape[1]} columns")

            except Exception as e:
                st.error(f"✗ Error loading {uploaded_file.name}: {str(e)}")
                continue
        
        self.loaded_files = dfs
        return dfs
    
    def standardize_sample_column(self, df: pd.DataFrame, filename: str = "") -> pd.DataFrame:
        """
        Standardize the sample name column to 'sample_name' (case-insensitive detection).
        
        Handles:
        - Unnamed: 0 columns
        - 'name' columns (case-insensitive)
        - Already standardized 'sample_name' columns
        """
        df = df.copy()
        
        # Check if first column is Unnamed
        first_col = df.columns[0]
        if first_col.startswith('Unnamed:'):
            old_name = first_col
            df.rename(columns={first_col: 'sample_name'}, inplace=True)
            if filename:
                st.info(f"✏️ Renamed '{old_name}' → 'sample_name' in {filename}")
            return df
        
        # Check for 'name' or 'sample_name' column (case-insensitive)
        for col in df.columns:
            col_lower = col.lower()
            if col_lower in ['name', 'sample_name'] and col != 'sample_name':
                old_name = col
                df.rename(columns={col: 'sample_name'}, inplace=True)
                if filename:
                    st.info(f"✏️ Renamed '{old_name}' → 'sample_name' in {filename}")
                return df
        
        # Check if already has sample_name (any case)
        sample_name_cols = [col for col in df.columns if col.lower() == 'sample_name']
        if sample_name_cols:
            # Already has sample_name column, ensure it's lowercase
            if sample_name_cols[0] != 'sample_name':
                df.rename(columns={sample_name_cols[0]: 'sample_name'}, inplace=True)
            return df
        
        # No sample name column found
        st.warning(f"⚠️ No sample name column detected in {filename}. First column will be used.")
        df.rename(columns={df.columns[0]: 'sample_name'}, inplace=True)
        
        return df
    
    def clean_sample_names(self, 
                          df: pd.DataFrame,
                          method: str = 'none',
                          separator: str = '_',
                          skip_parts: int = 2,
                          regex_pattern: str = None) -> pd.DataFrame:
        """
        Clean sample names using various methods.
        
        Args:
            df: DataFrame with sample_name column
            method: Cleaning method ('none', 'separator', 'regex', 'donor_asterisk')
            separator: Character to split by (for separator method)
            skip_parts: Number of parts to skip from start (for separator method)
            regex_pattern: Regex pattern to remove (for regex method)
            
        Returns:
            DataFrame with cleaned sample names
        """
        if 'sample_name' not in df.columns:
            st.warning("⚠️ No sample_name column found - skipping name cleaning")
            return df
        
        if method == 'none':
            return df
        
        df = df.copy()
        original_names = df['sample_name'].astype(str).copy()
        
        # Show examples before cleaning
        sample_originals = original_names.head(3).tolist()
        
        if method == 'donor_asterisk':
            # Preset for "DonorX*_B2_" format
            separator = '_'
            skip_parts = 2
            method = 'separator'
            st.info(f"🧹 Using preset cleaning for 'DonorX*_B2_' format")
        
        if method == 'separator':
            def clean_with_separator(name):
                try:
                    parts = str(name).split(separator)
                    if len(parts) > skip_parts:
                        return separator.join(parts[skip_parts:])
                    return name
                except:
                    return name
            
            df['sample_name'] = original_names.apply(clean_with_separator)
            st.success(f"✓ Cleaned using separator '{separator}', skipping first {skip_parts} parts")
            
        elif method == 'regex':
            if not regex_pattern:
                st.warning("⚠️ No regex pattern provided")
                return df
            
            try:
                df['sample_name'] = original_names.str.replace(regex_pattern, '', regex=True)
                st.success(f"✓ Cleaned using regex pattern: {regex_pattern}")
            except Exception as e:
                st.error(f"✗ Regex error: {str(e)}")
                return df
        
        # Show examples after cleaning
        cleaned_names = df['sample_name'].astype(str)
        sample_cleaned = cleaned_names.head(3).tolist()
        
        changes = (original_names != cleaned_names).sum()
        
        if changes > 0:
            with st.expander(f"👀 View cleaning results ({changes} names changed)"):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Before:**")
                    for name in sample_originals:
                        st.code(name, language=None)
                with col2:
                    st.markdown("**After:**")
                    for name in sample_cleaned:
                        st.code(name, language=None)
        
        return df
    
    def remove_fcs_extensions(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Remove .fcs extensions from sample names.
        """
        if 'sample_name' not in df.columns:
            return df
        
        df = df.copy()
        before = df['sample_name'].copy()
        
        # Remove .fcs (case insensitive)
        df['sample_name'] = df['sample_name'].astype(str).str.replace(
            r'\.fcs$', '', case=False, regex=True
        )
        
        changes = (before != df['sample_name']).sum()
        if changes > 0:
            st.success(f"✓ Removed .fcs extension from {changes} sample names")
        
        return df
    
    def remove_fmo_samples(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Remove FMO (Fluorescence Minus One) control samples.
        """
        if 'sample_name' not in df.columns:
            st.warning("⚠️ No sample_name column to filter FMO samples")
            return df
        
        df = df.copy()
        before_count = len(df)
        
        # Remove rows where sample_name contains 'fmo' (case insensitive)
        df = df[~df['sample_name'].astype(str).str.contains('fmo', case=False, na=False)]
        
        removed = before_count - len(df)
        if removed > 0:
            st.success(f"✓ Removed {removed} FMO samples")
        else:
            st.info("ℹ️ No FMO samples found")
        
        return df
    
    def analyze_file_structure(self, dfs: Dict[str, pd.DataFrame]) -> Dict:
        """
        Analyze the structure of multiple DataFrames with CASE-INSENSITIVE column comparison.
        
        Returns:
            Dictionary with structural analysis including per-file column differences
        """
        if not dfs:
            return {"error": "No files provided"}
        
        analysis = {
            "file_count": len(dfs),
            "shapes": {},
            "columns": {},
            "row_counts": {},
            "common_columns_ci": set(),  # Case-insensitive
            "all_columns_ci": set(),  # Case-insensitive
            "identical_structure": False,
            "missing_columns_per_file": {},
            "unique_columns_per_file": {},
            "case_mismatches": {},  # Maps lowercase -> {case1: [files], case2: [files]}
        }
        
        # Build lowercase -> original case mapping for each file
        file_col_mappings = {}
        for name, df in dfs.items():
            analysis["shapes"][name] = df.shape
            analysis["columns"][name] = list(df.columns)
            analysis["row_counts"][name] = len(df)
            
            # Build case mapping for this file
            file_col_mappings[name] = {col.lower(): col for col in df.columns}
        
        # Get all lowercase column names
        all_lower_sets = [set(mapping.keys()) for mapping in file_col_mappings.values()]
        
        # Column analysis (case-insensitive)
        if len(dfs) > 1:
            analysis["common_columns_ci"] = set.intersection(*all_lower_sets)
            analysis["all_columns_ci"] = set.union(*all_lower_sets)
            analysis["identical_structure"] = len(analysis["common_columns_ci"]) == len(analysis["all_columns_ci"])
            
            # Analyze what each file is missing (case-insensitive)
            for name, lower_mapping in file_col_mappings.items():
                file_cols_lower = set(lower_mapping.keys())
                analysis["missing_columns_per_file"][name] = analysis["all_columns_ci"] - file_cols_lower
                analysis["unique_columns_per_file"][name] = file_cols_lower - analysis["common_columns_ci"]
        else:
            file_name = list(dfs.keys())[0]
            analysis["common_columns_ci"] = set(file_col_mappings[file_name].keys())
            analysis["all_columns_ci"] = analysis["common_columns_ci"]
            analysis["identical_structure"] = True
        
        # Find case mismatches across files for common columns
        for col_lower in analysis["common_columns_ci"]:
            casings = {}
            for name, lower_mapping in file_col_mappings.items():
                if col_lower in lower_mapping:
                    original_case = lower_mapping[col_lower]
                    if original_case not in casings:
                        casings[original_case] = []
                    casings[original_case].append(name)
            
            if len(casings) > 1:
                analysis["case_mismatches"][col_lower] = casings
        
        return analysis
    
    def validate_against_metadata(self, 
                                  flow_df: pd.DataFrame, 
                                  metadata_df: pd.DataFrame) -> Dict:
        """
        Validate flow data sample names against metadata.
        
        Args:
            flow_df: Flow cytometry DataFrame with sample_name column
            metadata_df: Metadata DataFrame with sample_name column
            
        Returns:
            Dictionary with validation results
        """
        validation = {
            "valid": True,
            "flow_samples": set(),
            "metadata_samples": set(),
            "in_flow_not_metadata": set(),
            "in_metadata_not_flow": set(),
            "matching_samples": set()
        }
        
        if 'sample_name' not in flow_df.columns:
            validation["valid"] = False
            validation["error"] = "sample_name column not found in flow data"
            return validation
        
        if 'sample_name' not in metadata_df.columns:
            validation["valid"] = False
            validation["error"] = "sample_name column not found in metadata"
            return validation
        
        # Get sample sets
        flow_samples = set(flow_df['sample_name'].dropna().astype(str).unique())
        metadata_samples = set(metadata_df['sample_name'].dropna().astype(str).unique())
        
        validation["flow_samples"] = flow_samples
        validation["metadata_samples"] = metadata_samples
        validation["matching_samples"] = flow_samples & metadata_samples
        validation["in_flow_not_metadata"] = flow_samples - metadata_samples
        validation["in_metadata_not_flow"] = metadata_samples - flow_samples
        
        # Check if valid
        if validation["in_flow_not_metadata"]:
            validation["valid"] = False
        
        return validation
    
    def detect_merge_type(self, dfs: Dict[str, pd.DataFrame]) -> str:
        """
        Detect whether ALL files should be merged by row or by feature.
        Returns 'feature' if >50% of unique sample names appear in more than one
        file, otherwise 'row'.  Use detect_merge_groups() for mixed scenarios.
        """
        if len(dfs) <= 1:
            return 'row'

        sample_sets = {}
        for name, df in dfs.items():
            if 'sample_name' in df.columns:
                sample_sets[name] = set(df['sample_name'].dropna().astype(str).unique())

        if len(sample_sets) < 2:
            return 'row'

        all_samples = set.union(*sample_sets.values())
        if not all_samples:
            return 'row'

        overlapping = sum(
            1 for s in all_samples
            if sum(1 for ss in sample_sets.values() if s in ss) > 1
        )
        overlap_ratio = overlapping / len(all_samples)
        return 'feature' if overlap_ratio > 0.5 else 'row'

    def detect_merge_groups(self, dfs: Dict[str, pd.DataFrame],
                            overlap_threshold: float = 0.3) -> Dict[str, int]:
        """
        Cluster files into merge groups using connected components.

        Two files are connected (placed in the same group) when the fraction of
        sample names they share — relative to the smaller file — exceeds
        *overlap_threshold*.  Files in the same group will be feature-merged
        (column-wise join on sample_name); groups are then row-merged together.

        Args:
            dfs: Dict of filename -> DataFrame (must have sample_name column).
            overlap_threshold: Minimum overlap ratio to connect two files (default 0.3).

        Returns:
            Dict mapping filename -> group_id (1-indexed integers).
        """
        if len(dfs) <= 1:
            return {name: 1 for name in dfs}

        sample_sets: Dict[str, set] = {}
        for name, df in dfs.items():
            if 'sample_name' in df.columns:
                sample_sets[name] = set(df['sample_name'].dropna().astype(str).unique())
            else:
                sample_sets[name] = set()

        file_names = list(dfs.keys())

        # Build adjacency list: edge if overlap ratio > threshold
        adj: Dict[str, set] = {name: set() for name in file_names}
        for i, a in enumerate(file_names):
            for b in file_names[i + 1:]:
                sa, sb = sample_sets[a], sample_sets[b]
                if not sa or not sb:
                    continue
                overlap = len(sa & sb)
                smaller = min(len(sa), len(sb))
                if smaller > 0 and overlap / smaller > overlap_threshold:
                    adj[a].add(b)
                    adj[b].add(a)

        # BFS connected components → group ids
        visited: Dict[str, int] = {}
        group_id = 1
        for name in file_names:
            if name not in visited:
                queue = [name]
                while queue:
                    current = queue.pop(0)
                    if current not in visited:
                        visited[current] = group_id
                        queue.extend(adj[current] - set(visited.keys()))
                group_id += 1

        return visited

    def merge_files_by_feature(self, dfs: Dict[str, pd.DataFrame],
                               canonical_map: Optional[Dict[str, str]] = None) -> pd.DataFrame:
        """
        Merge files column-wise by outer-joining on sample_name.

        Used when multiple files contain different features (markers) for the
        same set of samples.  Duplicate non-key columns that appear in more than
        one file are suffixed with the source filename stem.

        Args:
            dfs: Dictionary of DataFrames to merge
            canonical_map: Optional canonical column name mapping (lowercase -> proper case)

        Returns:
            Wide DataFrame with one row per sample and all feature columns combined
        """
        if len(dfs) == 1:
            return list(dfs.values())[0].copy()

        st.info(f"🔗 Feature merge: joining {len(dfs)} files by sample_name (column-wise)...")

        file_names = list(dfs.keys())
        merged = None

        for i, (fname, df) in enumerate(dfs.items()):
            df_copy = df.copy()

            # Standardise casing if canonical map supplied
            if canonical_map:
                rename_map = {
                    col: canonical_map[col.lower()]
                    for col in df_copy.columns
                    if col.lower() in canonical_map and col != canonical_map[col.lower()]
                }
                if rename_map:
                    df_copy = df_copy.rename(columns=rename_map)

            if merged is None:
                merged = df_copy
                continue

            # Determine which non-key columns collide
            existing_cols = set(merged.columns) - {'sample_name'}
            incoming_cols = set(df_copy.columns) - {'sample_name'}
            collisions = existing_cols & incoming_cols

            if collisions:
                stem = Path(fname).stem
                st.warning(
                    f"⚠️ {len(collisions)} column(s) from **{fname}** already exist — "
                    f"suffixing with `_{stem}`"
                )
                df_copy = df_copy.rename(
                    columns={col: f"{col}_{stem}" for col in collisions}
                )

            merged = pd.merge(merged, df_copy, on='sample_name', how='outer')
            st.success(f"  ✓ Joined {fname}: result is {merged.shape[0]} rows × {merged.shape[1]} columns")

        st.success(f"✅ Feature merge complete: {merged.shape[0]} rows × {merged.shape[1]} columns")
        return merged

    def merge_files_mixed(self, dfs: Dict[str, pd.DataFrame],
                          file_groups: Dict[str, int],
                          canonical_map: Optional[Dict[str, str]] = None) -> pd.DataFrame:
        """
        Mixed merge: feature-merge files within each group, then row-merge groups.

        Args:
            dfs: Dict of filename -> DataFrame.
            file_groups: Dict mapping filename -> group_id (1-indexed).
            canonical_map: Optional canonical column casing map.

        Returns:
            Final merged DataFrame.
        """
        # Bucket files by group
        groups: Dict[int, Dict[str, pd.DataFrame]] = {}
        for name, gid in file_groups.items():
            if name in dfs:
                groups.setdefault(gid, {})[name] = dfs[name]

        n_groups = len(groups)
        n_feature_groups = sum(1 for g in groups.values() if len(g) > 1)
        st.info(
            f"🗂️ Mixed merge: {n_groups} group(s), "
            f"{n_feature_groups} will be feature-merged, "
            f"{n_groups - n_feature_groups} will pass through as-is"
        )

        group_results = []
        for gid in sorted(groups.keys()):
            group_dfs = groups[gid]
            st.markdown(f"**Group {gid}** ({len(group_dfs)} file(s)):")
            if len(group_dfs) == 1:
                result = list(group_dfs.values())[0].copy()
                st.success(f"  ✓ Group {gid}: single file — {result.shape}")
            else:
                result = self.merge_files_by_feature(group_dfs, canonical_map=canonical_map)
                st.success(f"  ✓ Group {gid}: feature-merged → {result.shape}")
            group_results.append(result)

        if len(group_results) == 1:
            return group_results[0]

        # Row-merge across groups (reindex to align columns)
        st.info(f"↕️ Row-merging {len(group_results)} groups...")
        merged = pd.concat(group_results, ignore_index=True)
        st.success(f"✅ Mixed merge complete: {merged.shape[0]} rows × {merged.shape[1]} columns")
        return merged

    def merge_files(self, dfs: Dict[str, pd.DataFrame],
                   remove_donor_source: bool = True,
                   canonical_map: Optional[Dict[str, str]] = None,
                   merge_type: str = 'row') -> pd.DataFrame:
        """
        Merge multiple DataFrames into one with CASE-INSENSITIVE column handling.

        Args:
            dfs: Dictionary of DataFrames to merge
            remove_donor_source: Whether to remove the Donor_Source tracking column
            canonical_map: Optional canonical column name mapping (lowercase -> proper case)
            merge_type: 'row' (concatenate rows) or 'feature' (join columns on sample_name)

        Returns:
            Merged DataFrame with standardized column names
        """
        if len(dfs) == 1:
            name, df = list(dfs.items())[0]
            df_copy = df.copy()
            if not remove_donor_source:
                df_copy['Donor_Source'] = name
            st.info(f"📄 Single file: {df_copy.shape}")
            return df_copy

        # Feature (column-wise) merge
        if merge_type == 'feature':
            return self.merge_files_by_feature(dfs, canonical_map=canonical_map)

        # --- Row-wise merge (original behaviour) ---
        st.info(f"🔄 Merging {len(dfs)} files with case-insensitive column standardization...")
        
        # Build canonical map if not provided (use first file as reference)
        if canonical_map is None:
            first_df = list(dfs.values())[0]
            canonical_map = {col.lower(): col for col in first_df.columns}
            st.info(f"📋 Using first file as canonical column reference")
        
        # Get all unique columns (case-insensitive) and map to canonical names
        all_columns_lower = set()
        for df in dfs.values():
            all_columns_lower.update(col.lower() for col in df.columns)
        
        # Map to canonical names
        all_columns_canonical = []
        for col_lower in all_columns_lower:
            if col_lower in canonical_map:
                all_columns_canonical.append(canonical_map[col_lower])
            else:
                # Use the first occurrence we find
                for df in dfs.values():
                    for col in df.columns:
                        if col.lower() == col_lower:
                            all_columns_canonical.append(col)
                            canonical_map[col_lower] = col
                            break
                    else:
                        continue
                    break
        
        st.info(f"📊 Found {len(all_columns_canonical)} unique columns (case-insensitive) across all files")
        
        # Prepare dataframes with standardized columns
        labeled_dfs = []
        for name, df in dfs.items():
            df_copy = df.copy()
            
            # Standardize column names to canonical
            rename_map = {}
            for col in df_copy.columns:
                col_lower = col.lower()
                if col_lower in canonical_map:
                    canonical_col = canonical_map[col_lower]
                    if col != canonical_col:
                        rename_map[col] = canonical_col
            
            if rename_map:
                df_copy = df_copy.rename(columns=rename_map)
                st.info(f"   🔤 {name}: Standardized {len(rename_map)} column names")
            
            # Reindex to include all canonical columns
            df_copy = df_copy.reindex(columns=sorted(all_columns_canonical))
            
            # Add source tracking
            if not remove_donor_source:
                df_copy['Donor_Source'] = name
            
            labeled_dfs.append(df_copy)
            st.success(f"  ✓ Prepared {name}: {df_copy.shape}")
        
        # Concatenate
        merged_df = pd.concat(labeled_dfs, ignore_index=True)
        
        st.success(f"✅ Merged into {merged_df.shape[0]} rows × {merged_df.shape[1]} columns")
        
        # Show donor counts if tracking enabled
        if not remove_donor_source and 'Donor_Source' in merged_df.columns:
            donor_counts = merged_df['Donor_Source'].value_counts()
            with st.expander("📊 View merged file breakdown"):
                for donor, count in donor_counts.items():
                    st.metric(donor, f"{count} rows")
        
        return merged_df
    
    def process_files(self,
                     uploaded_files: List,
                     cleaning_method: str = 'none',
                     separator: str = '_',
                     skip_parts: int = 2,
                     regex_pattern: str = None,
                     remove_fmo: bool = True,
                     metadata_df: Optional[pd.DataFrame] = None,
                     canonical_map: Optional[Dict[str, str]] = None,
                     merge_type: str = 'auto',
                     file_groups: Optional[Dict[str, int]] = None) -> Tuple[pd.DataFrame, Dict]:
        """
        Complete processing pipeline for uploaded files with case-insensitive handling.

        Args:
            uploaded_files: List of uploaded file objects
            cleaning_method: Method for cleaning sample names
            separator: Separator for splitting names
            skip_parts: Parts to skip when splitting
            regex_pattern: Regex pattern for cleaning
            remove_fmo: Whether to remove FMO samples
            metadata_df: Optional metadata for validation
            canonical_map: Optional canonical column mapping (from Day 0)
            merge_type: 'auto' (detect groups via connected components),
                        'row' (stack all files), 'feature' (join all files on sample_name),
                        or 'manual' (use file_groups argument).
            file_groups: Dict mapping filename -> group_id used when merge_type='manual'.
                         Files in the same group are feature-merged; groups are row-merged.

        Returns:
            Tuple of (processed DataFrame, summary dict)
        """
        summary = {
            "files_loaded": 0,
            "original_rows": 0,
            "final_rows": 0,
            "final_cols": 0,
            "cleaning_applied": cleaning_method != 'none',
            "fmo_removed": 0,
            "merge_type_used": None,
            "per_file_input_shapes": {},   # filename -> (rows, cols) at load time
            "per_file_pre_merge_shapes": {},  # filename -> (rows, cols) after cleaning
            "merged_shape": None,          # (rows, cols) immediately after merge
            "validation": None
        }
        
        # Step 1: Load files (now includes duplicate column removal)
        st.subheader("📁 Loading Files")
        dfs = self.load_files(uploaded_files)
        summary["files_loaded"] = len(dfs)
        
        if not dfs:
            st.error("❌ No files could be loaded")
            return None, summary
        
        summary["original_rows"] = sum(len(df) for df in dfs.values())
        summary["per_file_input_shapes"] = {name: df.shape for name, df in dfs.items()}
        
        # Step 2: Standardize column names
        st.subheader("📝 Standardizing Column Names")
        standardized_dfs = {}
        for name, df in dfs.items():
            standardized_dfs[name] = self.standardize_sample_column(df, name)
        
        # Step 3: Analyze structure with case-insensitive comparison
        st.subheader("🔍 Analyzing File Structure (Case-Insensitive)")
        analysis = self.analyze_file_structure(standardized_dfs)
        
        if analysis["file_count"] > 1:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Files", analysis["file_count"])
            with col2:
                st.metric("Common Columns", len(analysis["common_columns_ci"]))
            with col3:
                st.metric("Total Unique Columns", len(analysis["all_columns_ci"]))
            
            # Display detailed validation
            st.markdown("#### 🧬 Intra-Day Validation Results")
            
            # Validation 1: Sample overlap check
            st.markdown("#### 👥 Sample Name Overlap Check")
            
            if len(standardized_dfs) > 1:
                # Build sets of samples per file
                sample_sets = {}
                for name, df in standardized_dfs.items():
                    if 'sample_name' in df.columns:
                        sample_sets[name] = set(df['sample_name'].dropna().astype(str).unique())
                
                # Find all unique samples and duplicates
                all_samples = set()
                for samples in sample_sets.values():
                    all_samples.update(samples)
                
                duplicate_samples = set()
                for sample in all_samples:
                    files_with_sample = [name for name, samples in sample_sets.items() if sample in samples]
                    if len(files_with_sample) > 1:
                        duplicate_samples.add(sample)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Unique Samples", len(all_samples))
                    st.metric("Samples in Multiple Files", len(duplicate_samples))
                
                with col2:
                    total_samples_all_files = sum(len(s) for s in sample_sets.values())
                    st.metric("Total Samples (all files)", total_samples_all_files)
                    st.metric("Expected After Merge", len(all_samples))
                
                if duplicate_samples:
                    if merge_type in ('feature', 'auto'):
                        detected = self.detect_merge_type(standardized_dfs)
                        if merge_type == 'auto':
                            if detected == 'feature':
                                st.info(
                                    f"🔍 **Auto-detected: Feature merge** — "
                                    f"{len(duplicate_samples)} sample(s) appear in multiple files. "
                                    f"Files will be joined column-wise on `sample_name`."
                                )
                            else:
                                st.warning(
                                    f"⚠️ **Found {len(duplicate_samples)} samples present in multiple files** "
                                    f"(overlap < 50 %). Defaulting to row merge — "
                                    f"this may produce duplicate rows. Consider switching to Feature merge."
                                )
                        else:  # merge_type == 'feature'
                            st.info(
                                f"🔗 Feature merge selected — {len(duplicate_samples)} overlapping "
                                f"sample(s) will be joined column-wise."
                            )
                    else:  # explicit 'row'
                        st.error(f"❌ **Found {len(duplicate_samples)} samples present in multiple files!**")
                        with st.expander("⚠️ View duplicate samples"):
                            for sample in sorted(duplicate_samples):
                                files_with_sample = [name for name, samples in sample_sets.items() if sample in samples]
                                st.markdown(f"- `{sample}` appears in: **{', '.join(files_with_sample)}**")
                        st.error("⚠️ **This will cause duplicate rows in merged data!** Consider switching to Feature merge.")
                else:
                    st.success("✅ No duplicate sample names across files - all samples are unique!")
                
                # Show per-file sample counts
                with st.expander("📊 View sample counts per file"):
                    for name, samples in sample_sets.items():
                        st.markdown(f"- **{name}**: {len(samples)} samples")
            
            st.divider()
            
            # Validation 2: Column consistency (case-insensitive)
            st.markdown("#### 📊 Column Consistency Check (Case-Insensitive)")
            
            if not analysis["identical_structure"]:
                st.warning("⚠️ **Files have different column structures**")
                
                # Find columns with partial presence
                col_presence_ci = {}
                for col_lower in analysis["all_columns_ci"]:
                    files_with_col = []
                    for name, df in standardized_dfs.items():
                        if any(c.lower() == col_lower for c in df.columns):
                            files_with_col.append(name)
                    col_presence_ci[col_lower] = files_with_col
                
                partial_columns = {col: files for col, files in col_presence_ci.items() 
                                 if len(files) < len(standardized_dfs) and len(files) > 0}
                
                if partial_columns:
                    st.error(f"❌ **{len(partial_columns)} columns are only in some files:**")
                    
                    with st.expander(f"View {len(partial_columns)} partially present columns"):
                        for col_lower, files in sorted(partial_columns.items()):
                            missing_files = set(standardized_dfs.keys()) - set(files)
                            st.markdown(f"**`{col_lower}`**")
                            st.markdown(f"  - ✅ Present in: {', '.join(files)}")
                            st.markdown(f"  - ❌ Missing from: {', '.join(missing_files)}")
                            st.markdown("")
                
                # Check for case mismatches
                if analysis["case_mismatches"]:
                    st.warning(f"⚠️ **Found {len(analysis['case_mismatches'])} columns with different casing across files:**")
                    with st.expander("View case mismatches (will be standardized in merge)"):
                        for col_lower, casings in sorted(analysis["case_mismatches"].items()):
                            st.markdown(f"**Lowercase: `{col_lower}`**")
                            for casing, files in casings.items():
                                st.markdown(f"  - `{casing}` in: {', '.join(files)}")
                    st.info("💡 These will be standardized to first file's casing during merge")
                
            else:
                st.success("✅ **Perfect match!** All files have identical column structure (case-insensitive)")
                st.info(f"All {len(analysis['common_columns_ci'])} columns are consistent across {len(standardized_dfs)} files")
            
            st.divider()
            
            # Validation 3: Data quality checks
            st.markdown("#### 🔬 Data Quality Checks")
            
            quality_issues = []
            
            for name, df in standardized_dfs.items():
                # Check for empty dataframes
                if len(df) == 0:
                    quality_issues.append(f"**{name}**: Empty dataframe (0 rows)")
                
                # Check for excessive NaN values
                if 'sample_name' in df.columns:
                    nan_count = df['sample_name'].isna().sum()
                    if nan_count > 0:
                        quality_issues.append(f"**{name}**: {nan_count} rows with missing sample names")
                
                # Check for very small files (< 5 samples)
                if 'sample_name' in df.columns:
                    unique_samples = df['sample_name'].nunique()
                    if unique_samples < 5:
                        quality_issues.append(f"**{name}**: Only {unique_samples} unique samples (possibly incomplete file)")
            
            if quality_issues:
                st.warning(f"⚠️ **Found {len(quality_issues)} potential quality issues:**")
                for issue in quality_issues:
                    st.markdown(f"- {issue}")
            else:
                st.success("✅ All files passed quality checks!")
            
            st.divider()
            st.info("💡 **All intra-day validation complete!** Review any warnings above before proceeding with merge.")
        
        # Step 4: Clean sample names
        if cleaning_method != 'none':
            st.subheader("🧹 Cleaning Sample Names")
            cleaned_dfs = {}
            for name, df in standardized_dfs.items():
                st.markdown(f"**Cleaning {name}:**")
                cleaned_dfs[name] = self.clean_sample_names(
                    df,
                    method=cleaning_method,
                    separator=separator,
                    skip_parts=skip_parts,
                    regex_pattern=regex_pattern
                )
        else:
            cleaned_dfs = standardized_dfs
        
        # Step 5: Remove FCS extensions
        st.subheader("✂️ Removing File Extensions")
        for name in cleaned_dfs:
            cleaned_dfs[name] = self.remove_fcs_extensions(cleaned_dfs[name])

        summary["per_file_pre_merge_shapes"] = {name: df.shape for name, df in cleaned_dfs.items()}

        # Step 6: Resolve merge strategy and merge
        st.subheader("🔗 Merging Files")

        if len(cleaned_dfs) <= 1:
            resolved_merge_type = 'row'
            resolved_groups = None
        elif merge_type == 'manual':
            resolved_merge_type = 'manual'
            resolved_groups = file_groups  # caller-supplied
        elif merge_type == 'auto':
            detected_groups = self.detect_merge_groups(cleaned_dfs)
            n_distinct = len(set(detected_groups.values()))
            files_per_group = {}
            for fname, gid in detected_groups.items():
                files_per_group.setdefault(gid, []).append(fname)
            feature_groups = [g for g, fs in files_per_group.items() if len(fs) > 1]

            if n_distinct == 1 and feature_groups:
                # All files share samples → pure feature merge
                resolved_merge_type = 'feature'
                resolved_groups = None
                st.info("🔍 Auto-detected: **Feature merge** (all files share samples)")
            elif not feature_groups:
                # No file shares samples with any other → pure row merge
                resolved_merge_type = 'row'
                resolved_groups = None
                st.info("🔍 Auto-detected: **Row merge** (all samples are unique across files)")
            else:
                # Mixed
                resolved_merge_type = 'mixed'
                resolved_groups = detected_groups
                st.info(
                    f"🔍 Auto-detected: **Mixed merge** — "
                    f"{len(feature_groups)} feature-merge group(s) + "
                    f"{n_distinct - len(feature_groups)} row-only file(s)"
                )
                with st.expander("🗂️ View detected groups"):
                    for gid in sorted(files_per_group):
                        strategy = "feature merge" if len(files_per_group[gid]) > 1 else "pass-through"
                        st.markdown(f"**Group {gid}** ({strategy}):")
                        for f in files_per_group[gid]:
                            st.markdown(f"  - `{f}`")
        else:
            # Explicit 'row' or 'feature'
            resolved_merge_type = merge_type
            resolved_groups = None

        summary["merge_type_used"] = resolved_merge_type

        if resolved_merge_type == 'mixed' or (resolved_merge_type == 'manual' and resolved_groups):
            merged_df = self.merge_files_mixed(
                cleaned_dfs,
                file_groups=resolved_groups,
                canonical_map=canonical_map,
            )
        else:
            merged_df = self.merge_files(
                cleaned_dfs,
                remove_donor_source=True,
                canonical_map=canonical_map,
                merge_type=resolved_merge_type if resolved_merge_type in ('row', 'feature') else 'row',
            )
        
        summary["merged_shape"] = merged_df.shape

        # Step 7: Remove FMO samples
        if remove_fmo:
            st.subheader("🗑️ Removing FMO Samples")
            before_fmo = len(merged_df)
            merged_df = self.remove_fmo_samples(merged_df)
            summary["fmo_removed"] = before_fmo - len(merged_df)
        
        summary["final_rows"] = len(merged_df)
        summary["final_cols"] = merged_df.shape[1]
        
        # Step 8: Validate against metadata (if provided)
        if metadata_df is not None:
            st.subheader("✅ Validating Against Metadata")
            validation = self.validate_against_metadata(merged_df, metadata_df)
            summary["validation"] = validation
            
            if validation["valid"]:
                st.success(f"✅ All {len(validation['matching_samples'])} samples match metadata!")
            else:
                st.warning("⚠️ Sample name mismatches detected")
                
                if validation["in_flow_not_metadata"]:
                    st.error(f"❌ {len(validation['in_flow_not_metadata'])} samples in flow data but not in metadata:")
                    with st.expander("View mismatched samples"):
                        for sample in sorted(validation["in_flow_not_metadata"]):
                            st.code(sample, language=None)
                    st.info("💡 Try adjusting the cleaning settings to match your metadata format")
        
        return merged_df, summary
