"""Metadata upload screen."""
from __future__ import annotations
import pandas as pd
import streamlit as st

def _read_metadata(upload) -> pd.DataFrame:
    if upload.name.lower().endswith(".csv"):
        frame = pd.read_csv(upload)
    else:
        frame = pd.read_excel(upload)
    first = frame.columns[0]
    if str(first).startswith("Unnamed:") or ("name" in str(first).lower() and "sample" not in str(first).lower()):
        frame = frame.rename(columns={first: "sample_name"})
    return frame

def render() -> None:
    st.header("Study metadata")
    st.write("Upload the metadata file produced by the plate designer. It will be used to validate sample names during processing.")
    upload = st.file_uploader("Upload metadata file (Excel or CSV)", type=["xlsx", "xls", "csv"],
                              key="metadata_upload", help="Should contain a sample_name column matching the flow data")
    if upload is not None:
        try:
            metadata = _read_metadata(upload)
            st.session_state.metadata_df = metadata
            st.session_state.metadata_uploaded = True
            st.session_state.workflow_stage = "day_0"
            st.success(f"Metadata loaded: {len(metadata)} samples")
            st.subheader("Metadata preview")
            st.dataframe(metadata.head(10), use_container_width=True)
            if "sample_name" in metadata:
                st.info(f"Found {metadata['sample_name'].nunique()} unique sample names")
                with st.expander("View first 10 sample names"):
                    for sample in metadata["sample_name"].head(10): st.code(sample, language=None)
            else:
                st.warning("No 'sample_name' column was found in metadata.")
        except Exception as error:
            st.error(f"Could not load metadata: {error}")
    if not st.session_state.metadata_uploaded:
        st.info("Upload a metadata file to continue.")
    else:
        st.success("Metadata is ready. Continue to Day 0.")
