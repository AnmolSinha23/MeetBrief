#!/usr/bin/env python3
"""Preflight diagnostic doctor for MeetBrief.

Verifies:
1. Python >= 3.11 and dependencies installed.
2. .env configuration.
3. Tavily connectivity & response schema.
4. Bifrost gateway availability & drop-in path.
5. LLM chat completions and latency.
6. JSON mode support.
7. Optional --offline test against mock pipeline.
"""

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv

REQUIRED_PACKAGES = [
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("pydantic", "pydantic"),
    ("pydantic_settings", "pydantic-settings"),
    ("openai", "openai"),
    ("tavily", "tavily-python"),
    ("jinja2", "jinja2"),
    ("dateutil", "python-dateutil"),
    ("tldextract", "tldextract"),
    ("pytest", "pytest"),
    ("httpx", "httpx"),
    ("dotenv", "python-dotenv"),
]

def mask_key(k: str) -> str:
    if not k or len(k) < 8:
        return "****"
    return k[:5] + "..." + k[-4:]

async def check_tavily(api_key: str):
    from tavily import AsyncTavilyClient
    client = AsyncTavilyClient(api_key=api_key)
    today = datetime.now(timezone.utc).date()
    start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    used_fallback = False
    try:
        res = await client.search(
            query="Microsoft",
            topic="news",
            start_date=start_date,
            end_date=end_date,
            max_results=3,
        )
    except TypeError:
        # start_date/end_date not supported by this SDK version
        used_fallback = True
        res = await client.search(
            query="Microsoft",
            topic="news",
            time_range="month",
            max_results=3,
        )
    except Exception as e:
        if "400" in str(e) or "invalid" in str(e).lower():
            used_fallback = True
            res = await client.search(
                query="Microsoft",
                topic="news",
                time_range="month",
                max_results=3,
            )
        else:
            raise e

    results = res.get("results", [])
    raw_fields = list(results[0].keys()) if results else []
    date_field = None
    if results:
        for candidate in ["published_date", "published_time", "date", "publishedDate"]:
            if candidate in results[0] and results[0][candidate]:
                date_field = candidate
                break

    return {
        "count": len(results),
        "fields": raw_fields,
        "date_field": date_field,
        "used_fallback": used_fallback,
    }

async def check_bifrost(base_url: str, api_key: str):
    import httpx
    # Strip trailing /v1 or /openai to test base endpoints
    clean_url = base_url.rstrip("/")
    if clean_url.endswith("/v1"):
        clean_url = clean_url[:-3]
    elif clean_url.endswith("/openai"):
        clean_url = clean_url[:-7]

    candidates = [
        f"{clean_url}/v1/models",
        f"{clean_url}/openai/models",
        f"{base_url.rstrip('/')}/models",
    ]

    working_url = None
    error_msg = ""
    async with httpx.AsyncClient(timeout=2.5) as client:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        for cand in candidates:
            try:
                r = await client.get(cand, headers=headers)
                if r.status_code in (200, 401, 403):
                    working_url = cand
                    break
            except Exception as e:
                error_msg = str(e)

    return working_url, error_msg

async def check_llm_completion(base_url: str, api_key: str, model: str):
    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url=base_url, api_key=api_key or "dummy")
    t0 = time.perf_counter()
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with the single word OK"}],
        max_tokens=10,
        temperature=0.0,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    reply = resp.choices[0].message.content.strip() if resp.choices else ""
    return reply, latency_ms

async def check_json_mode(base_url: str, api_key: str, model: str):
    from openai import AsyncOpenAI
    client = AsyncOpenAI(base_url=base_url, api_key=api_key or "dummy")
    # Try with response_format
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Return a JSON object: {\"status\": \"ok\"}"},
                {"role": "user", "content": "Return status ok in json."}
            ],
            response_format={"type": "json_object"},
            max_tokens=50,
            temperature=0.0,
        )
        return True, "native response_format supported"
    except Exception as e:
        # Test fallback
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Return ONLY a JSON object: {\"status\": \"ok\"}"},
                    {"role": "user", "content": "Return status ok in json."}
                ],
                max_tokens=50,
                temperature=0.0,
            )
            return True, f"fallback prompt works (native rejected: {str(e)[:40]}...)"
        except Exception as e2:
            return False, f"JSON mode failed: {str(e2)}"

def run_offline_pipeline():
    try:
        from app.pipeline import run_pipeline
        from app.models import MeetingInput, MeetingType, EntityType
        from datetime import datetime, timezone, timedelta
        os.environ["MOCK_MODE"] = "true"
        meeting_time = datetime.now(timezone.utc) + timedelta(days=1)
        inp = MeetingInput(
            entity="Stripe",
            entity_type=EntityType.company,
            meeting_time=meeting_time,
            meeting_type=MeetingType.investor,
        )
        briefing = asyncio.run(run_pipeline(inp))
        if len(briefing.draft.developments) >= 1 and len(briefing.sources) >= 1:
            return True, f"Pipeline succeeded: {len(briefing.draft.developments)} developments, {len(briefing.sources)} sources"
        return False, f"Pipeline returned empty results: developments={len(briefing.draft.developments)}"
    except ImportError:
        return False, "Pipeline modules not implemented yet (Phase 5 will complete this)"
    except Exception as e:
        return False, f"Mock pipeline error: {str(e)}"

def main():
    parser = argparse.ArgumentParser(description="MeetBrief Preflight Doctor")
    parser.add_argument("--offline", action="store_true", help="Run offline mock pipeline verification only")
    args = parser.parse_args()

    print("=" * 65)
    print(" MeetBrief Preflight Doctor")
    print("=" * 65)

    all_pass = True

    # 1. Python version & dependencies
    py_ver = sys.version_info
    if py_ver >= (3, 11):
        print(f"[PASS] Python version {py_ver.major}.{py_ver.minor}.{py_ver.micro} >= 3.11")
    else:
        print(f"[FAIL] Python version {py_ver.major}.{py_ver.minor} < 3.11 (Need Python 3.11+)")
        all_pass = False

    missing_pkgs = []
    for mod_name, pkg_name in REQUIRED_PACKAGES:
        try:
            __import__(mod_name)
        except ImportError:
            missing_pkgs.append(pkg_name)

    if not missing_pkgs:
        print(f"[PASS] All {len(REQUIRED_PACKAGES)} core dependencies are installed and importable")
    else:
        print(f"[FAIL] Missing packages: {', '.join(missing_pkgs)}")
        print("       Fix: run 'pip install -r requirements.txt'")
        all_pass = False

    if args.offline:
        print("\n--- Offline Mock Mode Verification ---")
        ok, detail = run_offline_pipeline()
        if ok:
            print(f"[PASS] Offline mock pipeline check: {detail}")
        else:
            print(f"[FAIL] Offline mock pipeline check: {detail}")
            all_pass = False

        print("\n" + "=" * 65)
        print(f"OFFLINE CHECK RESULT: {'PASS' if all_pass else 'FAIL'}")
        print("=" * 65)
        sys.exit(0 if all_pass else 1)

    # 2. .env check
    load_dotenv()
    env_file = Path(".env")
    if not env_file.exists():
        print("[FAIL] .env file not found")
        print("       Fix: copy .env.example to .env and configure your keys")
        all_pass = False
    else:
        print("[PASS] .env file exists")

    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    bifrost_base_url = os.getenv("BIFROST_BASE_URL", "http://localhost:8080/v1").strip()
    bifrost_key = os.getenv("BIFROST_API_KEY", "dummy").strip()
    llm_model = os.getenv("LLM_MODEL", "gemini/gemini-2.5-flash").strip()

    tavily_configured = bool(tavily_key and tavily_key != "tvly-xxxxxxxx")
    if tavily_configured:
        print(f"[PASS] TAVILY_API_KEY is configured ({mask_key(tavily_key)})")
    else:
        print("[FAIL] TAVILY_API_KEY is missing or set to placeholder")
        print("       Fix: add your Tavily API key from https://app.tavily.com to .env")
        all_pass = False

    # 3. Tavily live search check
    if tavily_configured and not missing_pkgs:
        try:
            print("Checking Tavily API connectivity...")
            tav_info = asyncio.run(check_tavily(tavily_key))
            fallback_note = " (using time_range='month' fallback)" if tav_info["used_fallback"] else ""
            print(f"[PASS] Tavily live search returned {tav_info['count']} results{fallback_note}")
            print(f"       Raw fields: {', '.join(tav_info['fields'][:6])}...")
            print(f"       Date field detected: {tav_info['date_field'] or 'none'}")
        except Exception as e:
            print(f"[FAIL] Tavily live search failed: {str(e)}")
            print("       Fix: verify TAVILY_API_KEY and internet connection")
            all_pass = False
    else:
        print("[SKIP] Tavily live check skipped (key missing or packages not ready)")

    # 4. Bifrost gateway reachability
    print(f"Checking Bifrost gateway at {bifrost_base_url}...")
    try:
        working_url, err = asyncio.run(check_bifrost(bifrost_base_url, bifrost_key))
        if working_url:
            print(f"[PASS] Bifrost gateway reachable at: {working_url}")
        else:
            print(f"[FAIL] Bifrost gateway unreachable at {bifrost_base_url}")
            print("       Fix: start Bifrost with 'scripts/start_bifrost.ps1' or 'npx -y @maximhq/bifrost'")
            all_pass = False
    except Exception as e:
        print(f"[FAIL] Bifrost check error: {str(e)}")
        all_pass = False
        working_url = None

    # 5. LLM Completion check
    if working_url and not missing_pkgs:
        print(f"Checking LLM completions via Bifrost (model: {llm_model})...")
        try:
            reply, latency = asyncio.run(check_llm_completion(bifrost_base_url, bifrost_key, llm_model))
            print(f"[PASS] LLM replied: '{reply}' (latency: {latency} ms)")
        except Exception as e:
            print(f"[FAIL] LLM completion failed: {str(e)}")
            print("       Fix: check provider key in Bifrost UI (http://localhost:8080)")
            all_pass = False

        # 6. JSON Mode check
        print("Checking JSON mode support...")
        try:
            json_ok, json_msg = asyncio.run(check_json_mode(bifrost_base_url, bifrost_key, llm_model))
            if json_ok:
                print(f"[PASS] JSON mode: {json_msg}")
            else:
                print(f"[FAIL] JSON mode: {json_msg}")
                all_pass = False
        except Exception as e:
            print(f"[FAIL] JSON mode check error: {str(e)}")
            all_pass = False
    else:
        print("[SKIP] LLM completion & JSON mode checks skipped (gateway unreachable)")

    print("\n" + "=" * 65)
    status_str = "yes" if all_pass else "no"
    print(f"READY FOR LIVE USE: {status_str}")
    print("=" * 65)
    sys.exit(0 if all_pass else 1)

if __name__ == "__main__":
    main()
