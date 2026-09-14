#!/usr/bin/env python3
"""Start an eval run for every eval in evals.json, then poll until they finish."""

import json
import os
import re
import time
from pathlib import Path

import requests

from utils import HEADERS

ROOT = Path(__file__).parent
DONE = {"completed", "failed", "cancelled", "error", "interrupted"}

# Fields passed straight through from an eval entry to the request body.
PASSTHROUGH = ("repository", "persona", "tags", "skills", "skill_ids", "mcps", "clis")


def resolve_env(env):
    """Build the write-only `env` map, keeping secrets out of evals.json.

    `env` may be a list of variable names (read from the environment) or a
    mapping whose values may contain ${VAR} references (also read from the
    environment). MCP/CLI headers reference the same ${VAR} names.
    """
    if isinstance(env, list):
        return {name: os.environ[name] for name in env}
    return {
        key: re.sub(r"\$\{(\w+)\}", lambda m: os.environ[m.group(1)], value)
        for key, value in env.items()
    }


def start_run(eval_def):
    """POST /v2/eval-runs — create and run one eval, return the run object."""
    resp = requests.post(
        "https://api.lightsage.com/v2/eval-runs",
        headers=HEADERS,
        json={
            "name": eval_def["name"],
            "prompts": [eval_def["prompt"]],
            "judges": eval_def["judge"],
            "agent": eval_def["agent"],
            "runs": eval_def.get("runs", 1),
            **{k: eval_def[k] for k in PASSTHROUGH if k in eval_def},
            **({"env": resolve_env(eval_def["env"])} if eval_def.get("env") else {}),
        },
    )
    resp.raise_for_status()
    return resp.json()


def get_run(run_id):
    """GET /v2/eval-runs/{run_id} — current status and progress."""
    resp = requests.get(f"https://api.lightsage.com/v2/eval-runs/{run_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def print_table(rows):
    """Clear the screen and print the current status of every run."""
    print("\033[H\033[J", end="")
    print(f"{'EVAL':<28}{'RUN ID':<22}{'STATUS':<12}PROGRESS")
    for name, run_id, run in rows:
        p = run.get("progress") or {}
        prog = f"{p.get('completed', 0)}/{p.get('total', 0)} ({p.get('percent', 0)}%)"
        print(f"{str(name)[:27]:<28}{str(run_id):<22}{str(run.get('status')):<12}{prog}")


def monitor(records):
    """Poll every run until all reach a terminal status, updating the table."""
    while True:
        rows = [(r["eval_name"], r["run_id"], get_run(r["run_id"])) for r in records]
        print_table(rows)
        for record, (_, _, run) in zip(records, rows):
            record["status"] = run.get("status")
            record["progress"] = run.get("progress")
        if all(row[2].get("status") in DONE for row in rows):
            return
        time.sleep(4)


def save(records):
    """Write results/execute/results.json with every prompt and its run."""
    out = ROOT / "results" / "execute" / "results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"runs": records}, indent=2) + "\n")
    print(f"\nSaved {out}")


def run():
    """Start every eval in evals.json, poll until done, return the run records."""
    evals = json.loads((ROOT / "evals.json").read_text())

    records = []
    for eval_def in evals:
        print(f"Starting '{eval_def['name']}'...")
        result = start_run(eval_def)
        records.append(
            {
                "eval_name": eval_def["name"],
                "prompt": eval_def["prompt"],
                "judges": result.get("judges"),
                "agent": eval_def["agent"],
                "eval_id": result.get("eval_id"),
                "run_id": result["id"],
                "status": result.get("status"),
                "progress": result.get("progress"),
            }
        )

    save(records)      # persist run ids before we start waiting
    monitor(records)   # poll + live table until everything is done
    save(records)      # persist final statuses
    return records


if __name__ == "__main__":
    run()
