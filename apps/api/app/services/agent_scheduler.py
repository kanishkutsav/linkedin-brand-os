from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import AgentRun, BrandMemory, UserProfile

from app.agents.orchestrator import AgentOrchestrator
from app.services.brand_learning import BrandLearningService
from app.services.retention import RetentionService
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
        self._last_retention_date: str | None = None

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

            async with self.session_factory() as learning_session:
                try:
                    await BrandLearningService(learning_session).process_pending(limit=10)
                except Exception as exc:
                    # Learning is additive. A temporary embedding/LLM outage must never affect scheduled content generation.
                    print(f"Brand learning cycle skipped: {exc}")

                if self._last_retention_date != now.date().isoformat():
                    try:
                        retention = await RetentionService().compact(learning_session)
                        print(f"Brand OS retention cycle completed: {retention}")
                        self._last_retention_date = now.date().isoformat()
                    except Exception as exc:
                        await learning_session.rollback()
                        # Retention is strictly additive to the product lifecycle:
                        # a cleanup failure must never block learning or generation.
                        print(f"Brand OS retention cycle skipped: {exc}")

            await asyncio.sleep(30)

    async def _run(self, mode: str) -> None:
        async with self.session_factory() as session:
            result = await session.execute(
                select(UserProfile.id)
                .join(BrandMemory, BrandMemory.profile_id == UserProfile.id)
                .where(BrandMemory.status == "READY")
            )
            profile_ids = [int(row[0]) for row in result.all()]

            for profile_id in profile_ids:
                run = AgentRun(
                    user_id=profile_id,
                    mode=mode,
                    trigger=f"scheduled:{mode}",
                    status="RUNNING",
                )
                session.add(run)
                await session.flush()
                try:
                    orchestrator = AgentOrchestrator(session, profile_id)
                    if mode == "calendar":
                        run_result = await orchestrator.run_calendar()
                    else:
                        run_result = await orchestrator.run_discovery()
                    run.status = "SUCCEEDED"
                    run.created_count = run_result["created_count"]
                    run.details = str(run_result)
                except Exception as exc:
                    run.status = "FAILED"
                    run.details = str(exc)
                finally:
                    run.finished_at = datetime.now(ZoneInfo("UTC"))
                    await session.commit()
