"""Where learner state lives — the one seam between the engine and persistence.

Two documents per learner, plus generated challenges:

    profile     {"student": {...}, "student_capabilities": [...]}   rewritten on save
    evidence    [{"evidence": {...}, "assessment": {...}}, ...]       append-only
    activities  one record per generated challenge (prompt + rubric)  write-once

Every read and write of those goes through `get_storage()`. Before this module existed
the engine opened `data/students/*.json` and `data/evidence/*.json` from seven places,
which made a Firestore backend a refactor of the engine rather than a new class.

Selected by COGNITH_STORAGE:

    file        (default) JSON files under data/ — what every CLI has always used.
                COGNITH_DATA_DIR points it elsewhere, e.g. a scratch copy for a demo run.
    firestore   not built here; see FirestoreStorage below for the contract.

The shapes are unchanged from the file format, so a Firestore backend stores the same
records and the engine cannot tell the difference.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class Storage(Protocol):
    def load_profile(self, student_id: str) -> dict[str, Any] | None: ...
    def save_profile(self, student_id: str, record: dict[str, Any]) -> None: ...
    def list_students(self) -> list[str]: ...
    def load_evidence(self, student_id: str) -> list[dict[str, Any]]: ...
    def append_evidence(self, student_id: str, entry: dict[str, Any]) -> None: ...
    def save_activity(self, record: dict[str, Any]) -> None: ...
    def list_activities(self) -> list[dict[str, Any]]: ...


class FileStorage:
    def __init__(self, root: Path = DATA_DIR):
        self.students = root / "students"
        self.evidence = root / "evidence"
        self.generated = root / "generated"

    def load_profile(self, student_id: str) -> dict[str, Any] | None:
        path = self.students / f"{student_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save_profile(self, student_id: str, record: dict[str, Any]) -> None:
        self.students.mkdir(parents=True, exist_ok=True)
        path = self.students / f"{student_id}.json"
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    def list_students(self) -> list[str]:
        if not self.students.exists():
            return []
        return sorted(p.stem for p in self.students.glob("*.json"))

    def load_evidence(self, student_id: str) -> list[dict[str, Any]]:
        path = self.evidence / f"{student_id}.json"
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def append_evidence(self, student_id: str, entry: dict[str, Any]) -> None:
        self.evidence.mkdir(parents=True, exist_ok=True)
        log = self.load_evidence(student_id)
        log.append(entry)
        path = self.evidence / f"{student_id}.json"
        path.write_text(json.dumps(log, indent=2), encoding="utf-8")

    def save_activity(self, record: dict[str, Any]) -> None:
        self.generated.mkdir(parents=True, exist_ok=True)
        path = self.generated / f"{record['id']}.json"
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    def list_activities(self) -> list[dict[str, Any]]:
        if not self.generated.exists():
            return []
        return [json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(self.generated.glob("*.json"))]


class FirestoreStorage:
    """NOT BUILT — owned by the backend/data developer.

    Suggested layout, matching Claude.md §19:

        students/{id}                          the "student" record
        student_capabilities/{id}__{capId}     one doc per row in "student_capabilities"
        evidence/{autoId}                      one doc per log entry, with studentId and
                                               evidence.createdAt for ordering
        learning_experiences/{id}              generated challenges (save/list_activities)

    `load_evidence` must return entries oldest first; history and retry detection
    depend on that order. The full contract, as tests, is tests/test_storage_contract.py;
    the handoff note is docs/firestore-handoff.md.

    `prefix` namespaces every collection name, so tests can isolate their data.
    """

    def __init__(self, client: Any = None, prefix: str = "") -> None:
        raise NotImplementedError("Set COGNITH_STORAGE=file until Firestore is wired in.")


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        kind = os.environ.get("COGNITH_STORAGE", "file")
        root = Path(os.environ.get("COGNITH_DATA_DIR", DATA_DIR))
        _storage = FirestoreStorage() if kind == "firestore" else FileStorage(root)
    return _storage


def set_storage(storage: Storage | None) -> None:
    """Swap the backend — for tests, or a Firestore instance built elsewhere."""
    global _storage
    _storage = storage
