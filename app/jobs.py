"""In-memory job tracking store for asynchronous briefing generation."""

import uuid
from datetime import datetime, timezone
from typing import Dict, Literal, Optional
from pydantic import BaseModel, Field

JobStatus = Literal["queued", "running", "done", "error"]

class JobRecord(BaseModel):
    id: str
    status: JobStatus = "queued"
    step: str = "Initializing briefing request..."
    steps_done: int = 0
    steps_total: int = 7
    briefing_id: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class JobStore:
    """Thread-safe in-memory store for active jobs."""

    def __init__(self):
        self._jobs: Dict[str, JobRecord] = {}

    def create_job(self) -> JobRecord:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        job = JobRecord(id=job_id)
        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        return self._jobs.get(job_id)

    def update_job(
        self,
        job_id: str,
        status: Optional[JobStatus] = None,
        step: Optional[str] = None,
        steps_done: Optional[int] = None,
        briefing_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Optional[JobRecord]:
        job = self._jobs.get(job_id)
        if not job:
            return None

        if status is not None:
            job.status = status
        if step is not None:
            job.step = step
        if steps_done is not None:
            job.steps_done = steps_done
        if briefing_id is not None:
            job.briefing_id = briefing_id
        if error is not None:
            job.error = error

        return job

# Global singleton job store
job_store = JobStore()
