import streamlit as st
from pathlib import Path
from scheduler.parser import parse_input
from scheduler.config import idx_to_rotation
from scheduler.writer import solve_and_export
from scheduler.model import build_model

st.title("Medical Rotation Scheduler")

uploaded_file = st.file_uploader("Upload input Excel file", type=["xlsx"])

if uploaded_file is not None:
	st.success("File uploaded successfully.")
	if st.button("Run Scheduler"):
		with st.spinner("Solving rotation schedule..."):
			input_path = Path("input_temp.xlsx")
			output_path = Path("output_schedule.xlsx")

			with open(input_path, "wb") as f:
				f.write(uploaded_file.getbuffer())

			try:
				residents, pgys, leave_dict = parse_input(input_path)
				model, x, y = build_model(residents, pgys, leave_dict)
				success = solve_and_export(model, x, residents, output_path)

				if success:
					with open(output_path, "rb") as f:
						st.download_button("Download Schedule", f, file_name="output_schedule.xlsx")
				else:
					st.error("❌ No feasible solution found.")
			except Exception as e:
				st.error(f"An error occurred: {e}")