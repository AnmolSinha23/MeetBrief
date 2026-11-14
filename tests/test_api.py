"""Tests for FastAPI endpoints."""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport

from app.main import app

@pytest.mark.asyncio
async def test_api_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "model" in data
        assert "mock_mode" in data

@pytest.mark.asyncio
async def test_api_demo_sample():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/samples/demo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["draft"]["developments"]) >= 1

@pytest.mark.asyncio
async def test_api_briefing_lifecycle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create briefing job
        payload = {
            "entity": "Stripe",
            "entity_type": "company",
            "meeting_time": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "timezone": "UTC",
            "meeting_type": "investor",
            "user_context": "Checking recent announcements.",
        }
        post_resp = await client.post("/api/briefings", json=payload)
        assert post_resp.status_code == 202
        job_id = post_resp.json()["job_id"]

        # 2. Wait and poll job status
        briefing_id = None
        for _ in range(30):
            job_resp = await client.get(f"/api/jobs/{job_id}")
            assert job_resp.status_code == 200
            job_data = job_resp.json()
            if job_data["status"] == "done":
                briefing_id = job_data["briefing_id"]
                break
            elif job_data["status"] == "error":
                pytest.fail(f"Job failed: {job_data.get('error')}")
            await asyncio.sleep(0.1)

        assert briefing_id is not None

        # 3. Get JSON
        get_resp = await client.get(f"/api/briefings/{briefing_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == briefing_id

        # 4. View HTML
        view_resp = await client.get(f"/api/briefings/{briefing_id}/view")
        assert view_resp.status_code == 200
        assert "text/html" in view_resp.headers["content-type"]
        assert "Stripe" in view_resp.text

        # 5. Export Markdown
        export_resp = await client.get(f"/api/briefings/{briefing_id}/export.md")
        assert export_resp.status_code == 200
        assert "text/markdown" in export_resp.headers["content-type"]
        assert "# Briefing: Stripe" in export_resp.text
