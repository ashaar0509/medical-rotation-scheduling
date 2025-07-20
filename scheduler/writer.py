# scheduler/writer.py

import pandas as pd
from typing import Any, Dict, List, Tuple

from scheduler.parser import RotationDataParser
from scheduler.config import NUM_BLOCKS, REWARD_WEIGHT, PENALTY_WEIGHT

class SolutionWriter:
	def __init__(
		self,
		solver: Any,
		parsed_data: RotationDataParser,
		model_variables: Dict[Tuple[int, int], Any],
		soft_constraints_map: Dict[str, Any],
		max_possible_score: int,
		output_path: str
	):
		self.solver = solver
		self.data = parsed_data
		self.x = model_variables
		self.soft_constraints_map = soft_constraints_map
		self.max_possible_score = max_possible_score
		self.output_path = output_path
		self.schedule_df = self._extract_schedule_dataframe()

	def process_and_write_solution(self) -> Tuple[pd.DataFrame, pd.DataFrame, int, int, List[str], List[str], pd.DataFrame]:
		"""
		Analyzes the solution and generates all necessary outputs.
		"""
		summary_df = self._create_summary_dataframe()
		final_score, satisfied, unsatisfied, log_df = self._analyze_soft_constraints()
		
		self._write_to_excel(summary_df, log_df)
		
		return self.schedule_df, summary_df, final_score, self.max_possible_score, satisfied, unsatisfied, log_df

	def _analyze_soft_constraints(self) -> Tuple[int, List[str], List[str], pd.DataFrame]:
		"""
		Analyzes soft constraints to calculate the score, sort constraints
		into satisfied/unsatisfied lists, and create a full log DataFrame.
		"""
		final_score = 0
		satisfied_constraints = []
		unsatisfied_constraints = []
		log_records = []

		for description, variable in self.soft_constraints_map.items():
			is_satisfied = self.solver.Value(variable) == 1
			score_contribution = 0
			
			if "REWARD" in description:
				weight = 2 * REWARD_WEIGHT if "MICU" in description or "CCU" in description else REWARD_WEIGHT
				if is_satisfied:
					final_score += weight
					score_contribution = weight
					satisfied_constraints.append(f"{description}")
				else:
					unsatisfied_constraints.append(f"{description}")

			elif "PENALTY" in description:
				weight = 2 * PENALTY_WEIGHT if "Senior" in description or "Registrar" in description else PENALTY_WEIGHT
				if is_satisfied:
					final_score += weight
					score_contribution = weight
					satisfied_constraints.append(f"{description}")
				else:
					unsatisfied_constraints.append(f"{description} (Penalty Avoided)")
			
			log_records.append({
				"Constraint": description,
				"Status": "Satisfied" if is_satisfied else "Not Satisfied",
				"Score Contribution": score_contribution
			})
			
		log_df = pd.DataFrame(log_records)
		return final_score, satisfied_constraints, unsatisfied_constraints, log_df

	def _write_to_excel(self, summary_df: pd.DataFrame, log_df: pd.DataFrame) -> None:
		"""Writes all generated data to a multi-sheet Excel file."""
		with pd.ExcelWriter(self.output_path, engine="openpyxl") as writer:
			log_df.to_excel(writer, sheet_name="ObjectiveLog", index=False)
			summary_df.to_excel(writer, sheet_name="Summary")
			self.schedule_df.drop(columns="PGY").to_excel(writer, sheet_name="FullSchedule", index=False)
			
			pgy_schedules = {
				level: self.schedule_df[self.schedule_df["PGY"] == level].drop(columns="PGY")
				for level in sorted(self.schedule_df["PGY"].unique())
			}
			for pgy_level, df in pgy_schedules.items():
				df.to_excel(writer, sheet_name=pgy_level, index=False)

	def _extract_schedule_dataframe(self) -> pd.DataFrame:
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