"""The Storage contract, run against every backend.

FileStorage always runs. FirestoreStorage runs when COGNITH_TEST_STORAGE=firestore, which
is meant for the Firestore emulator:

    gcloud emulators firestore start --host-port=localhost:8085
    FIRESTORE_EMULATOR_HOST=localhost:8085 COGNITH_TEST_STORAGE=firestore \
        GOOGLE_CLOUD_PROJECT=demo-cognith pytest tests/

Each Firestore test gets its own collection prefix, so tests never see each other's data.
"""

from __future__ import annotations

import copy
import os
import uuid

import pytest

from cognith_student.storage import FileStorage


def backends() -> list[str]:
    return ["file", "firestore"] if os.environ.get("COGNITH_TEST_STORAGE") == "firestore" else ["file"]


def make_storage(kind: str, tmp_path):
    if kind == "firestore":
        from cognith_student.storage import FirestoreStorage

        return FirestoreStorage(prefix=f"test-{uuid.uuid4().hex[:8]}-")
    return FileStorage(tmp_path)


@pytest.fixture(params=backends())
def store(request, tmp_path):
    return make_storage(request.param, tmp_path)


def profile(sid: str, mastery: float | None = 0.42) -> dict:
    return {
        "student": {"id": sid, "name": "Ada", "goal": "Build a production-ready REST API",
                    "course": "rest-api", "createdAt": "2026-10-16T09:00:00+00:00"},
        "student_capabilities": [
            {"id": f"{sid}__http-requests", "studentId": sid, "capabilityId": "http-requests",
             "confidence": 0.475, "mastery": mastery, "status": "developing",
             "evidenceCount": 3, "lastAssessedAt": None},
        ],
    }


def entry(sid: str, n: int, at: str = "2026-10-16T09:30:00+00:00") -> dict:
    return {
        "evidence": {"id": f"{sid}__ex-{n}", "studentId": sid, "experienceId": f"ex-{n}",
                     "capabilityId": "http-requests", "type": "exercise_response",
                     "attempt": n, "response": f"answer {n}: ∀n (n² odd → n odd)",
                     "results": [{"criterionId": "c1", "verdict": "met", "justification": "ok"}],
                     "createdAt": at},
        "assessment": {"studentId": sid, "experienceId": f"ex-{n}", "createdAt": at,
                       "outcomes": [{"capabilityId": "http-requests", "score": 1.0,
                                     "masteryBefore": None, "masteryAfter": 0.7,
                                     "met": ["c1"], "partial": [], "unmet": []}],
                       "explanation": "…"},
    }


def test_missing_profile_is_none(store):
    assert store.load_profile("nobody") is None


def test_profile_round_trips_unchanged_and_save_overwrites(store):
    store.save_profile("ada", profile("ada"))
    assert store.load_profile("ada") == profile("ada")
    store.save_profile("ada", profile("ada", mastery=0.9))
    assert store.load_profile("ada")["student_capabilities"][0]["mastery"] == 0.9


def test_list_students_is_sorted(store):
    for sid in ("zoe", "ada", "moe"):
        store.save_profile(sid, profile(sid))
    assert store.list_students() == ["ada", "moe", "zoe"]


def test_missing_evidence_is_empty(store):
    assert store.load_evidence("nobody") == []


def test_evidence_is_oldest_first_even_with_equal_timestamps(store):
    # History and retry detection read this order; entries saved in the same second
    # must still come back in the order they were appended.
    entries = [entry("ada", n) for n in range(1, 6)]
    for e in entries:
        store.append_evidence("ada", copy.deepcopy(e))
    assert store.load_evidence("ada") == entries  # same order, no extra fields


def test_evidence_is_per_student(store):
    store.append_evidence("ada", entry("ada", 1))
    store.append_evidence("moe", entry("moe", 1))
    assert [e["evidence"]["studentId"] for e in store.load_evidence("ada")] == ["ada"]


def test_activities_round_trip_and_save_overwrites(store):
    record = {"id": "gen-http-requests-1a2b3c4d", "course": "rest-api", "type": "generated",
              "title": "A new challenge", "prompt": "1. … 2. …",
              "rubric": [{"id": "r1", "criterion": "Names GET", "capability": "http-requests",
                          "weight": 1.0}]}
    store.save_activity(record)
    store.save_activity({**record, "title": "Renamed"})
    assert store.list_activities() == [{**record, "title": "Renamed"}]
