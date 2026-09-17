#!/usr/bin/env python3
"""Start an eval run for every eval in evals.json, then poll until they finish."""

import json
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from utils import HEADERS

ROOT = Path(__file__).resolve().parent.parent
DONE = {"completed", "failed", "cancelled", "error", "interrupted"}

# Fields passed straight through from an eval entry to the request body.
PASSTHROUGH = ("repository", "persona", "tags", "skills", "skill_ids", "mcps", "clis")


def resolve_env(env):
    """Resolve ${VAR} references in an env map from the environment.

    Keeps secrets out of evals.json: values hold ${VAR} placeholders (the same
    names MCP/CLI headers reference) and are filled from the local environment.
    """
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
    if not resp.ok:
        raise SystemExit(f"POST /v2/eval-runs failed [{resp.status_code}]: {resp.text}")
    return resp.json()


def get_run(run_id):
    """GET /v2/eval-runs/{run_id} — current status and progress."""
    resp = requests.get(f"https://api.lightsage.com/v2/eval-runs/{run_id}", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def format_progress(run):
    """Format terminal child-job progress without implying run completion."""
    progress = run.get("progress") or {}
    total = int(progress.get("total") or 0)
    terminal_counts = {
        status: int(progress.get(status) or 0)
        for status in ("completed", "failed", "cancelled", "interrupted")
    }
    done = sum(terminal_counts.values())
    issues = [
        f"{count} {status}"
        for status, count in terminal_counts.items()
        if status != "completed" and count
    ]
    detail = f" ({', '.join(issues)})" if issues else ""
    return f"{done}/{total}{detail}"


def truncate_cell(value, width):
    """Keep a table cell on one line while preserving its column boundary."""
    text = str(value or "")
    if len(text) <= width:
        return text
    return f"{text[: width - 1]}…"


def format_agent(agent):
    """Render an eval's agent list as comma-joined {harness}:{model} strings."""
    if isinstance(agent, (list, tuple)):
        return ", ".join(str(a) for a in agent)
    return str(agent or "")


def print_table(rows):
    """Clear the screen and print the current status of every run."""
    formatted_rows = [
        (
            str(name),
            format_agent(agent),
            str(run.get("status") or ""),
            format_progress(run),
        )
        for name, agent, run in rows
    ]
    separator = " │ "
    agent_width = max(len("AGENT"), *(len(row[1]) for row in formatted_rows))
    status_width = max(len("STATUS"), *(len(row[2]) for row in formatted_rows))
    progress_width = max(len("PROGRESS"), *(len(row[3]) for row in formatted_rows))
    fixed_width = agent_width + status_width + progress_width + len(separator) * 3
    terminal_width = shutil.get_terminal_size(fallback=(120, 24)).columns
    eval_width = max(24, min(44, terminal_width - fixed_width))

    print("\033[H\033[J", end="")
    print(
        separator.join(
            (
                f"{'EVAL':<{eval_width}}",
                f"{'AGENT':<{agent_width}}",
                f"{'STATUS':<{status_width}}",
                f"{'PROGRESS':<{progress_width}}",
            )
        )
    )
    print(
        "─" * eval_width
        + "─┼─"
        + "─" * agent_width
        + "─┼─"
        + "─" * status_width
        + "─┼─"
        + "─" * progress_width
    )
    for name, agent, status, progress in formatted_rows:
        print(
            separator.join(
                (
                    f"{truncate_cell(name, eval_width):<{eval_width}}",
                    f"{truncate_cell(agent, agent_width):<{agent_width}}",
                    f"{truncate_cell(status, status_width):<{status_width}}",
                    f"{truncate_cell(progress, progress_width):<{progress_width}}",
                )
            )
        )


def monitor(records):
    """Poll every run until all reach a terminal status, updating the table."""
    rows = [
        (
            record["eval_name"],
            record["agent"],
            {"status": record.get("status"), "progress": record.get("progress")},
        )
        for record in records
    ]
    while True:
        print_table(rows)
        for record, (_, _, run) in zip(records, rows):
            record["status"] = run.get("status")
            record["progress"] = run.get("progress")
        if all(row[2].get("status") in DONE for row in rows):
            return
        time.sleep(4)
        with ThreadPoolExecutor(max_workers=min(12, len(records))) as pool:
            runs = list(pool.map(lambda r: get_run(r["run_id"]), records))
        rows = [(r["eval_name"], r["agent"], run) for r, run in zip(records, runs)]


def save(records):
    """Write results/execute/results.json with every prompt and its run."""
    out = ROOT / "results" / "execute" / "results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"runs": records}, indent=2) + "\n")
    print(f"\nSaved {out}")


def run():
    """Start every eval in evals.json, poll until done, return the run records."""
    evals = json.loads((ROOT / "evals.json").read_text())

    records = [None] * len(evals)

    def _start(idx, eval_def):
        print(f"Starting '{eval_def['name']}' [{eval_def['agent'][0]}]...")
        result = start_run(eval_def)
        return idx, eval_def, result

    with ThreadPoolExecutor(max_workers=min(12, len(evals))) as pool:
        futures = [pool.submit(_start, i, e) for i, e in enumerate(evals)]
        for fut in as_completed(futures):
            idx, eval_def, result = fut.result()
            records[idx] = {
                "eval_name": eval_def["name"],
                "prompt": eval_def["prompt"],
                "judges": result.get("judges"),
                "agent": eval_def["agent"],
                "eval_id": result.get("eval_id"),
                "run_id": result["id"],
                "status": result.get("status"),
                "progress": result.get("progress"),
            }

    save(records)      # persist run ids before we start waiting
    monitor(records)   # poll + live table until everything is done
    save(records)      # persist final statuses
    return records


if __name__ == "__main__":
    run()
