"""Turn results/sweep.jsonl into the same CSV + meta files the single experiments write, in a folder
of their own so the committed small runs stay intact. Then plot them:
    python experiments/export_sweep.py                 # -> results/sweep/
    python experiments/make_plots.py results/sweep     # figures + summary.md in that folder
"""
import argparse
import json
import os

import sweep
from common import save_csv

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="results/sweep.jsonl")
    ap.add_argument("--out", default="results/sweep")
    a = ap.parse_args()

    recs = {}
    with open(a.src) as f:
        for line in f:
            r = json.loads(line)
            recs[r["key"]] = r
    # job order from the sweep definition, so the files do not depend on which worker finished first
    order = [k for _, _, k in sweep.build_jobs(list(sweep.DO), True) if k in recs]
    os.makedirs(a.out, exist_ok=True)
    for exp in sweep.DO:
        rs = [recs[k] for k in order if recs[k]["exp"] == exp]
        if not rs:
            continue
        # every row and meta carries its job's settings (family, seed, damage, ...)
        rows = [{**r["params"], **row} for r in rs for row in r["rows"]]
        metas = [{**r["params"], **r["meta"]} for r in rs]
        if exp == "extrapolation":
            json.dump(rows, open(f"{a.out}/extrapolation.json", "w"), indent=1)
            json.dump(metas, open(f"{a.out}/extrapolation_meta.json", "w"), indent=1)
        else:
            name = "learning" if exp == "learning" else exp
            save_csv(rows, f"{a.out}/{name}.csv")
            json.dump(metas, open(f"{a.out}/{name}_meta.json", "w"), indent=1)
        print(f"{exp:13s} {len(rs):3d} jobs, {len(rows):4d} rows -> {a.out}/")
    missing = len(sweep.build_jobs(list(sweep.DO), True)) - len(order)
    if missing:
        print(f"note: {missing} sweep jobs are not in {a.src} yet")
