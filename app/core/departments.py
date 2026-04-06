"""Common university department definitions and helpers."""

from typing import Final

COMMON_UNIVERSITY_DEPARTMENTS: Final[list[str]] = [
    "Architecture",
    "Artificial Intelligence",
    "Biomedical Engineering",
    "Business Administration",
    "Chemical Engineering",
    "Civil Engineering",
    "Computer Science",
    "Data Science",
    "Electrical Engineering",
    "Electronics Engineering",
    "Industrial Engineering",
    "Mechanical Engineering",
    "Software Engineering",
    "Telecommunication Engineering",
]

_DEPARTMENT_LOOKUP: Final[dict[str, str]] = {
    department.lower(): department for department in COMMON_UNIVERSITY_DEPARTMENTS
}


def normalize_department(value: str) -> str:
    """Validate and normalize a department name to the canonical list."""
    if not value:
        raise ValueError("Department is required.")

    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("Department is required.")

    canonical = _DEPARTMENT_LOOKUP.get(normalized)
    if not canonical:
        allowed = ", ".join(COMMON_UNIVERSITY_DEPARTMENTS)
        raise ValueError(f"Department must be one of: {allowed}")

    return canonical


__all__ = ["COMMON_UNIVERSITY_DEPARTMENTS", "normalize_department"]
