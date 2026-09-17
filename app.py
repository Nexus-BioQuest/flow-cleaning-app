"""Rerun-safe launcher for the Flow Cytometry Data Preparation interface."""
from pathlib import Path

APP_MODULE = Path(__file__).parent / "flow_cleaning" / "streamlit_app.py"

# Streamlit executes this launcher repeatedly in one Python process. Executing
# the UI module as a script ensures every widget interaction rebuilds the page;
# importing a top-level UI module would be skipped after Python caches it.
source = compile(APP_MODULE.read_bytes(), str(APP_MODULE), "exec")
exec(source, {"__name__": "__main__", "__file__": str(APP_MODULE), "__package__": "flow_cleaning"})

