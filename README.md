# Lightsage eval pipeline

A small, three-stage pipeline over the [Lightsage](https://lightsage.com) v2 API:

1. **`execute.py`** — read eval definitions from `evals.json`, start an eval run
   for each, and monitor them live.
2. **`analyze.py`** — retrieve the analysis (verdicts/findings) for one or all runs.
3. **`trace.py`** — retrieve the full execution trace for one or all runs.

All API calls go through `POST /v2/eval-runs` and friends using the direct
create-and-run form — no separate eval/configuration objects to manage.

## Layout

```
.
├── execute.py            # start eval runs + poll until done
├── analyze.py            # fetch eval-run analysis
├── trace.py              # fetch eval-run trace (paginated)
├── utils.py              # loads .env + builds the auth header (HEADERS)
├── evals.json            # eval definitions (edit this)
├── .env                  # API key + config (edit this)
├── requirements.txt
└── results/
    ├── execute/results.json   # written by execute.py — every prompt + its run
    ├── analyze/{run_id}.json  # written by analyze.py
    └── trace/{run_id}.json    # written by trace.py
```

Each script is self-contained: a few plain functions calling the API with
`requests`, wired together in an `if __name__ == "__main__":` block.

## Setup

```bash
pip install -r requirements.txt
```

Then put your API key in `.env`:

```
LIGHTSAGE_API_KEY=your-api-key-here
```

Real environment variables always win over `.env`.

## Defining evals

`evals.json` is a **JSON array** of eval objects. Each eval has a single
`prompt`, one or more `judge`s, and its own `agent`/`runs`:

```json
[
  {
    "name": "Hello world",
    "prompt": "Navigate to https://example.com and describe what you see.",
    "judge": [
      "The agent visited https://example.com.",
      "The agent accurately described the page content."
    ],
    "agent": ["claude-code:claude-opus-4-8"],
    "runs": 1
  },
  {
    "name": "SDK smoke test",
    "prompt": "Install the SDK and send a successful request.",
    "judge": ["The SDK is installed.", "A request succeeds."],
    "agent": ["claude-code:claude-opus-4-8", "codex:gpt-5-4"],
    "runs": 2,
    "repository": "nextjs-starter",
    "tags": ["sdk", "smoke-test"]
  }
]
```

Per-eval fields:

| Field | Notes |
|-------|-------|
| `name` | Display name (defaults to the prompt). |
| `prompt` | The single task for this eval. Required. |
| `judge` | One success criterion or a list of them (`judges` also accepted). Required. |
| `agent` | Agent id(s) from `GET /v2/agents`. String or list. |
| `runs` | Independent attempts per agent. |
| `repository` | Saved repo id, alias (e.g. `nextjs-starter`), or public GitHub URL. |
| `persona`, `tags`, `env`, `skills`, `skill_ids`, `clis`, `mcps` | Optional; see the API reference. |

Each eval is one prompt; a run fans out across **agents × runs**.

## Usage

### 1. Execute

```bash
python execute.py     # run everything in evals.json
```

Each eval becomes one `POST /v2/eval-runs`. Run ids are written to
`results/execute/results.json` right after the runs start (so they're never
lost), then each run is polled with `GET /v2/eval-runs/{run_id}` and the status
is redrawn as a table until everything finishes:

```
EVAL                        RUN ID                STATUS      PROGRESS
Hello world                 run_abc123            running     2/4 (50%)
SDK smoke test              run_def456            completed   8/8 (100%)
```

Completion is detected from `status`, not `percent` (percent can hit 100 while
the job is still summarizing).

### 2. Analyze

```bash
python analyze.py <run_id>     # analyze a single run
python analyze.py --all        # analyze every run in results/execute/results.json
```

Writes `results/analyze/{run_id}.json` and prints a verdict summary per run.

### 3. Trace

```bash
python trace.py <run_id>       # trace a single run
python trace.py --all          # trace every run in results/execute/results.json
```

Pages through `GET /v2/eval-runs/{run_id}/trace` and writes the merged trace to
`results/trace/{run_id}.json`.

## Typical run

```bash
python execute.py       # start + watch runs, populate results/execute/results.json
python analyze.py --all # pull analysis for every run
python trace.py --all   # pull traces for every run
```

## API reference

- Docs index: <https://lightsage.com/docs/llms.txt>
- Start an eval run: <https://lightsage.com/docs/api-reference/eval-runs/start-an-eval-run>
- Monitor runs: <https://lightsage.com/docs/api-reference/eval-runs/monitor-runs>
- Retrieve analysis: <https://lightsage.com/docs/api-reference/eval-runs/retrieve-eval-run-analysis>
- Retrieve trace: <https://lightsage.com/docs/api-reference/eval-runs/retrieve-an-eval-run-trace>

Auth is an API key sent in the `X-Lightsage-Api-Key` header on every request.
# sample
