#!/usr/bin/env python3
"""Fetch the execution trace for an eval run.

Usage:
  python trace.py <run_id>
  python trace.py --all      # every run in results/execute/results.json
"""

import json
import sys
from pathlib import Path

import requests

from utils import HEADERS

ROOT = Path(__file__).parent


def trace(run_id):
    """Page through /v2/eval-runs/{run_id}/trace and write results/trace/{run_id}.json."""
    events = []
    after_id = 0
    while True:
        resp = requests.get(
            f"https://api.lightsage.com/v2/eval-runs/{run_id}/trace",
            params={"after_id": after_id, "limit": 500},
            headers=HEADERS,
        )
        resp.raise_for_status()
        page = resp.json()
        events.extend(page.get("data") or [])
        if not page.get("has_more"):
            break
        after_id = page["next_after_id"]

    out = ROOT / "results" / "trace" / f"{run_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"run_id": run_id, "events": events}, indent=2) + "\n")
    print(f"{run_id} -> {out} ({len(events)} events)")


def all_run_ids():
    """Run ids recorded by execute.py."""
    results = json.loads((ROOT / "results" / "execute" / "results.json").read_text())
    return [r["run_id"] for r in results["runs"] if r.get("run_id")]


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--all" in args:
        for run_id in all_run_ids():
            trace(run_id)
    elif args:
        trace(args[0])
    else:
        sys.exit("Usage: trace.py <run_id> | --all")
