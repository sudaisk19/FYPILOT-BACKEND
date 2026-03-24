import asyncio

from sqlalchemy import text

from app.db import AsyncSessionLocal


async def check_students():
    async with AsyncSessionLocal() as db:
        # Check how many students would be deactivated
        check_sql = text(
            """
            SELECT user_id, roll_number, fyp_start_semester, fyp_start_year, is_active
            FROM students
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

        result = await db.execute(check_sql)
        expired_students = result.fetchall()

        print(
            f"Number of students currently active but eligible for deactivation: {len(expired_students)}"
        )
        for student in expired_students:
            print(
                f" - {student.roll_number} ({student.fyp_start_semester} {student.fyp_start_year})"
            )


if __name__ == "__main__":
    asyncio.run(check_students())
