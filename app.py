"""Launch the Flow Cytometry Data Preparation interface."""
from pathlib import Path

APP_MODULE = Path(__file__).parent / "flow_cleaning" / "streamlit_app.py"

source = compile(APP_MODULE.read_bytes(), str(APP_MODULE), "exec")
exec(source, {"__name__": "__main__", "__file__": str(APP_MODULE), "__package__": "flow_cleaning"})
