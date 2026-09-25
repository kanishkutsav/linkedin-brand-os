from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.orchestrator import AgentOrchestrator
from app.models.models import AgentRun, BrandMemory, UserProfile
from app.services.brand_learning import BrandLearningService
from app.services.retention import RetentionService


class ScheduledJobs:
    """Business operations invoked by a scheduler.

    No timing or task-lifecycle concerns belong here. Keeping these operations
    behind a small job boundary lets the same work be called by the current
    in-process scheduler and, later, by durable scheduled execution.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def run(self, mode: str) -> None:
        if mode not in {"discovery", "calendar"}:
            raise ValueError(f"Unsupported scheduled job: {mode}")

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

    async def process_learning(self, session: AsyncSession, *, limit: int = 10) -> None:
        await BrandLearningService(session).process_pending(limit=limit)

    async def process_retention(self, session: AsyncSession):
        return await RetentionService().compact(session)
