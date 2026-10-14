"""Course packs — which course's data the engine is reading right now.

A course is a folder under `courses/<id>/` with everything course-specific:

    course.yaml        id, name, subject, settings (e.g. inline_math)
    capabilities.yaml  the skill map and prerequisites
    onboarding.yaml    goals, levels, topics, start-page text
    diagnostics.yaml   diagnosis questions with rubrics
    exercises.yaml     rubrics for the exercises in the material
    milestones.yaml    what "ready" means for the goal
    applications.yaml  optional combined challenges
    missions.yaml      optional simulation missions
    knowledge/*.md     the course material the tutor teaches from
    index.json         its embeddings (built by `build_pack.py <id>`)

Learners, evidence and generated challenges are NOT in the pack: they live in `data/`
(see cognith_student/storage.py) and each learner record names its course.

The active course is a context variable: the API sets it per request from the learner's
record, so concurrent requests for different courses never see each other's data. The
command-line tools use COGNITH_COURSE, defaulting to LEGACY_COURSE — the original
software-engineering pack, whose learners predate the `course` field.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

import yaml

ROOT = Path(__file__).resolve().parent.parent
COURSES_DIR = ROOT / "courses"

#: Learners created before course packs have no `course` field; they belong here.
LEGACY_COURSE = "backend-engineering"

_current: ContextVar[str] = ContextVar(
    "cognith_course", default=os.environ.get("COGNITH_COURSE", LEGACY_COURSE))


class UnknownCourse(KeyError):
    pass


def current() -> str:
    return _current.get()


def set_course(course_id: str) -> None:
    """Make `course_id` active for the rest of this context (one API request)."""
    if not (COURSES_DIR / course_id / "course.yaml").exists():
        raise UnknownCourse(course_id)
    _current.set(course_id)


@contextmanager
def using(course_id: str) -> Iterator[None]:
    token = _current.set(course_id)
    try:
        yield
    finally:
        _current.reset(token)


def course_dir(course_id: str | None = None) -> Path:
    return COURSES_DIR / (course_id or current())


def path(name: str, course_id: str | None = None) -> Path:
    """A file in the active course pack, e.g. path("capabilities.yaml")."""
    return course_dir(course_id) / name


@lru_cache
def info(course_id: str) -> dict[str, Any]:
    spec = yaml.safe_load((COURSES_DIR / course_id / "course.yaml").read_text(encoding="utf-8"))
    return {"id": course_id, "inline_math": False, "default": False, **(spec or {})}


def all_courses() -> list[dict[str, Any]]:
    """Every pack, default course first."""
    found = [info(p.parent.name) for p in sorted(COURSES_DIR.glob("*/course.yaml"))]
    return sorted(found, key=lambda c: (not c.get("default"), c.get("order", 99), c["id"]))
