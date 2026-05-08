# scheduler/main.py

"""
Orchestrator for the Medical Rotation Scheduling Workflow.

This module provides the RotationScheduler class, which coordinates the full
pipeline: parsing input data, building the CP-SAT constraint model, invoking
the solver, and writing the output. It is the single entry point used by both
the Streamlit web interface (app.py) and the command-line standalone mode.

Standalone usage:
    python -m scheduler.main
    # Uses the default input file from sample_data/ and writes output to
    # the project root directory.
"""

import os
import pandas as pd
from typing import Any, List, Tuple

from scheduler.config import (
    APP_DIR,
    SAMPLE_DATA_DIR,
    INPUT_FILE,
    OUTPUT_SCHEDULE_FILE,
)
from scheduler.parser import RotationDataParser
from scheduler.model import ScheduleModelBuilder
from scheduler.writer import SolutionWriter


class RotationScheduler:
    """
    End-to-end coordinator for the medical rotation scheduling pipeline.

    This class wires together the parser, model builder, solver, and writer.
    Callers receive structured results and do not need to interact with the
    underlying OR-Tools API directly.

    Args:
        input_path: Absolute path to the input Excel file.
        output_path: Absolute path where the output Excel file will be written.
    """

    def __init__(self, input_path: str, output_path: str):
        self.input_path = input_path
        self.output_path = output_path

    def run(
        self,
    ) -> Tuple[bool, pd.DataFrame, pd.DataFrame, int, float, List[str], List[str], pd.DataFrame]:
        """
        Executes the full scheduling pipeline.

        Steps:
            1. Parse the input Excel file.
            2. Build the CP-SAT constraint model.
            3. Solve the model.
            4. If feasible, extract and write the solution.

        Returns:
            A tuple of:
                - success (bool): True if a feasible solution was found.
                - schedule_df: Full schedule DataFrame (empty on failure).
                - summary_df: Staffing summary DataFrame (empty on failure).
                - raw_score (int): Raw objective score (0 on failure).
                - normalized_score (float): Quality score 0.0-1.0 (0.0 on failure).
                - satisfied (List[str]): Satisfied soft constraint descriptions.
                - unsatisfied (List[str]): Unsatisfied soft constraint descriptions.
                - log_df: Constraint log DataFrame (empty on failure).
        """
        from ortools.sat.python import cp_model

        print("Step 1: Parsing input data...")
        parsed_data = RotationDataParser(self.input_path)
        print(f"         Loaded {parsed_data.num_residents} residents.")

        print("Step 2: Building the constraint model...")
        model_builder = ScheduleModelBuilder(parsed_data)
        model = model_builder.build_model()
        print("         Model construction complete.")

        print("Step 3: Solving...")
        solver = cp_model.CpSolver()
        status = solver.Solve(model)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            status_name = solver.StatusName(status)
            print(f"Step 4: Solution found — status: {status_name}")

            writer = SolutionWriter(
                solver=solver,
                parsed_data=parsed_data,
                model_variables=model_builder.x,
                soft_constraints_map=model_builder.soft_constraints_map,
                max_possible_score=model_builder.max_possible_score,
                output_path=self.output_path,
            )
            (
                schedule_df,
                summary_df,
                raw_score,
                normalized_score,
                satisfied,
                unsatisfied,
                log_df,
            ) = writer.process_and_write_solution()

            return True, schedule_df, summary_df, raw_score, normalized_score, satisfied, unsatisfied, log_df

        print("Step 4: No feasible solution found.")
        return False, pd.DataFrame(), pd.DataFrame(), 0, 0.0, [], [], pd.DataFrame()


# =============================================================================
# Standalone Entry Point
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m scheduler.main",
        description=(
            "Medical Residency Rotation Scheduler — command-line interface.\n"
            "Generates an optimised 13-block annual schedule from an Excel input file."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m scheduler.main\n"
            "  python -m scheduler.main --input sample_data/hmc_im_residency_sample_input.xlsx\n"
            "  python -m scheduler.main --input my_input.xlsx --output my_schedule.xlsx\n"
        ),
    )
    parser.add_argument(
        "--input", "-i",
        default=os.path.join(SAMPLE_DATA_DIR, INPUT_FILE),
        metavar="PATH",
        help=f"Path to the input Excel file (default: sample_data/{INPUT_FILE})",
    )
    parser.add_argument(
        "--output", "-o",
        default=os.path.join(APP_DIR, OUTPUT_SCHEDULE_FILE),
        metavar="PATH",
        help=f"Path for the output Excel file (default: ./{OUTPUT_SCHEDULE_FILE})",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  Medical Rotation Scheduler")
    print("=" * 60)
    print(f"  Input  : {args.input}")
    print(f"  Output : {args.output}\n")

    scheduler = RotationScheduler(input_path=args.input, output_path=args.output)
    (
        success, schedule_df, summary_df,
        raw_score, normalized_score,
        satisfied, unsatisfied, log_df,
    ) = scheduler.run()

    print()
    if success:
        print("=" * 60)
        print("  Schedule generated successfully.")
        print(f"  Residents scheduled : {len(schedule_df)}")
        print(f"  Raw score           : {raw_score}")
        print(f"  Normalized quality  : {normalized_score:.1%}")
        print(f"  Constraints met     : {len(satisfied)}")
        print(f"  Constraints missed  : {len(unsatisfied)}")
        print(f"  Output written to   : {args.output}")
        print("=" * 60)
    else:
        print("=" * 60)
        print("  No feasible solution found.")
        print("  Check input constraints for over-restriction.")
        print("=" * 60)
