"""API tests. No API key, no network: Gemini is replaced by ManualEvaluator, which the
engine already treats as a legitimate evaluator, and storage points at a temp dir.

The central test is `test_same_goal_different_evidence_different_next_step` — it is the
MVP definition of success, run end to end through HTTP.

    .venv/bin/python -m pytest tests -q
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app, evaluator, library
from cognith_student.evidence import ManualEvaluator
from cognith_student.storage import FileStorage, set_storage

ONBOARDING = {
    "goal": "I want to build production-ready REST APIs",
    "technologies": ["python", "postgres", "redis", "docker"],
    "knows": "I have built APIs with authentication and caching",
    "built": "A booking system backend",
    "level": "intermediate",
}


class Judge:
    """Every criterion gets the same verdict — a strong or a weak answer."""

    verdict = "met"

    def evaluate(self, item, response):
        return ManualEvaluator({c.id: self.verdict for c in item.rubric},
                               justification=f"test: {self.verdict}").evaluate(item, response)


judge = Judge()


@pytest.fixture
def client(tmp_path):
    set_storage(FileStorage(tmp_path))
    app.dependency_overrides[evaluator] = lambda: judge
    yield TestClient(app)
    app.dependency_overrides.clear()
    set_storage(None)


def onboard(client, name):
    r = client.post("/api/learners", json={"name": name, **ONBOARDING})
    assert r.status_code == 201, r.text
    return r.json()


def answer_diagnostic(client, learner_id, verdict):
    """Answer every activity in the learner's diagnostic with the same verdict."""
    judge.verdict = verdict
    diag = client.get(f"/api/learners/{learner_id}/diagnostic").json()
    assert diag["activities"], "diagnostic selected nothing"
    last = None
    for a in diag["activities"]:
        last = client.post(f"/api/learners/{learner_id}/attempts",
                           json={"activityId": a["id"], "response": f"{verdict} answer"})
        assert last.status_code == 200, last.text
    return last.json()


def test_onboarding_creates_unverified_profile(client):
    body = onboard(client, "Ada")
    assert body["goal"] == {"text": ONBOARDING["goal"], "goalId": "backend-engineer",
                            "goalName": "Backend Software Engineer", "supported": True}
    assert body["initialEstimates"], "technologies produced no estimates"
    skills = body["profile"]["skills"]
    # Onboarding produces claims, never evidence.
    assert all(s["mastery"] is None and s["state"] == "unknown" for s in skills)
    assert any(s["selfRated"] for s in skills)


def test_first_step_is_verification(client):
    learner = onboard(client, "Ada")["learner"]["id"]
    nxt = client.get(f"/api/learners/{learner}/next").json()
    assert nxt["stage"] == "claimed, unverified"
    assert nxt["steps"][0]["kind"] == "diagnose"
    assert nxt["steps"][0]["reason"]


def test_attempt_updates_profile_and_explains(client):
    learner = onboard(client, "Ada")["learner"]["id"]
    result = answer_diagnostic(client, learner, "met")
    assert result["changes"], "no capability moved"
    change = result["changes"][0]
    assert change["masteryBefore"] is None and change["masteryAfter"] > 0
    assert result["explanation"]
    assert all(c["verdict"] == "met" and c["criterion"] for c in result["criteria"])
    # Persisted: a fresh read sees the evidence.
    profile = client.get(f"/api/learners/{learner}/profile").json()
    assert any(s["evidenceCount"] for s in profile["skills"])
    assert client.get(f"/api/learners/{learner}/evidence").json()


def test_retry_increments_attempt(client):
    learner = onboard(client, "Ada")["learner"]["id"]
    activity = client.get(f"/api/learners/{learner}/diagnostic").json()["activities"][0]["id"]
    judge.verdict = "unmet"
    body = {"activityId": activity, "response": "first try"}
    assert client.post(f"/api/learners/{learner}/attempts", json=body).json()["attempt"] == 1
    assert client.post(f"/api/learners/{learner}/attempts", json=body).json()["attempt"] == 2


def test_same_goal_different_evidence_different_next_step(client):
    strong = onboard(client, "Strong")["learner"]["id"]
    weak = onboard(client, "Weak")["learner"]["id"]
    s_result = answer_diagnostic(client, strong, "met")
    w_result = answer_diagnostic(client, weak, "unmet")

    s_states = {s["capabilityId"]: s["state"] for s in s_result["profile"]["skills"]}
    w_states = {s["capabilityId"]: s["state"] for s in w_result["profile"]["skills"]}
    assert s_states != w_states, "same evidence profile from opposite answers"

    s_next, w_next = s_result["next"]["steps"], w_result["next"]["steps"]
    assert s_next and w_next
    assert (s_next[0]["kind"], s_next[0]["title"]) != (w_next[0]["kind"], w_next[0]["title"])
    assert s_next[0]["reason"] and w_next[0]["reason"]


def test_every_activity_type_is_fetchable(client):
    """Exercise ids contain '#' and '.', so clients must URL-encode them."""
    from urllib.parse import quote

    for type_ in {e.type for e in library().experiences.values()}:
        a = library().of_type(type_)[0]
        r = client.get(f"/api/activities/{quote(a.id, safe='')}")
        assert r.status_code == 200, (a.id, r.text)
        assert r.json()["prompt"] and r.json()["criteria"]


def test_unknown_ids_404(client):
    assert client.get("/api/learners/nobody/profile").status_code == 404
    assert client.get("/api/activities/nothing").status_code == 404


def test_failed_judgement_changes_nothing(client):
    learner = onboard(client, "Ada")["learner"]["id"]
    activity = client.get(f"/api/learners/{learner}/diagnostic").json()["activities"][0]["id"]

    class Broken:
        def evaluate(self, item, response):
            raise RuntimeError("quota")

    app.dependency_overrides[evaluator] = lambda: Broken()
    r = client.post(f"/api/learners/{learner}/attempts",
                    json={"activityId": activity, "response": "x"})
    assert r.status_code == 502
    assert client.get(f"/api/learners/{learner}/evidence").json() == []


def test_first_step_does_not_depend_on_limit(client):
    learner = onboard(client, "Ada")["learner"]["id"]
    answer_diagnostic(client, learner, "met")
    one = client.get(f"/api/learners/{learner}/next?limit=1").json()["steps"]
    three = client.get(f"/api/learners/{learner}/next?limit=3").json()["steps"]
    assert len(one) == 1 and one[0] == three[0]
