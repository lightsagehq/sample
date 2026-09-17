#!/usr/bin/env python3
"""Fetch the analysis for an eval run.

Usage:
  python scripts/analyze.py <run_id>
  python scripts/analyze.py --all      # every run in results/execute/results.json
"""

import json
import sys
from pathlib import Path

import requests

from utils import HEADERS

ROOT = Path(__file__).resolve().parent.parent


def analyze(run_id):
    """GET /v2/eval-runs/{run_id} and write its analysis to results/analyze/{run_id}.json.

    The dedicated /analysis sub-resource was removed; analysis is now returned
    as a top-level `analysis` array on the eval-run detail response (populated
    once an attempt has been analyzed).
    """
    resp = requests.get(f"https://api.lightsage.com/v2/eval-runs/{run_id}", headers=HEADERS)
    resp.raise_for_status()
    data = resp.json()
    analysis = data.get("analysis") or []
    out = ROOT / "results" / "analyze" / f"{run_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(analysis, indent=2) + "\n")
    print(f"{run_id} [{data.get('status')}] {len(analysis)} analyzed -> {out}")


def all_run_ids():
    """Run ids recorded by execute.py."""
    results = json.loads((ROOT / "results" / "execute" / "results.json").read_text())
    return [r["run_id"] for r in results["runs"] if r.get("run_id")]


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--all" in args:
        for run_id in all_run_ids():
            analyze(run_id)
    elif args:
        analyze(args[0])
    else:
        sys.exit("Usage: analyze.py <run_id> | --all")
