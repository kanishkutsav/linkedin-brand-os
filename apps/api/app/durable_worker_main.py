from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import SessionLocal
from app.jobs.durable_worker import DurableJobWorker
from app.models.models import DurableJob
from app.services.brand_learning import BrandLearningService


async def _learning(session: AsyncSession, job: DurableJob, payload: dict) -> dict:
    processed = await BrandLearningService(session).process_pending(limit=10)
    return {"processed_events": processed}


def build_durable_job_handlers() -> dict[str, Any]:
    return {"brand_learning_event": _learning}


def allowed_job_types() -> set[str]:
    allowed: set[str] = set()
    if settings.durable_learning_worker_enabled:
        allowed.add("brand_learning_event")
    return allowed


async def main() -> None:
    if not settings.durable_learning_worker_enabled:
        raise RuntimeError("Durable learning worker is disabled.")

    worker = DurableJobWorker(
        SessionLocal,
        build_durable_job_handlers(),
        allowed_job_types=allowed_job_types(),
        poll_interval_seconds=settings.durable_worker_poll_seconds,
        lease_seconds=settings.durable_worker_lease_seconds,
        max_attempts=settings.durable_worker_max_attempts,
    )
    await worker.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
