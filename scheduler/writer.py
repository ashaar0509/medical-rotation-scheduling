# scheduler/writer.py

"""
Solution Writer for the Medical Rotation Scheduling Problem.

This module is responsible for all post-solve processing: extracting the
schedule from the solver, analysing soft constraint outcomes, computing
quality scores, and writing the final multi-sheet Excel report.

The soft_constraints_map is expected to contain (BoolVar, weight) tuples,
as populated by ScheduleModelBuilder._register_soft_constraint(). This
eliminates the need to infer weights from description strings.
"""

import pandas as pd
from typing import Any, Dict, List, Tuple

from scheduler.parser import RotationDataParser
from scheduler.config import NUM_BLOCKS


class SolutionWriter:
    """
    Processes a solved CP-SAT model and writes the results to Excel.

    Attributes:
        solver: The solved CpSolver instance.
        data: Parsed input data from RotationDataParser.
        x: Primary decision variables from the model.
        soft_constraints_map: Maps description → (BoolVar, weight).
        max_possible_score: Theoretical maximum score (all rewards, no penalties).
        output_path: File path for the Excel output.
        schedule_df: DataFrame built from the solver solution.
    """

    def __init__(
        self,
        solver: Any,
        parsed_data: RotationDataParser,
        model_variables: Dict[Tuple[int, int], Any],
        soft_constraints_map: Dict[str, Tuple[Any, int]],
        max_possible_score: int,
        output_path: str,
    ):
        self.solver = solver
        self.data = parsed_data
        self.x = model_variables
        self.soft_constraints_map = soft_constraints_map
        self.max_possible_score = max_possible_score
        self.output_path = output_path
        self.schedule_df = self._extract_schedule_dataframe()

    # =========================================================================
    # Public Interface
    # =========================================================================

    def process_and_write_solution(
        self,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, int, float, List[str], List[str], pd.DataFrame]:
        """
        Runs all post-solve processing and writes the Excel report.

        Returns:
            A tuple of:
                - schedule_df: Full schedule as a DataFrame.
                - summary_df: Per-rotation, per-block staffing counts.
                - raw_score: Sum of all reward/penalty contributions.
                - normalized_score: raw_score / max_possible_score (0.0-1.0+).
                - satisfied: List of human-readable satisfied constraint strings.
                - unsatisfied: List of human-readable unsatisfied constraint strings.
                - log_df: DataFrame with one row per soft constraint for download.
        """
        summary_df = self._create_summary_dataframe()
        raw_score, normalized_score, satisfied, unsatisfied, log_df = (
            self._analyze_soft_constraints()
        )
        self._write_to_excel(summary_df, log_df)
        return self.schedule_df, summary_df, raw_score, normalized_score, satisfied, unsatisfied, log_df

    # =========================================================================
    # Schedule Extraction
    # =========================================================================

    def _extract_schedule_dataframe(self) -> pd.DataFrame:
        """
        Reads the solver's variable values and constructs the schedule DataFrame.

        Returns:
            A DataFrame with columns: Resident, PGY, Block_1 ... Block_13.
        """
        rows = []
        for r_idx, resident_id in enumerate(self.data.residents):
            row = {"Resident": resident_id}
            for b_idx in range(NUM_BLOCKS):
                rotation_idx = self.solver.Value(self.x[r_idx, b_idx])
                row[f"Block_{b_idx + 1}"] = self.data.idx_to_rotation[rotation_idx]
            rows.append(row)

        df = pd.DataFrame(rows)
        df.insert(1, "PGY", self.data.pgys)
        return df

    def _create_summary_dataframe(self) -> pd.DataFrame:
        """
        Builds a rotation x block staffing count table.

        Returns:
            A DataFrame indexed by rotation name with columns Block_1 ... Block_13,
            showing how many residents are on each rotation per block.
        """
        block_columns = [f"Block_{i + 1}" for i in range(NUM_BLOCKS)]
        melted = self.schedule_df.melt(
            id_vars=["Resident"],
            value_vars=block_columns,
            var_name="Block",
            value_name="Rotation",
        )
        summary = (
            melted.groupby(["Rotation", "Block"])
            .size()
            .unstack(fill_value=0)
            .sort_index()
        )
        summary.index.name = None
        summary.columns.name = None
        return summary[block_columns]

    # =========================================================================
    # Soft Constraint Analysis
    # =========================================================================

    def _analyze_soft_constraints(
        self,
    ) -> Tuple[int, float, List[str], List[str], pd.DataFrame]:
        """
        Evaluates each soft constraint against the solver solution.

        Uses the (BoolVar, weight) tuples stored in soft_constraints_map to
        compute the exact score contribution without string-matching heuristics.

        Returns:
            raw_score: Total score (rewards minus penalties incurred).
            normalized_score: raw_score / max_possible_score.
            satisfied: Descriptions of constraints whose BoolVar is True.
            unsatisfied: Descriptions of constraints whose BoolVar is False.
            log_df: DataFrame with columns [Constraint, Status, Score Contribution].
        """
        raw_score = 0
        satisfied: List[str] = []
        unsatisfied: List[str] = []
        log_records = []

        for description, (variable, weight) in self.soft_constraints_map.items():
            is_active = self.solver.Value(variable) == 1
            score_contribution = weight if is_active else 0
            raw_score += score_contribution

            is_reward = weight > 0

            if is_active:
                satisfied.append(f"{'✅' if is_reward else '❌'} {description}")
            else:
                if is_reward:
                    unsatisfied.append(f"➖ {description}")
                else:
                    unsatisfied.append(f"👍 {description} (Penalty Avoided)")

            log_records.append({
                "Constraint": description,
                "Status": "Active" if is_active else "Inactive",
                "Score Contribution": score_contribution,
            })

        if self.max_possible_score > 0:
            normalized_score = raw_score / self.max_possible_score
        else:
            normalized_score = 1.0 if raw_score >= 0 else 0.0

        return raw_score, normalized_score, satisfied, unsatisfied, pd.DataFrame(log_records)

    # =========================================================================
    # Excel Output
    # =========================================================================

    def _write_to_excel(self, summary_df: pd.DataFrame, log_df: pd.DataFrame) -> None:
        """
        Writes the full solution to a multi-sheet Excel workbook.

        Sheets produced:
            FullSchedule  - All residents across all 13 blocks.
            Summary       - Rotation x block staffing counts.
            ObjectiveLog  - Per-constraint score contributions.
            <PGY level>   - One sheet per PGY level (R1, R2, R3 ...).

        Args:
            summary_df: The rotation staffing summary DataFrame.
            log_df: The soft constraint log DataFrame.
        """
        with pd.ExcelWriter(self.output_path, engine="openpyxl") as writer:
            self.schedule_df.drop(columns="PGY").to_excel(
                writer, sheet_name="FullSchedule", index=False
            )
            summary_df.to_excel(writer, sheet_name="Summary")
            log_df.to_excel(writer, sheet_name="ObjectiveLog", index=False)

            for pgy_level in sorted(self.schedule_df["PGY"].unique()):
                pgy_df = (
                    self.schedule_df[self.schedule_df["PGY"] == pgy_level]
                    .drop(columns="PGY")
                )
                pgy_df.to_excel(writer, sheet_name=pgy_level, index=False)
