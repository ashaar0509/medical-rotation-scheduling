# scheduler/main.py

"""
Main Orchestrator for the Medical Rotation Scheduling Application.

This module contains the primary class that drives the scheduling process,
coordinating the parser, model builder, solver, and writer modules. It is
designed to be the main point of interaction for any user interface, such as
the Streamlit application.
"""

import os
import pandas as pd
from ortools.sat.python import cp_model
from typing import Tuple

# Import the refactored modules and configuration constants
from scheduler.config import (
	APP_DIR,
	SAMPLE_DATA_DIR,
	INPUT_FILE,
	OUTPUT_SCHEDULE_FILE
)
from scheduler.parser import RotationDataParser
from scheduler.model import ScheduleModelBuilder
from scheduler.writer import SolutionWriter

class RotationScheduler:
	"""
	Orchestrates the end-to-end rotation scheduling workflow.
	"""

	def __init__(self, input_path: str, output_path: str):
		"""
		Initializes the scheduler with specified file paths.

		Args:
			input_path: The full path to the input Excel file.
			output_path: The full path where the output Excel file will be saved.
		"""
		self.input_path = input_path
		self.output_path = output_path

	def run(self) -> Tuple[bool, pd.DataFrame, pd.DataFrame]:
		"""
		Executes the full scheduling workflow and returns the results.

		The process is executed in four distinct steps:
		1.  **Load**: Data is parsed from the source file.
		2.  **Build**: The CP-SAT model is constructed with all constraints.
		3.  **Solve**: The solver attempts to find a feasible/optimal solution.
		4.  **Write**: If a solution is found, it is formatted and exported.

		Returns:
			A tuple containing:
			- A boolean indicating if a solution was found.
			- The main schedule DataFrame.
			- The summary/distribution DataFrame.
			Returns (False, pd.DataFrame(), pd.DataFrame()) on failure.
		"""
		# 1. LOAD: Parse the input data.
		print("Step 1: Parsing input data...")
		parsed_data = RotationDataParser(self.input_path)
		print(f"Successfully parsed data for {parsed_data.num_residents} residents.")

		# 2. BUILD: Construct the CP-SAT model.
		print("Step 2: Building the constraint model...")
		model_builder = ScheduleModelBuilder(parsed_data)
		model = model_builder.build_model()
		print("Model construction complete.")

		# 3. SOLVE: Run the CP-SAT solver on the constructed model.
		print("Step 3: Solving the model... (This may take a few moments)")
		solver = cp_model.CpSolver()
		status = solver.Solve(model)

		# 4. PROCESS & WRITE: Handle the solver's result.
		if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
			status_name = solver.StatusName(status)
			print(f"Step 4: Solution found with status: {status_name}")
			
			writer = SolutionWriter(
				solver=solver,
				parsed_data=parsed_data,
				model_variables=model_builder.x
			)
			schedule_df, summary_df = writer.write_to_excel(self.output_path)
			
			return True, schedule_df, summary_df
		else:
			print("Step 4: No feasible solution found.")
			return False, pd.DataFrame(), pd.DataFrame()

# ============================================================================
# Example of Standalone Execution
# ============================================================================
if __name__ == '__main__':
	"""
	This block allows the scheduler to be run directly from the command line,
	which is useful for testing or for environments without a UI.
	"""
	
	print("--- Running Scheduler in Standalone Mode ---")
	
	# Define the full paths for the default input and output files.
	default_input = os.path.join(SAMPLE_DATA_DIR, INPUT_FILE)
	default_output = os.path.join(APP_DIR, OUTPUT_SCHEDULE_FILE)
	
	print(f"Using default input: {default_input}")
	print(f"Using default output: {default_output}")
	
	# Instantiate and run the scheduler.
	scheduler = RotationScheduler(input_path=default_input, output_path=default_output)
	success, _, _ = scheduler.run()
	
	if success:
		print("--- Scheduler finished successfully. ---")
	else:
		print("--- Scheduler failed to find a solution. ---")