"""FastAPI main application module for MeetBrief."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.jobs import job_store
from app.models import Briefing, MeetingInput
from app.pipeline import load_briefing, run_pipeline
from app.steps.render import render_html, render_markdown

logger = logging.getLogger("meetbrief")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = FastAPI(
    title="MeetBrief API",
    description="Pre-Meeting Briefing Agent — Grounded, source-backed briefings powered by Tavily & Bifrost",
    version="1.0.0",
)

# Enable CORS for frontend flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def _background_briefing_task(job_id: str, meeting_input: MeetingInput):
    """Executes briefing pipeline in the background and updates job store."""
    def on_progress(step_num: int, message: str):
        job_store.update_job(
            job_id,
            status="running",
            step=message,
            steps_done=step_num,
        )

    try:
        on_progress(1, "Starting pipeline...")
        briefing = await run_pipeline(
            meeting_input=meeting_input,
            progress_callback=on_progress,
        )
        job_store.update_job(
            job_id,
            status="done",
            step="Briefing generated successfully.",
            steps_done=7,
            briefing_id=briefing.id,
        )
    except Exception as e:
        logger.exception(f"Briefing generation failed for job {job_id}: {e}")
        # Friendly user-facing message per §8
        err_str = str(e)
        user_msg = err_str
        if "401" in err_str or "unauthorized" in err_str.lower() or "tavily" in err_str.lower():
            user_msg = "Tavily API key invalid or missing. Please check your .env configuration."
        elif "bifrost" in err_str.lower() or "connect" in err_str.lower() or "8080" in err_str:
            settings = get_settings()
            user_msg = f"Cannot reach Bifrost at {settings.BIFROST_BASE_URL}. Start it with 'npx -y @maximhq/bifrost' or 'scripts/start_bifrost.ps1'."

        job_store.update_job(
            job_id,
            status="error",
            step="Generation failed.",
            error=user_msg,
        )

@app.post("/api/briefings", status_code=status.HTTP_202_ACCEPTED)
async def create_briefing(meeting_input: MeetingInput, background_tasks: BackgroundTasks) -> Dict[str, str]:
    """Starts a briefing generation job."""
    job = job_store.create_job()
    background_tasks.add_task(_background_briefing_task, job.id, meeting_input)
    return {"job_id": job.id}

@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str) -> Dict[str, Any]:
    """Polls briefing job progress."""
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.model_dump()

@app.get("/api/briefings/{briefing_id}")
async def get_briefing_json(briefing_id: str) -> Briefing:
    """Returns full Briefing JSON."""
    briefing = load_briefing(briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    return briefing

@app.get("/api/briefings/{briefing_id}/view", response_class=HTMLResponse)
async def view_briefing_html(briefing_id: str):
    """Returns rendered A4 HTML printable one-pager."""
    briefing = load_briefing(briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    html_content = render_html(briefing)
    return HTMLResponse(content=html_content)

@app.get("/api/briefings/{briefing_id}/export.md")
async def export_briefing_markdown(briefing_id: str):
    """Downloads briefing as a Markdown file."""
    briefing = load_briefing(briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found")
    md_content = render_markdown(briefing)
    filename = f"briefing_{briefing.entity.canonical_name.replace(' ', '_').lower()}.md"
    return Response(
        content=md_content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@app.get("/api/samples/demo")
async def get_demo_briefing() -> Briefing:
    """Returns committed sample briefing for offline demo mode."""
    briefing = load_briefing("demo")
    if not briefing:
        # Fallback: create mock briefing on the fly
        from datetime import datetime, timezone, timedelta
        from app.models import EntityType, MeetingType
        inp = MeetingInput(
            entity="Stripe",
            entity_type=EntityType.company,
            meeting_time=datetime.now(timezone.utc) + timedelta(days=1),
            meeting_type=MeetingType.investor,
            user_context="Evaluating payment infrastructure partnership opportunities.",
        )
        briefing = await run_pipeline(inp)
    return briefing

@app.get("/api/health")
async def health_check() -> Dict[str, Any]:
    """Health status check verifying Bifrost reachability and Tavily key setup."""
    settings = get_settings()

    tavily_ok = bool(settings.TAVILY_API_KEY and settings.TAVILY_API_KEY != "tvly-xxxxxxxx")
    bifrost_reachable = False

    # Ping Bifrost /models with 2.0s timeout
    try:
        clean_base = settings.BIFROST_BASE_URL.rstrip("/")
        models_url = f"{clean_base}/models"
        async with httpx.AsyncClient(timeout=2.0) as client:
            headers = {"Authorization": f"Bearer {settings.BIFROST_API_KEY}"} if settings.BIFROST_API_KEY else {}
            resp = await client.get(models_url, headers=headers)
            if resp.status_code in (200, 401, 403):
                bifrost_reachable = True
    except Exception:
        bifrost_reachable = False

    all_ok = (tavily_ok and bifrost_reachable) or settings.MOCK_MODE

    return {
        "ok": all_ok,
        "tavily_configured": tavily_ok,
        "bifrost_reachable": bifrost_reachable,
        "model": settings.LLM_MODEL,
        "mock_mode": settings.MOCK_MODE,
    }

# Mount static files and web frontend
web_dir = Path(__file__).parent.parent / "web"
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = web_dir / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>MeetBrief API is running. Web interface not found.</h1>")
