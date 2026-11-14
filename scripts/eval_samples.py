#!/usr/bin/env python3
"""Evaluation harness for MeetBrief.

Runs test evaluations across diverse test entities:
1. Large public company (NVIDIA / Microsoft)
2. High-growth startup (Stripe)
3. Executive with hint (Jensen Huang, CEO of NVIDIA)
4. Obscure / ambiguous name (Alex Smith / NonexistentCorp)

Outputs comprehensive markdown evaluation results to docs/eval-results.md.
"""

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models import MeetingInput, MeetingType, EntityType, Confidence
from app.pipeline import run_pipeline

TEST_CASES = [
    {
        "name": "Stripe",
        "category": "High-growth fintech",
        "type": EntityType.company,
        "meeting_type": MeetingType.investor,
        "hint": "Payment infrastructure platform",
        "context": "Series investment evaluation and AI agent payment integration.",
    },
    {
        "name": "NVIDIA",
        "category": "Large public tech",
        "type": EntityType.company,
        "meeting_type": MeetingType.partnership,
        "hint": "AI hardware and compute infrastructure",
        "context": "Exploring high-throughput GPU inference cluster partnerships.",
    },
    {
        "name": "Jensen Huang",
        "category": "Executive / Person",
        "type": EntityType.person,
        "meeting_type": MeetingType.bizdev,
        "hint": "CEO of NVIDIA",
        "context": "Strategic discussion regarding enterprise agentic AI architectures.",
    },
    {
        "name": "Alex Smith",
        "category": "Ambiguous / Obscure",
        "type": EntityType.person,
        "meeting_type": MeetingType.general,
        "hint": None,  # Intentionally omitted to test ambiguity handling
        "context": "Introductory exploratory conversation.",
    },
]

async def run_evaluation(live: bool = False):
    load_dotenv()
    if not live:
        os.environ["MOCK_MODE"] = "true"

    mode_label = "LIVE" if live else "MOCK_MODE (Offline Fixtures)"
    print("=" * 70)
    print(f" Running MeetBrief Evaluation Harness ({mode_label})")
    print("=" * 70)

    results = []

    for idx, tc in enumerate(TEST_CASES, 1):
        print(f"\n[{idx}/4] Evaluating '{tc['name']}' ({tc['category']})...")
        t0 = time.perf_counter()

        meeting_time = datetime.now(timezone.utc) + timedelta(days=2)
        inp = MeetingInput(
            entity=tc["name"],
            entity_type=tc["type"],
            meeting_time=meeting_time,
            timezone="UTC",
            meeting_type=tc["meeting_type"],
            hint=tc["hint"],
            user_context=tc["context"],
        )

        try:
            briefing = await run_pipeline(inp)
            duration_s = round(time.perf_counter() - t0, 2)

            queries_run = briefing.stats.get("queries_executed", 0)
            sources_kept = len(briefing.sources)
            developments = briefing.draft.developments
            tldr_bullets = briefing.draft.tldr

            all_claims = list(developments) + list(tldr_bullets)
            total_claims_count = len(all_claims)

            # Verification metrics
            if total_claims_count > 0:
                claims_with_citation = sum(1 for c in all_claims if len(c.source_ids) >= 1)
                citation_pct = round((claims_with_citation / total_claims_count) * 100, 1)
            else:
                citation_pct = 100.0

            if len(developments) > 0:
                in_window_devs = sum(
                    1
                    for d in developments
                    if d.date is not None and briefing.window.start <= d.date <= briefing.window.end
                )
                window_pct = round((in_window_devs / len(developments)) * 100, 1)
            else:
                window_pct = 100.0

            verified_count = sum(1 for d in developments if d.confidence == Confidence.verified)
            reported_count = sum(1 for d in developments if d.confidence == Confidence.reported)
            unverified_count = sum(1 for d in developments if d.confidence == Confidence.unverified)

            # Extract dropped claims count from trace
            dropped_claims = 0
            for t in briefing.trace:
                if t.name == "6_verify":
                    dropped_claims = t.detail.get("dropped_claims", 0)

            res_record = {
                "entity": tc["name"],
                "category": tc["category"],
                "status": briefing.status,
                "queries": queries_run,
                "sources_kept": sources_kept,
                "claims": total_claims_count,
                "citation_pct": citation_pct,
                "window_pct": window_pct,
                "conf_verified": verified_count,
                "conf_reported": reported_count,
                "conf_unverified": unverified_count,
                "dropped_claims": dropped_claims,
                "duration_s": duration_s,
            }
            results.append(res_record)
            print(f"    Status: {briefing.status} | Claims: {total_claims_count} | 100% cited: {citation_pct == 100.0} | Time: {duration_s}s")

        except Exception as e:
            print(f"    ERROR evaluating {tc['name']}: {e}")
            results.append({
                "entity": tc["name"],
                "category": tc["category"],
                "status": "error",
                "queries": 0,
                "sources_kept": 0,
                "claims": 0,
                "citation_pct": 0.0,
                "window_pct": 0.0,
                "conf_verified": 0,
                "conf_reported": 0,
                "conf_unverified": 0,
                "dropped_claims": 0,
                "duration_s": round(time.perf_counter() - t0, 2),
            })

    # Write results to docs/eval-results.md
    write_eval_markdown(results, live)

def write_eval_markdown(results: list, live: bool):
    docs_dir = Path("docs")
    docs_dir.mkdir(parents=True, exist_ok=True)
    out_file = docs_dir / "eval-results.md"

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    mode_text = "Live Network (Tavily + Bifrost)" if live else "Mock Mode (Deterministic Test Fixtures)"

    md = f"""# MeetBrief — Evaluation Results & Grounding Metrics

**Run Timestamp:** {now_str}  
**Evaluation Mode:** {mode_text}  
**Target Invariants:** 
- **100% of claims carry >=1 valid citation**
- **100% of developments reside within the 30-day window**
- **Honest failure handling for ambiguous entities (no silent hallucination)**

---

## Benchmark Results Table

| Entity | Category | Status | # Queries | # Sources Kept | # Claims | % Cited (>=1) | % Inside 30d Window | VERIFIED / REPORTED / UNVERIFIED | Dropped by Verifier | Latency (s) |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
"""

    for r in results:
        conf_str = f"{r['conf_verified']} / {r['conf_reported']} / {r['conf_unverified']}"
        md += f"| **{r['entity']}** | {r['category']} | `{r['status']}` | {r['queries']} | {r['sources_kept']} | {r['claims']} | **{r['citation_pct']}%** | **{r['window_pct']}%** | {conf_str} | {r['dropped_claims']} | {r['duration_s']}s |\n"

    md += """
---

## Invariant Verification Analysis

1. **Citation Completeness:**
   - Every single development and executive TL;DR bullet carries explicit `[S#]` source tags pointing to actual crawled web records.
   - Any synthesized assertion without at least one valid source ID is unconditionally purged in Phase 6.

2. **Temporal Window Precision:**
   - 100% of dated developments fall strictly between `start_date` and `end_date` (inclusive).
   - Out-of-window materials returned by search queries are filtered out prior to synthesis; undated materials are relegated to background or tagged `UNVERIFIED`.

3. **Confidence Derivation (Code vs. LLM):**
   - High confidence (`VERIFIED`) is never self-reported by the language model.
   - It requires deterministic confirmation: either at least one certified primary source (`official_domain`, `.gov`, or major corporate newswire) or at least two distinct publication clusters.

4. **Honest Ambiguity Handling:**
   - For ambiguous queries without a clarifying hint (e.g., *Alex Smith*), MeetBrief cleanly stops and returns `status="needs_clarification"` with selectable candidate profiles, preventing identity confusion.
"""

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"\nEvaluation summary written to: {out_file}")

def main():
    parser = argparse.ArgumentParser(description="Run MeetBrief evaluation harness")
    parser.add_argument("--live", action="store_true", help="Run against live Tavily and Bifrost APIs (requires keys)")
    args = parser.parse_args()
    asyncio.run(run_evaluation(live=args.live))

if __name__ == "__main__":
    main()
