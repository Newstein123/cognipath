"""Assessment rules: what a challenge may decide (D3), and judgements we refuse (D6).

D3 — the "challenge decides mastery" rule (decisions.md D61) settles the challenge's OWN
skill. It was also applied to every other skill in the rubric, and to capstones, so one
missed point on a neighbouring skill set a mastered skill to 0%, and one met point made a
neighbouring skill "mastered".

D6 — a judgement missing a criterion was scored as unmet, so a model hiccup looked like a
weak answer (and could decide a challenge). Unusable judgements now fail recoverably.

No network: Gemini is a ManualEvaluator, or a fake client returning a given reply.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import cognith_course as courses
import cognith_rag.embeddings as emb
from api.main import app, evaluator, library
from cognith_student.evidence import (
    EvaluationError, GeminiEvaluator, ManualEvaluator, Verdict, next_mastery, read_judgements,
)
from cognith_student.storage import FileStorage, set_storage


class Judge:
    """Verdict per criterion from `rule(criterion)`; everything met by default."""

    rule = staticmethod(lambda c: "met")

    def evaluate(self, item, response):
        return ManualEvaluator({c.id: self.rule(c) for c in item.rubric},
                               justification="test").evaluate(item, response)


judge = Judge()


@pytest.fixture
def client(tmp_path):
    set_storage(FileStorage(tmp_path))
    judge.rule = staticmethod(lambda c: "met")
    app.dependency_overrides[evaluator] = lambda: judge
    yield TestClient(app)
    app.dependency_overrides.clear()
    set_storage(None)


def learner(client, course):
    body = {"name": "T", "course": course, "goal": "build a REST API", "technologies": [],
            "knows": "", "built": "", "level": "none"}
    return client.post("/api/learners", json=body).json()["learner"]["id"]


def item(course, activity_id):
    with courses.using(course):
        library.cache_clear()
        return library().get(activity_id)


def exercise(course, cap):
    with courses.using(course):
        library.cache_clear()
        return next(e for e in library().experiences.values()
                    if e.capability_id == cap and e.type.value == "exercise")


def attempt(client, lid, activity_id):
    r = client.post(f"/api/learners/{lid}/attempts", json={"activityId": activity_id, "response": "x"})
    assert r.status_code == 200, r.text
    return r.json()


def change(result, cap):
    return next(c for c in result["changes"] if c["capabilityId"] == cap)


def skill(client, lid, cap):
    return next(s for s in client.get(f"/api/learners/{lid}/profile").json()["skills"]
                if s["capabilityId"] == cap)


# --- D3 ------------------------------------------------------------------------------
def test_a_missed_capstone_point_blends_and_does_not_wipe_a_mastered_skill(client):
    lid = learner(client, "rest-api")
    capstone = item("rest-api", "capstone-secure-task-api")
    for cap in sorted({c.capability_id for c in capstone.rubric}):
        for _ in range(2):  # pass each unit's challenge twice: mastered at 0.85
            attempt(client, lid, exercise("rest-api", cap).id)
    assert skill(client, lid, "authentication")["mastery"] == 0.85

    judge.rule = staticmethod(lambda c: "unmet" if c.capability_id == "authentication" else "met")
    r = attempt(client, lid, capstone.id)
    auth = change(r, "authentication")
    assert auth["masteryAfter"] == next_mastery(0.85, 0.0, 2) > 0.5, "one missed point wiped the skill"
    # The capstone's first `requires` entry is not "its" skill either: plain blend.
    assert change(r, "endpoint-design")["masteryAfter"] == next_mastery(0.85, 1.0, 2)
    assert "This challenge decides" not in r["explanation"]


def test_a_neighbouring_criterion_neither_wipes_nor_masters_that_skill(client):
    lid = learner(client, "backend-engineering")
    for _ in range(2):
        attempt(client, lid, exercise("backend-engineering", "http").id)  # HTTP mastered, 0.85
    critique = item("backend-engineering", "rest-api.md#exercise-critique-an-endpoint")  # api-design x4, http x1
    judge.rule = staticmethod(lambda c: "unmet" if c.capability_id == "http" else "met")
    r = attempt(client, lid, critique.id)
    assert change(r, "http")["masteryAfter"] == next_mastery(0.85, 0.0, 2) > 0.5
    assert change(r, "api-design")["masteryAfter"] >= 0.7  # its own skill: still decided
    assert "This challenge decides API Design" in r["explanation"]

    # One met Reliability point inside the HTTP exercise is evidence, not Reliability's challenge.
    lid = learner(client, "backend-engineering")
    judge.rule = staticmethod(lambda c: "met" if c.capability_id == "reliability" else "unmet")
    attempt(client, lid, exercise("backend-engineering", "http").id)
    assert skill(client, lid, "reliability")["state"] != "mastered"


def test_a_unit_challenge_still_decides_its_own_skill(client):
    lid = learner(client, "rest-api")
    ex = exercise("rest-api", "web-basics")
    assert change(attempt(client, lid, ex.id), "web-basics")["stateAfter"] == "mastered"
    assert skill(client, lid, "web-basics")["state"] == "mastered"
    judge.rule = staticmethod(lambda c: "unmet")
    assert change(attempt(client, lid, ex.id), "web-basics")["masteryAfter"] == 0.0  # a fail still decides


# --- D6 ------------------------------------------------------------------------------
def rubric():
    return exercise("rest-api", "web-basics").rubric


def reply(*judgements):
    return json.dumps({"judgements": [{"criterion_id": i, "verdict": v, "justification": "j"}
                                      for i, v in judgements]})


def test_a_complete_judgement_is_read():
    r = rubric()
    results = read_judgements(r, reply(*[(f" {c.id} ", "Met") for c in r]))
    assert [x.criterion_id for x in results] == [c.id for c in r]
    assert all(x.verdict is Verdict.MET for x in results)


@pytest.mark.parametrize("make, says", [
    (lambda r: reply(*[(c.id, "met") for c in r[1:]]), "not judged"),
    (lambda r: reply(*[(c.id, "met") for c in r], (r[0].id, "unmet")), "more than once"),
    (lambda r: reply(*[(c.id, "met") for c in r], ("invented-id", "met")), "not in the rubric"),
    (lambda r: reply(*[(c.id, "met") for c in r[:-1]], (r[-1].id, "excellent")), "unrecognised verdict"),
    (lambda r: '{"judgements": [', "malformed"),
    (lambda r: '{"verdicts": []}', "malformed"),
    (lambda r: None, "malformed"),
])
def test_an_unusable_judgement_is_refused(make, says):
    with pytest.raises(EvaluationError, match=says):
        read_judgements(rubric(), make(rubric()))


@pytest.fixture
def gemini_replies(monkeypatch):
    """The real GeminiEvaluator, with Gemini's reply set by the test."""
    said = {}
    fake = SimpleNamespace(interactions=SimpleNamespace(
        create=lambda **kw: SimpleNamespace(output_text=said["text"])))
    monkeypatch.setattr(emb, "get_client", lambda: fake)
    app.dependency_overrides[evaluator] = lambda: GeminiEvaluator()
    return said


def test_an_incomplete_judgement_is_recoverable_and_changes_nothing(client, gemini_replies):
    lid = learner(client, "rest-api")
    ex = exercise("rest-api", "web-basics")
    before = client.get(f"/api/learners/{lid}/profile").json()
    gemini_replies["text"] = reply(*[(c.id, "met") for c in ex.rubric[1:]])  # one criterion missing
    r = client.post(f"/api/learners/{lid}/attempts", json={"activityId": ex.id, "response": "x"})
    assert r.status_code == 502
    assert r.json()["detail"].startswith("The AI marker returned an incomplete result.")
    assert "not judged" not in r.json()["detail"]  # details stay in the server log
    assert client.get(f"/api/learners/{lid}/profile").json() == before
    assert client.get(f"/api/learners/{lid}/evidence").json() == []

    gemini_replies["text"] = reply(*[(c.id, "met") for c in ex.rubric])  # the retry succeeds
    r = client.post(f"/api/learners/{lid}/attempts", json={"activityId": ex.id, "response": "x"})
    assert r.status_code == 200 and r.json()["attempt"] == 1


def test_an_incomplete_lesson_task_judgement_is_recoverable(client, gemini_replies):
    lid = learner(client, "rest-api")
    gemini_replies["text"] = reply(("t0", "met"))  # the task has two criteria, t0 and t1
    r = client.post(f"/api/learners/{lid}/lessons/judge", json={
        "capabilityId": "web-basics", "concept": "URLs", "answer": "an answer",
        "task": {"kind": "explain", "prompt": "Split this URL", "criteria": ["Names the host", "Names the path"],
                 "modelAnswer": "host and path"}})
    assert r.status_code == 502 and "incomplete result" in r.json()["detail"], r.text
