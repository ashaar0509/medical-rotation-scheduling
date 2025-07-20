# app.py

"""
Streamlit User Interface for the Medical Rotation Scheduler.

This script provides a web-based front-end that allows a user to upload an
input file and trigger the backend scheduling engine. It interacts solely
with the `RotationScheduler` class, which encapsulates the entire backend logic.
"""

import os
import pandas as pd
import streamlit as st
from io import BytesIO

# Import the main orchestrator class and configuration constants
from scheduler.main import RotationScheduler
from scheduler.config import APP_DIR, OUTPUT_SCHEDULE_FILE

# --- Page Configuration ---
st.set_page_config(
	page_title="Medical Rotation Scheduler",
	layout="wide"
)

# --- Helper Function ---
def to_excel_bytes(schedule_df: pd.DataFrame) -> bytes:
	"""Converts a DataFrame to an in-memory Excel file (as bytes)."""
	output = BytesIO()
	# Use a context manager to ensure the writer is properly closed
	with pd.ExcelWriter(output, engine='openpyxl') as writer:
		schedule_df.to_excel(writer, index=False, sheet_name='Schedule')
	# Retrieve the byte data from the buffer
	return output.getvalue()

# --- Main Application UI ---
st.title("Medical Rotation Scheduler")
st.write(
	"Upload an Excel file containing resident data, leave requests, and "
	"pre-assignments to generate an optimized rotation schedule."
)

# --- File Uploader ---
uploaded_file = st.file_uploader(
	"Upload Input Excel File", type=["xlsx"]
)

if uploaded_file is not None:
	# Use a temporary directory for uploaded files to keep the root clean
	temp_dir = os.path.join(APP_DIR, "temp")
	os.makedirs(temp_dir, exist_ok=True)
	
	# Define paths for the temporary input and final output
	input_path = os.path.join(temp_dir, uploaded_file.name)
	output_path = os.path.join(temp_dir, OUTPUT_SCHEDULE_FILE)

	# Save the uploaded file to the temporary location
	with open(input_path, "wb") as f:
		f.write(uploaded_file.getbuffer())

	st.success(f"File '{uploaded_file.name}' uploaded successfully.")
	
	# --- Scheduler Execution Button ---
	if st.button("Run Scheduler", type="primary"):
		with st.spinner("Processing... The model is building and solving the schedule."):
			# Instantiate the single orchestrator class
			scheduler = RotationScheduler(
				input_path=input_path, output_path=output_path
			)
			# Run the entire backend process
			success, schedule_df, summary_df = scheduler.run()

		# --- Results Display ---
		if success:
			st.success("A feasible schedule was successfully generated.")

			st.subheader("Rotation Distribution Summary")
			st.dataframe(summary_df)

			st.subheader("Full Generated Schedule")
			st.dataframe(schedule_df)

			# Generate in-memory Excel file for download
			excel_bytes = to_excel_bytes(schedule_df)
			st.download_button(
				label="Download Schedule as Excel",
				data=excel_bytes,
				file_name=OUTPUT_SCHEDULE_FILE,
				mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
			)
		else:
			st.error(
				"No feasible solution could be found. "
				"This may be due to overly restrictive constraints in the input "
				"file or the model's configuration."
			)