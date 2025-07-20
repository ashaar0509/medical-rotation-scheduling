# scheduler/writer.py

"""
Output Generation for the Medical Rotation Scheduling Model.

This module provides a class to transform the solved model's data into a
human-readable format, creating a primary schedule, a summary view, and
PGY-specific sheets, then exporting them to an Excel file.
"""

import pandas as pd
from typing import Any, Dict, List, Tuple

from scheduler.parser import RotationDataParser
from scheduler.config import NUM_BLOCKS, REWARD_WEIGHT, PENALTY_WEIGHT

class SolutionWriter:
	"""
	Handles the extraction, formatting, and export of the solver's solution.
	"""

	def __init__(
		self,
		solver: Any, # cp_model.CpSolver
		parsed_data: RotationDataParser,
		model_variables: Dict[Tuple[int, int], Any], # cp_model.IntVar
		soft_constraints_map: Dict[str, Any], # cp_model.IntVar
		max_possible_score: int,
		output_path: str
	):
		"""
		Initializes the writer with the necessary solution components.
		"""
		self.solver = solver
		self.data = parsed_data
		self.x = model_variables
		self.soft_constraints_map = soft_constraints_map
		self.max_possible_score = max_possible_score
		self.output_path = output_path
		self.schedule_df = self._extract_schedule_dataframe()

	def process_and_write_solution(self) -> Tuple[pd.DataFrame, pd.DataFrame, int, int, List[str]]:
		"""
		Analyzes the solution and generates all necessary outputs, including
		the final Excel file and the data for the UI.
		"""
		summary_df = self._create_summary_dataframe()
		final_score, applied_constraints = self._analyze_soft_constraints()
		
		# Write the comprehensive, multi-sheet Excel report
		self._write_to_excel(summary_df)
		
		return self.schedule_df, summary_df, final_score, self.max_possible_score, applied_constraints

	def _extract_schedule_dataframe(self) -> pd.DataFrame:
		"""Constructs the primary schedule DataFrame from the solver's solution."""
		solution_rows = []
		for r_idx, resident_id in enumerate(self.data.residents):
			row_data = {"Resident": resident_id}
			for b_idx in range(NUM_BLOCKS):
				rotation_idx = self.solver.Value(self.x[r_idx, b_idx])
				rotation_name = self.data.idx_to_rotation[rotation_idx]
				row_data[f"Block_{b_idx + 1}"] = rotation_name
			solution_rows.append(row_data)

		df = pd.DataFrame(solution_rows)
		df["PGY"] = self.data.pgys
		return df

	def _create_summary_dataframe(self) -> pd.DataFrame:
		"""Creates the rotation distribution summary DataFrame."""
		block_columns = [f"Block_{i + 1}" for i in range(NUM_BLOCKS)]
		melted_df = self.schedule_df.melt(
			id_vars=["Resident"], value_vars=block_columns,
			var_name="Block", value_name="Rotation"
		)
		summary_df = (
			melted_df.groupby(["Rotation", "Block"])
			.size().unstack(fill_value=0).sort_index()
		)
		summary_df.index.name = None
		summary_df.columns.name = None
		return summary_df[block_columns]
		
	def _analyze_soft_constraints(self) -> Tuple[int, List[str]]:
		"""
		Analyzes the soft constraints map to calculate the final score and
		compile a list of all applied rewards and penalties.
		"""
		final_score = 0
		applied_constraints = []

		for description, variable in self.soft_constraints_map.items():
			if self.solver.Value(variable) == 1:
				# The condition for this soft constraint was met
				score_contribution = 0
				if "REWARD" in description:
					# Logic to determine the score value from the description
					score = 2 * REWARD_WEIGHT if "MICU" in description or "CCU" in description else REWARD_WEIGHT
					final_score += score
					applied_constraints.append(f"✅ {description}")
				elif "PENALTY" in description:
					# Logic to determine the score value from the description
					score = 2 * PENALTY_WEIGHT if "Senior" in description or "Registrar" in description else PENALTY_WEIGHT
					final_score += score
					applied_constraints.append(f"❌ {description}")
		
		return final_score, applied_constraints

	def _write_to_excel(self, summary_df: pd.DataFrame) -> None:
		"""Writes all generated data to a multi-sheet Excel file."""
		pgy_schedules = {}
		for level in sorted(self.schedule_df["PGY"].unique()):
			pgy_schedules[level] = self.schedule_df[self.schedule_df["PGY"] == level].drop(columns="PGY")

		with pd.ExcelWriter(self.output_path, engine="openpyxl") as writer:
			summary_df.to_excel(writer, sheet_name="Summary")
			self.schedule_df.drop(columns="PGY").to_excel(writer, sheet_name="FullSchedule", index=False)
			for pgy_level, df in pgy_schedules.items():
				df.to_excel(writer, sheet_name=pgy_level, index=False)