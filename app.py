# app.py

"""
Streamlit Web Interface for the Medical Residency Rotation Scheduler.

Launch with:
    streamlit run app.py

The same scheduling pipeline is available headlessly via the command line:
    python -m scheduler.main [--input PATH] [--output PATH]
"""

import os
import pandas as pd
import streamlit as st

from scheduler.main import RotationScheduler
from scheduler.config import APP_DIR, OUTPUT_SCHEDULE_FILE

# ── Page configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Medical Rotation Scheduler",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🏥 Rotation Scheduler")
    st.markdown(
        "Automated medical residency scheduling using **Google OR-Tools CP-SAT**."
    )
    st.divider()

    st.markdown("**How to use**")
    st.markdown(
        "1. Upload your resident input `.xlsx` file.\n"
        "2. Click **Run Scheduler**.\n"
        "3. Review results and download the report."
    )
    st.divider()

    st.markdown("**Resources**")
    st.markdown(
        "- [Technical Report](https://github.com/ashaar0509/medical-rotation-scheduling/blob/main/docs/TECHNICAL_REPORT.md)\n"
        "- [GitHub Repository](https://github.com/ashaar0509/medical-rotation-scheduling)\n"
        "- Sample input files are in `sample_data/`"
    )
    st.divider()

    st.caption(
        "Built by Abdullah Shaar · HBKU"
    )


# ── Helper functions ──────────────────────────────────────────────────────────
def _read_excel_bytes(file_path: str) -> bytes:
    """Read a generated Excel file from disk and return its raw bytes."""
    with open(file_path, "rb") as f:
        return f.read()


def _df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Serialise a DataFrame to UTF-8 CSV bytes."""
    return df.to_csv(index=False).encode("utf-8")


# ── Main page ─────────────────────────────────────────────────────────────────
st.title("Medical Residency Rotation Scheduler")
st.markdown(
    "Upload a resident input file to generate an optimised 13-block annual schedule. "
    "The solver satisfies all hard constraints and maximises a quality score over soft preferences."
)

uploaded_file = st.file_uploader(
    "Upload resident input file (.xlsx)",
    type=["xlsx"],
    help="See the sample files in the `sample_data/` directory for the expected format.",
)

if uploaded_file is not None:
    # Save uploaded file to a temp directory
    temp_dir = os.path.join(APP_DIR, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    input_path  = os.path.join(temp_dir, uploaded_file.name)
    output_path = os.path.join(temp_dir, OUTPUT_SCHEDULE_FILE)

    with open(input_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.success(f"✓ **{uploaded_file.name}** uploaded successfully.")

    if st.button("Run Scheduler", type="primary", use_container_width=False):
        with st.spinner("Solving… This may take a moment."):
            scheduler = RotationScheduler(
                input_path=input_path,
                output_path=output_path,
            )
            (
                success, schedule_df, summary_df,
                raw_score, normalized_score,
                satisfied, unsatisfied, log_df,
            ) = scheduler.run()

        # ── Results ──────────────────────────────────────────────────────────
        if not success:
            st.error(
                "No feasible solution found. "
                "This is usually caused by conflicting pre-assignments or over-constrained "
                "leave periods. Check `scheduler/config.py` and the input file."
            )
            st.stop()

        st.success("Schedule generated successfully.")
        st.divider()

        # Quality score metrics
        st.subheader("Schedule Quality")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(
            "Normalized Quality",
            f"{normalized_score:.1%}",
            help="100% means all rewards were achieved with no penalties.",
        )
        col2.metric(
            "Raw Score",
            raw_score,
            help="Sum of all reward (+) and penalty (−) contributions.",
        )
        col3.metric("Constraints Met", len(satisfied))
        col4.metric("Constraints Missed", len(unsatisfied))

        st.divider()

        # Downloads
        st.subheader("Downloads")
        dl_col1, dl_col2 = st.columns(2)
        with dl_col1:
            st.download_button(
                label="⬇ Download Full Schedule (.xlsx)",
                data=_read_excel_bytes(output_path),
                file_name=OUTPUT_SCHEDULE_FILE,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with dl_col2:
            st.download_button(
                label="⬇ Download Constraint Log (.csv)",
                data=_df_to_csv_bytes(log_df),
                file_name="objective_log.csv",
                mime="text/csv",
                use_container_width=True,
            )

        st.divider()

        # Soft constraint details
        with st.expander("Soft Constraint Details", expanded=False):
            tab1, tab2 = st.tabs(["Active Constraints", "Inactive Constraints"])
            with tab1:
                st.text_area(
                    "Rewards gained & penalties incurred",
                    "\n".join(satisfied),
                    height=220,
                    key="tab_satisfied",
                )
            with tab2:
                st.text_area(
                    "Rewards missed & penalties avoided",
                    "\n".join(unsatisfied),
                    height=220,
                    key="tab_unsatisfied",
                )

        st.divider()

        # Staffing summary table
        st.subheader("Staffing Summary (Residents per Rotation per Block)")
        st.dataframe(summary_df, use_container_width=True)

        st.divider()

        # Full schedule table with PGY filter
        st.subheader("Generated Schedule")
        pgy_options = ["All"] + sorted(schedule_df["PGY"].unique().tolist())
        selected_pgy = st.selectbox("Filter by PGY level", pgy_options)
        display_df = (
            schedule_df if selected_pgy == "All"
            else schedule_df[schedule_df["PGY"] == selected_pgy]
        )
        st.dataframe(display_df.reset_index(drop=True), use_container_width=True)
