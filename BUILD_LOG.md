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
- **Phase 0 (Scaffold & Preflight)**: In progress.
  - Git repository initialized.
  - `.gitignore`, `.env.example`, `LICENSE`, `requirements.txt` created.
  - Directory structure initialized.
  - `scripts/start_bifrost.ps1`, `scripts/start_bifrost.sh`, `bifrost/config.json` created.
  - `scripts/doctor.py` and `scripts/run.py` created.

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
