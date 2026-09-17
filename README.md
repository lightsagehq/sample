# Lightsage eval pipeline

A small pipeline over the [Lightsage v2 API](https://lightsage.com/docs/api-reference/eval-runs/start-an-eval-run) that runs evals, then pulls each run's trace and analysis:

1. `scripts/execute.py` — read eval definitions from `evals.json`, start an eval run for each, and poll until they finish.
2. `scripts/trace.py` — retrieve the full execution trace for one or all runs.
3. `scripts/analyze.py` — retrieve the analysis (verdicts/findings) for one or all runs.

`main.py` runs all three in sequence. All API calls hit the `/v2/eval-runs` family — `POST` to create a run, `GET` to poll status, and `GET …/trace` to pull the execution log. There are no separate eval or configuration objects; one POST starts the run directly.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env      # then paste in your API key
# edit evals.json to define your evals
python main.py            # run evals -> trace -> analyze, into results/
```

## Layout

```
.
├── main.py               # run the whole pipeline (execute -> trace -> analyze)
├── evals.json            # eval definitions (edit this)
├── .env                  # API key (copy from .env.example)
├── requirements.txt
├── scripts/
│   ├── execute.py        # start eval runs + poll until done
│   ├── trace.py          # fetch eval-run trace (paginated)
│   ├── analyze.py        # fetch eval-run analysis
│   └── utils.py          # loads .env + builds the auth header (HEADERS)
└── results/
    ├── execute/results.json   # written by execute.py — every prompt + its run
    ├── trace/{run_id}.json    # written by trace.py
    └── analyze/{run_id}.json  # written by analyze.py
```

`main.py` and `evals.json` sit at the root — the file you run and the file you edit. The stage scripts live under `scripts/`.

Each script is self-contained: a few plain functions calling the API with `requests`, wired together in an `if __name__ == "__main__":` block. `utils.py` loads `.env` on import (real environment variables win) and builds the auth header.

## Defining evals

`evals.json` is a **JSON array** of eval objects. Each eval has a single `prompt`, one or more `judge`s, and its own `agent`/`runs`:

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

| Field                          | Notes                                                                                                                     |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| `name`                         | Display name (defaults to the prompt).                                                                                    |
| `prompt`                       | The single task for this eval. Required.                                                                                  |
| `judge`                        | One success criterion or a list of them (`judges` also accepted). Required.                                               |
| `agent`                        | Agent id(s) as `harness:model` strings. Call `GET /v2/agents` to list all available harnesses and models. String or list. |
| `runs`                         | Independent attempts per agent.                                                                                           |
| `repository`                   | Saved repo UUID (from `GET /v2/repositories`) or a public GitHub URL. Plain aliases are rejected.                         |
| `skills`                       | Public skill packages, e.g. `["resend/resend-skills"]`.                                                                   |
| `clis`                         | Install commands to run before the agent starts, e.g. `["pip install firecrawl-py"]`.                                     |
| `mcps`                         | Inline MCP server config (see below) or saved refs (`{"id": "..."}`).                                                     |
| `env`                          | Secret values for this run — see below.                                                                                   |
| `persona`, `tags`, `skill_ids` | Optional; see the API reference.                                                                                          |

Each eval is one prompt; a run fans out across **agents × runs**.

### Available agents

Agent ids follow the format `harness:model` (e.g. `claude-code:claude-fable-5-1`, `codex:gpt-6-terra`). To see every supported combination, call the agents endpoint:

```bash
curl -H "X-Lightsage-Api-Key: $LIGHTSAGE_API_KEY" \
  https://api.lightsage.com/v2/agents
```

Each entry in the response has an `id` you can use directly in the `agent` field of your eval definitions.

### MCP servers, CLIs, and secrets

There's no separate config store — define tools **inline** in the eval. Secrets never go in `evals.json`: MCP/CLI configs reference `${VAR}` placeholders, and `env` is a JSON object of variables to send with the run, whose values may themselves be `${VAR}` placeholders pulled from your environment (loaded from `.env`).

```json
{
  "name": "MCP eval",
  "prompt": "Use the lightsage MCP server to look something up.",
  "judge": ["The agent used the MCP server."],
  "agent": ["claude-code:claude-opus-4-8"],
  "mcps": [
    {
      "name": "lightsage",
      "type": "http",
      "url": "https://mcp.lightsage.com/mcp",
      "headers": {"X-Lightsage-Api-Key": "${LIGHTSAGE_API_KEY}"}
    }
  ],
  "clis": ["brew install lightsagehq/tools/lightsage"],
  "env": {"LIGHTSAGE_API_KEY": "${LIGHTSAGE_API_KEY}"}
}
```

`env` is a `{ "NAME": "value-or-${VAR}" }` object. `execute.py` resolves each `${VAR}` to the real value from your environment right before sending, so the committed JSON stays clean.

## Usage

The one-shot path is `python main.py` (execute → trace → analyze). You can also run each stage on its own:

### Execute

```bash
python scripts/execute.py     # run everything in evals.json
```

Each eval becomes one `POST /v2/eval-runs`. Run ids are written to `results/execute/results.json` right after the runs start (so they're never lost), then each run is polled with `GET /v2/eval-runs/{run_id}` and the status is redrawn as a table until everything finishes:

```
EVAL                         │ AGENT                          │ STATUS    │ PROGRESS
─────────────────────────────┼────────────────────────────────┼───────────┼─────────
Hello world                  │ claude-code:claude-opus-4-8    │ running   │ 2/4
SDK smoke test               │ claude-code:claude-opus-4-8    │ completed │ 8/8
```

Progress counts terminal child jobs (completed + failed + cancelled + interrupted) against the total. Non-completed terminal states are called out explicitly, e.g. `6/8 (1 failed)`. Completion is detected from `status`, not the progress counter.

### Trace

```bash
python scripts/trace.py <run_id>   # trace a single run
python scripts/trace.py --all      # trace every run in results/execute/results.json
```

Pages through `GET /v2/eval-runs/{run_id}/trace` and writes the merged trace to `results/trace/{run_id}.json`.

### Analyze

```bash
python scripts/analyze.py <run_id>   # analyze a single run
python scripts/analyze.py --all      # analyze every run in results/execute/results.json
```

Writes the run's per-attempt analysis (verdicts/findings) to `results/analyze/{run_id}.json`.

## API reference

- Docs index: [https://lightsage.com/docs/llms.txt](https://lightsage.com/docs/llms.txt)
- Start an eval run: [https://lightsage.com/docs/api-reference/eval-runs/start-an-eval-run](https://lightsage.com/docs/api-reference/eval-runs/start-an-eval-run)
- Monitor runs: [https://lightsage.com/docs/api-reference/eval-runs/monitor-runs](https://lightsage.com/docs/api-reference/eval-runs/monitor-runs)
- Retrieve analysis (top-level `analysis` on the run detail): [https://lightsage.com/docs/api-reference/eval-runs/retrieve-an-eval-run](https://lightsage.com/docs/api-reference/eval-runs/retrieve-an-eval-run)
- Retrieve trace: [https://lightsage.com/docs/api-reference/eval-runs/retrieve-an-eval-run-trace](https://lightsage.com/docs/api-reference/eval-runs/retrieve-an-eval-run-trace)

Auth is an API key sent in the `X-Lightsage-Api-Key` header on every request.
