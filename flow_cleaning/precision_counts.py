"""Pure precision-count transformations."""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd

@dataclass(frozen=True)
class PrecisionCountSettings:
    bead_concentration_per_ml: float
    beads_per_microlitre: float
    bead_volume_microlitre: float
    cell_volume_microlitre: float

def detect_bead_count_column(df: pd.DataFrame) -> str | None:
    """Select the first numeric column matching the documented priority rules."""
    numeric = [column for column in df.columns if pd.api.types.is_numeric_dtype(df[column])]
    priorities = (
        lambda name: "bead" in name and "count" in name,
        lambda name: "precision" in name and "count" in name,
        lambda name: "bead" in name,
        lambda name: "count" in name,
    )
    for matches in priorities:
        candidate = next((column for column in numeric if matches(str(column).casefold())), None)
        if candidate is not None: return candidate
    return None

def filter_summary_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if df is None or "sample_name" not in df.columns: return df, 0
    remove = df["sample_name"].astype("string").str.casefold().isin({"mean", "sd"})
    return df.loc[~remove].copy(), int(remove.sum())

def create_precision_count_table(df: pd.DataFrame, bead_column: str, settings: PrecisionCountSettings) -> pd.DataFrame:
    """Create the established precision-count export schema."""
    return pd.DataFrame({
        "sample_name": df["sample_name"],
        "bead_conc_per_ml": round(settings.bead_concentration_per_ml),
        "beads_per_microlitre": round(settings.beads_per_microlitre),
        "bead_vol_microlitre": settings.bead_volume_microlitre,
        "bead_count": round(settings.beads_per_microlitre * settings.bead_volume_microlitre),
        "cell_vol_microlitre": settings.cell_volume_microlitre,
        "precision_count_beads": pd.to_numeric(df[bead_column], errors="raise").astype(int),
    })
