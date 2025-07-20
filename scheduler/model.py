# scheduler/model.py

"""
CP-SAT Model Builder for the Medical Rotation Scheduling Problem.

This module defines the class responsible for constructing the CP-SAT model.
It creates decision variables, adds all hard and soft constraints, and sets
the optimization objective based on the parsed input data and static configs.
"""

from ortools.sat.python import cp_model
from typing import List, Dict, Tuple, Any

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
	REWARD_WEIGHT
)

class ScheduleModelBuilder:
	"""
	Constructs the complete CP-SAT model for the scheduling problem.

	This class takes structured data from the RotationDataParser and builds
	the corresponding constraint model, which can then be passed to the solver.
	"""

	def __init__(self, parsed_data: RotationDataParser):
		"""
		Initializes the model builder.

		Args:
			parsed_data: An instance of RotationDataParser containing all
						 the necessary input data and mappings.
		"""
		self.data = parsed_data
		self.model = cp_model.CpModel()

		# Decision variables will be stored in these dictionaries.
		# x: Main assignment variable mapping (resident, block) to a rotation_idx.
		self.x: Dict[Tuple[int, int], cp_model.IntVar] = {}
		# y: Boolean indicator variables for specific assignments.
		self.y: Dict[Tuple[int, int, str], cp_model.IntVar] = {}

		# The list of terms to be summed for the final objective function.
		self.objective_terms: List[Any] = []

		# This map will store soft constraint variables for later analysis.
		self.soft_constraints_map: Dict[str, cp_model.IntVar] = {}
		
	def build_model(self) -> cp_model.CpModel:
		"""
		Constructs and returns the complete, solved-ready CP-SAT model.

		This is the main public method for this class and executes the entire
		model construction workflow.
		
		Returns:
			The fully constructed cp_model.CpModel instance.
		"""
		self._create_decision_variables()
		self._apply_hard_constraints()
		self._set_objective_function()
		return self.model

	def _create_decision_variables(self) -> None:
		"""
		Creates the core decision and indicator variables for the model.
		"""
		# --- Primary Assignment Variables (x) ---
		# x[r, b] is an integer variable representing the rotation index
		# assigned to resident `r` in block `b`.
		for r in range(self.data.num_residents):
			pgy = self.data.pgys[r]
			resident_id = self.data.residents[r]
			for b in range(NUM_BLOCKS):
				domain = self._get_assignment_domain(b, resident_id, pgy)
				self.x[r, b] = self.model.NewIntVarFromDomain(
					domain, f"x_res{r}_blk{b}"
				)

		# --- Indicator Variables (y) ---
		# y[r, b, rot] is a boolean variable that is true if and only if
		# resident `r` is assigned to rotation `rot` in block `b`.
		for r in range(self.data.num_residents):
			for b in range(NUM_BLOCKS):
				for rot in ALL_ROTATIONS:
					rot_idx = self.data.rotation_to_idx[rot]
					var = self.model.NewBoolVar(f"y_res{r}_blk{b}_{rot}")
					# Link the indicator variable to the primary variable.
					self.model.Add(self.x[r, b] == rot_idx).OnlyEnforceIf(var)
					self.model.Add(self.x[r, b] != rot_idx).OnlyEnforceIf(var.Not())
					self.y[r, b, rot] = var

		# --- Fundamental Constraint: One Rotation Per Block ---
		# Each resident must be assigned to exactly one rotation per block.
		for r in range(self.data.num_residents):
			for b in range(NUM_BLOCKS):
				self.model.AddExactlyOne(
					[self.y[r, b, rot] for rot in ALL_ROTATIONS]
				)

	def _get_assignment_domain(
		self, b_idx: int, resident_id: str, pgy: str
	) -> Any:
		"""
		Determines the set of allowed rotation indices for a given
		resident-block slot, considering leaves and PGY eligibility.
		
		Args:
			b_idx: The integer index of the block.
			resident_id: The string ID of the resident.
			pgy: The PGY level of the resident.

		Returns:
			A cp_model.Domain object containing the allowed rotation indices.
		"""
		leave_info = self.data.leave_dict[resident_id]
		block_num = b_idx + 1  # Convert 0-indexed block to 1-indexed

		# If the resident has a full-block leave, they can only be assigned LEAVE.
		if block_num in leave_info["full"]:
			return cp_model.Domain.FromValues([self.data.leave_idx])

		# Start with all rotations eligible for the resident's PGY level.
		eligible_rots = self.data.eligibility_map.get(pgy, set())

		# If it is a half-leave block, the cp_model.domain is restricted further to
		# only those rotations explicitly allowed during leave.
		if block_num in leave_info["half"]:
			leave_allowed_rots = LEAVE_ELIGIBLE_ROTATIONS.get(pgy, set())
			eligible_rots = eligible_rots.intersection(leave_allowed_rots)

		# Convert rotation names to indices, always excluding the LEAVE rotation
		# itself, as it's handled by the full-leave case above.
		eligible_indices = [
			self.data.rotation_to_idx[rot]
			for rot in eligible_rots
			if rot != LEAVE_ROTATION and rot in self.data.rotation_to_idx
		]
		return cp_model.Domain.FromValues(eligible_indices)

	def _apply_hard_constraints(self) -> None:
		"""
		Applies all absolute, non-negotiable rules to the model by calling
		the respective specialized constraint methods.
		"""
		self._add_hard_forced_and_forbidden_assignments()
		self._add_hard_graduation_requirements()
		self._add_hard_block_coverage_rules()
		self._add_hard_pgy_specific_rules()
		self._add_hard_consecutive_rotation_rules()
		self._add_hard_cross_batch_rules()
		self._add_hard_neuro_resident_rules()

	def _add_hard_forced_and_forbidden_assignments(self) -> None:
		"""Applies pre-assignments specified in the input file."""
		for (r, b), rot_name in self.data.forced_assignments.items():
			rot_idx = self.data.rotation_to_idx.get(rot_name)
			if rot_idx is not None:
				self.model.Add(self.x[r, b] == rot_idx)

		for (r, b), rot_name in self.data.forbidden_assignments.items():
			rot_idx = self.data.rotation_to_idx.get(rot_name)
			if rot_idx is not None:
				self.model.Add(self.x[r, b] != rot_idx)

	def _add_hard_graduation_requirements(self) -> None:
		"""Ensures each resident meets their PGY-specific block counts."""
		for r_idx in range(self.data.num_residents):
			pgy = self.data.pgys[r_idx]
			resident_id = self.data.residents[r_idx]
			full_leave_blocks = self.data.leave_dict[resident_id]["full"]

			for requirement in GRADUATION_REQUIREMENTS[pgy]:
				# Special exemption for R3s on a specific elective group
				# if they have taken a full block of leave.
				if (
					pgy == "R3"
					and set(requirement.rotations) == {"Cardiology", "ED", "Medical Consultation"}
					and full_leave_blocks
				):
					continue

				total_rotations_in_group = sum(
					self.y[r_idx, b_idx, rot]
					for b_idx in range(NUM_BLOCKS)
					for rot in requirement.rotations
					if rot in self.data.rotation_to_idx
				)
				
				self.model.Add(total_rotations_in_group >= requirement.min_blocks)
				self.model.Add(total_rotations_in_group <= requirement.max_blocks)

	def _add_hard_block_coverage_rules(self) -> None:
		"""Enforces minimum and exact staffing for rotations in each block."""
		for b in range(NUM_BLOCKS):
			# Exact counts for critical on-call rotations
			self.model.Add(sum(self.y[r, b, "Senior Rotation"] for r in range(self.data.num_residents)) == 10)
			self.model.Add(sum(self.y[r, b, "Registrar Rotation"] for r in range(self.data.num_residents)) == 20)

			# Coverage for Medical Teams (stricter after the first 3 blocks)
			if b >= 3:
				self.model.Add(sum(self.y[r, b, "Medical Teams"] for r in range(self.data.num_residents)) == 20)

			# Minimum unweighted staffing for other core rotations
			for rot, min_val in PER_BLOCK_MINIMUM_STAFFING.items():
				self.model.Add(sum(self.y[r, b, rot] for r in range(self.data.num_residents)) >= min_val)

			# Weighted coverage for the 2nd On-Call group
			# A resident on half-leave contributes 3 points; otherwise 6.
			# R_NEURO residents are excluded from this on-call pool.
			self.model.Add(
				sum(
					(3 if (b + 1) in self.data.leave_dict[self.data.residents[r]]["half"] else 6) *
					self.y[r, b, rot]
					for r in range(self.data.num_residents) if self.data.pgys[r] != "R_NEURO"
					for rot in COVERAGE_GROUPS["2ndOnCall"]
				) >= 60
			)

			# Unweighted coverage for the Floater group
			self.model.Add(
				sum(
					self.y[r, b, rot]
					for r in range(self.data.num_residents) if self.data.pgys[r] != "R_NEURO"
					for rot in COVERAGE_GROUPS["Floater"]
				) >= 10
			)

	def _add_hard_pgy_specific_rules(self) -> None:
		"""Adds rules specific to PGY levels, like first-block assignments."""
		med_teams_idx = self.data.rotation_to_idx["Medical Teams"]
		senior_idx = self.data.rotation_to_idx["Senior Rotation"]

		for r_idx in range(self.data.num_residents):
			pgy = self.data.pgys[r_idx]
			if pgy == "R1":
				self.model.Add(self.x[r_idx, 0] == med_teams_idx)
			elif pgy == "R2":
				self.model.Add(self.x[r_idx, 0] != senior_idx)

		# Special rule for Block 2: must have high coverage on Medical Teams.
		self.model.Add(sum(self.y[r, 1, "Medical Teams"] for r in range(self.data.num_residents)) >= 25)

	def _add_hard_consecutive_rotation_rules(self) -> None:
		"""Prevents residents from being in certain rotations for too long."""
		for r_idx in range(self.data.num_residents):
			pgy = self.data.pgys[r_idx]
			# R1s cannot do 6 consecutive Medical Teams blocks.
			if pgy == "R1":
				for start in range(NUM_BLOCKS - 5):
					self.model.Add(sum(self.y[r_idx, b, "Medical Teams"] for b in range(start, start + 6)) <= 5)

			# R2s and R3s cannot do consecutive Senior Rotation blocks.
			if pgy in ("R2", "R3"):
				for b in range(NUM_BLOCKS - 1):
					self.model.AddBoolOr([
						self.y[r_idx, b, "Senior Rotation"].Not(),
						self.y[r_idx, b + 1, "Senior Rotation"].Not()
					])

	def _add_hard_cross_batch_rules(self) -> None:
		"""Prevents certain 2-block rotations from being split across batches."""
		# Batches are blocks (1,2), (3,4), etc. The transitions to check
		# are at the end of blocks 1, 3, 5, 7, 9.
		for r_idx in range(self.data.num_residents):
			for b_idx in [1, 3, 5, 7, 9]:
				if b_idx < NUM_BLOCKS - 1:
					for rot in ["AMAU", "CCU"]:
						self.model.AddBoolOr([
							self.y[r_idx, b_idx, rot].Not(),
							self.y[r_idx, b_idx + 1, rot].Not()
						])

	def _add_hard_neuro_resident_rules(self) -> None:
		"""Applies the fixed schedule template for R_NEURO residents."""
		med_teams_idx = self.data.rotation_to_idx["Medical Teams"]
		transfer_idx = self.data.rotation_to_idx["TRANSFER"]

		for r_idx in range(self.data.num_residents):
			if self.data.pgys[r_idx] == "R_NEURO":
				# First three blocks must be Medical Teams.
				self.model.Add(self.x[r_idx, 0] == med_teams_idx)
				self.model.Add(self.x[r_idx, 1] == med_teams_idx)
				self.model.Add(self.x[r_idx, 2] == med_teams_idx)

				# Last two blocks must be TRANSFER.
				self.model.Add(self.x[r_idx, 11] == transfer_idx)
				self.model.Add(self.x[r_idx, 12] == transfer_idx)

	def _set_objective_function(self) -> None:
		"""
		Defines the soft constraints (rewards and penalties) that guide the
		solver towards a more desirable solution among all feasible ones.
		"""
		self._add_soft_r1_penalties()
		self._add_soft_r2_rewards()
		self._add_soft_r3_penalties()
		self._add_soft_r4_penalties()

		# The final objective is to maximize the sum of all collected terms.
		self.model.Maximize(sum(self.objective_terms))

	def _add_soft_r1_penalties(self) -> None:
		"""Penalizes undesirable schedules for R1 residents."""
		for r_idx in range(self.data.num_residents):
			if self.data.pgys[r_idx] == "R1":
				# Penalize 4 consecutive Medical Teams blocks.
				for start in range(NUM_BLOCKS - 3):
					window = [self.y[r_idx, b, "Medical Teams"] for b in range(start, start + 4)]
					all_four = self.model.NewBoolVar(f"pen_r1_med4_{r_idx}_{start}")
					self.model.Add(sum(window) == 4).OnlyEnforceIf(all_four)
					self.model.Add(sum(window) != 4).OnlyEnforceIf(all_four.Not())
					self.objective_terms.append(PENALTY_WEIGHT * all_four)

				# Penalize consecutive Cardiology blocks.
				for b_idx in range(NUM_BLOCKS - 1):
					is_consecutive = self._create_consecutive_bool(r_idx, b_idx, "Cardiology")
					self.objective_terms.append(PENALTY_WEIGHT * is_consecutive)

	def _add_soft_r2_rewards(self) -> None:
		"""Rewards desirable schedules for R2 residents."""
		for r_idx in range(self.data.num_residents):
			if self.data.pgys[r_idx] == "R2":
				# Strongly reward completing 2-block ICU rotations consecutively.
				for b_idx in range(NUM_BLOCKS - 1):
					micu_consecutive = self._create_consecutive_bool(r_idx, b_idx, "MICU")
					self.objective_terms.append(2 * REWARD_WEIGHT * micu_consecutive)

					ccu_consecutive = self._create_consecutive_bool(r_idx, b_idx, "CCU")
					self.objective_terms.append(2 * REWARD_WEIGHT * ccu_consecutive)

	def _add_soft_r3_penalties(self) -> None:
		"""Penalizes poor spacing of Senior rotations for R3s."""
		for r_idx in range(self.data.num_residents):
			if self.data.pgys[r_idx] == "R3":
				# Penalize Senior rotations that are too close together.
				for b_idx in range(NUM_BLOCKS - 2):
					# Consecutive (strongly penalized)
					consecutive = self._create_consecutive_bool(r_idx, b_idx, "Senior Rotation")
					self.objective_terms.append(2 * PENALTY_WEIGHT * consecutive)

					# Spaced by only one block (less penalized)
					gap1_var = self.model.NewBoolVar(f"pen_r3_senior_gap1_{r_idx}_{b_idx}")
					self.model.AddBoolAnd([
						self.y[r_idx, b_idx, "Senior Rotation"],
						self.y[r_idx, b_idx + 2, "Senior Rotation"]
					]).OnlyEnforceIf(gap1_var)
					self.objective_terms.append(PENALTY_WEIGHT * gap1_var)

	def _add_soft_r4_penalties(self) -> None:
		"""Penalizes undesirable schedules for R4 residents."""
		for r_idx in range(self.data.num_residents):
			if self.data.pgys[r_idx] in ("R4", "R4_Chiefs"):
				# Penalize more than 5 consecutive Registrar rotations.
				for start in range(NUM_BLOCKS - 5):
					window = [self.y[r_idx, b, "Registrar Rotation"] for b in range(start, start + 6)]
					too_long = self.model.NewBoolVar(f"pen_r4_reg6_{r_idx}_{start}")
					self.model.Add(sum(window) == 6).OnlyEnforceIf(too_long)
					self.model.Add(sum(window) != 6).OnlyEnforceIf(too_long.Not())
					self.objective_terms.append(2 * PENALTY_WEIGHT * too_long)

	def _create_consecutive_bool(self, r_idx: int, b_idx: int, rot: str) -> cp_model.IntVar:
		"""
		Helper to create a BoolVar that is true if a resident `r_idx` is
		in rotation `rot` for two consecutive blocks starting at `b_idx`.
		"""
		is_consecutive = self.model.NewBoolVar(f"consecutive_{r_idx}_{b_idx}_{rot}")
		self.model.AddBoolAnd([
			self.y[r_idx, b_idx, rot],
			self.y[r_idx, b_idx + 1, rot]
		]).OnlyEnforceIf(is_consecutive)
		self.model.AddBoolOr([
			self.y[r_idx, b_idx, rot].Not(),
			self.y[r_idx, b_idx + 1, rot].Not()
		]).OnlyEnforceIf(is_consecutive.Not())
		return is_consecutive