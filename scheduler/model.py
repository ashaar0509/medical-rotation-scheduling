# scheduler/model.py

"""
CP-SAT Model Builder for the Medical Rotation Scheduling Problem.

This module defines the class responsible for constructing the CP-SAT model.
It creates decision variables, adds all hard and soft constraints, and sets
the optimization objective based on the parsed input data and static configs.

The soft_constraints_map stores entries as (BoolVar, weight) tuples so that
the SolutionWriter can accurately reconstruct each constraint's score
contribution without re-inferring weights from description strings.
"""

from typing import Any, Dict, List, Tuple

from ortools.sat.python import cp_model

from scheduler.parser import RotationDataParser
from scheduler.config import (
    ALL_ROTATIONS,
    NUM_BLOCKS,
    GRADUATION_REQUIREMENTS,
    PER_BLOCK_MINIMUM_STAFFING,
    LEAVE_ELIGIBLE_ROTATIONS,
    LEAVE_ROTATION,
    COVERAGE_GROUPS,
    PENALTY_WEIGHT,
    REWARD_WEIGHT,
)


class ScheduleModelBuilder:
    """
    Constructs the complete CP-SAT model for the scheduling problem.

    This class takes structured data from the RotationDataParser and builds
    the corresponding constraint model, which can then be passed to the solver.

    Attributes:
        data: The parsed input data from RotationDataParser.
        model: The CP-SAT CpModel instance being constructed.
        x: Primary decision variables. x[r, b] holds the rotation index
           assigned to resident r in block b.
        y: Indicator variables. y[r, b, rot] is True iff resident r is
           assigned to rotation rot in block b.
        objective_terms: Accumulated terms for the objective function.
        soft_constraints_map: Maps a human-readable description to a
           (BoolVar, weight) tuple for post-solve analysis.
        max_possible_score: The theoretical maximum score if every reward
           fires and no penalty fires.
    """

    def __init__(self, parsed_data: RotationDataParser):
        """
        Initializes the model builder with parsed resident data.

        Args:
            parsed_data: An instance of RotationDataParser containing all
                         the necessary input data and mappings.
        """
        self.data = parsed_data
        self.model = cp_model.CpModel()

        # Primary and indicator decision variables.
        self.x: Dict[Tuple[int, int], Any] = {}
        self.y: Dict[Tuple[int, int, str], Any] = {}

        # Accumulated terms for the objective function.
        self.objective_terms: List[Any] = []

        # Maps description → (BoolVar, weight) for post-solve analysis.
        self.soft_constraints_map: Dict[str, Tuple[Any, int]] = {}
        self.max_possible_score: int = 0

    # =========================================================================
    # Public Interface
    # =========================================================================

    def build_model(self) -> cp_model.CpModel:
        """
        Constructs and returns the complete, solver-ready CP-SAT model.

        Returns:
            The fully constructed cp_model.CpModel instance.
        """
        self._create_decision_variables()
        self._apply_hard_constraints()
        self._set_objective_function()
        return self.model

    # =========================================================================
    # Variable Creation
    # =========================================================================

    def _create_decision_variables(self) -> None:
        """Creates the primary (x) and indicator (y) decision variables."""
        # x[r, b]: integer variable whose value is the index of the rotation
        # assigned to resident r in block b. Domain is restricted per resident.
        for r in range(self.data.num_residents):
            pgy = self.data.pgys[r]
            resident_id = self.data.residents[r]
            for b in range(NUM_BLOCKS):
                domain = self._get_assignment_domain(b, resident_id, pgy)
                self.x[r, b] = self.model.NewIntVarFromDomain(
                    domain, f"x_res{r}_blk{b}"
                )

        # y[r, b, rot]: Boolean indicator — True iff x[r, b] == rotation_index.
        for r in range(self.data.num_residents):
            for b in range(NUM_BLOCKS):
                for rot in ALL_ROTATIONS:
                    rot_idx = self.data.rotation_to_idx[rot]
                    var = self.model.NewBoolVar(f"y_res{r}_blk{b}_{rot}")
                    self.model.Add(self.x[r, b] == rot_idx).OnlyEnforceIf(var)
                    self.model.Add(self.x[r, b] != rot_idx).OnlyEnforceIf(var.Not())
                    self.y[r, b, rot] = var

        # Each resident must have exactly one rotation per block.
        for r in range(self.data.num_residents):
            for b in range(NUM_BLOCKS):
                self.model.AddExactlyOne(
                    [self.y[r, b, rot] for rot in ALL_ROTATIONS]
                )

    def _get_assignment_domain(
        self, b_idx: int, resident_id: str, pgy: str
    ) -> cp_model.Domain:
        """
        Determines the set of allowed rotation indices for a given
        resident-block slot, accounting for full and half-block leave.

        Args:
            b_idx: Zero-based block index.
            resident_id: The unique identifier for the resident.
            pgy: The resident's postgraduate year level.

        Returns:
            A cp_model.Domain containing the permitted rotation indices.
        """
        leave_info = self.data.leave_dict[resident_id]
        block_num = b_idx + 1

        # Full-block leave forces the LEAVE rotation.
        if block_num in leave_info["full"]:
            return cp_model.Domain.FromValues([self.data.leave_idx])

        eligible_rots = self.data.eligibility_map.get(pgy, set())

        # Half-block leave restricts eligible rotations to those that allow
        # a resident to still be on call during the other half.
        if block_num in leave_info["half"]:
            leave_allowed_rots = LEAVE_ELIGIBLE_ROTATIONS.get(pgy, set())
            eligible_rots = eligible_rots.intersection(leave_allowed_rots)

        eligible_indices = [
            self.data.rotation_to_idx[rot]
            for rot in eligible_rots
            if rot != LEAVE_ROTATION and rot in self.data.rotation_to_idx
        ]
        return cp_model.Domain.FromValues(eligible_indices)

    # =========================================================================
    # Hard Constraints
    # =========================================================================

    def _apply_hard_constraints(self) -> None:
        """Applies all mandatory, non-negotiable rules to the model."""
        self._add_hard_forced_and_forbidden_assignments()
        self._add_hard_graduation_requirements()
        self._add_hard_block_coverage_rules()
        self._add_hard_pgy_specific_rules()
        self._add_hard_consecutive_rotation_rules()
        self._add_hard_cross_batch_rules()
        self._add_hard_neuro_resident_rules()

    def _add_hard_forced_and_forbidden_assignments(self) -> None:
        """Applies pre-assignments specified in the input file.

        Forced assignments (including OR conditions) restrict x[r, b] to a
        set of allowed indices. Forbidden assignments exclude specific indices.
        """
        # Forced assignments: x[r, b] must equal one of the listed rotation indices.
        # A list with multiple entries encodes an OR condition.
        for (r, b), rot_list in self.data.forced_assignments.items():
            allowed_indices = [
                self.data.rotation_to_idx[rot_name]
                for rot_name in rot_list
                if rot_name in self.data.rotation_to_idx
            ]
            if allowed_indices:
                self.model.AddAllowedAssignments(
                    [self.x[r, b]],
                    [[idx] for idx in allowed_indices]
                )

        # Forbidden assignments: x[r, b] must not equal any forbidden index.
        for (r, b), rot_list in self.data.forbidden_assignments.items():
            for rot_name in rot_list:
                rot_idx = self.data.rotation_to_idx.get(rot_name)
                if rot_idx is not None:
                    self.model.Add(self.x[r, b] != rot_idx)

    def _add_hard_graduation_requirements(self) -> None:
        """Ensures each resident meets their PGY-specific block counts.

        For each PGYRequirement, the total number of blocks a resident spends
        in the named rotation group must fall within [min_blocks, max_blocks].
        """
        for r_idx in range(self.data.num_residents):
            pgy = self.data.pgys[r_idx]
            resident_id = self.data.residents[r_idx]
            full_leave_blocks = self.data.leave_dict[resident_id]["full"]

            for requirement in GRADUATION_REQUIREMENTS[pgy]:
                # Special case: R3 residents on full-block leave are exempt from
                # the elective group (Cardiology / ED / Medical Consultation).
                if (
                    pgy == "R3"
                    and set(requirement.rotations) == {"Cardiology", "ED", "Medical Consultation"}
                    and full_leave_blocks
                ):
                    continue

                total_in_group = sum(
                    self.y[r_idx, b_idx, rot]
                    for b_idx in range(NUM_BLOCKS)
                    for rot in requirement.rotations
                    if rot in self.data.rotation_to_idx
                )
                self.model.Add(total_in_group >= requirement.min_blocks)
                self.model.Add(total_in_group <= requirement.max_blocks)

    def _add_hard_block_coverage_rules(self) -> None:
        """Enforces minimum and exact staffing levels for every block.

        Covers:
        - Exact headcounts for Senior Rotation, Registrar Rotation, Medical Teams.
        - Minimum headcounts from PER_BLOCK_MINIMUM_STAFFING.
        - Weighted 2nd on-call coverage (accounting for half-leave blocks).
        - Floater coverage (Nephrology + Endocrine).
        """
        for b in range(NUM_BLOCKS):
            # Exact staffing for administrative/senior rotations.
            self.model.Add(
                sum(self.y[r, b, "Senior Rotation"] for r in range(self.data.num_residents)) == 10
            )
            self.model.Add(
                sum(self.y[r, b, "Registrar Rotation"] for r in range(self.data.num_residents)) == 20
            )

            # Medical Teams headcount is only enforced from block 4 onward
            # (blocks 1–3 are the R1 onboarding period).
            if b >= 3:
                self.model.Add(
                    sum(self.y[r, b, "Medical Teams"] for r in range(self.data.num_residents)) == 20
                )

            # Minimum staffing for all key clinical rotations.
            for rot, min_val in PER_BLOCK_MINIMUM_STAFFING.items():
                self.model.Add(
                    sum(self.y[r, b, rot] for r in range(self.data.num_residents)) >= min_val
                )

            # 2nd on-call weighted coverage: residents on half-leave contribute
            # 3 units; full-availability residents contribute 6 units. Minimum 60.
            self.model.Add(
                sum(
                    (3 if (b + 1) in self.data.leave_dict[self.data.residents[r]]["half"] else 6)
                    * self.y[r, b, rot]
                    for r in range(self.data.num_residents)
                    if self.data.pgys[r] != "R_NEURO"
                    for rot in COVERAGE_GROUPS["2ndOnCall"]
                ) >= 60
            )

            # Floater coverage (Nephrology + Endocrine): at least 10 residents.
            self.model.Add(
                sum(
                    self.y[r, b, rot]
                    for r in range(self.data.num_residents)
                    if self.data.pgys[r] != "R_NEURO"
                    for rot in COVERAGE_GROUPS["Floater"]
                ) >= 10
            )

    def _add_hard_pgy_specific_rules(self) -> None:
        """Adds rules specific to PGY levels.

        - All R1 residents must start Block 1 on Medical Teams (onboarding).
        - R2 residents cannot start Block 1 on Senior Rotation.
        - At least 25 residents must be on Medical Teams in Block 2.
        """
        med_teams_idx = self.data.rotation_to_idx["Medical Teams"]
        senior_idx = self.data.rotation_to_idx["Senior Rotation"]

        for r_idx in range(self.data.num_residents):
            pgy = self.data.pgys[r_idx]
            if pgy == "R1":
                self.model.Add(self.x[r_idx, 0] == med_teams_idx)
            elif pgy == "R2":
                self.model.Add(self.x[r_idx, 0] != senior_idx)

        self.model.Add(
            sum(self.y[r, 1, "Medical Teams"] for r in range(self.data.num_residents)) >= 25
        )

    def _add_hard_consecutive_rotation_rules(self) -> None:
        """Prevents residents from staying in certain rotations too long.

        - R1: No more than 5 consecutive Medical Teams blocks in any 6-block window.
        - R2/R3: Cannot do Senior Rotation in two consecutive blocks.
        """
        for r_idx in range(self.data.num_residents):
            pgy = self.data.pgys[r_idx]
            if pgy == "R1":
                for start in range(NUM_BLOCKS - 5):
                    self.model.Add(
                        sum(self.y[r_idx, b, "Medical Teams"] for b in range(start, start + 6)) <= 5
                    )
            if pgy in ("R2", "R3"):
                for b in range(NUM_BLOCKS - 1):
                    self.model.AddBoolOr([
                        self.y[r_idx, b, "Senior Rotation"].Not(),
                        self.y[r_idx, b + 1, "Senior Rotation"].Not(),
                    ])

    def _add_hard_cross_batch_rules(self) -> None:
        """Prevents MICU and CCU from being split across scheduling batches.

        Blocks 2, 4, 6, 8, 10 are batch boundaries. A resident cannot be in
        MICU or CCU in both the boundary block and the following block, as this
        would span two separate scheduling batches.
        """
        for r_idx in range(self.data.num_residents):
            for b_idx in [1, 3, 5, 7, 9]:
                if b_idx < NUM_BLOCKS - 1:
                    for rot in ["MICU", "CCU"]:
                        self.model.AddBoolOr([
                            self.y[r_idx, b_idx, rot].Not(),
                            self.y[r_idx, b_idx + 1, rot].Not(),
                        ])

    def _add_hard_neuro_resident_rules(self) -> None:
        """Applies the fixed schedule template for R_NEURO residents.

        Neurology residents follow a predetermined pattern:
        - Blocks 1–3: Medical Teams
        - Blocks 12–13: TRANSFER (off-site neurology rotation)
        """
        med_teams_idx = self.data.rotation_to_idx["Medical Teams"]
        transfer_idx = self.data.rotation_to_idx["TRANSFER"]

        for r_idx in range(self.data.num_residents):
            if self.data.pgys[r_idx] == "R_NEURO":
                self.model.Add(self.x[r_idx, 0] == med_teams_idx)
                self.model.Add(self.x[r_idx, 1] == med_teams_idx)
                self.model.Add(self.x[r_idx, 2] == med_teams_idx)
                self.model.Add(self.x[r_idx, 11] == transfer_idx)
                self.model.Add(self.x[r_idx, 12] == transfer_idx)

    # =========================================================================
    # Soft Constraints (Objective Function)
    # =========================================================================

    def _set_objective_function(self) -> None:
        """Builds the objective function from all soft constraint terms.

        Each soft constraint adds a weighted BoolVar to objective_terms.
        Positive weights are rewards; negative weights are penalties.
        The solver maximises the total.
        """
        self._add_soft_r1_penalties()
        self._add_soft_r2_rewards()
        self._add_soft_r3_penalties()
        self._add_soft_r4_penalties()
        self._add_soft_hem_onc_preference()
        self.model.Maximize(sum(self.objective_terms))

    def _register_soft_constraint(
        self, key: str, var: Any, weight: int
    ) -> None:
        """
        Registers a soft constraint variable and adds it to the objective.

        Stores (var, weight) in soft_constraints_map so the SolutionWriter
        can recover the exact weight without re-inferring it from strings.
        Tracks the maximum achievable score for normalisation.

        Args:
            key: Human-readable description of the constraint.
            var: The BoolVar that is True when the constraint is active.
            weight: Positive for a reward, negative for a penalty.
        """
        self.soft_constraints_map[key] = (var, weight)
        self.objective_terms.append(weight * var)
        if weight > 0:
            self.max_possible_score += weight

    def _add_soft_hem_onc_preference(self) -> None:
        """Rewards schedules where Hematology and Oncology are consecutive.

        Applies to any resident eligible for both rotations, regardless of PGY.
        Either ordering (Hema→Onco or Onco→Hema) earns the reward.
        Weight: +2 per consecutive pair.
        """
        for r_idx in range(self.data.num_residents):
            pgy = self.data.pgys[r_idx]
            is_eligible = (
                "Hematology" in self.data.eligibility_map[pgy]
                and "Oncology" in self.data.eligibility_map[pgy]
            )
            if not is_eligible:
                continue

            res_id = self.data.residents[r_idx]
            for b_idx in range(NUM_BLOCKS - 1):
                # Pattern A: Hematology → Oncology
                hema_onco = self.model.NewBoolVar(f"hema_onco_{r_idx}_{b_idx}")
                self.model.AddBoolAnd([
                    self.y[r_idx, b_idx, "Hematology"],
                    self.y[r_idx, b_idx + 1, "Oncology"],
                ]).OnlyEnforceIf(hema_onco)

                # Pattern B: Oncology → Hematology
                onco_hema = self.model.NewBoolVar(f"onco_hema_{r_idx}_{b_idx}")
                self.model.AddBoolAnd([
                    self.y[r_idx, b_idx, "Oncology"],
                    self.y[r_idx, b_idx + 1, "Hematology"],
                ]).OnlyEnforceIf(onco_hema)

                # Combined: reward fires if either pattern is active.
                is_consecutive = self.model.NewBoolVar(f"hem_onc_consecutive_{r_idx}_{b_idx}")
                self.model.AddBoolOr([hema_onco, onco_hema]).OnlyEnforceIf(is_consecutive)
                self.model.AddBoolAnd([
                    hema_onco.Not(), onco_hema.Not()
                ]).OnlyEnforceIf(is_consecutive.Not())

                key = (
                    f"REWARD: {res_id} has consecutive Hematology/Oncology "
                    f"(Blocks {b_idx + 1}-{b_idx + 2})"
                )
                self._register_soft_constraint(key, is_consecutive, 2 * REWARD_WEIGHT)

    def _add_soft_r1_penalties(self) -> None:
        """Penalises undesirable patterns for R1 residents.

        - 4 consecutive Medical Teams blocks in any window: penalty -1.
        - Consecutive Cardiology blocks: penalty -1.
        """
        for r_idx in range(self.data.num_residents):
            if self.data.pgys[r_idx] != "R1":
                continue
            res_id = self.data.residents[r_idx]

            for start in range(NUM_BLOCKS - 3):
                window = [self.y[r_idx, b, "Medical Teams"] for b in range(start, start + 4)]
                all_four = self.model.NewBoolVar(f"pen_r1_med4_{r_idx}_{start}")
                self.model.Add(sum(window) == 4).OnlyEnforceIf(all_four)
                self.model.Add(sum(window) != 4).OnlyEnforceIf(all_four.Not())
                key = (
                    f"PENALTY (R1): {res_id} in 4 consecutive Medical Teams "
                    f"(Blocks {start + 1}-{start + 4})"
                )
                self._register_soft_constraint(key, all_four, PENALTY_WEIGHT)

            for b_idx in range(NUM_BLOCKS - 1):
                is_consecutive = self._create_consecutive_bool(r_idx, b_idx, "Cardiology")
                key = (
                    f"PENALTY (R1): {res_id} in consecutive Cardiology "
                    f"(Blocks {b_idx + 1}-{b_idx + 2})"
                )
                self._register_soft_constraint(key, is_consecutive, PENALTY_WEIGHT)

    def _add_soft_r2_rewards(self) -> None:
        """Rewards desirable patterns for R2 residents.

        - Consecutive MICU blocks: reward +2 (continuity of care).
        - Consecutive CCU blocks: reward +2 (continuity of care).
        """
        for r_idx in range(self.data.num_residents):
            if self.data.pgys[r_idx] != "R2":
                continue
            res_id = self.data.residents[r_idx]

            for b_idx in range(NUM_BLOCKS - 1):
                micu_consecutive = self._create_consecutive_bool(r_idx, b_idx, "MICU")
                key_micu = (
                    f"REWARD (R2): {res_id} in consecutive MICU "
                    f"(Blocks {b_idx + 1}-{b_idx + 2})"
                )
                self._register_soft_constraint(key_micu, micu_consecutive, 2 * REWARD_WEIGHT)

                ccu_consecutive = self._create_consecutive_bool(r_idx, b_idx, "CCU")
                key_ccu = (
                    f"REWARD (R2): {res_id} in consecutive CCU "
                    f"(Blocks {b_idx + 1}-{b_idx + 2})"
                )
                self._register_soft_constraint(key_ccu, ccu_consecutive, 2 * REWARD_WEIGHT)

    def _add_soft_r3_penalties(self) -> None:
        """Penalises poor spacing of Senior Rotation blocks for R3 residents.

        - Consecutive Senior Rotation blocks: penalty -2.
        - Senior Rotation blocks with only a 1-block gap: penalty -1.
        """
        for r_idx in range(self.data.num_residents):
            if self.data.pgys[r_idx] != "R3":
                continue
            res_id = self.data.residents[r_idx]

            for b_idx in range(NUM_BLOCKS - 2):
                consecutive = self._create_consecutive_bool(r_idx, b_idx, "Senior Rotation")
                key_consecutive = (
                    f"PENALTY (R3): {res_id} in consecutive Senior Rotation "
                    f"(Blocks {b_idx + 1}-{b_idx + 2})"
                )
                self._register_soft_constraint(key_consecutive, consecutive, 2 * PENALTY_WEIGHT)

                gap1_var = self.model.NewBoolVar(f"pen_r3_senior_gap1_{r_idx}_{b_idx}")
                self.model.AddBoolAnd([
                    self.y[r_idx, b_idx, "Senior Rotation"],
                    self.y[r_idx, b_idx + 2, "Senior Rotation"],
                ]).OnlyEnforceIf(gap1_var)
                key_gap1 = (
                    f"PENALTY (R3): {res_id} in Senior Rotation with only 1 block gap "
                    f"(Blocks {b_idx + 1} & {b_idx + 3})"
                )
                self._register_soft_constraint(key_gap1, gap1_var, PENALTY_WEIGHT)

    def _add_soft_r4_penalties(self) -> None:
        """Penalises excessively long Registrar Rotation runs for R4 residents.

        Six or more consecutive Registrar Rotation blocks in any window: penalty -2.
        """
        for r_idx in range(self.data.num_residents):
            if self.data.pgys[r_idx] not in ("R4", "R4_Chiefs"):
                continue
            res_id = self.data.residents[r_idx]

            for start in range(NUM_BLOCKS - 5):
                window = [self.y[r_idx, b, "Registrar Rotation"] for b in range(start, start + 6)]
                too_long = self.model.NewBoolVar(f"pen_r4_reg6_{r_idx}_{start}")
                self.model.Add(sum(window) == 6).OnlyEnforceIf(too_long)
                self.model.Add(sum(window) != 6).OnlyEnforceIf(too_long.Not())
                key = (
                    f"PENALTY (R4): {res_id} in >5 consecutive Registrar Rotations "
                    f"(Blocks {start + 1}-{start + 6})"
                )
                self._register_soft_constraint(key, too_long, 2 * PENALTY_WEIGHT)

    # =========================================================================
    # Helpers
    # =========================================================================

    def _create_consecutive_bool(self, r_idx: int, b_idx: int, rot: str) -> Any:
        """
        Creates and returns a BoolVar that is True iff a resident is assigned
        to the same rotation in two consecutive blocks.

        Args:
            r_idx: Zero-based resident index.
            b_idx: Zero-based index of the first block in the pair.
            rot: Name of the rotation to check.

        Returns:
            A BoolVar that is True when y[r_idx, b_idx, rot] and
            y[r_idx, b_idx+1, rot] are both True.
        """
        is_consecutive = self.model.NewBoolVar(f"consecutive_{r_idx}_{b_idx}_{rot}")
        self.model.AddBoolAnd([
            self.y[r_idx, b_idx, rot],
            self.y[r_idx, b_idx + 1, rot],
        ]).OnlyEnforceIf(is_consecutive)
        self.model.AddBoolOr([
            self.y[r_idx, b_idx, rot].Not(),
            self.y[r_idx, b_idx + 1, rot].Not(),
        ]).OnlyEnforceIf(is_consecutive.Not())
        return is_consecutive
