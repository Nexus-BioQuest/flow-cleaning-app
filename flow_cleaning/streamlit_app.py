#!/usr/bin/env python3
"""
Precision Count File Generator - Enhanced Version with Optional Precision Counts
Upload raw or cleaned flow cytometry data and automatically generate precision count files

NEW in v5.2:
- Optional precision count data for Day 0 and/or Day 7
- Automatic removal of Mean and SD summary rows
- Intra-day validation results displayed in Day 0 and Day 7 tabs
- Validation warnings before proceeding to next step
- Visual indicators for data quality issues
- Dynamic master file generation based on available data
"""

import re
import zipfile
import streamlit as st
import pandas as pd
import io
from typing import Optional, List

# Import custom modules
from flow_cleaning.data_processing import FlowDataCleaner
from flow_cleaning.validation import DataValidator
from flow_cleaning.gate_mapping import generate_gate_mapping
from flow_cleaning.master_export import build_master_workbook
from flow_cleaning.precision_counts import (PrecisionCountSettings, create_precision_count_table,
                              concentration_per_microlitre, detect_bead_count_column,
                              filter_summary_rows)
from flow_cleaning.ui.metadata_tab import render as render_metadata_tab


def _parse_gating_name(gating_name: str) -> tuple[list[str], str]:
    """Split a gating name into path segments and metric."""
    name = str(gating_name)
    if '|' in name:
        parts = [part.strip() for part in name.split('|', 1)]
        gate_path = parts[0]
        metric = parts[1] if len(parts) > 1 else 'Count'
    else:
        gate_path = name
        metric = 'Count'

    segments = [segment.strip() for segment in gate_path.split('/') if segment.strip()]
    return segments, metric


def _build_name_mapping_tree_df(name_mapping_df: pd.DataFrame) -> pd.DataFrame:
    """Build a worksheet-friendly tree representation of gate paths."""
    rows = []
    max_depth = 0

    for _, row in name_mapping_df.iterrows():
        gating_name = row.get('gating_name', '')
        metric = row.get('metric', '')
        if not metric or pd.isna(metric):
            _, metric = _parse_gating_name(gating_name)

        segments, metric = _parse_gating_name(gating_name)
        max_depth = max(max_depth, len(segments))

        row_data = {f'Level {i+1}': segments[i] if i < len(segments) else '' for i in range(max_depth)}
        row_data.update({
            'Metric': metric,
            'Gating Name': gating_name,
            'Plot Name': row.get('plot_name', ''),
            'Subset': row.get('subset', ''),
            'Cell Lineage': row.get('cell_lineage', ''),
            'Cell Subset': row.get('cell_subset', ''),
            'For Graphing': row.get('for_graphing', True),
        })
        rows.append(row_data)

    if not rows:
        return pd.DataFrame()

    # Normalize columns so all rows contain all levels
    columns = [f'Level {i+1}' for i in range(max_depth)] + [
        'Metric', 'Gating Name', 'Plot Name', 'Subset', 'Cell Lineage', 'Cell Subset', 'For Graphing'
    ]
    return pd.DataFrame(rows, columns=columns)


def _normalize_lineage_label(lineage: str) -> str:
    """Normalize major lineage labels for sheet names."""
    if not lineage:
        return 'Unknown'
    label = str(lineage).strip().lower()
    if 'b cell' in label or label == 'b' or label == 'b cells':
        return 'B Cells'
    if 't cell' in label or label == 't' or label == 't cells':
        return 'T Cells'
    if 'nk' in label:
        return 'NK'
    if 'myeloid' in label:
        return 'Myeloid'
    if 'unknown' in label or not label:
        return 'Unknown'
    return str(lineage).strip()


def _normalize_sheet_name(name: str) -> str:
    """Generate a valid Excel worksheet name from a lineage label."""
    if not name:
        return 'Unknown'
    clean = re.sub(r'[^A-Za-z0-9 ]+', '', str(name)).strip()
    if not clean:
        return 'Unknown'
    return clean[:31]


def _group_gate_names_by_lineage(name_mapping_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Group gate names by major cell lineage for export tabs."""
    if 'cell_lineage' not in name_mapping_df.columns:
        name_mapping_df = name_mapping_df.copy()
        name_mapping_df['cell_lineage'] = 'Unknown'

    lineage_groups: dict[str, pd.DataFrame] = {}
    for lineage, group in name_mapping_df.fillna({'cell_lineage': 'Unknown'}).groupby('cell_lineage', sort=False):
        lineage_name = _normalize_lineage_label(str(lineage).strip())
        if lineage_name not in lineage_groups:
            lineage_groups[lineage_name] = group.copy()
        else:
            lineage_groups[lineage_name] = pd.concat([lineage_groups[lineage_name], group.copy()], ignore_index=True)

    return {k: v for k, v in lineage_groups.items() if not v.empty}


def _write_lineage_tabs_with_tree(writer: pd.ExcelWriter, gate_names_df: pd.DataFrame) -> None:
    """Write one worksheet per major lineage containing only a rendered tree image."""
    from openpyxl.drawing.image import Image

    lineage_groups = _group_gate_names_by_lineage(gate_names_df)
    used_sheet_names = set()

    for lineage, lineage_df in lineage_groups.items():
        sheet_name = _normalize_sheet_name(lineage)
        original_sheet_name = sheet_name
        suffix = 1
        while sheet_name in used_sheet_names:
            suffix += 1
            sheet_name = f"{original_sheet_name}_{suffix}"
        used_sheet_names.add(sheet_name)

        # Create a blank sheet for the lineage image
        worksheet = writer.book.create_sheet(title=sheet_name)
        writer.sheets[sheet_name] = worksheet

        tree_lines = _build_tree_text(lineage_df)
        if not tree_lines:
            continue

        try:
            image_bytes = _build_tree_image(tree_lines)
            img = Image(io.BytesIO(image_bytes))
            worksheet.add_image(img, "A1")
        except Exception:
            pass


def _build_tree_text(name_mapping_df: pd.DataFrame, max_lines: int | None = 200) -> list[str]:
    """Build a text-based tree from the gating_name and metric columns."""
    tree: dict = {}

    for _, row in name_mapping_df.iterrows():
        gating_name = row.get('gating_name', '')
        segments, metric = _parse_gating_name(gating_name)
        current = tree
        for segment in segments:
            current = current.setdefault(segment, {})
        leaf_label = f"[{metric}]"
        current.setdefault(leaf_label, {})

    lines: list[str] = []

    def walk(node: dict, prefix: str = '') -> None:
        items = sorted(node.items())
        for index, (label, subtree) in enumerate(items):
            connector = '└─ ' if index == len(items) - 1 else '├─ '
            lines.append(f"{prefix}{connector}{label}")
            if subtree:
                extension = '   ' if index == len(items) - 1 else '│  '
                walk(subtree, prefix + extension)

    walk(tree)
    if max_lines is None:
        return lines
    if len(lines) > max_lines:
        return lines[:max_lines] + [f"... ({len(lines) - max_lines} more lines truncated)"]
    return lines


def _build_tree_image(tree_lines: list[str]) -> bytes:
    """Render the tree lines into a PNG image."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        raise

    height = max(4, min(20, len(tree_lines) * 0.25))
    fig, ax = plt.subplots(figsize=(10, height))
    ax.axis('off')

    y = 1.0
    step = 1.0 / max(len(tree_lines), 20)
    for line in tree_lines:
        ax.text(0.01, y, line, fontfamily='monospace', fontsize=8, va='top')
        y -= step

    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _filter_tree_for_lineage(name_mapping_df: pd.DataFrame, lineage: str) -> pd.DataFrame:
    """Return the subset of gate names belonging to a major lineage."""
    if 'cell_lineage' not in name_mapping_df.columns:
        return pd.DataFrame()

    normalized = _normalize_lineage_label(str(lineage).strip())
    subset_df = name_mapping_df[name_mapping_df['cell_lineage'].fillna('Unknown').apply(
        lambda x: _normalize_lineage_label(str(x).strip()) == normalized
    )]
    return subset_df


def _lineage_pngs_zip(name_mapping_df: pd.DataFrame, lineages: list[str]) -> bytes:
    """Build a ZIP package containing PNGs for requested major lineages."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for lineage in lineages:
            subset_df = _filter_tree_for_lineage(name_mapping_df, lineage)
            if subset_df.empty:
                continue
            tree_lines = _build_tree_text(subset_df)
            if not tree_lines:
                continue
            png_bytes = _build_tree_image(tree_lines)
            zf.writestr(f"{_normalize_sheet_name(lineage)}.png", png_bytes)

    buf.seek(0)
    return buf.getvalue()


def _lineage_texts_zip(name_mapping_df: pd.DataFrame, lineages: list[str]) -> bytes:
    """Build a ZIP package containing text trees for requested major lineages."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for lineage in lineages:
            subset_df = _filter_tree_for_lineage(name_mapping_df, lineage)
            if subset_df.empty:
                continue
            tree_lines = _build_tree_text(subset_df, max_lines=None)
            if not tree_lines:
                continue
            text_blob = "\n".join(tree_lines)
            zf.writestr(f"{_normalize_sheet_name(lineage)}.txt", text_blob)

    buf.seek(0)
    return buf.getvalue()


def _full_tree_text(name_mapping_df: pd.DataFrame) -> str:
    """Build the full, untruncated text tree for the entire gate mapping."""
    return "\n".join(_build_tree_text(name_mapping_df, max_lines=None))

# Gate generation is local and rule-based; importing gate_mapping above verifies
# that its required rule tables are available.
GATE_NAMER_AVAILABLE = True

# Page configuration
st.set_page_config(
    page_title="Flow Cytometry Data Preparation",
    page_icon="◼",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    :root {
        color-scheme: light dark;
        --app-bg: #ffffff;
        --surface: #f8fafc;
        --surface-raised: #ffffff;
        --ink: #172033;
        --muted: #667085;
        --line: #e4e7ec;
        --accent: #315b8a;
    }
    @media (prefers-color-scheme: dark) {
        :root {
            --app-bg: #0e1117;
            --surface: #151a23;
            --surface-raised: #1b2230;
            --ink: #f2f4f7;
            --muted: #aeb7c6;
            --line: #30394a;
            --accent: #78a9df;
        }
    }
    .stApp { background: var(--app-bg); color: var(--ink); }
    .block-container { max-width: 1320px; padding-top: 2.5rem; padding-bottom: 4rem; }
    h1, h2, h3 { color: var(--ink); letter-spacing: -0.025em; }
    h1 { font-size: 2.15rem !important; font-weight: 650 !important; }
    h2 { font-size: 1.45rem !important; font-weight: 620 !important; margin-top: 1.25rem !important; }
    h3 { font-size: 1.1rem !important; font-weight: 620 !important; }
    [data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--line); }
    [data-testid="stSidebar"] h1 { font-size: 1.2rem !important; }
    [data-testid="stMetric"] { background:var(--surface-raised); border:1px solid var(--line); border-radius:8px; padding:1rem; }
    [data-testid="stMetricLabel"], [data-testid="stCaptionContainer"] { color:var(--muted); }
    .stTabs [data-baseweb="tab-list"] { gap:1.5rem; border-bottom:1px solid var(--line); }
    .stTabs [data-baseweb="tab"] { padding:.75rem .1rem; font-weight:550; color:var(--muted); }
    .stTabs [aria-selected="true"] { color:var(--accent) !important; }
    .stButton > button, .stDownloadButton > button { border-radius:7px; font-weight:600; }
    .stAlert { border-radius:7px; border-width:1px; }
    hr { border-color:var(--line) !important; }
    code, pre { color:var(--ink) !important; }
</style>
""", unsafe_allow_html=True)

# Initialize session state
def init_session_state():
    """Initialize all session state variables."""
    defaults = {
        # Metadata
        'metadata_df': None,
        'metadata_uploaded': False,
        
        # Day 0 data
        'day_0_raw_files': [],
        'day_0_df': None,
        'day_0_processed': None,
        'day_0_cleaning_summary': None,
        'day_0_validation_results': None,  
        
        # Day 7 data
        'day_7_raw_files': [],
        'day_7_df': None,
        'day_7_processed': None,
        'day_7_cleaning_summary': None,
        'day_7_validation_results': None, 
        
        # Gate names
        'gate_names_df': None,
        
        # Validation
        'validation_results': {},
        
        # Settings
        'defaults_set': False,
        'canonical_column_map': None,
        'workflow_stage': 'metadata',  # metadata -> day_0 -> day_7 -> validation -> export
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# Sidebar - Global Settings
st.sidebar.title("Run settings")

# Workflow progress
st.sidebar.header("Workflow progress")
stages = ['Metadata', 'Day 0', 'Day 7', 'Validation', 'Export']
stage_mapping = {
    'metadata': 0,
    'day_0': 1,
    'day_7': 2,
    'validation': 3,
    'export': 4
}
current_stage = stage_mapping.get(st.session_state.workflow_stage, 0)

for i, stage in enumerate(stages):
    if i < current_stage:
        st.sidebar.success(f"Complete · {stage}")
    elif i == current_stage:
        st.sidebar.info(f"Current · {stage}")
    else:
        st.sidebar.text(f"Pending · {stage}")

st.sidebar.divider()

# Default values
st.sidebar.header("Precision count defaults")
st.sidebar.caption("Applied to all samples unless overridden.")
defaults_locked = st.session_state.defaults_set

default_bead_conc = st.sidebar.number_input(
    "Bead concentration (per mL)",
    min_value=0.0,
    value=1.00e6,
    format="%.2e",
    help="Default: 1.00E+06",
    disabled=defaults_locked,
)

default_beads_per_ul = concentration_per_microlitre(default_bead_conc)
st.sidebar.metric("Calculated beads per µL", f"{default_beads_per_ul:,.2f}")
st.sidebar.caption("Calculated as concentration per mL ÷ 1,000.")

default_bead_vol = st.sidebar.number_input(
    "Bead Volume (µL)",
    value=50,
    step=5,
    help="Default: 50 µL",
    disabled=defaults_locked,
)

default_cell_vol = st.sidebar.number_input(
    "Cell Volume (µL)",
    value=150,
    step=10,
    help="Default: 150 µL",
    disabled=defaults_locked,
)

if not defaults_locked:
    if st.sidebar.button("Lock defaults", type="primary"):
        st.session_state.defaults_set = True
        st.rerun()
else:
    st.sidebar.success("Defaults locked")
    if st.sidebar.button("Unlock defaults"):
        st.session_state.defaults_set = False
        st.rerun()

# Main content
st.title("Flow Cytometry Data Preparation")
st.markdown("""
Prepare FlowJo exports for downstream quality control and analysis. Upload the
study metadata, process Day 0 and Day 7 files, review the gate mapping and
validation results, then export a single analysis-ready workbook.
""")

# Create tabs for workflow stages
tab_metadata, tab_day0, tab_day7, tab_gates, tab_validation, tab_export = st.tabs([
    "01  Metadata",
    "02  Day 0", 
    "03  Day 7",
    "04  Gate mapping",
    "05  Validation",
    "06  Export"
])

def render_merge_qc_summary(summary: dict, label: str):
    """
    Render a QC panel showing per-file shapes and before/after merge comparison.

    Args:
        summary: Dict returned by FlowDataCleaner.process_files()
        label: "Day 0" or "Day 7" used in headings
    """
    merge_type = summary.get("merge_type_used", "row") or "row"
    per_file_input   = summary.get("per_file_input_shapes", {})
    per_file_cleaned = summary.get("per_file_pre_merge_shapes", {})
    merged_shape     = summary.get("merged_shape")       # (rows, cols) right after merge
    final_rows       = summary.get("final_rows", 0)
    final_cols       = summary.get("final_cols", 0)
    fmo_removed      = summary.get("fmo_removed", 0)
    mean_sd_removed  = summary.get("mean_sd_removed", 0)

    # ── top-line metrics ────────────────────────────────────────────────────
    total_input_rows = sum(r for r, _ in per_file_input.values()) if per_file_input else summary.get("original_rows", 0)
    total_input_cols = max((c for _, c in per_file_input.values()), default=0) if per_file_input else 0
    merged_rows = merged_shape[0] if merged_shape else final_rows
    merged_cols = merged_shape[1] if merged_shape else final_cols

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Files Loaded", summary.get("files_loaded", 0))
    c2.metric("Input Rows (total)", total_input_rows)
    c3.metric("After Merge", f"{merged_rows} × {merged_cols}",
              delta=f"+{merged_cols - total_input_cols} cols" if merge_type in ("feature", "mixed", "manual") else None)
    c4.metric("Final Rows", final_rows,
              delta=f"-{merged_rows - final_rows}" if merged_rows > final_rows else None,
              delta_color="inverse")
    c5.metric("Merge Type", merge_type)

    # ── detailed breakdown (collapsible) ────────────────────────────────────
    with st.expander(f"📊 {label} Merge QC — per-file detail"):

        # Input files table
        if per_file_input:
            st.markdown("**Input files (at load time):**")
            rows_data = []
            for fname, (r, c) in per_file_input.items():
                cleaned_shape = per_file_cleaned.get(fname)
                rows_data.append({
                    "File": fname,
                    "Rows (raw)": r,
                    "Cols (raw)": c,
                    "Rows (pre-merge)": cleaned_shape[0] if cleaned_shape else "—",
                    "Cols (pre-merge)": cleaned_shape[1] if cleaned_shape else "—",
                    "Rows removed": r - cleaned_shape[0] if cleaned_shape else "—",
                })
            st.dataframe(rows_data, use_container_width=True, hide_index=True)

        st.markdown("---")

        # Merge summary arrow
        if len(per_file_input) > 1:
            parts = [f"{r}r × {c}c" for _, (r, c) in per_file_cleaned.items()] if per_file_cleaned else []
            arrow = " + " if merge_type in ("row", "mixed") else " ⟕ "
            merge_label = {
                "row": "↕️ Row merge (concat)",
                "feature": "↔️ Feature merge (join on sample_name)",
                "mixed": "🔀 Mixed merge",
                "manual": "⚙️ Manual groups merge",
            }.get(merge_type, merge_type)
            st.markdown(f"**{merge_label}**")
            if parts:
                st.markdown(f"`{arrow.join(parts)}` → `{merged_rows}r × {merged_cols}c`")

        # After-merge vs final
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**After merge:**")
            st.metric("Rows", merged_rows)
            st.metric("Columns", merged_cols)
        with col2:
            st.markdown("**After cleanup (FMO / Mean-SD):**")
            st.metric("Rows", final_rows,
                      delta=f"-{merged_rows - final_rows}" if merged_rows > final_rows else "no change",
                      delta_color="inverse" if merged_rows > final_rows else "off")
            st.metric("Columns", final_cols)

        if fmo_removed or mean_sd_removed:
            st.caption(
                f"Removed: {fmo_removed} FMO row(s)"
                + (f", {mean_sd_removed} Mean/SD row(s)" if mean_sd_removed else "")
            )


def display_intra_day_validation_summary(validation_results: dict, day_label: str):
    """
    Display a summary card of intra-day validation results.
    
    Args:
        validation_results: Dict containing validation results from cleaning process
        day_label: "Day 0" or "Day 7"
    """
    if not validation_results:
        return
    
    # Determine overall status
    has_errors = False
    has_warnings = False
    
    # Check for various issues
    if validation_results.get('duplicate_samples'):
        has_errors = True
    if validation_results.get('partial_columns'):
        has_warnings = True
    if validation_results.get('case_mismatches'):
        has_warnings = True
    if validation_results.get('quality_issues'):
        has_warnings = True
    
    # Display status card
    if has_errors:
        st.error(f"❌ **{day_label} Intra-Day Validation: ERRORS FOUND**")
    elif has_warnings:
        st.warning(f"⚠️ **{day_label} Intra-Day Validation: Warnings**")
    else:
        st.success(f"✅ **{day_label} Intra-Day Validation: All Clear**")
    
    # Create expandable section with details
    with st.expander(f"🔍 View {day_label} Validation Details"):
        
        # Sample duplicates
        if validation_results.get('duplicate_samples'):
            st.error(f"**❌ Found {len(validation_results['duplicate_samples'])} duplicate samples across files:**")
            for sample, files in list(validation_results['duplicate_samples'].items())[:10]:
                st.markdown(f"- `{sample}` appears in: **{', '.join(files)}**")
            if len(validation_results['duplicate_samples']) > 10:
                st.markdown(f"... and {len(validation_results['duplicate_samples']) - 10} more duplicates")
        else:
            st.success("✅ No duplicate sample names across files")
        
        st.divider()
        
        # Column consistency
        if validation_results.get('partial_columns'):
            st.warning(f"**⚠️ {len(validation_results['partial_columns'])} columns not in all files:**")
            for col, files in list(validation_results['partial_columns'].items())[:5]:
                st.markdown(f"- `{col}` only in: {', '.join(files)}")
            if len(validation_results['partial_columns']) > 5:
                st.markdown(f"... and {len(validation_results['partial_columns']) - 5} more")
        else:
            st.success("✅ All columns present in all files")
        
        st.divider()
        
        # Case mismatches
        if validation_results.get('case_mismatches'):
            st.warning(f"**⚠️ {len(validation_results['case_mismatches'])} columns with case differences:**")
            for col_lower, casings in list(validation_results['case_mismatches'].items())[:5]:
                st.markdown(f"**`{col_lower}`**: {', '.join([f'`{c}`' for c in casings.keys()])}")
        else:
            st.success("✅ No case mismatches in column names")
        
        st.divider()
        
        # Quality issues
        if validation_results.get('quality_issues'):
            st.warning(f"**⚠️ {len(validation_results['quality_issues'])} data quality issues:**")
            for issue in validation_results['quality_issues']:
                st.markdown(f"- {issue}")
        else:
            st.success("✅ All files passed quality checks")
        
        st.divider()
        
        # Summary metrics
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Files Merged", validation_results.get('file_count', 0))
        with col2:
            st.metric("Total Samples", validation_results.get('total_samples', 0))
        with col3:
            st.metric("Unique Samples", validation_results.get('unique_samples', 0))


# TAB 1: METADATA
with tab_metadata:
    render_metadata_tab()


# TAB 2: DAY 0 DATA
with tab_day0:
    st.header("Day 0 data")
    
    if not st.session_state.metadata_uploaded:
        st.warning("⚠️ Please upload metadata first (Tab 1)")
    else:
        st.markdown("""
        Upload your Day 0 flow cytometry files. You can upload:
        - Single cleaned file, or
        - Multiple raw files (will be merged and cleaned automatically)
        """)
        
        # Multi-file uploader
        uploaded_day_0_files = st.file_uploader(
            "Upload Day 0 file(s)",
            type=['xlsx', 'xls', 'csv'],
            accept_multiple_files=True,
            key="day_0_files_upload",
            help="Upload one or more files"
        )
        
        if uploaded_day_0_files:
            st.info(f"📁 {len(uploaded_day_0_files)} file(s) selected")
            
            # Show file list
            with st.expander("📋 View selected files"):
                for f in uploaded_day_0_files:
                    st.text(f"- {f.name}")
            
            st.divider()
            
            # Cleaning options (if multiple files or needs cleaning)
            st.subheader("Processing options")
            
            col1, col2 = st.columns(2)
            
            with col1:
                cleaning_method = st.selectbox(
                    "Sample Name Cleaning Method",
                    options=['none', 'donor_asterisk', 'separator', 'regex'],
                    format_func=lambda x: {
                        'none': '❌ No cleaning needed',
                        'donor_asterisk': '⭐ DonorX*_B2_ format (preset)',
                        'separator': '🔪 Split by separator',
                        'regex': '🔧 Custom regex pattern'
                    }[x],
                    help="Select how to clean sample names",
                    key="day_0_cleaning_method"
                )
            
            with col2:
                remove_fmo = st.checkbox(
                    "Remove FMO samples",
                    value=True,
                    help="Remove Fluorescence Minus One controls",
                    key="day_0_remove_fmo"
                )
            
            # Additional cleaning options based on method
            separator = '_'
            skip_parts = 2
            regex_pattern = None
            
            if cleaning_method == 'separator':
                col1, col2 = st.columns(2)
                with col1:
                    separator = st.text_input(
                        "Separator character",
                        value='_',
                        help="Character to split sample names by",
                        key="day_0_separator"
                    )
                with col2:
                    skip_parts = st.number_input(
                        "Parts to skip from start",
                        value=2,
                        min_value=0,
                        max_value=10,
                        help="Number of separator-delimited parts to remove",
                        key="day_0_skip_parts"
                    )
                
                st.info(f"Example: `Donor1*_B2_Sample1` → `Sample1` (skips first {skip_parts} parts)")
            
            elif cleaning_method == 'regex':
                regex_pattern = st.text_input(
                    "Regex pattern to remove",
                    value=r'^[^_]*\*_[^_]*_',
                    help="Regular expression to remove from start of sample names",
                    key="day_0_regex"
                )
                st.info(f"Pattern: `{regex_pattern}`")
            
            st.divider()

            # Merge type selector (only relevant when multiple files are uploaded)
            if len(uploaded_day_0_files) > 1:
                merge_type_day0 = st.radio(
                    "Merge strategy",
                    options=['auto', 'row', 'feature', 'manual'],
                    format_func=lambda x: {
                        'auto':    '🔍 Auto-detect (recommended)',
                        'row':     '↕️ Row merge — different samples, same features',
                        'feature': '↔️ Feature merge — same samples, different features/markers',
                        'manual':  '⚙️ Manual groups — assign each file to a group',
                    }[x],
                    index=0,
                    key='day_0_merge_type',
                    help=(
                        "Auto: detects groups automatically using sample-name overlap. "
                        "Row: stack all files (new rows). "
                        "Feature: join all files side-by-side on sample_name. "
                        "Manual: assign files to numbered groups; files in the same group "
                        "are feature-merged, then groups are row-merged."
                    ),
                    horizontal=True,
                )

                # Manual group assignment
                file_groups_day0 = None
                if merge_type_day0 == 'manual':
                    st.markdown("**Assign each file to a group number.** Files in the same group are feature-merged; groups are then row-merged.")
                    file_groups_day0 = {}
                    for i, f in enumerate(uploaded_day_0_files):
                        gid = st.number_input(
                            f"`{f.name}`",
                            min_value=1, max_value=len(uploaded_day_0_files),
                            value=i + 1,
                            step=1,
                            key=f"day_0_group_{i}",
                            help="Files with the same group number will be feature-merged (column join).",
                        )
                        file_groups_day0[f.name] = int(gid)
            else:
                merge_type_day0 = 'row'
                file_groups_day0 = None

            st.divider()
            
            # Process button
            if st.button("Process Day 0 files", type="primary", use_container_width=True):
                with st.spinner("Processing Day 0 files..."):
                    # Create cleaner instance
                    cleaner = FlowDataCleaner()
                    
                    # Process files
                    cleaned_df, summary = cleaner.process_files(
                        uploaded_files=uploaded_day_0_files,
                        cleaning_method=cleaning_method,
                        separator=separator,
                        skip_parts=skip_parts,
                        regex_pattern=regex_pattern,
                        remove_fmo=remove_fmo,
                        metadata_df=st.session_state.metadata_df,
                        merge_type=merge_type_day0,
                        file_groups=file_groups_day0,
                    )
                    
                    if cleaned_df is not None:
                        # Filter out Mean and SD rows
                        cleaned_df, removed_mean_sd = filter_summary_rows(cleaned_df)
                        if removed_mean_sd > 0:
                            st.info(f"🧹 Removed {removed_mean_sd} Mean/SD summary rows")
                        
                        # Store removal count in summary
                        summary['mean_sd_removed'] = removed_mean_sd
                        
                        # Ensure sample_name is always the first column
                        if 'sample_name' in cleaned_df.columns:
                            cols = ['sample_name'] + [col for col in cleaned_df.columns if col != 'sample_name']
                            cleaned_df = cleaned_df[cols]
                        
                        st.session_state.day_0_df = cleaned_df
                        # BUILD CANONICAL COLUMN MAP FROM DAY 0
                        if st.session_state.day_0_df is not None:
                            st.session_state.canonical_column_map = cleaner.build_canonical_column_map(
                                st.session_state.day_0_df
                            )
                            st.success(f"✓ Day 0 columns set as canonical reference ({len(st.session_state.canonical_column_map)} columns)")
                        st.session_state.day_0_cleaning_summary = summary
                        
                        # Extract validation results from summary if multiple files were processed
                        if len(uploaded_day_0_files) > 1 and 'structure_analysis' in summary:
                            analysis = summary['structure_analysis']
                            
                            # Build validation results dict
                            validation_results = {
                                'file_count': analysis['file_count'],
                                'total_samples': summary['final_rows'],
                                'unique_samples': cleaned_df['sample_name'].nunique() if 'sample_name' in cleaned_df.columns else 0,
                                'duplicate_samples': {},
                                'partial_columns': {},
                                'case_mismatches': {},
                                'quality_issues': []
                            }
                            
                            # Extract duplicate samples (from structure analysis if available)
                            # Note: This requires the cleaner to pass this info back, which we'll need to add
                            # For now, we'll recalculate here
                            if 'sample_name' in cleaned_df.columns:
                                # Count how many times each sample appears
                                sample_counts = cleaned_df['sample_name'].value_counts()
                                duplicates = sample_counts[sample_counts > 1]
                                if len(duplicates) > 0:
                                    validation_results['duplicate_samples'] = {
                                        sample: ['merged_file'] for sample in duplicates.index
                                    }
                            
                            # Extract partial columns
                            if not analysis['identical_structure']:
                                validation_results['partial_columns'] = {
                                    col: list(files) for col, files in 
                                    analysis.get('unique_columns_per_file', {}).items()
                                    if files
                                }
                            
                            st.session_state.day_0_validation_results = validation_results
                        
                        st.session_state.workflow_stage = 'day_7'
                        
                        st.success("✅ Day 0 data processed successfully!")
                        st.balloons()
                        st.rerun()
            
            # Show processed data if available
            if st.session_state.day_0_df is not None:
                st.divider()
                st.subheader("✅ Processed Day 0 Data")
                
                # Display intra-day validation results if available
                if st.session_state.day_0_validation_results and len(uploaded_day_0_files) > 1:
                    display_intra_day_validation_summary(
                        st.session_state.day_0_validation_results,
                        "Day 0"
                    )
                    st.divider()
                
                # QC summary
                summary = st.session_state.day_0_cleaning_summary
                render_merge_qc_summary(summary, "Day 0")
                
                # Preview data
                st.dataframe(st.session_state.day_0_df.head(10), use_container_width=True)
                
                # ====== NEW: OPTIONAL PRECISION COUNT SECTION ======
                st.divider()
                st.subheader("🎯 Precision Count Table (Optional)")
                
                include_day_0_precision = st.checkbox(
                    "Include Day 0 precision count data",
                    value=True,
                    help="Uncheck if precision count beads were not captured for Day 0",
                    key="include_day_0_precision"
                )
                
                if include_day_0_precision:
                    # Detect bead column
                    detected_bead = detect_bead_count_column(st.session_state.day_0_df)
                    
                    if detected_bead:
                        st.info(f"✨ Auto-detected bead count column: `{detected_bead}`")
                    
                    bead_col_0 = st.selectbox(
                        "Select bead count column",
                        options=st.session_state.day_0_df.columns.tolist(),
                        index=st.session_state.day_0_df.columns.tolist().index(detected_bead) if detected_bead else 0,
                        key="day_0_bead_col"
                    )
                    
                    if not st.session_state.defaults_set:
                        st.warning("⚠️ Please lock default values in the sidebar first")
                    else:
                        if st.button("✨ Generate Day 0 Precision Count", type="primary"):
                            precision_df = create_precision_count_table(
                                st.session_state.day_0_df, bead_col_0,
                                PrecisionCountSettings(default_bead_conc, default_beads_per_ul, default_bead_vol, default_cell_vol)
                            )
                            st.session_state.day_0_processed = precision_df
                            st.success("✓ Day 0 precision count generated!")
                            st.rerun()
                    
                    # Show precision count table if generated
                    if st.session_state.day_0_processed is not None:
                        st.subheader("✏️ Edit Day 0 Precision Count")
                        edited_df = st.data_editor(
                            st.session_state.day_0_processed,
                            use_container_width=True,
                            num_rows="dynamic",
                            key="day_0_precision_editor"
                        )
                        st.session_state.day_0_processed = edited_df
                        
                        # Validate
                        validator = DataValidator()
                        validation = validator.validate_precision_counts(edited_df)
                        
                        if validation['warnings']:
                            st.warning("**Precision Count Warnings:**")
                            for warning in validation['warnings']:
                                st.markdown(f"- ⚠️ {warning}")
                else:
                    st.info("ℹ️ Day 0 precision count data will not be included in master file")
                    # Clear any existing precision count data
                    if st.session_state.day_0_processed is not None:
                        if st.button("🗑️ Clear existing Day 0 precision count"):
                            st.session_state.day_0_processed = None
                            st.rerun()


# TAB 3: DAY 7 DATA
with tab_day7:
    st.header("Day 7 data")
    
    if not st.session_state.metadata_uploaded:
        st.warning("⚠️ Please upload metadata first (Tab 1)")
    elif st.session_state.day_0_df is None:
        st.warning("⚠️ Please process Day 0 data first (Tab 2)")
    else:
        st.markdown("""
        Upload your Day 7 flow cytometry files. The same cleaning settings will be suggested
        based on your Day 0 processing.
        """)
        
        # Multi-file uploader
        uploaded_day_7_files = st.file_uploader(
            "Upload Day 7 file(s)",
            type=['xlsx', 'xls', 'csv'],
            accept_multiple_files=True,
            key="day_7_files_upload",
            help="Upload one or more files"
        )
        
        if uploaded_day_7_files:
            st.info(f"📁 {len(uploaded_day_7_files)} file(s) selected")
            
            # Show file list
            with st.expander("📋 View selected files"):
                for f in uploaded_day_7_files:
                    st.text(f"- {f.name}")
            
            st.divider()
            
            # Cleaning options
            st.subheader("Processing options")
            
            # Suggest same settings as Day 0
            default_method = 'none'
            if st.session_state.day_0_cleaning_summary:
                if st.session_state.day_0_cleaning_summary.get('cleaning_applied'):
                    st.info("💡 Using same cleaning settings as Day 0")
            
            col1, col2 = st.columns(2)
            
            with col1:
                cleaning_method = st.selectbox(
                    "Sample Name Cleaning Method",
                    options=['none', 'donor_asterisk', 'separator', 'regex'],
                    format_func=lambda x: {
                        'none': '❌ No cleaning needed',
                        'donor_asterisk': '⭐ DonorX*_B2_ format (preset)',
                        'separator': '🔪 Split by separator',
                        'regex': '🔧 Custom regex pattern'
                    }[x],
                    help="Select how to clean sample names",
                    key="day_7_cleaning_method"
                )
            
            with col2:
                remove_fmo = st.checkbox(
                    "Remove FMO samples",
                    value=True,
                    help="Remove Fluorescence Minus One controls",
                    key="day_7_remove_fmo"
                )
            
            # Additional cleaning options
            separator = '_'
            skip_parts = 2
            regex_pattern = None
            
            if cleaning_method == 'separator':
                col1, col2 = st.columns(2)
                with col1:
                    separator = st.text_input(
                        "Separator character",
                        value='_',
                        key="day_7_separator"
                    )
                with col2:
                    skip_parts = st.number_input(
                        "Parts to skip from start",
                        value=2,
                        min_value=0,
                        max_value=10,
                        key="day_7_skip_parts"
                    )
            
            elif cleaning_method == 'regex':
                regex_pattern = st.text_input(
                    "Regex pattern to remove",
                    value=r'^[^_]*\*_[^_]*_',
                    key="day_7_regex"
                )
            
            st.divider()

            # Merge type selector
            if len(uploaded_day_7_files) > 1:
                merge_type_day7 = st.radio(
                    "Merge strategy",
                    options=['auto', 'row', 'feature', 'manual'],
                    format_func=lambda x: {
                        'auto':    '🔍 Auto-detect (recommended)',
                        'row':     '↕️ Row merge — different samples, same features',
                        'feature': '↔️ Feature merge — same samples, different features/markers',
                        'manual':  '⚙️ Manual groups — assign each file to a group',
                    }[x],
                    index=0,
                    key='day_7_merge_type',
                    help=(
                        "Auto: detects groups automatically using sample-name overlap. "
                        "Row: stack all files (new rows). "
                        "Feature: join all files side-by-side on sample_name. "
                        "Manual: assign files to numbered groups; files in the same group "
                        "are feature-merged, then groups are row-merged."
                    ),
                    horizontal=True,
                )

                # Manual group assignment
                file_groups_day7 = None
                if merge_type_day7 == 'manual':
                    st.markdown("**Assign each file to a group number.** Files in the same group are feature-merged; groups are then row-merged.")
                    file_groups_day7 = {}
                    for i, f in enumerate(uploaded_day_7_files):
                        gid = st.number_input(
                            f"`{f.name}`",
                            min_value=1, max_value=len(uploaded_day_7_files),
                            value=i + 1,
                            step=1,
                            key=f"day_7_group_{i}",
                            help="Files with the same group number will be feature-merged (column join).",
                        )
                        file_groups_day7[f.name] = int(gid)
            else:
                merge_type_day7 = 'row'
                file_groups_day7 = None

            st.divider()
            
            # Process button
            if st.button("Process Day 7 files", type="primary", use_container_width=True):
                with st.spinner("Processing Day 7 files..."):
                    cleaner = FlowDataCleaner()
                    
                    cleaned_df, summary = cleaner.process_files(
                        uploaded_files=uploaded_day_7_files,
                        cleaning_method=cleaning_method,
                        separator=separator,
                        skip_parts=skip_parts,
                        regex_pattern=regex_pattern,
                        remove_fmo=remove_fmo,
                        metadata_df=st.session_state.metadata_df,
                        merge_type=merge_type_day7,
                        file_groups=file_groups_day7,
                    )
                    
                    if cleaned_df is not None:
                        # Filter out Mean and SD rows
                        cleaned_df, removed_mean_sd = filter_summary_rows(cleaned_df)
                        if removed_mean_sd > 0:
                            st.info(f"🧹 Removed {removed_mean_sd} Mean/SD summary rows")
                        
                        # Store removal count in summary
                        summary['mean_sd_removed'] = removed_mean_sd
                        
                        # Ensure sample_name is always the first column
                        if 'sample_name' in cleaned_df.columns:
                            cols = ['sample_name'] + [col for col in cleaned_df.columns if col != 'sample_name']
                            cleaned_df = cleaned_df[cols]
                        
                        st.session_state.day_7_df = cleaned_df
                        # STANDARDIZE DAY 7 TO DAY 0 CASING
                        if st.session_state.get('canonical_column_map') and st.session_state.day_7_df is not None:
                            st.session_state.day_7_df = cleaner.standardize_columns_to_canonical(
                                st.session_state.day_7_df,
                                st.session_state.canonical_column_map
                            )
                            st.success("✓ Day 7 columns standardized to match Day 0 casing")
                        st.session_state.day_7_cleaning_summary = summary
                        
                        # Extract validation results from summary if multiple files
                        if len(uploaded_day_7_files) > 1 and 'structure_analysis' in summary:
                            analysis = summary['structure_analysis']
                            
                            validation_results = {
                                'file_count': analysis['file_count'],
                                'total_samples': summary['final_rows'],
                                'unique_samples': cleaned_df['sample_name'].nunique() if 'sample_name' in cleaned_df.columns else 0,
                                'duplicate_samples': {},
                                'partial_columns': {},
                                'case_mismatches': {},
                                'quality_issues': []
                            }
                            
                            # Recalculate duplicates
                            if 'sample_name' in cleaned_df.columns:
                                sample_counts = cleaned_df['sample_name'].value_counts()
                                duplicates = sample_counts[sample_counts > 1]
                                if len(duplicates) > 0:
                                    validation_results['duplicate_samples'] = {
                                        sample: ['merged_file'] for sample in duplicates.index
                                    }
                            
                            # Extract partial columns
                            if not analysis['identical_structure']:
                                validation_results['partial_columns'] = {
                                    col: list(files) for col, files in 
                                    analysis.get('unique_columns_per_file', {}).items()
                                    if files
                                }
                            
                            st.session_state.day_7_validation_results = validation_results
                        
                        st.session_state.workflow_stage = 'validation'
                        
                        st.success("✅ Day 7 data processed successfully!")
                        st.balloons()
                        st.rerun()
            
            # Show processed data
            if st.session_state.day_7_df is not None:
                st.divider()
                st.subheader("✅ Processed Day 7 Data")
                
                # Display intra-day validation results if available
                if st.session_state.day_7_validation_results and len(uploaded_day_7_files) > 1:
                    display_intra_day_validation_summary(
                        st.session_state.day_7_validation_results,
                        "Day 7"
                    )
                    st.divider()
                
                # QC summary
                summary = st.session_state.day_7_cleaning_summary
                render_merge_qc_summary(summary, "Day 7")
                
                st.dataframe(st.session_state.day_7_df.head(10), use_container_width=True)
                
                # ====== NEW: OPTIONAL PRECISION COUNT SECTION ======
                st.divider()
                st.subheader("🎯 Precision Count Table (Optional)")
                
                include_day_7_precision = st.checkbox(
                    "Include Day 7 precision count data",
                    value=True,
                    help="Uncheck if precision count beads were not captured for Day 7",
                    key="include_day_7_precision"
                )
                
                if include_day_7_precision:
                    detected_bead = detect_bead_count_column(st.session_state.day_7_df)
                    
                    if detected_bead:
                        st.info(f"✨ Auto-detected bead count column: `{detected_bead}`")
                    
                    bead_col_7 = st.selectbox(
                        "Select bead count column",
                        options=st.session_state.day_7_df.columns.tolist(),
                        index=st.session_state.day_7_df.columns.tolist().index(detected_bead) if detected_bead else 0,
                        key="day_7_bead_col"
                    )
                    
                    if not st.session_state.defaults_set:
                        st.warning("⚠️ Please lock default values in the sidebar first")
                    else:
                        if st.button("✨ Generate Day 7 Precision Count", type="primary"):
                            precision_df = create_precision_count_table(
                                st.session_state.day_7_df, bead_col_7,
                                PrecisionCountSettings(default_bead_conc, default_beads_per_ul, default_bead_vol, default_cell_vol)
                            )
                            st.session_state.day_7_processed = precision_df
                            st.success("✓ Day 7 precision count generated!")
                            st.rerun()
                    
                    if st.session_state.day_7_processed is not None:
                        st.subheader("✏️ Edit Day 7 Precision Count")
                        edited_df = st.data_editor(
                            st.session_state.day_7_processed,
                            use_container_width=True,
                            num_rows="dynamic",
                            key="day_7_precision_editor"
                        )
                        st.session_state.day_7_processed = edited_df
                        
                        validator = DataValidator()
                        validation = validator.validate_precision_counts(edited_df)
                        
                        if validation['warnings']:
                            st.warning("**Precision Count Warnings:**")
                            for warning in validation['warnings']:
                                st.markdown(f"- ⚠️ {warning}")
                else:
                    st.info("ℹ️ Day 7 precision count data will not be included in master file")
                    # Clear any existing precision count data
                    if st.session_state.day_7_processed is not None:
                        if st.button("🗑️ Clear existing Day 7 precision count"):
                            st.session_state.day_7_processed = None
                            st.rerun()


# TAB 4: GATE NAMES (keeping same as original)
with tab_gates:
    st.header("Gate mapping")
    st.markdown("""
    Add gate naming information to enable better plotting and analysis downstream.
    """)
    
    # Check prerequisites
    has_day_0 = st.session_state.day_0_df is not None
    has_day_7 = st.session_state.day_7_df is not None
    
    if not has_day_0 or not has_day_7:
        st.info("📋 Process Day 0 and Day 7 data first to auto-generate gate names")
    
    # Option 1: Upload pre-generated
    st.subheader("Upload an existing mapping")
    uploaded_gates = st.file_uploader(
        "Upload gate names file",
        type=['xlsx', 'xls', 'csv'],
        key="gates_upload"
    )
    
    if uploaded_gates:
        try:
            if uploaded_gates.name.endswith('.csv'):
                gates_df = pd.read_csv(uploaded_gates)
            else:
                gates_df = pd.read_excel(uploaded_gates)
            
            st.session_state.gate_names_df = gates_df
            st.success(f"✅ Gate names loaded: {len(gates_df)} entries")
            st.dataframe(gates_df.head(), use_container_width=True)
        except Exception as e:
            st.error(f"❌ Error loading gate names: {str(e)}")
    
    # Option 2: Auto-generate (if modules available)
    if GATE_NAMER_AVAILABLE and has_day_0 and has_day_7:
        st.divider()
        st.subheader("Generate from flow columns")
        st.caption("Uses the project’s fixed naming and classification rules. No external service is used.")
        
        if st.button("Generate gate mapping", type="primary"):
            with st.spinner("Generating gate names from column headers..."):
                try:
                    # Get all unique column names from both files (excluding sample_name)
                    # Use case-insensitive deduplication
                    day_0_cols = set(st.session_state.day_0_df.columns) - {'sample_name'}
                    day_7_cols = set(st.session_state.day_7_df.columns) - {'sample_name'}
                    
                    # Combine and deduplicate by lowercase
                    all_columns_lower = {}
                    for col in day_0_cols:
                        all_columns_lower[col.lower()] = col
                    for col in day_7_cols:
                        if col.lower() not in all_columns_lower:
                            all_columns_lower[col.lower()] = col
                    
                    all_columns = sorted(all_columns_lower.values())
                    
                    if not all_columns:
                        st.error("❌ No columns found to generate gate names from")
                    else:
                        st.info(f"📊 Processing {len(all_columns)} unique columns (case-insensitive)")
                        
                        gate_names_mapping = generate_gate_mapping(
                            st.session_state.day_0_df,
                            st.session_state.day_7_df,
                        )
                        
                        # Get statistics for user feedback
                        total_combos = len(gate_names_mapping)
                        unique_names = gate_names_mapping['plot_name'].nunique()
                        duplicates_removed = total_combos - unique_names
                        
                        st.session_state.gate_names_df = gate_names_mapping
                        
                        # Show success with deduplication info
                        st.success(f"✅ Generated {unique_names} unique plot names from {total_combos} gate/metric combinations!")
                        
                        if duplicates_removed > 0:
                            st.info(f"📊 Deduplicated {duplicates_removed} case-variant duplicates (e.g., 'Tconv' vs 'tconv' vs 'TCONV')")
                        
                        # Show quick stats
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Original Combinations", total_combos)
                        with col2:
                            st.metric("Unique Plot Names", unique_names)
                        with col3:
                            reduction_pct = int((duplicates_removed / total_combos * 100)) if total_combos > 0 else 0
                            st.metric("Reduction", f"{reduction_pct}%", delta=f"-{duplicates_removed}")
                        
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"❌ Error generating gate names: {str(e)}")
                    import traceback
                    with st.expander("🔍 View error details"):
                        st.code(traceback.format_exc())
                    st.info("💡 You can still upload a pre-generated gate names file instead")
    
    # Show gate names preview if available
    if st.session_state.gate_names_df is not None:
        st.divider()
        st.subheader("Review and edit mapping")
        
        gate_df = st.session_state.gate_names_df
        
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Gates", len(gate_df))
        with col2:
            if 'for_graphing' in gate_df.columns:
                st.metric("For Graphing", gate_df['for_graphing'].sum())
        with col3:
            if 'subset' in gate_df.columns:
                st.metric("Count Metrics", len(gate_df[gate_df['subset'] == 'Count']))
        with col4:
            if 'subset' in gate_df.columns:
                st.metric("Freq Metrics", len(gate_df[gate_df['subset'] == 'Freq']))
        
        # Show info about columns
        st.info(f"**Columns:** {', '.join(gate_df.columns.tolist())} | ✏️ Click cells to edit, toggle checkboxes in 'for_graphing' column")
        
        # Use data_editor with checkbox column configuration
        column_config = {}
        if 'for_graphing' in gate_df.columns:
            column_config['for_graphing'] = st.column_config.CheckboxColumn(
                "For Graphing",
                help="Include in graphs?",
                default=True
            )
        
        edited_gate_df = st.data_editor(
            gate_df,
            use_container_width=True,
            height=400,
            num_rows="dynamic",
            column_config=column_config,
            key="gate_names_editor"
        )
        
        # Update session state with edited data
        if not edited_gate_df.equals(st.session_state.gate_names_df):
            st.session_state.gate_names_df = edited_gate_df
            st.success("✓ Gate names updated!")
        
        # Quick selection actions
        if 'for_graphing' in gate_df.columns:
            st.divider()
            st.subheader("🎛️ Quick Selection Actions")
            
            col_a1, col_a2, col_a3, col_a4 = st.columns(4)
            
            with col_a1:
                if st.button("✓ Select All", use_container_width=True, key="select_all_gates"):
                    st.session_state.gate_names_df['for_graphing'] = True
                    st.rerun()
            
            with col_a2:
                if st.button("✗ Deselect All", use_container_width=True, key="deselect_all_gates"):
                    st.session_state.gate_names_df['for_graphing'] = False
                    st.rerun()
            
            with col_a3:
                if st.button("✓ Only Counts", use_container_width=True, key="only_counts_gates"):
                    if 'subset' in st.session_state.gate_names_df.columns:
                        st.session_state.gate_names_df['for_graphing'] = \
                            st.session_state.gate_names_df['subset'] == 'Count'
                        st.rerun()
            
            with col_a4:
                if st.button("✗ Exclude MFIs", use_container_width=True, key="exclude_mfi_gates"):
                    if 'subset' in st.session_state.gate_names_df.columns:
                        st.session_state.gate_names_df['for_graphing'] = \
                            st.session_state.gate_names_df['subset'] != 'MFI'
                        st.rerun()
    else:
        st.info("💡 Gate names are optional but recommended for better visualizations")


# TAB 5: VALIDATION
with tab_validation:
    st.header("Validation")
    
    has_day_0 = st.session_state.day_0_df is not None
    has_day_7 = st.session_state.day_7_df is not None
    has_metadata = st.session_state.metadata_df is not None
    
    if not (has_day_0 and has_day_7):
        st.warning("⚠️ Please process Day 0 and Day 7 data first")
    else:
        st.markdown("""
        Run comprehensive validation checks to ensure data quality and consistency.
        """)
        
        if st.button("Run validation", type="primary", use_container_width=True):
            validator = DataValidator()
            
            # Column consistency check
            st.subheader("📊 Column Consistency Check")
            col_validation = validator.validate_column_consistency(
                st.session_state.day_0_df,
                st.session_state.day_7_df
            )

            # Apply standardization if not already done
            if col_validation.get('case_mismatches') and col_validation.get('canonical_map'):
                st.info("⚙️ Applying automatic column standardization...")
                st.session_state.day_7_df = validator.standardize_day_7_to_day_0(
                    st.session_state.day_7_df,
                    col_validation['canonical_map']
                )
                st.success("✓ Day 7 columns standardized to Day 0 casing")
                
                # Re-validate after standardization
                col_validation = validator.validate_column_consistency(
                    st.session_state.day_0_df,
                    st.session_state.day_7_df
                )
            
            if col_validation['valid']:
                st.success("✅ All columns match between Day 0 and Day 7!")
            else:
                st.warning("⚠️ Column mismatches detected")
                
                if col_validation['only_in_day_0']:
                    with st.expander(f"❌ Columns only in Day 0 ({len(col_validation['only_in_day_0'])})"):
                        for col in sorted(col_validation['only_in_day_0']):
                            st.code(col, language=None)
                
                if col_validation['only_in_day_7']:
                    with st.expander(f"❌ Columns only in Day 7 ({len(col_validation['only_in_day_7'])})"):
                        for col in sorted(col_validation['only_in_day_7']):
                            st.code(col, language=None)
                
                if col_validation['case_mismatches']:
                    with st.expander(f"⚠️ Case mismatches ({len(col_validation['case_mismatches'])})"):
                        for col_lower, cases in col_validation['case_mismatches'].items():
                            st.markdown(f"- Day 0: `{cases['day_0']}` vs Day 7: `{cases['day_7']}`")
            
            st.divider()
            
            # Sample validation
            st.subheader("🔬 Sample Name Validation")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Day 0:**")
                day_0_val = validator.validate_sample_names(
                    st.session_state.day_0_df,
                    st.session_state.metadata_df
                )
                validator.display_validation_results(day_0_val, "Day 0 Samples")
            
            with col2:
                st.markdown("**Day 7:**")
                day_7_val = validator.validate_sample_names(
                    st.session_state.day_7_df,
                    st.session_state.metadata_df
                )
                validator.display_validation_results(day_7_val, "Day 7 Samples")
            
            st.divider()

            st.subheader("📈 Frequency Data Validation")
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Day 0:**")
                day_0_frequency_val = validator.validate_frequency_ranges(st.session_state.day_0_df)
                validator.display_validation_results(day_0_frequency_val, "Day 0 Frequency Validation")

            with col2:
                st.markdown("**Day 7:**")
                day_7_frequency_val = validator.validate_frequency_ranges(st.session_state.day_7_df)
                validator.display_validation_results(day_7_frequency_val, "Day 7 Frequency Validation")

            st.divider()

            st.subheader("🧩 Duplicate Column Value Validation")
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Day 0:**")
                day_0_duplicate_val = validator.validate_duplicate_columns(
                    st.session_state.day_0_df,
                    ignore_columns=['sample_name']
                )
                validator.display_validation_results(day_0_duplicate_val, "Day 0 Duplicate Columns")

            with col2:
                st.markdown("**Day 7:**")
                day_7_duplicate_val = validator.validate_duplicate_columns(
                    st.session_state.day_7_df,
                    ignore_columns=['sample_name']
                )
                validator.display_validation_results(day_7_duplicate_val, "Day 7 Duplicate Columns")

            st.divider()

            # Precision count validation - only if data exists
            if st.session_state.day_0_processed is not None or st.session_state.day_7_processed is not None:
                st.subheader("🎯 Precision Count Validation")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Day 0:**")
                    if st.session_state.day_0_processed is not None:
                        pc_val_0 = validator.validate_precision_counts(st.session_state.day_0_processed)
                        validator.display_validation_results(pc_val_0, "Day 0 Precision Counts")
                    else:
                        st.info("ℹ️ Precision count data not included for Day 0")
                
                with col2:
                    st.markdown("**Day 7:**")
                    if st.session_state.day_7_processed is not None:
                        pc_val_7 = validator.validate_precision_counts(st.session_state.day_7_processed)
                        validator.display_validation_results(pc_val_7, "Day 7 Precision Counts")
                    else:
                        st.info("ℹ️ Precision count data not included for Day 7")
            
            # Store validation results
            st.session_state.validation_results = {
                'column': col_validation,
                'day_0_samples': day_0_val,
                'day_7_samples': day_7_val,
                'day_0_frequency': day_0_frequency_val,
                'day_7_frequency': day_7_frequency_val,
                'day_0_duplicate_columns': day_0_duplicate_val,
                'day_7_duplicate_columns': day_7_duplicate_val
            }
            
            st.session_state.workflow_stage = 'export'
            
            st.divider()
            st.success("✅ Validation complete! Proceed to Export tab.")
        
        # Export validation report
        if st.session_state.validation_results:
            st.divider()
            validator = DataValidator()
            report = validator.create_validation_report(
                day_0_val=st.session_state.validation_results.get('day_0_samples'),
                day_7_val=st.session_state.validation_results.get('day_7_samples'),
                column_val=st.session_state.validation_results.get('column')
            )
            
            st.download_button(
                label="📥 Download Validation Report",
                data=report,
                file_name="validation_report.md",
                mime="text/markdown"
            )


# TAB 6: EXPORT (UPDATED FOR OPTIONAL PRECISION COUNTS)
with tab_export:
    st.header("Export")
    
    # Updated prerequisites - flow data is required, precision counts are optional
    has_day_0_flow = st.session_state.day_0_df is not None
    has_day_7_flow = st.session_state.day_7_df is not None
    has_day_0_precision = st.session_state.day_0_processed is not None
    has_day_7_precision = st.session_state.day_7_processed is not None
    has_metadata = st.session_state.metadata_df is not None
    has_gates = st.session_state.gate_names_df is not None
    
    if not (has_day_0_flow and has_day_7_flow):
        st.warning("⚠️ Please process Day 0 and Day 7 flow data first")
    else:
        st.markdown("### Master workbook")
        
        # Calculate completion - dynamic sheet count
        total_sheets = 2  # Day 0 and Day 7 flow data (minimum)
        completed = 2  # Always have Day 0 and Day 7 flow
        
        if has_day_0_precision:
            total_sheets += 1
            completed += 1
        if has_day_7_precision:
            total_sheets += 1
            completed += 1
        if has_gates:
            total_sheets += 1
            completed += 1
        if has_metadata:
            total_sheets += 1
            completed += 1
        
        completion_pct = int((completed / total_sheets) * 100)
        
        st.progress(completion_pct / 100, text=f"Master file: {completion_pct}% complete ({completed}/{total_sheets} sheets)")
        
        # Show what's included
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Day 0 Flow Data", len(st.session_state.day_0_df), delta="✓")
            if has_day_0_precision:
                st.metric("Day 0 Precision", len(st.session_state.day_0_processed), delta="✓")
            else:
                st.metric("Day 0 Precision", "Not included", delta="Skipped")
        
        with col2:
            st.metric("Day 7 Flow Data", len(st.session_state.day_7_df), delta="✓")
            if has_day_7_precision:
                st.metric("Day 7 Precision", len(st.session_state.day_7_processed), delta="✓")
            else:
                st.metric("Day 7 Precision", "Not included", delta="Skipped")
        
        with col3:
            if has_gates:
                st.metric("Gate Names", len(st.session_state.gate_names_df), delta="✓")
            else:
                st.metric("Gate Names", "Not included", delta="Missing")
            
            if has_metadata:
                st.metric("Metadata", len(st.session_state.metadata_df), delta="✓")
            else:
                st.metric("Metadata", "Not included", delta="Missing")
        
        st.divider()
        
        # Show what will be included
        st.info("**Sheets to be included in master file:**")
        sheets_list = []
        sheets_list.append("✅ day_0_flow_data")
        if has_day_0_precision:
            sheets_list.append("✅ day_0_precision_count")
        sheets_list.append("✅ day_7_flow_data")
        if has_day_7_precision:
            sheets_list.append("✅ day_7_precision_count")
        if has_gates:
            sheets_list.append("✅ name_mapping")
            sheets_list.append("✅ name_mapping_tree")
        if has_metadata:
            sheets_list.append("✅ metadata")
        
        for sheet in sheets_list:
            st.markdown(f"- {sheet}")

        if has_gates:
            st.divider()
            st.subheader("🌳 Gating Name Tree Preview")
            tree_lines = _build_tree_text(st.session_state.gate_names_df)
            if tree_lines:
                with st.expander("Show gating tree text preview", expanded=False):
                    st.code("\n".join(tree_lines), language=None)

                try:
                    tree_image = _build_tree_image(tree_lines)
                    st.image(tree_image, caption="Gating name tree preview", use_column_width=True)
                except Exception:
                    st.warning("Could not render tree image preview; displaying text output instead.")

                st.markdown("---")
                st.subheader("📷 Export Tree PNGs")
                st.info("Export separate PNGs for major lineage subsets.")

                selected_lineages = st.multiselect(
                    "Select major lineages to export",
                    options=['B Cells', 'T Cells', 'NK', 'Myeloid', 'Unknown'],
                    default=['B Cells', 'T Cells']
                )

                if selected_lineages:
                    png_zip_bytes = _lineage_pngs_zip(st.session_state.gate_names_df, selected_lineages)
                    if png_zip_bytes:
                        st.download_button(
                            label="📥 Download Lineage Tree PNGs",
                            data=png_zip_bytes,
                            file_name="lineage_tree_pngs.zip",
                            mime="application/zip",
                            use_container_width=True
                        )
                    else:
                        st.warning("No PNGs were generated for the selected lineages.")

                st.subheader("📄 Export Full Tree Text")
                full_tree_text = _full_tree_text(st.session_state.gate_names_df)
                st.download_button(
                    label="📥 Download Full Tree Text",
                    data=full_tree_text,
                    file_name="full_gate_tree.txt",
                    mime="text/plain",
                    use_container_width=True
                )

                if selected_lineages:
                    st.subheader("🧾 Export Lineage Tree Texts")
                    text_zip_bytes = _lineage_texts_zip(st.session_state.gate_names_df, selected_lineages)
                    if text_zip_bytes:
                        st.download_button(
                            label="📥 Download Lineage Tree Texts",
                            data=text_zip_bytes,
                            file_name="lineage_tree_texts.zip",
                            mime="application/zip",
                            use_container_width=True
                        )
                    else:
                        st.warning("No lineage text files were generated for the selected lineages.")
            else:
                st.info("No gating names available to build a tree preview.")
        
        st.divider()
        
        # Generate master file
        if st.button("Prepare master workbook", type="primary", use_container_width=True):
            output = build_master_workbook(
                st.session_state.day_0_df,
                st.session_state.day_7_df,
                st.session_state.day_0_processed if has_day_0_precision else None,
                st.session_state.day_7_processed if has_day_7_precision else None,
                st.session_state.gate_names_df if has_gates else None,
                st.session_state.metadata_df if has_metadata else None,
            )
            
            st.download_button(
                label=f"Download master workbook ({completed} sheets)",
                data=output,
                file_name="flow_cytometry_master_file.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
            st.success(f"🎉 Master file generated with {completed} sheets!")
            
            # Show info about what wasn't included
            not_included = []
            if not has_day_0_precision:
                not_included.append("Day 0 precision count")
            if not has_day_7_precision:
                not_included.append("Day 7 precision count")
            if not has_gates:
                not_included.append("Gate names")
            if not has_metadata:
                not_included.append("Metadata")
            
            if not_included:
                st.info(f"**Not included:** {', '.join(not_included)}")


# Footer
st.divider()
with st.expander("User guide"):
    st.markdown("""
    ### Quick Start Guide
    
    **New in v5.2:**
    - ✨ **Automatic Mean/SD row removal** - Summary rows are filtered out automatically
    - ✨ **Optional precision count data** for Day 0 and/or Day 7
    - ✨ Dynamic master file generation based on available data
    - ✨ Multi-file upload support
    - ✨ Integrated sample name cleaning
    - ✨ Intra-day validation displayed in tabs
    - ✨ Enhanced validation checks
    
    **Workflow:**
    
    1. **Metadata** (Tab 1)
       - Upload your metadata file first
       - This enables validation throughout the process
    
    2. **Day 0 Data** (Tab 2)
       - Upload one or more Day 0 files
       - Choose cleaning method if needed
       - Remove FMO samples automatically
       - Mean and SD summary rows removed automatically
       - **Optional:** Generate precision count table (uncheck if not captured)
       - View intra-day validation results
    
    3. **Day 7 Data** (Tab 3)
       - Repeat for Day 7 files
       - Same cleaning options available
       - Mean and SD summary rows removed automatically
       - **Optional:** Generate precision count table (uncheck if not captured)
       - View intra-day validation results
    3. **Day 7 Data** (Tab 3)
       - Repeat for Day 7 files
       - Same cleaning options available
       - **Optional:** Generate precision count table (uncheck if not captured)
       - View intra-day validation results
    
    4. **Gate Names** (Tab 4) - Optional
       - Upload or auto-generate gate names
       - Improves downstream plotting
    
    5. **Validation** (Tab 5)
       - Run comprehensive checks
       - Validates columns, samples, and counts
       - Export validation report
    
    6. **Export** (Tab 6)
       - Download master file with 2-6 sheets (dynamic)
       - Includes all available processed data
    
    **About Precision Counts:**
    
    - If you don't have precision count beads for one or both days, simply uncheck the box
    - The master file will only include sheets for data you've generated
    - Minimum 2 sheets (Day 0 and Day 7 flow data), maximum 6 sheets
    
    **Cleaning Methods:**
    
    - **None**: Files are already clean
    - **DonorX*_B2_**: Preset for "Donor1*_B2_Sample" format
    - **Separator**: Split by custom character
    - **Regex**: Advanced pattern matching
    
    **Tips:**
    
    - Upload metadata first for best validation
    - Use the same cleaning settings for Day 0 and Day 7
    - Check intra-day validation warnings in each tab
    - Review all validation results before exporting
    - Master file adapts to include only the data you've generated
    """)

st.sidebar.divider()
st.sidebar.caption("Flow cytometry preparation workflow")
st.sidebar.caption("Local, deterministic processing")
