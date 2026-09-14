#!/usr/bin/env python3
"""Run the whole pipeline: start the evals, then trace and analyze every run."""

from analyze import analyze
from execute import run
from trace import trace

if __name__ == "__main__":
    records = run()  # start + monitor every eval in evals.json

    for record in records:
        run_id = record["run_id"]
        trace(run_id)    # -> results/trace/{run_id}.json
        analyze(run_id)  # -> results/analyze/{run_id}.json

    print("\nDone. Results are in results/.")
