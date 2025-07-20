# scheduler/main.py

import os
import pandas as pd
from typing import Any, List, Tuple

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
    def __init__(self, input_path: str, output_path: str):
        self.input_path = input_path
        self.output_path = output_path

    def run(self) -> Tuple[bool, pd.DataFrame, pd.DataFrame, int, float, List[str], List[str], pd.DataFrame]:
        from ortools.sat.python import cp_model

        print("Step 1: Parsing input data...")
        parsed_data = RotationDataParser(self.input_path)
        print(f"Successfully parsed data for {parsed_data.num_residents} residents.")

        print("Step 2: Building the constraint model...")
        model_builder = ScheduleModelBuilder(parsed_data)
        model = model_builder.build_model()
        print("Model construction complete.")

        print("Step 3: Solving the model...")
        solver = cp_model.CpSolver()
        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            status_name = solver.StatusName(status)
            print(f"Step 4: Solution found with status: {status_name}")
            
            writer = SolutionWriter(
                solver=solver,
                parsed_data=parsed_data,
                model_variables=model_builder.x,
                soft_constraints_map=model_builder.soft_constraints_map,
                max_possible_score=model_builder.max_possible_score,
                output_path=self.output_path
            )
            schedule_df, summary_df, raw_score, normalized_score, satisfied, unsatisfied, log_df = writer.process_and_write_solution()
            
            return True, schedule_df, summary_df, raw_score, normalized_score, satisfied, unsatisfied, log_df
        else:
            print("Step 4: No feasible solution found.")
            return False, pd.DataFrame(), pd.DataFrame(), 0, 0.0, [], [], pd.DataFrame()

if __name__ == '__main__':
    print("--- Running Scheduler in Standalone Mode ---")
    default_input = os.path.join(SAMPLE_DATA_DIR, INPUT_FILE)
    default_output = os.path.join(APP_DIR, OUTPUT_SCHEDULE_FILE)
    print(f"Using default input: {default_input}")
    print(f"Saving output to: {default_output}")
    
    scheduler = RotationScheduler(input_path=default_input, output_path=default_output)
    success, schedule_df, summary_df, raw_score, normalized_score, satisfied, unsatisfied, log_df = scheduler.run()
    