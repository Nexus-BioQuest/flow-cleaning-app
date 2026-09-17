"""Master-workbook assembly with the original sheet names and schemas."""
from __future__ import annotations
from io import BytesIO
import re
import pandas as pd

def parse_gate_name(value: str) -> tuple[list[str], str]:
    path, separator, metric = str(value).partition("|")
    return [part.strip() for part in path.split("/") if part.strip()], metric.strip() if separator else "Count"

def mapping_tree_frame(mapping: pd.DataFrame) -> pd.DataFrame:
    parsed = [parse_gate_name(row.get("gating_name", "")) for _, row in mapping.iterrows()]
    depth = max((len(parts) for parts, _ in parsed), default=0)
    rows = []
    for (_, row), (parts, parsed_metric) in zip(mapping.iterrows(), parsed):
        item = {f"Level {i + 1}": parts[i] if i < len(parts) else "" for i in range(depth)}
        metric = row.get("metric", parsed_metric)
        item.update({"Metric": parsed_metric if pd.isna(metric) or metric == "" else metric,
            "Gating Name": row.get("gating_name", ""), "Plot Name": row.get("plot_name", ""),
            "For Graphing": row.get("for_graphing", True)})
        rows.append(item)
    columns = [f"Level {i + 1}" for i in range(depth)] + ["Metric", "Gating Name", "Plot Name", "For Graphing"]
    return pd.DataFrame(rows, columns=columns)

def normalize_lineage(value: str) -> str:
    label = str(value).strip().lower()
    if "b cell" in label or label in {"b", "b cells"}: return "B Cells"
    if "t cell" in label or label in {"t", "t cells"}: return "T Cells"
    if "nk" in label: return "NK"
    if "myeloid" in label: return "Myeloid"
    if not label or "unknown" in label: return "Unknown"
    return str(value).strip()

def _sheet_name(value: str) -> str:
    return (re.sub(r"[^A-Za-z0-9 ]+", "", value).strip() or "Unknown")[:31]

def _tree_lines(mapping: pd.DataFrame) -> list[str]:
    tree = {}
    for _, row in mapping.iterrows():
        parts, metric = parse_gate_name(row.get("gating_name", "")); node = tree
        for part in parts: node = node.setdefault(part, {})
        node.setdefault(f"[{metric}]", {})
    lines = []
    def walk(node, prefix=""):
        items = sorted(node.items())
        for index, (label, children) in enumerate(items):
            last = index == len(items) - 1; lines.append(f"{prefix}{'└─ ' if last else '├─ '}{label}")
            if children: walk(children, prefix + ("   " if last else "│  "))
    walk(tree); return lines

def _write_lineage_sheets(writer: pd.ExcelWriter, mapping: pd.DataFrame) -> None:
    from openpyxl.drawing.image import Image
    from matplotlib import pyplot as plt
    groups = mapping.assign(_lineage=mapping.get("cell_lineage", pd.Series("Unknown", index=mapping.index)).fillna("Unknown").map(normalize_lineage)).groupby("_lineage", sort=False)
    used = set()
    for lineage, group in groups:
        name, suffix = _sheet_name(lineage), 1; base = name
        while name in used: suffix += 1; name = f"{base}_{suffix}"[:31]
        used.add(name); sheet = writer.book.create_sheet(name); writer.sheets[name] = sheet
        lines = _tree_lines(group)
        if not lines: continue
        fig, ax = plt.subplots(figsize=(10, max(4, min(20, len(lines) * .25)))); ax.axis("off")
        step = 1 / max(len(lines), 20)
        for index, line in enumerate(lines): ax.text(.01, 1 - index * step, line, fontfamily="monospace", fontsize=8, va="top")
        image_data = BytesIO(); fig.tight_layout(); fig.savefig(image_data, format="png", dpi=150, bbox_inches="tight"); plt.close(fig); image_data.seek(0)
        sheet.add_image(Image(image_data), "A1")

def _write_tree_image_sheet(writer: pd.ExcelWriter, mapping: pd.DataFrame) -> None:
    from openpyxl.drawing.image import Image
    from matplotlib import pyplot as plt

    sheet = writer.book.create_sheet("name_mapping_tree")
    writer.sheets["name_mapping_tree"] = sheet
    lines = _tree_lines(mapping)
    if not lines:
        return

    fig, ax = plt.subplots(figsize=(12, max(5, min(30, len(lines) * .25))))
    ax.axis("off")
    step = 1 / max(len(lines), 20)
    for index, line in enumerate(lines):
        ax.text(.01, 1 - index * step, line, fontfamily="monospace", fontsize=8, va="top")
    image_data = BytesIO()
    fig.tight_layout()
    fig.savefig(image_data, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    image_data.seek(0)
    sheet.add_image(Image(image_data), "A1")

def build_master_workbook(day_0: pd.DataFrame, day_7: pd.DataFrame, day_0_precision=None,
                          day_7_precision=None, gate_names=None, metadata=None) -> bytes:
    """Return the same workbook sheets produced by the original Streamlit block."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        day_0.to_excel(writer, index=False, sheet_name="day_0_flow_data")
        day_7.to_excel(writer, index=False, sheet_name="day_7_flow_data")
        if day_0_precision is not None: day_0_precision.to_excel(writer, index=False, sheet_name="day_0_precision_count")
        if day_7_precision is not None: day_7_precision.to_excel(writer, index=False, sheet_name="day_7_precision_count")
        if gate_names is not None:
            gate_names.to_excel(writer, index=False, sheet_name="name_mapping")
        if metadata is not None: metadata.to_excel(writer, index=False, sheet_name="metadata")
    return output.getvalue()
