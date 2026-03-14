import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from app.db import AsyncSessionLocal

logger = logging.getLogger(__name__)

# SQL query to deactivate students whose FYP batch period has expired.
# Fall 20XX batches expire after 1st June 20XX+1
# Spring 20XX batches expire after 15th January 20XX+1
# We use make_date(year, month, day) which is Postgres-specific.
_DEACTIVATION_SQL = text(
    """
    UPDATE students
    SET is_active = false
    WHERE is_active = true
    AND fyp_start_semester IS NOT NULL
    AND fyp_start_year IS NOT NULL
    AND CURRENT_DATE >
        CASE
            WHEN LOWER(fyp_start_semester) = 'fall'
                THEN make_date(fyp_start_year + 1, 6, 1)
            WHEN LOWER(fyp_start_semester) = 'spring'
                THEN make_date(fyp_start_year + 1, 1, 15)
        END
"""
)


async def run_student_lifecycle_job():
    """
    Background job to deactivate students based on their FYP start batch.
    This job runs a single bulk SQL UPDATE for efficiency.
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(_DEACTIVATION_SQL)
            await db.commit()
            if result.rowcount > 0:
                logger.info(
                    f"[StudentLifecycle] Automatically deactivated {result.rowcount} expired students."
                )
    except Exception as e:
        logger.error(f"[StudentLifecycle] Job failed: {e}")


def create_scheduler() -> AsyncIOScheduler:
    """
    Creates and configures the AsyncIOScheduler for background tasks.
    Configured for Asia/Karachi (PKT) timezone.
    """
    scheduler = AsyncIOScheduler(timezone="Asia/Karachi")

    # Schedule the student deactivation job to run weekly every Monday at 2:00 AM
    scheduler.add_job(
        run_student_lifecycle_job,
        trigger="cron",
        day_of_week="mon",
        hour=2,
        minute=0,
        id="student_lifecycle_job",
        replace_existing=True,
    )

    return scheduler
