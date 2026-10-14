# Architecture

This documents the shape the agent settled into after the provider-resilience
and reliability work described in the project's architecture review. It maps
back to the 17-item proposal that drove it.

```
                    User Task
                        |
                        v
                 Planner Agent            (agent/planner.py)
                        |
                        v
              WebAgentReasoner            (agent/reasoning.py, the Executor)
                        |
          +-------------+--------------+
          v                            v
   Action Validator            Page-change detector
   (agent/validation.py)       (skips redundant LLM calls)
          |                            |
          +-------------+--------------+
                        v
                 Browser Executor       (agent/browser.py: Chromium/Firefox/WebKit)
                        |
                        v
                 Memory / State         (agent/memory.py: goal, facts, failures)
                        |
                        v
                Provider Router         (agent/llm/router.py)
                        |
    +----------+--------+----------+----------+
    v          v                   v          v
  Groq      Gemini             OpenRouter   Ollama (local)
                        |
                        v
                 Verifier Agent         (agent/verifier.py)
                        |
                        v
               Structured AgentRun
```

## Provider layer

`agent/llm/base.py` defines `BaseLLM` — a single `plan(system_prompt,
user_prompt, screenshot_b64, tools) -> LLMResponse` method every provider
implements. `agent/llm/router.py`'s `LLMRouter` tries providers in order,
retrying each with exponential backoff on retryable errors (429/503/timeout)
before falling through to the next. `agent/config.py::build_router` wires up
whichever of Groq / Gemini / OpenRouter / Ollama have credentials configured.
The Executor never talks to a specific SDK — a single provider outage no
longer stops the agent.

## Planner / Executor / Verifier

`WebAgentReasoner` is the Executor: it still runs a step-by-step ReAct loop
(see `run()`), but two more agents wrap it:

- **Planner** (`agent/planner.py`) produces a one-shot, non-binding subtask
  breakdown folded into the Executor's prompt as guidance. It's advisory —
  the Executor can and does deviate when the page doesn't match the plan.
- **Verifier** (`agent/verifier.py`) checks every `task_complete` claim
  against the actual final page state before accepting it. A rejected claim
  feeds back into the loop as a scratchpad note instead of ending the run,
  which is what `evaluation/metrics.py`'s `hallucination_rate` measures.

Both are auto-constructed from `Settings` for real runs and are off by
default in tests that inject a scripted fake router, so existing test
expectations about exact call counts didn't need to change.

## Memory, validation, and perception

- `agent/memory.py`'s `TaskMemory` tracks the goal, a scratchpad, visited
  URLs, extracted facts, and — separately from general action history — a
  `failures` list used to detect repeated dead ends (`is_repeating_failure`).
- `agent/validation.py` checks a proposed action's `element_id` and required
  arguments against the current `PageState` *before* it reaches the browser,
  turning a hallucinated element id into a cheap repair note instead of a
  wasted round trip.
- Perception combines DOM (`perception/dom_parser.py`), the accessibility
  tree (`perception/accessibility.py`), the annotated screenshot
  (`perception/screenshot.py`), and an optional OCR pass
  (`perception/ocr.py`, degrades to `""` when Tesseract isn't installed)
  into one `PageState`, capped at 100 elements and including focused-element
  and scroll-position signals to keep the prompt compact.
- `agent/reasoning.py` hashes page state each step and, after a settling
  action (`wait`/`scroll`) with no observed change, auto-retries a short
  wait instead of spending another LLM call — capped at `MAX_AUTO_SKIPS`.

## Multi-tab and multi-browser

`tools/parallel.py`'s `extract_from_urls_parallel` opens up to 5 URLs
concurrently on the same browser context for research-style tasks.
`agent/browser.py::BrowserSession` accepts `engine="chromium" | "firefox" |
"webkit"` and is exercised against all three in `tests/test_browser.py`.

## Observability

`observability/tracer.py`'s `Tracer` writes one JSONL record per step
(prompt/response summary, action, latency-relevant timestamp, tokens, a
per-step screenshot, and a DOM diff against the previous step's element
ids). `BrowserSession.start_tracing()`/`stop_tracing()` capture a Playwright
`trace.zip` (openable with `npx playwright show-trace`), and
`start(record_video_dir=...)` records a session video — both wired into
`scripts/run_benchmark.py`.

## Benchmark

`evaluation/tasks.py` covers 15 categories (the original 5 plus shopping,
Wikipedia, tables, downloads, authentication, pagination, infinite scroll,
CAPTCHA detection, dynamic content, and file uploads), using public QA/
scraping sandboxes (`books.toscrape.com`, `the-internet.herokuapp.com`) and
Google's own reCAPTCHA demo page for deterministic, legitimate coverage. The
CAPTCHA task explicitly instructs detection-and-fail rather than bypass.
`evaluation/metrics.py` reports success rate, avg steps/tokens/time, avg
retries, recovery rate (succeeded despite a mid-run failure), and
hallucination rate (verifier rejected at least one `task_complete` claim).

## Why not adopt a framework wholesale

LangGraph, AutoGen, and browser-use each solve part of this well, but
committing to one would mean designing around its state-machine or
multi-agent conventions instead of this project's own. The
`BrowserSession` / `Reasoner` (Executor) / `ActionDispatcher` split already
mirrors what those frameworks provide, at a fraction of the dependency
surface, and stays swappable — the Planner/Executor/Verifier split above was
built the same way rather than pulling in a multi-agent framework.

## Known gaps / config-dependent pieces

- **OpenRouter** needs `OPENROUTER_API_KEY` in `.env`; without it, `build_router`
  silently skips it in the fallback chain.
- **Ollama** defaults to `qwen2.5-coder:7b` and needs a local Ollama daemon;
  its tool-calling is unreliable on small models, so `OllamaLLM` also parses
  an inline-JSON fallback when `tool_calls` isn't populated.
- **OCR** needs the `tesseract` binary + `pytesseract`; when either is
  missing, `perception/ocr.py` degrades to `""` rather than failing
  perception.
