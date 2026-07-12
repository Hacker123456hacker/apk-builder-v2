from dataclasses import dataclass, field
from typing import Optional, List
import asyncio


@dataclass
class JobState:
    build_id: str
    phase: str = "analyzing"       # analyzing|fixing|uploading|building|done|error
    status: str = "queued"
    owner: str = ""
    repo: str = ""
    run_id: Optional[int] = None
    html_url: Optional[str] = None
    steps: List[dict] = field(default_factory=list)
    log_lines: List[str] = field(default_factory=list)
    upload_progress: float = 0.0
    upload_label: Optional[str] = None
    artifacts: List[dict] = field(default_factory=list)
    error: Optional[str] = None
    fix_results: List[dict] = field(default_factory=list)
    issues_found: int = 0
    issues_fixed: int = 0
    ai_analysis: Optional[dict] = None

    def log(self, line: str):
        self.log_lines.append(line)


class JobRegistry:
    def __init__(self):
        self._jobs: dict[str, JobState] = {}

    async def create(self, build_id: str) -> JobState:
        job = JobState(build_id=build_id)
        self._jobs[build_id] = job
        return job

    def get(self, build_id: str) -> Optional[JobState]:
        return self._jobs.get(build_id)

    def remove(self, build_id: str):
        self._jobs.pop(build_id, None)


registry = JobRegistry()
