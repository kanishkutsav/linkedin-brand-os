from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.orchestrator import AgentOrchestrator
from app.models.models import AgentRun, BrandMemory, UserProfile
from app.services.brand_learning import BrandLearningService
from app.services.retention import RetentionService


class ScheduledJobs:
    """Business operations invoked by a scheduler.

    PostgreSQL transaction-scoped advisory locks are held on a dedicated connection
    for the full invocation. Work sessions may commit per profile without
    releasing the scheduler lock.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    @staticmethod
    def scheduled_run_key(mode: str, profile_id: int, day: object) -> str:
        return f"{mode}:{profile_id}:{day.isoformat()}"

    async def run(self, mode: str, profile_id: int | None = None) -> dict:
        mode_aliases = {"discovery": "daily_post", "calendar": "research"}
        mode = mode_aliases.get(mode, mode)
        if mode not in {"daily_post", "research"}:
            raise ValueError(f"Unsupported scheduled job: {mode}")

        # Use one lock key per mode so an all-user invocation and a
        # single-profile invocation cannot race each other.
        async with self.session_factory() as lock_session:
            bind = lock_session.bind
            if bind is not None and bind.dialect.name == "postgresql":
                lock_key = f"brand-os-scheduled:{mode}"
                await lock_session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                    {"lock_key": lock_key},
                )
                # Keep this transaction open while work runs in another
                # session. Closing the lock session releases the xact lock.
                return await self._run_locked(mode, profile_id)

        # SQLite/unit-test fallback. The unique scheduled_key remains the
        # durable invariant in production; PostgreSQL provides cross-instance
        # serialization around the read/claim/run sequence.
        return await self._run_locked(mode, profile_id)

    async def _run_locked(self, mode: str, profile_id: int | None = None) -> dict:
        tz = ZoneInfo("Asia/Kolkata")
        today = datetime.now(tz).date()
        day_start = datetime.combine(today, time.min, tzinfo=tz)
        day_end = day_start + timedelta(days=1)
        stale_run_cutoff = datetime.now(timezone.utc) - timedelta(minutes=45)
        summary = {"mode": mode, "profiles": 0, "skipped": 0, "succeeded": 0, "failed": 0}

        async with self.session_factory() as session:
            profile_query = (
                select(UserProfile.id)
                .join(BrandMemory, BrandMemory.profile_id == UserProfile.id)
                .where(BrandMemory.status == "READY")
            )
            if profile_id is not None:
                profile_query = profile_query.where(UserProfile.id == profile_id)

            result = await session.execute(profile_query)
            profile_ids = [int(row[0]) for row in result.all()]
            if profile_id is not None and not profile_ids:
                summary["skipped"] = 1
                return summary

            for current_profile_id in profile_ids:
                summary["profiles"] += 1
                scheduled_key = self.scheduled_run_key(mode, current_profile_id, today)
                existing_result = await session.execute(
                    select(AgentRun).where(AgentRun.scheduled_key == scheduled_key).limit(1)
                )
                run = existing_result.scalar_one_or_none()

                # A successful legacy run always wins over a retryable row.
                # This also protects the rollout day when old and new workers
                # may have left more than one same-day record.
                successful_result = await session.execute(
                    select(AgentRun)
                    .where(
                        AgentRun.user_id == current_profile_id,
                        AgentRun.mode == mode,
                        AgentRun.trigger == f"scheduled:{mode}",
                        AgentRun.started_at >= day_start,
                        AgentRun.started_at < day_end,
                        AgentRun.status == "SUCCEEDED",
                    )
                    .order_by(AgentRun.started_at.desc())
                    .limit(1)
                )
                successful_run = successful_result.scalar_one_or_none()
                if successful_run is not None and successful_run.id != (run.id if run else None):
                    if run is not None:
                        run.scheduled_key = None
                    successful_run.scheduled_key = scheduled_key
                    await session.flush()
                    summary["skipped"] += 1
                    continue

                # Adopt a same-day run created by the previous application
                # version so deployment does not create a second run today.
                if run is None:
                    legacy_result = await session.execute(
                        select(AgentRun)
                        .where(
                            AgentRun.user_id == current_profile_id,
                            AgentRun.mode == mode,
                            AgentRun.trigger == f"scheduled:{mode}",
                            AgentRun.started_at >= day_start,
                            AgentRun.started_at < day_end,
                        )
                        .order_by(AgentRun.started_at.desc())
                        .limit(1)
                    )
                    run = legacy_result.scalar_one_or_none()
                    if run is not None:
                        run.scheduled_key = scheduled_key

                if run is None:
                    run = AgentRun(
                        user_id=current_profile_id,
                        mode=mode,
                        trigger=f"scheduled:{mode}",
                        status="RUNNING",
                        scheduled_key=scheduled_key,
                    )
                    session.add(run)
                    await session.flush()
                elif run.status == "SUCCEEDED":
                    summary["skipped"] += 1
                    continue
                elif run.status == "RUNNING" and run.started_at >= stale_run_cutoff:
                    # A recent RUNNING record may still belong to a live
                    # invocation from a pre-lock deployment.
                    summary["skipped"] += 1
                    continue

                # FAILED or stale RUNNING records are reused, not duplicated.
                run.status = "RUNNING"
                run.started_at = datetime.now(timezone.utc)
                run.finished_at = None
                run.created_count = 0
                run.details = None
                run_id = run.id
                await session.commit()

                try:
                    orchestrator = AgentOrchestrator(session, current_profile_id)
                    if mode == "daily_post":
                        run_result = await orchestrator.run_daily_post()
                    else:
                        run_result = await orchestrator.run_research_refresh()
                    run.status = "SUCCEEDED"
                    run.created_count = int(run_result["created_count"])
                    run.details = str(run_result)
                    summary["succeeded"] += 1
                except Exception as exc:
                    await session.rollback()
                    run = await session.get(AgentRun, run_id)
                    if run is not None:
                        run.status = "FAILED"
                        run.details = str(exc)[:4000]
                    summary["failed"] += 1
                finally:
                    run = await session.get(AgentRun, run_id)
                    if run is not None:
                        run.finished_at = datetime.now(timezone.utc)
                    await session.commit()

        return summary

    async def process_learning(self, session: AsyncSession, *, limit: int = 10) -> None:
        await BrandLearningService(session).process_pending(limit=limit)

    async def process_retention(self, session: AsyncSession):
        return await RetentionService().compact(session)
