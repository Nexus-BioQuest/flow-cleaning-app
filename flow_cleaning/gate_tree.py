"""Gate-tree rendering and downloads shared by the cleaning interface."""
import io
import re
import zipfile

import pandas as pd


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

