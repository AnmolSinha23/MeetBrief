# MeetBrief — Build Log

## Findings (Phase 0 Documentation Research)
1. **Tavily Python SDK**:
   - `AsyncTavilyClient` provides asynchronous `search()` and `extract()`.
   - `search()` accepts `query`, `topic` (`"general"`, `"news"`, `"finance"`), `time_range` (`"day"`, `"week"`, `"month"`, `"year"`), `start_date` and `end_date` (format: `YYYY-MM-DD`), `max_results`, `search_depth` (`"basic"`, `"advanced"`), and `include_domains`.
   - `extract()` accepts `urls` (list up to 20), `extract_depth` (`"basic"`, `"advanced"`), and `format` (`"markdown"`, `"text"`).
   - Defensive strategy: if an SDK version or endpoint rejects `start_date`/`end_date`, retry with `time_range="month"` and rely on strict in-code post-filtering.
2. **Bifrost AI Gateway**:
   - Started via `npx -y @maximhq/bifrost`. Dashboard and API default to `http://localhost:8080`.
   - OpenAI-compatible chat completions endpoint is exposed at `http://localhost:8080/v1/chat/completions` (and drop-in `/openai` path).
   - Models are addressed using the `provider/model` namespace (e.g. `gemini/gemini-2.5-flash`).
   - Provider keys can be configured via the Bifrost dashboard (`Model Providers -> Google Gemini -> Add Key`) or passed via environment variables (such as `GEMINI_API_KEY`).
   - If `response_format={"type": "json_object"}` is rejected by a provider, defensive fallback strips markdown code fences from the prompt-guided JSON response.

## Progress
- **Phase 0 (Scaffold & Preflight)**: Completed.
  - Git repository initialized.
  - `.gitignore`, `.env.example`, `LICENSE`, `requirements.txt` created.
  - Directory structure initialized.
  - `scripts/start_bifrost.ps1`, `scripts/start_bifrost.sh`, `bifrost/config.json` created.
  - `scripts/doctor.py` and `scripts/run.py` created.
- **Phase 1 (Core models, config, window)**: Completed.
  - Implemented `app/models.py` with all Pydantic models from §4.
  - Implemented `app/config.py` with `pydantic-settings` and cached `get_settings()`.
  - Implemented `app/steps/window.py` enforcing 30-day window, timezone awareness, future clipping, and warnings.
  - Implemented `tests/test_window.py` covering past meetings, today, 3-day future, 45-day future, midnight timezone crossings, and naive datetime rejection.
  - All 6 unit tests passing.
- **Phase 2 (Clients with cache and mocks)**: Completed.
  - Implemented `app/cache.py` disk JSON cache with TTL.
  - Implemented `app/clients/search.py` with `SearchClient` Protocol, `TavilySearchClient` (async, timeout, retries, date-fallback, extract), and `MockSearchClient`.
  - Implemented `app/clients/llm.py` with `LLMClient` Protocol, `BifrostLLMClient` (async OpenAI SDK pointed at Bifrost `/v1` and `/openai` drop-in route, JSON fence stripping, 429 rate limit backoff), and `MockLLMClient`.
  - Created realistic fixtures in `tests/fixtures/`: `tavily_stripe.json` (includes stale-dated, undated, wrong-entity, syndicated duplicate, and prompt-injection items), `tavily_person.json`, `llm_resolve.json`, `llm_synthesize.json`, `llm_verify.json`.
  - Added unit tests in `tests/test_clients.py`; 10/10 tests passing.
- **Phase 3 (Resolve, plan, research, normalize)**: Completed.
  - Implemented `app/steps/resolve.py` for entity disambiguation and candidate generation.
  - Implemented `app/steps/plan.py` for deterministic query planning across company and person entities.
  - Implemented `app/steps/research.py` for concurrent execution, error tolerance, and trace tracking.
  - Implemented `app/steps/normalize.py` for URL canonicalization, date parsing, 30-day window filtering, relevance checks, primary source tagging, deduplication & syndication clustering (Jaccard similarity), score/recency ranking, and ID assignment.
  - Added unit tests in `tests/test_normalize.py`; 14/14 tests passing.
  - Checkpoint 3 validation run output (Stripe):
    - Window: 2026-10-15 to 2026-11-14
    - Resolved: Stripe (company), official_domain: stripe.com
    - Planned queries: 8
    - Raw results found: 48 (deduped to 6 sources)
    - Kept Sources Table:
      - S1 | 2026-11-05 | stripe.com     | Primary: True  | Cluster: 1 | Stripe Introduces Agentic Payments Toolkit
      - S2 | 2026-10-29 | wsj.com        | Primary: False | Cluster: 5 | Stripe Q3 2026 Platform Volume Hits $350B
      - S3 | 2026-11-08 | prnewswire.com | Primary: True  | Cluster: 2 | Stripe Partners with NVIDIA on Enterprise Billing
      - S4 | 2026-11-02 | techcrunch.com | Primary: False | Cluster: 3 | Stripe Expands Global Stablecoin Payouts
      - S5 | 2026-11-05 | yahoo.com      | Primary: False | Cluster: 1 | Stripe Introduces Agentic Payments Toolkit (syndicated)
      - S6 | 2026-10-25 | bloomberg.com  | Primary: False | Cluster: 4 | Stripe Appoints Former AWS Executive Claire Hughes
- **Phase 4 (Grounded synthesis and verification)**: Completed.
  - Implemented `app/prompts.py` with system and user prompt templates per §7.
  - Implemented `app/steps/synthesize.py` adhering to schema validation and repair retries.
  - Implemented `app/steps/verify.py` with deterministic number grounding, date boundary enforcement, code-computed confidence (VERIFIED/REPORTED/UNVERIFIED), batched LLM claim grounding check, unknown source dropping, and citation renumbering S1..Sn.
  - Fixed Pydantic `Development.date` field annotation to prevent class-level namespace shadowing.
  - Added unit tests in `tests/test_verify.py`; 17/17 tests passing.
  - Checkpoint 4 validation run verified end-to-end for both Company (Stripe) and Person (Jensen Huang) with 100% citation coverage and valid URLs.
- **Phase 5 (Orchestrator, render, REST API)**: Completed.
  - Implemented `app/templates/briefing.html.j2` (A4 print styles, badge styling, clickable citation anchors).
  - Implemented `app/templates/briefing.md.j2` (structured Markdown export).
  - Implemented `app/steps/render.py` (word budget <= 520, trimming priority order, date/confidence sorting).
  - Implemented `app/jobs.py` (in-memory job store for async progress polling).
  - Implemented `app/pipeline.py` (7-step pipeline orchestrator, trace capture, stats calculation, disk persistence).
  - Implemented `app/main.py` with all REST API endpoints:
    - `POST /api/briefings` (202 Accepted)
    - `GET /api/jobs/{job_id}`
    - `GET /api/briefings/{id}`
    - `GET /api/briefings/{id}/view`
    - `GET /api/briefings/{id}/export.md`
    - `GET /api/samples/demo`
    - `GET /api/health`
  - Generated committed offline sample `data/samples/sample_briefing.json`.
  - Added `tests/test_render.py`, `tests/test_pipeline_mock.py`, `tests/test_api.py`.
  - All 25 unit & integration tests passing. `python scripts/doctor.py --offline` PASS.
- **Phase 6 (Frontend Web UI)**: Completed.
  - Implemented single-page UI in `web/index.html` with responsive sidebar form and A4 canvas.
  - Implemented `web/styles.css` with professional typography, badges, progress bar, trace viewer, and `@media print` rules.
  - Implemented `web/app.js` with client timezone auto-detection, async polling, candidate disambiguation, Markdown export/copy, and A4 print triggers.
  - Captured all required UI screenshots into `docs/screenshots/`:
    - `form.png` (input form with empty canvas state)
    - `progress.png` (7-step stepper during pipeline execution)
    - `finished_briefing.png` (rendered A4 sheet with badges and clickable citations)
    - `trace_panel.png` (collapsible deterministic research audit trace)
    - `print_preview.png` (pure printable one-pager layout)
    - `disambiguation.png` (interactive candidate selection cards)
- **Phase 7 (Quality pass: eval + sample)**: Completed.
  - Implemented `scripts/make_sample.py` to regenerate the committed sample briefing.
  - Implemented `scripts/eval_samples.py` covering 4 diverse scenarios (Stripe, NVIDIA, Jensen Huang, Alex Smith).
  - Executed evaluation harness and generated `docs/eval-results.md`.
  - Invariants confirmed:
    - 100% of claims carry >= 1 valid citation.
    - 100% of dated developments reside strictly inside the 30-day temporal window.
    - Ambiguous entities gracefully trigger `needs_clarification` without hallucinated assumptions.

## Commands & Outcomes
- `git init`: initialized repository.
- `python -m venv .venv`: created virtual environment.
- `pip install -r requirements.txt`: installing core dependencies.

## Decisions
- Used `gemini/gemini-2.5-flash` as default `LLM_MODEL` matching the guide and Bifrost docs.
- Provided both `scripts/start_bifrost.ps1` and `scripts/start_bifrost.sh` for cross-platform portability.
- Built defensive fallback handling directly into doctor script and clients for `start_date`/`end_date` and `response_format`.

## Deviations from Guide
- None so far.

## LIVE-PENDING
- [ ] Live Tavily API search with valid `TAVILY_API_KEY` (deferred to teammate with real keys).
- [ ] Live Bifrost gateway connectivity and Gemini completions (deferred to teammate with real keys).
- [ ] Live evaluation with real external API calls via `scripts/eval_samples.py --live`.
