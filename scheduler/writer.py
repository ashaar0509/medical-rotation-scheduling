# scheduler/writer.py

"""
Output Generation for the Medical Rotation Scheduling Model.

This module provides a class to transform the solved model's data into a
human-readable format, creating a primary schedule, a summary view, and
PGY-specific sheets, then exporting them to an Excel file.
"""

import pandas as pd
from ortools.sat.python import cp_model
from typing import Dict, Tuple

from scheduler.parser import RotationDataParser
from scheduler.config import NUM_BLOCKS

class SolutionWriter:
	"""
	Handles the extraction and formatting of the solver's solution.
	"""

	def __init__(
		self,
		solver: cp_model.CpSolver,
		parsed_data: RotationDataParser,
		model_variables: Dict[Tuple[int, int], cp_model.IntVar]
	):
		"""
		Initializes the writer with the necessary solution components.

		Args:
			solver: The ortools.sat.python.cp_model.CpSolver instance after
					the model has been solved.
			parsed_data: The fully populated instance of RotationDataParser.
			model_variables: A dictionary mapping (resident_idx, block_idx)
							 to the corresponding model integer variable. This
							 is the `x` variable from the model builder.
		"""
		self.solver = solver
		self.data = parsed_data
		self.x = model_variables
		self.schedule_df = self._extract_schedule_dataframe()

	def write_to_excel(self, output_file_path: str) -> None:
		"""
		Writes the complete, multi-sheet schedule report to an Excel file.

		Args:
			output_file_path: The path where the output .xlsx file will be saved.
		"""
		summary_df = self._create_summary_dataframe()
		pgy_schedules = self._split_schedule_by_pgy()

		with pd.ExcelWriter(output_file_path, engine="openpyxl") as writer:
			# Sheet 1: High-level summary of rotation counts per block
			summary_df.to_excel(writer, sheet_name="Summary")

			# Sheet 2: The full schedule for all residents
			self.schedule_df.drop(columns="PGY").to_excel(
				writer, sheet_name="FullSchedule", index=False
			)

			# Subsequent Sheets: Schedules filtered for each PGY level
			for pgy_level, df in pgy_schedules.items():
				df.to_excel(writer, sheet_name=pgy_level, index=False)
		
		print(f"Schedule successfully written to {output_file_path}")
		return self.schedule_df, summary_df

	def _extract_schedule_dataframe(self) -> pd.DataFrame:
		"""
		Constructs the primary schedule DataFrame from the solver's solution.

		This method iterates through the solution values, maps rotation indices
		back to their string names, and assembles the main schedule table.

		Returns:
			A pandas DataFrame containing the full schedule, including a 'PGY'
			column for subsequent filtering.
		"""
		solution_rows = []
		for r_idx, resident_id in enumerate(self.data.residents):
			# Start each row with the resident's ID.
			row_data = {"Resident": resident_id}
			
			# For each block, find the assigned rotation's name.
			for b_idx in range(NUM_BLOCKS):
				rotation_idx = self.solver.Value(self.x[r_idx, b_idx])
				rotation_name = self.data.idx_to_rotation[rotation_idx]
				row_data[f"Block_{b_idx + 1}"] = rotation_name
			
			solution_rows.append(row_data)

		# Create the DataFrame and add the PGY column for sorting.
		df = pd.DataFrame(solution_rows)
		df["PGY"] = self.data.pgys
		return df

	def _create_summary_dataframe(self) -> pd.DataFrame:
		"""
		Creates the rotation distribution summary DataFrame.

		This reshapes the main schedule data to show the count of residents
		in each rotation for every block.

		Returns:
			A pivoted pandas DataFrame summarizing rotation counts.
		"""
		block_columns = [f"Block_{i + 1}" for i in range(NUM_BLOCKS)]
		
		# Melt the DataFrame to a long format.
		melted_df = self.schedule_df.melt(
			id_vars=["Resident"],
			value_vars=block_columns,
			var_name="Block",
			value_name="Rotation"
		)
		
		# Create the pivot table (unstack) to get counts.
		summary_df = (
			melted_df.groupby(["Rotation", "Block"])
			.size()
			.unstack(fill_value=0)
			.sort_index()
		)
		
		# Clean up index and column names for presentation.
		summary_df.index.name = None
		summary_df.columns.name = None
		
		# Ensure original block order is maintained.
		return summary_df[block_columns]

	def _split_schedule_by_pgy(self) -> Dict[str, pd.DataFrame]:
		"""
		Filters the main schedule into separate DataFrames for each PGY level.

		Returns:
			A dictionary where keys are PGY levels (e.g., "R1") and values
			are the corresponding schedule DataFrames.
		"""
		pgy_schedules = {}
		
		# Get all unique PGY levels present in the data.
		pgy_levels = self.schedule_df["PGY"].unique()
		
		for level in sorted(pgy_levels):
			# Filter the DataFrame for the current PGY level and drop the
			# now-redundant 'PGY' column for the final sheet.
			pgy_df = self.schedule_df[self.schedule_df["PGY"] == level].drop(
				columns="PGY"
			)
			pgy_schedules[level] = pgy_df
			
		return pgy_schedules