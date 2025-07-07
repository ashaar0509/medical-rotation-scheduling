from typing import Any
from ortools.sat.python import cp_model
from scheduler.config import (
	BLOCKS, ROTATIONS, rotation_to_idx, ELIGIBILITY, LEAVE_IDX,
	LEAVE_ALLOWED, PER_BLOCK_MIN, GRAD_REQ, group_defs
)

def build_model(residents, pgys, leave_dict, forced_assignments, forbidden_assignments):
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


	for (res_id, b), rot in forced_assignments.items():
		r = residents.index(res_id)
		rot_idx = rotation_to_idx[rot]
		model.Add(x[r, b] == rot_idx)

	for (res_id, b), rot in forbidden_assignments.items():
		r = residents.index(res_id)
		rot_idx = rotation_to_idx[rot]
		model.Add(x[r, b] != rot_idx)

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
	# for b in range(BLOCKS):
	# 	for rot in PER_BLOCK_MIN:
	# 		model.Add(
	# 			sum(half_leave_weights[r, b] * y[r, b, rot] for r in range(n))
	# 			>= 2 * PER_BLOCK_MIN[rot]
	# 		)

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

			if not count_vars:
				print(f"[GRAD EMPTY] {res_id} ({pgy}) → {rotation_group} → SKIPPED")
			elif len(count_vars) < min(required_counts):
				print(f"[GRAD TOO FEW BLOCKS] {res_id} ({pgy}) needs ≥{min(required_counts)} "
					f"but only has {len(count_vars)} possible")

			model.Add(sum(count_vars) >= min(required_counts))
			model.Add(sum(count_vars) <= max(required_counts))



	# -------------------------
	# On-call Rules and Coverage
	# -------------------------
	# 1. Every block must have exactly 10 Senior Rotations.
	# 2. Every block must have exactly 20 Registrar Rotations.
	# 3. For 2nd-on-call rotations (GI, Rheumatology, Pulmonology), the total
	#    weighted count (3 if half leave, 6 otherwise) must be ≥ 60.
	# 4. For Floater rotations (Nephrology, Endocrine), ensure at least 10
	#    residents assigned in each block.

	second_wt = {
		(r, b): 3 if (b + 1) in leave_dict[residents[r]]["half"] else 6
		for r in range(n)
		for b in range(BLOCKS)
	}

	print(f"Residents: {n}")
	for b in range(BLOCKS):
		n_leave = sum(1 for r in range(n) if (b + 1) in leave_dict[residents[r]]["full"])
		print(f"Block {b+1}: {n_leave} on full leave")

	for b in range(BLOCKS):
		# Enforce fixed counts
		model.Add(sum(y[r, b, "Senior Rotation"] for r in range(n)) == 10)
		# model.Add(sum(y[r, b, "Senior Rotation"] for r in range(n)) <= 13)
	
		model.Add(sum(y[r, b, "Registrar Rotation"] for r in range(n)) == 20)

		# PER_BLOCK_MIN: simple unweighted counts
		for rot in PER_BLOCK_MIN:
			model.Add(
				sum(y[r, b, rot] for r in range(n)) >= PER_BLOCK_MIN[rot]
			)
	
		# Weighted 2nd on-call minimum
		# TODO: Add soft 2x +ve constraint where the sum is at least 64.
		model.Add(
			sum(
				second_wt[r, b] * y[r, b, rot]
				for r in range(n)
				for rot in group_defs["2ndOnCall"]
			) >= 60
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
		total_endo = sum(y[r, b, "Endocrine"] for r in range(n))
		total_neph = sum(y[r, b, "Nephrology"] for r in range(n))

		# Define new IntVar for extra_endo and extra_neph
		extra_endo = model.NewIntVar(0, n, f"extra_endo_b{b}")
		extra_neph = model.NewIntVar(0, n, f"extra_neph_b{b}")

		# Symbolic max(0, total - 5)
		model.AddMaxEquality(extra_endo, [0, total_endo - 5])
		model.AddMaxEquality(extra_neph, [0, total_neph - 5])
		
		# R2s in MOP
		r2_in_mop = sum(
			y[r, b, "MOP"]
			for r in range(n)
			if pgys[r] == "R2"
		)

		# Neurology
		neuro = sum(y[r, b, "Neurology"] for r in range(n))

		# Combined condition
		# model.Add(neuro + r2_in_mop + extra_endo + extra_neph >= 4)

	# -------------------------
	# Post-Block-3 Medical Teams Coverage
	# -------------------------
	# From Block 4 onwards (index 3), enforce exactly 20 residents on
	# Medical Teams per block.

	model.Add(sum(y[r, 1, "Medical Teams"] for r in range(n)) >= 25)

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
		if pgys[r] == "R3" or pgys[r] == "R2":
			for b in range(BLOCKS - 1):
				model.AddBoolOr([
					y[r, b, "Senior Rotation"].Not(),
					y[r, b + 1, "Senior Rotation"].Not()
				])


	# -------------------------
	# Soft Objective Components
	# -------------------------

	# R2/R3 mix in Cardiology and AMAU
	rotation_mix_score = []
	for b in range(BLOCKS):
		for rot in ["Cardiology", "AMAU"]:
			eligible_vars = [
				y[r, b, rot]
				for r in range(n)
				if pgys[r] in ("R2", "R3")
			]
			if eligible_vars:
				mix_ok = model.NewBoolVar(f"mix_r2r3_b{b}_{rot}")
				model.Add(sum(eligible_vars) >= 2).OnlyEnforceIf(mix_ok)
				model.Add(sum(eligible_vars) < 2).OnlyEnforceIf(mix_ok.Not())
				rotation_mix_score.append(mix_ok)

	# R1 penalties
	penalty_r1_long_medical = []
	penalty_r1_consec_cardiology = []

	for r in range(n):
		if pgys[r] == "R1":
			for start in range(BLOCKS - 3):
				window = [y[r, b, "Medical Teams"] for b in range(start, start + 4)]
				all_four = model.NewBoolVar(f"r1_medical_4consec_{r}_{start}")
				model.Add(sum(window) == 4).OnlyEnforceIf(all_four)
				model.Add(sum(window) != 4).OnlyEnforceIf(all_four.Not())
				penalty_r1_long_medical.append(all_four)

			for b in range(BLOCKS - 1):
				both = model.NewBoolVar(f"r1_cardio_consec_{r}_{b}")
				model.AddBoolAnd([
					y[r, b, "Cardiology"],
					y[r, b + 1, "Cardiology"]
				]).OnlyEnforceIf(both)
				model.AddBoolOr([
					y[r, b, "Cardiology"].Not(),
					y[r, b + 1, "Cardiology"].Not()
				]).OnlyEnforceIf(both.Not())
				penalty_r1_consec_cardiology.append(both)

	# R2 rewards
	reward_r2_consec_micu = []
	reward_r2_consec_ccu = []

	for r in range(n):
		if pgys[r] == "R2":
			for b in range(BLOCKS - 1):
				both_micu = model.NewBoolVar(f"r2_micu_consec_{r}_{b}")
				model.AddBoolAnd([
					y[r, b, "MICU"],
					y[r, b + 1, "MICU"]
				]).OnlyEnforceIf(both_micu)
				model.AddBoolOr([
					y[r, b, "MICU"].Not(),
					y[r, b + 1, "MICU"].Not()
				]).OnlyEnforceIf(both_micu.Not())
				reward_r2_consec_micu.append(both_micu)


				both_ccu = model.NewBoolVar(f"r2_ccu_consec_{r}_{b}")
				model.AddBoolAnd([
					y[r, b, "CCU"],
					y[r, b + 1, "CCU"]
				]).OnlyEnforceIf(both_ccu)
				model.AddBoolOr([
					y[r, b, "CCU"].Not(),
					y[r, b + 1, "CCU"].Not()
				]).OnlyEnforceIf(both_ccu.Not())
				reward_r2_consec_ccu.append(both_ccu)
	
	# R3 penalties: insufficient spacing between Senior blocks
	penalty_r3_senior_spacing = []

	for r in range(n):
		if pgys[r] == "R3":
			for b in range(BLOCKS - 1):
				p = model.NewBoolVar(f"r3_senior_consec_{r}_{b}")
				model.AddBoolAnd([
					y[r, b, "Senior Rotation"],
					y[r, b + 1, "Senior Rotation"]
				]).OnlyEnforceIf(p)
				model.AddBoolOr([
					y[r, b, "Senior Rotation"].Not(),
					y[r, b + 1, "Senior Rotation"].Not()
				]).OnlyEnforceIf(p.Not())
				penalty_r3_senior_spacing.append(p)

			for b in range(BLOCKS - 2):
				p = model.NewBoolVar(f"r3_senior_gap1_{r}_{b}")
				model.AddBoolAnd([
					y[r, b, "Senior Rotation"],
					y[r, b + 2, "Senior Rotation"]
				]).OnlyEnforceIf(p)
				model.AddBoolOr([
					y[r, b, "Senior Rotation"].Not(),
					y[r, b + 2, "Senior Rotation"].Not()
				]).OnlyEnforceIf(p.Not())
				penalty_r3_senior_spacing.append(p)

	# R4 penalties: >5 consecutive Registrar rotations
	penalty_r4_long_registrar = []

	for r in range(n):
		if pgys[r] == "R4":
			for start in range(BLOCKS - 5):
				window = [y[r, b, "Registrar Rotation"] for b in range(start, start + 6)]
				too_long = model.NewBoolVar(f"r4_registrar_6consec_{r}_{start}")
				model.Add(sum(window) == 6).OnlyEnforceIf(too_long)
				model.Add(sum(window) != 6).OnlyEnforceIf(too_long.Not())
				penalty_r4_long_registrar.append(too_long)

	# -------------------------
	# Final Objective
	# -------------------------
	#TODO: Get preferences score (normalized to 1). Provide summary with the score.
	model.Maximize(
		sum(rotation_mix_score)
		- sum(penalty_r1_long_medical)
		- sum(penalty_r1_long_medical)
		- sum(penalty_r1_consec_cardiology)
	
		+ sum(reward_r2_consec_micu)
		+ sum(reward_r2_consec_micu)
		+ sum(reward_r2_consec_ccu)
		+ sum(reward_r2_consec_ccu)
	
		- sum(penalty_r3_senior_spacing)
		- sum(penalty_r3_senior_spacing)
	
		- sum(penalty_r4_long_registrar)
		- sum(penalty_r4_long_registrar)
	
	)
	return model, x, y
