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
