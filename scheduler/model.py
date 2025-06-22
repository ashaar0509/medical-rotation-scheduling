from typing import Any
from ortools.sat.python import cp_model
from scheduler.config import (
	BLOCKS, ROTATIONS, rotation_to_idx, ELIGIBILITY, LEAVE_IDX,
	LEAVE_ALLOWED, PER_BLOCK_MIN, GRAD_REQ, group_defs
)

def build_model(residents, pgys, leave_dict):
	# -------------------------
	# CP-SAT Model Setup
	# -------------------------
	model = cp_model.CpModel()
	n = len(residents)
	# x[r, b]: Integer variable representing the rotation index assigned to
	# resident r in block b (0-based: 0..12).
	# - If block b is a full leave block, x[r, b] is fixed to LEAVE_IDX.
	# - Else, x[r, b] is constrained to eligible rotations based on PGY and
	#   further restricted to LEAVE_ALLOWED if it's a half-leave block.
	x = {}
	for r in range(n):
		res_id = residents[r]
		pgy = pgys[r]
		for b in range(BLOCKS):
			if (b + 1) in leave_dict[res_id]["full"]:
				x[r, b] = model.NewIntVarFromDomain(
					cp_model.Domain.FromValues([LEAVE_IDX]), f"x_{r}_{b}"
				)
			else:
				eligible = [
					rotation_to_idx[rot]
					for rot in ELIGIBILITY[pgy]
					if rot in rotation_to_idx
				]
				if (b + 1) in leave_dict[res_id]["half"]:
					eligible = [
						rotation_to_idx[rot]
						for rot in ELIGIBILITY[pgy]
						if rot in rotation_to_idx and
						rot in LEAVE_ALLOWED.get(pgy, set())
					]
				x[r, b] = model.NewIntVarFromDomain(
					cp_model.Domain.FromValues(eligible), f"x_{r}_{b}"
				)


	# -------------------------
	# Indicator Variables y[r, b, rot]
	# -------------------------
	# For each rotation (including LEAVE), y[r, b, rot] = 1 iff resident r
	# is assigned to rotation `rot` in block b. These are boolean indicators
	# tied to the integer decision variable x[r, b].
	y = {}
	for r in range(n):
		for b in range(BLOCKS):  # BLOCKS = 13, blocks 0 to 12
			for rot in ROTATIONS:
				rot_id = rotation_to_idx[rot]
				var = model.NewBoolVar(f"y_{r}_{b}_{rot}")
				model.Add(x[r, b] == rot_id).OnlyEnforceIf(var)
				model.Add(x[r, b] != rot_id).OnlyEnforceIf(var.Not())
				y[r, b, rot] = var

	# Enforce that each block has exactly one assigned rotation
	for r in range(n):
		for b in range(BLOCKS):
			model.AddExactlyOne([y[r, b, rot] for rot in ROTATIONS])


	# -------------------------
	# Leave Weights
	# -------------------------
	# Weight each resident-block pair by:
	#   - 1 if it's a half-leave block (less time available),
	#   - 2 otherwise.
	# These weights are used to scale contributions to minimum coverage constraints.
	half_leave_weights = {
		(r, b): 1 if (b + 1) in leave_dict[residents[r]]["half"] else 2
		for r in range(n)
		for b in range(BLOCKS)
	}

	# -------------------------
	# Per-Block Minimum Rotation Coverage
	# -------------------------
	# For each rotation `rot` that has a minimum coverage requirement:
	# In every block, the sum of weighted assignments to `rot`
	# must be ≥ 2 × PER_BLOCK_MIN[rot].
	for b in range(BLOCKS):
		for rot in PER_BLOCK_MIN:
			model.Add(
				sum(half_leave_weights[r, b] * y[r, b, rot] for r in range(n))
				>= 2 * PER_BLOCK_MIN[rot]
			)

	# -------------------------
	# Graduation Requirements
	# -------------------------
	# Each resident must fulfill graduation requirements for specific rotation
	# groups, unless exempt (R3s with full leave can skip one group).

	for r in range(n):
		res_id = residents[r]
		pgy = pgys[r]
		leave_blocks = leave_dict[res_id]["full"]

		for rotation_group, required_counts in GRAD_REQ[pgy].items():
			if (
				pgy == "R3"
				and set(rotation_group) == {"Cardiology", "ED", "Medical Consultation"}
				and leave_blocks
			):
				continue

			count_vars = []
			for b in range(BLOCKS):
				if (b+1) not in leave_blocks:
					for rot in rotation_group:
						if rot in rotation_to_idx:
							count_vars.append(y[r, b, rot])

			model.Add(sum(count_vars) >= min(required_counts))
			model.Add(sum(count_vars) <= max(required_counts))



	# -------------------------
	# On-call Rules and Coverage
	# -------------------------
	# 1. Every block must have exactly 10 Senior Rotations.
	# 2. Every block must have exactly 20 Registrar Rotations.
	# 3. For 2nd-on-call rotations (GI, Rheumatology, Pulmonology), the total
	#    weighted count (3 if half leave, 5 otherwise) must be ≥ 54.
	# 4. For Floater rotations (Nephrology, Endocrine), ensure at least 10
	#    residents assigned in each block.

	second_wt = {
		(r, b): 3 if (b + 1) in leave_dict[residents[r]]["half"] else 5
		for r in range(n)
		for b in range(BLOCKS)
	}

	for b in range(BLOCKS):
		# Enforce fixed counts
		model.Add(sum(y[r, b, "Senior Rotation"] for r in range(n)) == 10)
		model.Add(sum(y[r, b, "Registrar Rotation"] for r in range(n)) == 20)

		# Weighted 2nd on-call minimum
		model.Add(
			sum(
				second_wt[r, b] * y[r, b, rot]
				for r in range(n)
				for rot in group_defs["2ndOnCall"]
			) >= 54
		)

		# Floater (Nephrology + Endocrine) ≥ 10 residents
		model.Add(
			sum(
				y[r, b, rot]
				for r in range(n)
				for rot in group_defs["Floater"]
			) >= 10
		)

		# Extra Nephrology + Extra Endocrine = total - 5 each
		extra_endo = sum(y[r, b, "Endocrine"] for r in range(n)) - 5
		extra_neph = sum(y[r, b, "Nephrology"] for r in range(n)) - 5

		# R2s in MOP
		r2_in_mop = sum(
			y[r, b, "MOP"]
			for r in range(n)
			if pgys[r] == "R2"
		)

		# Neurology
		neuro = sum(y[r, b, "Neurology"] for r in range(n))

		# Combined condition
		model.Add(neuro + r2_in_mop + extra_endo + extra_neph >= 4)

	# -------------------------
	# Post-Block-3 Medical Teams Coverage
	# -------------------------
	# From Block 4 onwards (index 3), enforce exactly 20 residents on
	# Medical Teams per block.

	for b in range(3, BLOCKS):
		model.Add(sum(y[r, b, "Medical Teams"] for r in range(n)) == 20)

	# -------------------------
	# Block-1 PGY Restrictions
	# -------------------------
	# PGY-1 residents must start in Medical Teams in Block 1.
	# PGY-2 residents cannot be assigned to Senior Rotation in Block 1.

	med_teams_idx = rotation_to_idx["Medical Teams"]
	senior_idx = rotation_to_idx["Senior Rotation"]

	for r in range(n):
		if pgys[r] == "R1":
			model.Add(x[r, 0] == med_teams_idx)
		elif pgys[r] == "R2":
			model.Add(x[r, 0] != senior_idx)

	# -------------------------
	# R1: No 6 Consecutive Medical Teams
	# -------------------------
	# For each PGY-1 resident, in any 6-block window, they cannot have all
	# 6 blocks assigned to Medical Teams.

	for r in range(n):
		if pgys[r] == "R1":
			for start in range(BLOCKS - 5):
				model.Add(
					sum(y[r, b, "Medical Teams"] for b in range(start, start + 6))
					<= 5
				)

	return model, x, y
