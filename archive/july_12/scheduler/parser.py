import pandas as pd
import os

def parse_input(path: str):
    df = pd.read_excel(path).fillna({
        "Leave1Block": 0,
        "Leave2Block": 0,
        "Leave1Half": "",
        "Leave2Half": ""
    })

    residents = df["ID"].tolist()
    pgys = df["PGY"].tolist()
    leave_dict = {}
    forced_assignments = {}
    forbidden_assignments = {}

    for row in df.itertuples(index=False):
        b1, b2 = int(row.Leave1Block), int(row.Leave2Block)
        full, half = set(), set()

        if b1 and b1 == b2:
            full.add(b1)
        else:
            if b1:
                half.add(b1)
            if b2:
                half.add(b2)

        leave_dict[row.ID] = {
            "pgy": row.PGY,
            "full": full,
            "half": half
        }

        for b in range(1, 14):
            val = getattr(row, f"Block_{b}", "")
            val = str(val).strip()
            if not val or val.lower() in {"nan", "none"}:
                continue
            if val.startswith("!"):
                forbidden_assignments[(row.ID, b - 1)] = val[1:]
            else:
                forced_assignments[(row.ID, b - 1)] = val

    return residents, pgys, leave_dict, forced_assignments, forbidden_assignments
