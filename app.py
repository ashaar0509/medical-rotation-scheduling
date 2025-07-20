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

st.set_page_config(
	page_title="Medical Rotation Scheduler",
	layout="wide"
)

def to_excel_bytes(file_path: str) -> bytes:
	"""Reads the generated Excel file from disk and returns its byte content."""
	with open(file_path, "rb") as f:
		return f.read()

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
			success, schedule_df, summary_df, final_score, max_score, applied_constraints = scheduler.run()

		if success:
			st.success("✅ A feasible schedule was successfully generated.")

			st.subheader("Objective Score Summary")
			col1, col2 = st.columns(2)
			col1.metric(
				label="Score Achieved",
				value=f"{final_score}",
				help="The sum of all applied rewards (+) and penalties (-)."
			)
			col2.metric(
				label="Maximum Possible Score",
				value=f"{max_score}",
				help="The best possible score if all rewards are achieved and no penalties are incurred."
			)

			with st.expander("Show Log of Applied Soft Constraints"):
				st.write("The following rewards and penalties were applied to generate the final score:")
				st.markdown("---")
				# Display the log in a scrollable text area
				log_text = "\n".join(applied_constraints)
				st.text_area("Applied Constraints Log", log_text, height=250)
			
			st.subheader("Rotation Distribution Summary")
			st.dataframe(summary_df)

			st.subheader("Full Generated Schedule")
			st.dataframe(schedule_df)

			excel_bytes = to_excel_bytes(output_path)
			st.download_button(
				label="📥 Download Full Schedule as Excel",
				data=excel_bytes,
				file_name=OUTPUT_SCHEDULE_FILE,
				mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
			)
		else:
			st.error(
				"❌ No feasible solution could be found. This may be due to overly restrictive constraints "
				"in the input file or the model's configuration."
			)