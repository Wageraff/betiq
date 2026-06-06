"""Фоновый запуск CLI-задач парсера из админки."""
from __future__ import annotations

import asyncio
import os
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from src.config import BASE_DIR

_PY = BASE_DIR / "venv" / "bin" / "python3.11"
if not _PY.exists():
    _PY = BASE_DIR / "venv" / "bin" / "python"


@dataclass
class JobState:
    job_id: str
    command: str
    lines: deque[str] = field(default_factory=lambda: deque(maxlen=500))
    done: bool = False
    exit_code: Optional[int] = None


_jobs: dict[str, JobState] = {}


def _python() -> str:
    return str(_PY if _PY.exists() else "python3")


async def run_job(argv: list[str]) -> str:
    job_id = uuid.uuid4().hex[:12]
    cmd = " ".join(argv)
    state = JobState(job_id=job_id, command=cmd)
    _jobs[job_id] = state

    async def _runner() -> None:
        env = {"PYTHONPATH": str(BASE_DIR)}
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(BASE_DIR),
            env={**os.environ, **env},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert proc.stdout
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            state.lines.append(line)
        state.exit_code = await proc.wait()
        state.done = True
        state.lines.append(f"[exit {state.exit_code}]")

    asyncio.create_task(_runner())
    return job_id


def get_job_log(job_id: str) -> Optional[JobState]:
    return _jobs.get(job_id)


async def scrape_source(module: str, limit: int, force: bool) -> str:
    argv = [_python(), "-m", "src.scraper.engine", "--source", module, "--limit", str(limit)]
    if force:
        argv.append("--force")
    return await run_job(argv)


async def health_check(module: Optional[str] = None) -> str:
    argv = [_python(), "-m", "src.scraper.health_check"]
    if module:
        argv.extend(["--source", module])
    return await run_job(argv)


async def diagnose(module: str) -> str:
    return await run_job([_python(), "-m", "src.scraper.diagnose", "--source", module])


async def ai_summary(match_id: int, force: bool) -> str:
    argv = [_python(), "-m", "src.ai.summarizer", "--match-id", str(match_id)]
    if force:
        argv.append("--force")
    return await run_job(argv)


async def api_sync(action: str) -> str:
    allowed = {
        "link",
        "leagues",
        "logos",
        "form",
        "lineups",
        "odds",
        "stats",
        "cleanup",
        "cleanup_data",
        "reset_odds",
        "reset_odds_only",
    }
    if action not in allowed:
        raise ValueError(f"Unknown api_sync action: {action}")
    return await run_job([_python(), "scripts/api_sync.py", action])
