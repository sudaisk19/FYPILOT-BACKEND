import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db import AsyncSessionLocal
from app.repositories.student_repository import student_repository

# Use the uvicorn.error logger so it shows up in your terminal
logger = logging.getLogger("uvicorn.error")


async def run_student_lifecycle_job():
    """
    Background job to deactivate students based on their FYP start batch.
    This job runs a single bulk SQL UPDATE for efficiency via the repository.
    """
    try:
        async with AsyncSessionLocal() as db:
            rowcount = await student_repository.deactivate_expired_students(db)
            await db.commit()
            if rowcount > 0:
                logger.info(
                    f"✅ [StudentLifecycle] Automatically deactivated {rowcount} expired students."
                )
            else:
                logger.info(
                    "ℹ️ [StudentLifecycle] No students were eligible for deactivation today."
                )
    except Exception as e:
        logger.error(f"❌ [StudentLifecycle] Job failed: {e}")


def create_scheduler() -> AsyncIOScheduler:
    """
    Creates and configures the AsyncIOScheduler for background tasks.
    Configured for Asia/Karachi (PKT) timezone.
    """
    scheduler = AsyncIOScheduler(timezone="Asia/Karachi")

    # Temporarily scheduled for test: Tuesday at 12:20 AM
    scheduler.add_job(
        run_student_lifecycle_job,
        trigger="cron",
        day_of_week="tue",
        hour=0,
        minute=20,
        id="student_lifecycle_job",
        replace_existing=True,
    )

    return scheduler
