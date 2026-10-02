"""Pure precision-count transformations."""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd

@dataclass(frozen=True)
class PrecisionCountSettings:
    bead_concentration_per_ml: float
    bead_concentration_per_ul: float
    bead_volume_ul: float
    sample_volume_ul: float

def concentration_per_microlitre(concentration_per_ml: float) -> float:
    """Convert a bead concentration from per mL to per µL (1 mL = 1,000 µL)."""
    if concentration_per_ml < 0:
        raise ValueError("Bead concentration cannot be negative")
    return concentration_per_ml / 1000

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
    """Build precision-count fields for absolute-count QC.

    ``expected_bead_count`` is an audit-only estimate; QC uses the recorded
    bead count instead.
    """
    return pd.DataFrame({
        "sample_name": df["sample_name"],
        "bead_concentration_per_ml": round(settings.bead_concentration_per_ml),
        "bead_concentration_per_ul": round(settings.bead_concentration_per_ul),
        "bead_volume_ul": settings.bead_volume_ul,
        "expected_bead_count": round(settings.bead_concentration_per_ul * settings.bead_volume_ul),
        "sample_volume_ul": settings.sample_volume_ul,
        "recorded_bead_count": pd.to_numeric(df[bead_column], errors="raise").astype(int),
    })
