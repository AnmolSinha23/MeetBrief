# MeetBrief — Architecture & Technical Design

MeetBrief is an autonomous, grounded pre-meeting briefing agent engineered specifically for executive meeting preparation. Rather than relying on an unconstrained, non-deterministic chat agent, MeetBrief employs a **7-stage deterministic research and verification pipeline**.

---

## 1. System Architecture

```mermaid
flowchart LR
  UI[Web UI (Vanilla HTML/CSS/JS)] -->|POST /api/briefings| API[FastAPI Server]
  API --> ORCH[Pipeline Orchestrator]
  ORCH --> R1[1 Resolve Entity]
  R1 --> R2[2 Plan Queries]
  R2 --> R3[3 Research via Tavily]
  R3 --> R4[4 Normalize, Window Filter, Dedupe & Cluster]
  R4 --> R5[5 Synthesize Draft via Bifrost LLM]
  R5 --> R6[6 Grounding Verification & Confidence]
  R6 --> R7[7 Enforce A4 Budget & Render]
  R3 -.-> T[(Tavily API)]
  R1 -.-> T
  R5 -.-> B[Bifrost Gateway] --> P[LLM Provider - Gemini]
  R6 -.-> B
  R7 --> OUT[HTML / Markdown / JSON + Audit Trace]
```

---

## 2. Core Architectural Principles

### 2.1 Deterministic Pipeline vs. Free-Form Chatbot
Unconstrained AI chatbots frequently hallucinate dates, confuse corporate entities, and generate ungrounded claims. MeetBrief replaces the black-box agent loop with a deterministic state machine:
- Query templates are generated through rule-based priority heuristics across 7 business categories.
- Date filtering, relevance checks, and URL canonicalization are enforced in native Python code.
- Verification and confidence derivation are calculated algorithmically, not delegated to model self-reflection.

### 2.2 Strict 30-Day Window Enforcement
Temporal accuracy is critical in executive briefings. A launch from two years ago must not be represented as recent news.
1. The research window is calculated strictly as `end = min(meeting_date, today_date)` and `start = end - 30 days`.
2. Tavily queries pass `start_date` and `end_date` (with automatic fallback to `time_range="month"` if rejected).
3. The normalizer enforces a post-filter on parsed publication dates. Any dated article outside the window is dropped. Undated articles are marked `in_window=False` and can never serve as the sole source of a development.

### 2.3 Computed Confidence (Code, Not LLM)
Language models are notoriously prone to over-confidence. In MeetBrief, confidence badges are assigned strictly by code:
- **`VERIFIED`**: The claim's cited sources are all within the 30-day window AND supported by either:
  - At least 1 certified primary source (official domain, `.gov`, `sec.gov`, or major corporate newswire).
  - At least 2 distinct publication clusters.
- **`REPORTED`**: The claim is supported by exactly 1 non-primary in-window source cluster.
- **`UNVERIFIED`**: An undated source, ungrounded numerical figures, or claims flagged as partial by the verifier.

### 2.4 Syndication Clustering (Near-Duplicate Detection)
When a company publishes a press release, dozens of content aggregators republish identical copy across Yahoo Finance, Morningstar, and small blogs. Counting these as independent confirmations creates false confidence.
MeetBrief calculates word token Jaccard similarity between incoming titles ($J \ge 0.8$) and groups syndicated copies into a shared `cluster_id`. Multiple articles in the same cluster only count as **one** source of confirmation.

### 2.5 Dual-Pass Grounding Verification
1. **Deterministic Number & Entity Check**: Every number, percentage, currency amount, and 4-digit year in a claim must literally appear in the cited source text (`title` + `snippet`). Any claim failing this check is automatically downgraded to `UNVERIFIED` with a note appended to uncertainties.
2. **LLM Semantic Grounding**: A batched fact-checker checks whether cited text logically supports the assertion. Unsupported claims are purged completely.

### 2.6 A4 One-Page Budget Enforcement
Executive briefings must fit onto a single page. If content exceeds limits, MeetBrief enforces a deterministic trimming hierarchy:
1. Low-priority developments (UNVERIFIED first, then oldest)
2. Risks
3. Talking points
4. Evidence gaps
Total non-source words are capped at **520 words**, ensuring a single A4 printed page.

---

## 3. Technology Stack & Integration Architecture

| Component | Technology | Rationale |
|---|---|---|
| Web Gateway / API | FastAPI + Uvicorn | Async performance, strict Pydantic v2 schemas, automated OpenAPI docs |
| Search Engine | Tavily API (`AsyncTavilyClient`) | Real-time temporal filtering, high-quality news index, clean markdown/text extraction |
| LLM Gateway | Bifrost Gateway (`http://localhost:8080`) | OpenAI-compatible unified proxy, request logging, provider fallbacks |
| Default LLM | Google Gemini 2.5 Flash via Bifrost | Fast inference, large context window, cost-efficient structured JSON output |
| Frontend | Vanilla HTML5 / CSS3 / ES6 JS | Zero build step, instant local startup, lightweight, no framework churn |
| Templates | Jinja2 | Unified single source of truth for both A4 HTML and Markdown export |
| Storage & Cache | Local JSON files in `data/` | Zero external database dependencies; fully portable across environments |

---

## 4. Bifrost Gateway Deep Dive

MeetBrief interacts with language models **exclusively** through the Bifrost Gateway.
- **OpenAI SDK Compatibility**: The Python application initializes `AsyncOpenAI(base_url=settings.BIFROST_BASE_URL, api_key=settings.BIFROST_API_KEY)`.
- **Zero Lock-In**: Switching from Gemini to Claude, GPT-4o, or a local Ollama model requires changing only the `LLM_MODEL` environment variable (e.g., `gemini/gemini-2.5-flash` to `openai/gpt-4o`).
- **Defensive Gateway Fallback**: If Bifrost's default `/v1` endpoint is relocated, the client automatically detects and retries against the drop-in `/openai` route.
- **Observability**: All requests, latency metrics, and token usages are visible in the Bifrost web UI dashboard at `http://localhost:8080`.
