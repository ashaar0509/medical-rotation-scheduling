import streamlit as st
from pathlib import Path
import pandas as pd
from scheduler.parser import parse_input
from scheduler.config import idx_to_rotation, BLOCKS
from scheduler.writer import solve_and_export, extract_solution
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
				# residents, pgys, leave_dict = parse_input(input_path)
				residents, pgys, leave_dict, forced_assignments, forbidden_assignments = parse_input(input_path)

				model, x, y = build_model(residents, pgys, leave_dict, forced_assignments, forbidden_assignments)
				success, solver = solve_and_export(model, x, residents, output_path, pgys)

				if success and solver is not None:
					# Show rotation summary in the web app
					solution = extract_solution(solver, x, residents)
					df = pd.DataFrame(
						solution, columns=["Resident"] + [f"Block_{i+1}" for i in range(BLOCKS)]
					)
					df["PGY"] = pgys
					melted = df.melt(
						id_vars=["Resident"],
						value_vars=[f"Block_{i+1}" for i in range(BLOCKS)],
						var_name="Block",
						value_name="Rotation"
					)
					count_df = (
						melted.groupby(["Rotation", "Block"])
						.size()
						.unstack(fill_value=0)
						.sort_index()
					)
					st.subheader("📊 Rotation Distribution Summary")
					st.dataframe(count_df)

					# Download link
					with open(output_path, "rb") as f:
						st.download_button("📥 Download Schedule", f, file_name="output_schedule.xlsx")
				else:
					st.error("❌ No feasible solution found.")
			except Exception as e:
				st.error(f"An error occurred: {e}")
