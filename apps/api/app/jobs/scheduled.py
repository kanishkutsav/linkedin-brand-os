from __future__ import annotations

import argparse
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.agents.orchestrator import AgentOrchestrator
from app.db.database import SessionLocal
from app.models.models import AgentRun, BrandMemory, UserProfile
from app.core.config import settings

logger = logging.getLogger(__name__)

SCHEDULE_TIMEZONE = ZoneInfo("Asia/Kolkata")
SCHEDULES = {
    "discovery": (9, 0),
    "calendar": (9, 15),
}


async def _claim_run(session, *, profile_id: int, mode: str, scheduled_key: str) -> AgentRun | None:
    """Claim one scheduled execution for a profile.

    The unique scheduled_key constraint is the cross-process safety net. A
    successful or currently running execution is never duplicated. A failed
    execution can be retried manually on the same scheduled key.
    """
    existing = (
        await session.execute(
            select(AgentRun)
            .where(AgentRun.scheduled_key == scheduled_key)
            .limit(1)
        )
    ).scalar_one_or_none()

    if existing is not None:
        if existing.status in {"RUNNING", "SUCCEEDED"}:
            return None
        existing.status = "RUNNING"
        existing.created_count = 0
        existing.details = None
        existing.started_at = datetime.now(SCHEDULE_TIMEZONE)
        existing.finished_at = None
        await session.flush()
        return existing

    run = AgentRun(
        user_id=profile_id,
        mode=mode,
        trigger=f"scheduled:{mode}",
        status="RUNNING",
        scheduled_key=scheduled_key,
    )
    session.add(run)
    await session.flush()
    return run


async def run_scheduled(mode: str) -> dict[str, object]:
    if not settings.agent_enabled:
        logger.info("Scheduled agent disabled by AGENT_ENABLED")
        return {
            "mode": mode,
            "disabled": True,
            "reason": "agent_enabled=false",
        }

    if mode not in SCHEDULES:
        raise ValueError(f"Unsupported scheduled mode: {mode}")

    now = datetime.now(SCHEDULE_TIMEZONE)
    hour, minute = SCHEDULES[mode]
    scheduled_date = now.date().isoformat()
    scheduled_key_prefix = f"scheduled:{mode}:{scheduled_date}"

    logger.info(
        "Starting scheduled agent job mode=%s scheduled_date=%s timezone=%s",
        mode,
        scheduled_date,
        SCHEDULE_TIMEZONE.key,
    )

    async with SessionLocal() as session:
        result = await session.execute(
            select(UserProfile.id)
            .join(BrandMemory, BrandMemory.profile_id == UserProfile.id)
            .where(BrandMemory.status == "READY")
            .order_by(UserProfile.id)
        )
        profile_ids = [int(row[0]) for row in result.all()]

        processed = 0
        skipped = 0
        failed = 0
        created = 0

        for profile_id in profile_ids:
            scheduled_key = f"{scheduled_key_prefix}:{profile_id}"
            run = await _claim_run(
                session,
                profile_id=profile_id,
                mode=mode,
                scheduled_key=scheduled_key,
            )
            if run is None:
                skipped += 1
                continue

            processed += 1
            try:
                orchestrator = AgentOrchestrator(session, profile_id)
                if mode == "discovery":
                    run_result = await orchestrator.run_discovery(
                        trigger="scheduled_daily"
                    )
                else:
                    run_result = await orchestrator.run_calendar(
                        trigger="scheduled_calendar"
                    )

                run.status = "SUCCEEDED"
                run.created_count = int(run_result.get("created_count", 0))
                run.details = str(
                    {
                        "scheduled_date": scheduled_date,
                        "scheduled_time": f"{hour:02d}:{minute:02d}",
                        **run_result,
                    }
                )
                run.finished_at = datetime.now(SCHEDULE_TIMEZONE)
                created += run.created_count
                await session.commit()
                logger.info(
                    "Scheduled agent completed mode=%s profile_id=%s created=%s",
                    mode,
                    profile_id,
                    run.created_count,
                )
            except Exception as exc:
                await session.rollback()
                failed += 1
                logger.exception(
                    "Scheduled agent failed mode=%s profile_id=%s",
                    mode,
                    profile_id,
                )
                # Preserve a durable failed run so the failure is visible and
                # a manual rerun can retry the same scheduled key.
                failed_run = (
                    await session.execute(
                        select(AgentRun)
                        .where(AgentRun.scheduled_key == scheduled_key)
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if failed_run is not None:
                    failed_run.status = "FAILED"
                    failed_run.details = str(exc)
                    failed_run.finished_at = datetime.now(SCHEDULE_TIMEZONE)
                    await session.commit()

        summary = {
            "mode": mode,
            "scheduled_date": scheduled_date,
            "scheduled_time": f"{hour:02d}:{minute:02d}",
            "timezone": SCHEDULE_TIMEZONE.key,
            "profiles_found": len(profile_ids),
            "profiles_processed": processed,
            "profiles_skipped": skipped,
            "profiles_failed": failed,
            "created_count": created,
        }
        logger.info("Scheduled agent summary: %s", summary)
        return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a LinkedIn Brand OS scheduled agent job.")
    parser.add_argument("mode", choices=sorted(SCHEDULES))
    args = parser.parse_args()

    import asyncio

    asyncio.run(run_scheduled(args.mode))


if __name__ == "__main__":
    main()
