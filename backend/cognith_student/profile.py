"""CapabilityProfile — one student's capability state, validated against the graph.

This is where Phase 1 and Phase 2 meet. The profile holds StudentCapability rows, but it
needs the CapabilityGraph for two things it cannot do alone:

  1. reject rows for capabilities that do not exist
  2. answer questions that depend on structure — chiefly "which capabilities are blocked
     because something upstream was never demonstrated?"

Queries here return SIGNALS. Phase 5 decides which capabilities to diagnose and Phase 6
decides how evidence becomes mastery; neither policy lives in this file.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from cognith_capability.graph import CapabilityGraph
from cognith_capability.models import Capability

from .models import (
    DEMONSTRATED_AT,
    InvalidStudentCapability,
    MasteryStatus,
    Student,
    StudentCapability,
)

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "data" / "students"


class CapabilityProfile:
    """A student plus their capability rows, one row per capability at most.

    Capabilities with no row are not an error — an absent row and a row with everything
    None both mean "we know nothing", and `row_for()` returns an empty row so callers do
    not have to handle the two cases separately.
    """

    def __init__(
        self,
        student: Student,
        rows: Iterable[StudentCapability],
        graph: CapabilityGraph,
    ):
        self.student = student
        self.graph = graph
        self.rows: dict[str, StudentCapability] = {}
        for row in rows:
            if row.student_id != student.id:
                raise InvalidStudentCapability(
                    f"row for {row.capability_id!r} belongs to student "
                    f"{row.student_id!r}, not {student.id!r}"
                )
            if row.capability_id not in graph.capabilities:
                raise InvalidStudentCapability(
                    f"unknown capability {row.capability_id!r} — "
                    f"not in data/capabilities.yaml"
                )
            if row.capability_id in self.rows:
                raise InvalidStudentCapability(
                    f"duplicate row for capability {row.capability_id!r}"
                )
            self.rows[row.capability_id] = row

    # --- access ---------------------------------------------------------------------
    def row_for(self, capability_id: str) -> StudentCapability:
        """The row, or an empty (status=unknown) one. Never raises for a valid id."""
        self.graph.get(capability_id)  # raises with the list of valid ids
        return self.rows.get(
            capability_id,
            StudentCapability(student_id=self.student.id, capability_id=capability_id),
        )

    def all_rows(self) -> list[StudentCapability]:
        """Every capability in the graph, in §7 tree order, with empties filled in."""
        return [
            self.row_for(cap.id)
            for area in self.graph.areas
            for cap in self.graph.by_area(area)
        ]

    def capability(self, capability_id: str) -> Capability:
        return self.graph.get(capability_id)

    def set_confidence(self, capability_id: str, confidence: float | None) -> None:
        """Record a self-report. Cannot create or alter mastery — that needs evidence."""
        self.rows[capability_id] = self.row_for(capability_id).with_confidence(confidence)

    def record_assessment(
        self, capability_id: str, mastery: float, *, evidence_added: int = 1,
        at: datetime | None = None,
    ) -> StudentCapability:
        """Store an assessment outcome. Phase 6 computes `mastery` and calls this."""
        row = self.row_for(capability_id).record_assessment(
            mastery, evidence_added=evidence_added, at=at
        )
        self.rows[capability_id] = row
        return row

    # --- signals --------------------------------------------------------------------
    def by_status(self, status: MasteryStatus) -> list[StudentCapability]:
        return [r for r in self.all_rows() if r.status is status]

    def unverified(self) -> list[StudentCapability]:
        """Claimed but never assessed — what §9 means by "let's verify it".

        Ordered by confidence descending: the boldest unchecked claim first, because that
        is where a diagnostic is most informative.
        """
        return sorted(
            (r for r in self.all_rows() if r.is_unverified),
            key=lambda r: -(r.confidence or 0.0),
        )

    def calibration_gaps(self, min_gap: float = 0.0) -> list[StudentCapability]:
        """Assessed rows where the claim exceeds the evidence, widest gap first.

        Only meaningful once both numbers exist, so unverified rows are excluded by
        construction — there is nothing to compare them against yet.
        """
        scored = [
            r for r in self.all_rows()
            if r.calibration_gap is not None and r.calibration_gap >= min_gap
        ]
        return sorted(scored, key=lambda r: -(r.calibration_gap or 0.0))

    def blocked(self, threshold: float = DEMONSTRATED_AT) -> dict[str, list[Capability]]:
        """capability id -> prerequisites not demonstrated at `threshold`.

        The reason Phase 1 stored prerequisites as data. A student claiming System Design
        while Databases is unverified is not ready to be assessed on System Design — §10's
        point that the diagnostic should verify prerequisites rather than test everything.

        `threshold` is a parameter, not a constant, because what counts as "met" is a
        Phase 5 policy question. This method only reports structure.
        """
        out: dict[str, list[Capability]] = {}
        for cap in self.graph.capabilities.values():
            unmet = [
                prereq
                for prereq in self.graph.prerequisites_of(cap.id)
                if (self.row_for(prereq.id).mastery or 0.0) < threshold
            ]
            if unmet:
                out[cap.id] = unmet
        return out

    def weakest(self, n: int = 5) -> list[StudentCapability]:
        """Lowest demonstrated mastery first. Only assessed rows — a gap has to be shown.

        Deliberately NOT "gap detection". Phase 6 and Phase 7 decide what constitutes a
        gap worth acting on; this is the raw ordering they would start from.
        """
        assessed = [r for r in self.all_rows() if r.mastery is not None]
        return sorted(assessed, key=lambda r: r.mastery or 0.0)[:n]

    def summary(self) -> dict[str, Any]:
        rows = self.all_rows()
        counts = {s.value: 0 for s in MasteryStatus}
        for r in rows:
            counts[r.status.value] += 1
        assessed = [r.mastery for r in rows if r.mastery is not None]
        claimed = [r.confidence for r in rows if r.confidence is not None]
        return {
            "capabilities": len(rows),
            "by_status": counts,
            "evidence_total": sum(r.evidence_count for r in rows),
            "mean_confidence": round(sum(claimed) / len(claimed), 3) if claimed else None,
            "mean_mastery": round(sum(assessed) / len(assessed), 3) if assessed else None,
        }

    # --- persistence ----------------------------------------------------------------
    def to_records(self) -> dict[str, Any]:
        """The Claude.md §19 `students/` + `student_capabilities/` shape.

        Only rows that carry information are written. An empty row is the absence of data,
        and persisting 16 empty rows per student would make storage imply knowledge.
        """
        return {
            "student": self.student.to_record(),
            "student_capabilities": [
                r.to_record()
                for r in self.all_rows()
                if r.status is not MasteryStatus.UNKNOWN
            ],
        }

    def save(self) -> None:
        from .storage import get_storage

        get_storage().save_profile(self.student.id, self.to_records())

    @classmethod
    def load(cls, student_id: str, graph: CapabilityGraph) -> "CapabilityProfile":
        from .storage import get_storage

        payload = get_storage().load_profile(student_id)
        if payload is None:
            raise FileNotFoundError(f"No saved profile for {student_id!r}")
        return cls(
            student=Student.from_record(payload["student"]),
            rows=[
                StudentCapability.from_record(r)
                for r in payload.get("student_capabilities", [])
            ],
            graph=graph,
        )

    def __repr__(self) -> str:
        s = self.summary()
        return (
            f"CapabilityProfile(student={self.student.id!r}, "
            f"claimed={s['by_status']['claimed']}, "
            f"assessed={s['by_status']['developing'] + s['by_status']['demonstrated']}, "
            f"unknown={s['by_status']['unknown']})"
        )
