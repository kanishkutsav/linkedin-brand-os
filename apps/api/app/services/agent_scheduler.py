from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import AgentRun

from app.agents.orchestrator import AgentOrchestrator
from app.core.config import settings


class AgentScheduler:
    """Small in-process scheduler for the first production slice.

    It supports three independent triggers:
    1. daily discovery
    2. scheduled content calendar
    3. event-driven runs via the API event endpoint

    Render can run this alongside the FastAPI web process. The event endpoint is
    the integration point for future webhooks/event sources.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory
        self._task: asyncio.Task | None = None
        self._last_discovery_date: str | None = None
        self._last_calendar_date: str | None = None

    def start(self) -> None:
        if settings.agent_enabled and self._task is None:
            self._task = asyncio.create_task(self._loop(), name="agent-scheduler")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        tz = ZoneInfo(settings.agent_timezone)
        while True:
            now = datetime.now(tz)
            if settings.agent_daily_discovery_enabled:
                if (
                    now.hour == settings.agent_daily_discovery_hour
                    and now.minute == settings.agent_daily_discovery_minute
                    and self._last_discovery_date != now.date().isoformat()
                ):
                    await self._run("discovery")
                    self._last_discovery_date = now.date().isoformat()

            if settings.agent_calendar_enabled:
                if (
                    now.hour == settings.agent_calendar_hour
                    and now.minute == settings.agent_calendar_minute
                    and self._last_calendar_date != now.date().isoformat()
                ):
                    await self._run("calendar")
                    self._last_calendar_date = now.date().isoformat()

            await asyncio.sleep(30)

    async def _run(self, mode: str) -> None:
        async with self.session_factory() as session:
            run = AgentRun(
                mode=mode,
                trigger=f"scheduled:{mode}",
                status="RUNNING",
            )
            session.add(run)
            await session.flush()
            try:
                orchestrator = AgentOrchestrator(session)
                if mode == "calendar":
                    result = await orchestrator.run_calendar()
                else:
                    result = await orchestrator.run_discovery()
                run.status = "SUCCEEDED"
                run.created_count = result["created_count"]
                run.details = str(result)
            except Exception as exc:
                run.status = "FAILED"
                run.details = str(exc)
            finally:
                run.finished_at = datetime.now(ZoneInfo("UTC"))
                await session.commit()
