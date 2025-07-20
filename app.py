# app.py

"""
Streamlit User Interface for the Medical Rotation Scheduler.
"""

import os
import pandas as pd
import streamlit as st
from io import BytesIO

from scheduler.main import RotationScheduler
from scheduler.config import APP_DIR, OUTPUT_SCHEDULE_FILE

# --- Page Configuration ---
st.set_page_config(
	page_title="Medical Rotation Scheduler",
	layout="wide"
)

# --- Helper Functions ---
def to_excel_bytes(file_path: str) -> bytes:
	"""Reads a generated Excel file from disk and returns its byte content."""
	with open(file_path, "rb") as f:
		return f.read()

def convert_df_to_csv_bytes(df: pd.DataFrame) -> bytes:
	"""Converts a DataFrame to CSV format in memory for downloading."""
	return df.to_csv(index=False).encode('utf-8')

# --- Main App UI ---
st.title("Medical Rotation Scheduler 🗓️")
st.write(
	"Upload an Excel file with resident data to generate an optimized rotation schedule. "
	"The model will satisfy all hard constraints and attempt to maximize a score based on soft preferences."
)

uploaded_file = st.file_uploader(
	"Upload Input Excel File", type=["xlsx"]
)

if uploaded_file is not None:
	temp_dir = os.path.join(APP_DIR, "temp")
	os.makedirs(temp_dir, exist_ok=True)
	
	input_path = os.path.join(temp_dir, uploaded_file.name)
	output_path = os.path.join(temp_dir, OUTPUT_SCHEDULE_FILE)

	with open(input_path, "wb") as f:
		f.write(uploaded_file.getbuffer())

	st.success(f"File '{uploaded_file.name}' uploaded successfully.")
	
	if st.button("Run Scheduler", type="primary"):
		with st.spinner("Processing... The model is building and solving the schedule. This may take a moment."):
			scheduler = RotationScheduler(
				input_path=input_path, output_path=output_path
			)
			# Unpack all the new return values from the updated scheduler
			success, schedule_df, summary_df, raw_score, normalized_score, satisfied, unsatisfied, log_df = scheduler.run()

		if success:
			st.success("A feasible schedule was successfully generated.")

			# --- Objective Score Display ---
			st.subheader("Objective Score Summary")
			col1, col2 = st.columns(2)
			col1.metric(
				label="Normalized Schedule Quality",
				value=f"{normalized_score:.1%}",
				help="A score of 100% indicates all possible rewards were achieved. Penalties can lower this score."
			)
			# Display the raw score for reference
			col2.metric(
				label="Raw Score",
				value=f"{raw_score}",
				help="The sum of all rewards (+) and penalties (-)."
			)

			# --- Download Button for the Constraint Log ---
			st.download_button(
				label="Download Full Constraint Log (.csv)",
				data=convert_df_to_csv_bytes(log_df),
				file_name="objective_log.csv",
				mime="text/csv",
			)
			
			# --- Display for Satisfied vs. Unsatisfied Constraints ---
			with st.expander("Show Details of Applied and Missed Soft Constraints"):
				st.write("#### Satisfied Constraints (Rewards Gained & Penalties Incurred)")
				st.text_area("Satisfied", "\n".join(satisfied), height=200, key="satisfied_log")
				
				st.write("#### Unsatisfied Constraints (Rewards Missed & Penalties Avoided)")
				st.text_area("Unsatisfied", "\n".join(unsatisfied), height=200, key="unsatisfied_log")

			# --- DataFrames for Schedule and Summary ---
			st.subheader("Rotation Distribution Summary")
			st.dataframe(summary_df)

			st.subheader("Full Generated Schedule")
			st.dataframe(schedule_df)

			# --- Download Button for the Main Schedule ---
			excel_bytes = to_excel_bytes(output_path)
			st.download_button(
				label="Download Full Schedule as Excel",
				data=excel_bytes,
				file_name=OUTPUT_SCHEDULE_FILE,
				mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
			)
		else:
			st.error(
				"No feasible solution could be found. This may be due to overly restrictive constraints "
				"in the input file or the model's configuration."
			)