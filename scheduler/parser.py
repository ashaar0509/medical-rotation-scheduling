from typing import Any
import pandas as pd

def parse_input(path) -> tuple[list[Any], list[Any], dict[Any, Any]]:
	"""Read Excel input and return residents, PGYs, and leave info dict."""
	df = pd.read_excel(path).fillna({
		"Leave1Block": 0,
		"Leave2Block": 0,
		"Leave1Half": "",
		"Leave2Half": ""
	})

	residents = df["ID"].tolist()
	pgys = df["PGY"].tolist()
	leave_dict = {}

	for _, row in df.iterrows():
		b1 = int(row["Leave1Block"])
		b2 = int(row["Leave2Block"])

		full, half = set(), set()

		if b1 and b1 == b2:
			full.add(b1)
		else:
			if b1:
				half.add(b1)
			if b2:
				half.add(b2)

		leave_dict[row["ID"]] = {
			"pgy": row["PGY"],
			"full": full,
			"half": half
		}

	return residents, pgys, leave_dict
