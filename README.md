# Autonomous Web Agent

[![CI](https://github.com/Parakh20/autonomous-web-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Parakh20/autonomous-web-agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An autonomous agent that drives a real browser (Chromium, Firefox, or WebKit)
through Playwright and reasons in a ReAct loop. On each step it perceives the
page, decides the next action, executes it, and repeats until the task is done
or the step cap is reached. A Planner sketches subtasks up front, and a
Verifier checks every completion claim against the actual final page before
accepting it. LLM calls go through a provider router (Groq, Gemini,
OpenRouter, Ollama) with retry and fallback, so one provider going down
doesn't stop the agent.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full system diagram and
per-component detail. This file is the quickstart.

## Architecture (short version)

```
Task → Planner (subtask sketch)
     → Executor ReAct loop:
         Perceive (DOM + a11y tree + screenshot + OCR + viewport)
         → Validate the proposed action against the page
         → Reason via Provider Router (Groq → Gemini → OpenRouter → Ollama)
         → Execute via Playwright
     → Verifier checks task_complete claims against final page state
     → Result
```

- **LLM layer** (`agent/llm/`): a `BaseLLM` interface with Groq, Gemini,
  OpenRouter, and Ollama providers behind an `LLMRouter`. The router retries
  with exponential backoff and falls back to the next configured provider on
  429/503/timeout.
- **Planner / Executor / Verifier** (`agent/planner.py`,
  `agent/reasoning.py`, `agent/verifier.py`): the Executor runs the
  step-by-step loop. The Planner sketches non-binding subtasks up front. The
  Verifier checks `task_complete` claims against the real final page, and a
  rejected claim goes back into the loop instead of ending the run.
- **Memory** (`agent/memory.py`): goal, scratchpad, extracted facts, and a
  separate failures list used to detect repeated dead ends and loops.
- **Validation** (`agent/validation.py`): checks a proposed action's
  `element_id` and required arguments against the current page *before* it
  reaches the browser. A hallucinated element id becomes a cheap repair note
  instead of a wasted round trip.
- **Perception** (`perception/`): DOM, accessibility tree, annotated
  screenshot, an optional OCR pass, and viewport/scroll/focused-element
  signals. Capped at 100 elements to keep prompts compact.
- **Browser** (`agent/browser.py`): Chromium, Firefox, or WebKit via
  Playwright. Multi-tab parallel extraction lives in `tools/parallel.py`.
- **Observability** (`observability/`): per-step JSONL trace with screenshot
  and DOM diff. Playwright `trace.zip` and session video capture are wired
  into the benchmark runner.
- **Evaluation** (`evaluation/`): 37 benchmark tasks across 15 categories
  (information extraction, multi-step navigation, form interaction, data
  aggregation, reasoning over content, shopping, Wikipedia, tables,
  downloads, authentication, pagination, infinite scroll, CAPTCHA detection,
  dynamic content, file uploads). An LLM judge scores them, and
  success rate, efficiency, recovery rate, and hallucination rate are rolled
  up into `results/summary.txt`.

## Quick start

Requires Python 3.11+.

```bash
git clone https://github.com/Parakh20/autonomous-web-agent.git
cd autonomous-web-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium firefox webkit
cp .env.example .env   # then add at least one provider key (see below)
```

On a fresh Linux machine, `python -m playwright install --with-deps ...` also
installs the system libraries the browsers need.

`requirements.txt` includes `pytesseract` for OCR. It also needs the
`tesseract-ocr` system package (`sudo apt-get install tesseract-ocr` on
Debian/Ubuntu). If either piece is missing, OCR returns an empty string and
the agent keeps working without it.

### Configuration (`.env`)

Copy [`.env.example`](.env.example) to `.env` and set at least one provider.
Providers are tried in `LLM_PROVIDER_ORDER` (default
`groq,gemini,openrouter,ollama`), falling back left to right on failure.

| Provider | Env vars | Notes |
|---|---|---|
| Groq | `GROQ_API_KEY`, `GROQ_MODEL` | |
| Gemini | `GEMINI_API_KEY`, `GEMINI_MODEL` | |
| OpenRouter | `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | one key, many models |
| Ollama | `OLLAMA_MODEL`, `OLLAMA_BASE_URL` | local, no key needed; requires `ollama serve` |

`BROWSER_ENGINE` selects `chromium` (default), `firefox`, or `webkit`.

## Usage

### Run a single task

```bash
python scripts/run_task.py "Go to Hacker News and summarize today's #1 story" --max-steps 15
```

A browser window performs the task live (pass `--headless` to hide it). The
CLI prints the final result, step count, token count, duration, and final URL.

### Run interactively

```bash
python scripts/interactive.py
```

Keeps one browser session open and takes instructions one at a time from the
terminal until you type `exit`.

### Run the benchmark

```bash
python scripts/run_benchmark.py
```

Runs all 37 tasks against live websites (this needs a provider key and makes
real LLM calls). Each task gets a trace, a `trace.zip`, and a session video
under `results/traces/<task_id>/`. Per-task JSON goes to `results/benchmark/`,
and the run rolls up into `results/summary.txt` and
`results/benchmark_summary.csv`. All of `results/` output is gitignored.

### Run the UI

```bash
streamlit run ui/app.py
```

## Running the tests

```bash
python -m pytest -q
```

The suite runs fully offline: browser tests load local HTML fixtures from
`tests/fixtures/` through a throwaway HTTP server, and LLM providers are
replaced with scripted fakes or mocked HTTP transports. No API keys are
needed. The browser-engine tests need all three Playwright browsers installed
(see Quick start). CI runs the same command on every push and pull request.

## Project structure

```
agent/            Core agent: browser session, ReAct executor, planner, verifier,
                  memory, action validation, config
  llm/            BaseLLM interface, provider router, Groq/Gemini/OpenRouter/Ollama
perception/       DOM parser, accessibility tree, annotated screenshots, OCR
tools/            Browser actions: navigate, interact, extract, search, wait, parallel tabs
evaluation/       Benchmark task set, LLM judge, metrics aggregation
observability/    Per-step JSONL tracer and replay
scripts/          CLI entry points: run_task, interactive, run_benchmark
ui/               Streamlit front end
tests/            pytest suite and HTML fixtures
ARCHITECTURE.md   Detailed design notes
```

## Known limitations

- CAPTCHAs are detected and reported via `task_failed`, never bypassed. The
  `captcha_detection` benchmark category grades on graceful failure, not on
  solving the challenge.
- DuckDuckGo's HTML search endpoint can change its markup. If search results
  suddenly come back empty, the CSS selectors in `tools/search.py` may need
  updating.
- Benchmark tasks hit live public websites, so results can vary from run to
  run as those sites change their layout or content.

## License

[MIT](LICENSE)
