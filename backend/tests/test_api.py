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


def test_estimate_reasons_are_readable(client):
    reasons = [e["reason"] for e in onboard(client, "Ada")["initialEstimates"]]
    assert reasons and not any("--" in r for r in reasons), reasons


def test_weak_attempt_says_what_to_learn(client):
    learner = onboard(client, "Ada")["learner"]["id"]
    result = answer_diagnostic(client, learner, "unmet")
    teach = result["teach"]
    assert teach and teach["missed"] and teach["name"]
    judge.verdict = "met"
    strong = onboard(client, "Bo")["learner"]["id"]
    assert answer_diagnostic(client, strong, "met")["teach"] is None


class FakeGenerator:
    model = "fake"

    def generate(self, capability_id, hits, missed=(), avoid_prompt=None, focused=False):
        from cognith_learning.generator import _Challenge, to_experience
        from api.main import graph

        assert hits, "challenge must be written from retrieved material"
        raw = _Challenge(title="A new situation", prompt="x" * 80, minutes=6, criteria=[
            {"criterion": f"Criterion {i}", "excerpt_id": hits[0].chunk.id} for i in range(3)])
        return to_experience(raw, graph().get(capability_id), hits)


def test_generated_challenge_is_persisted_and_assessable(client, monkeypatch):
    from api.main import generator
    import numpy as np

    monkeypatch.setattr("cognith_rag.embeddings.embed_query",
                        lambda text: np.ones(768, dtype=np.float32) / np.sqrt(768))
    app.dependency_overrides[generator] = lambda: FakeGenerator()
    learner = onboard(client, "Ada")["learner"]["id"]
    r = client.post(f"/api/learners/{learner}/challenges", json={"capabilityId": "http"})
    assert r.status_code == 201, r.text
    challenge = r.json()
    assert challenge["type"] == "generated" and challenge["source"].startswith("generated from")

    from urllib.parse import quote
    assert client.get(f"/api/activities/{quote(challenge['id'], safe='')}").status_code == 200
    judge.verdict = "met"
    res = client.post(f"/api/learners/{learner}/attempts",
                      json={"activityId": challenge["id"], "response": "an answer"}).json()
    assert [c["capabilityId"] for c in res["changes"]] == ["http"]
    history = client.get(f"/api/learners/{learner}/evidence").json()
    assert history[-1]["criteria"][0]["criterion"] == "Criterion 0"


def test_challenge_needs_course_material(client):
    learner = onboard(client, "Ada")["learner"]["id"]
    r = client.post(f"/api/learners/{learner}/challenges", json={"capabilityId": "git"})
    assert r.status_code == 400


def test_validation_rejects_ungrounded_challenges():
    from cognith_learning.generator import _Challenge, validate

    def make(ids, prompt="p" * 80):
        return _Challenge(title="t", prompt=prompt, minutes=5,
                          criteria=[{"criterion": "c", "excerpt_id": i} for i in ids])

    assert validate(make(["a", "b", "a"]), {"a", "b"}, None) == []
    assert validate(make(["a", "zzz", "a"]), {"a"}, None)          # cites unsent excerpt
    assert validate(make(["a", "a"]), {"a"}, None)                 # too few criteria
    assert validate(make(["a"] * 3, "same " * 20), {"a"}, "same " * 20)  # repeats original


def test_new_learner_is_taught_not_tested(client):
    body = client.post("/api/learners", json={**ONBOARDING, "name": "New", "level": "none"}).json()
    nxt = client.get(f"/api/learners/{body['learner']['id']}/next").json()
    assert nxt["stage"] == "starting from scratch"
    assert all(s["kind"] == "learn" for s in nxt["steps"])
    assert "new to this" in nxt["steps"][0]["reason"]


def test_goal_with_no_topics_is_taught_too(client):
    body = client.post("/api/learners", json={**ONBOARDING, "name": "Blank", "technologies": [],
                                              "knows": "", "built": "", "level": "none"}).json()
    assert body["initialEstimates"] == []
    nxt = client.get(f"/api/learners/{body['learner']['id']}/next").json()
    assert nxt["stage"] == "starting from scratch" and nxt["steps"][0]["kind"] == "learn"


def test_lesson_result_is_light_evidence(client):
    learner = onboard(client, "Ada")["learner"]["id"]
    body = {"capabilityId": "http", "concepts": [
        {"title": "Request and response", "verdict": "met"},
        {"title": "Status codes", "verdict": "met"}]}
    res = client.post(f"/api/learners/{learner}/lessons/result", json=body)
    assert res.status_code == 200, res.text
    change = res.json()["changes"][0]
    assert change["capabilityId"] == "http"
    assert change["masteryAfter"] <= 0.6 and change["stateAfter"] == "developing"
    history = client.get(f"/api/learners/{learner}/evidence").json()
    assert history[-1]["criteria"][0]["criterion"] == "Understands: Request and response"


def test_assisted_attempt_is_capped_and_says_so(client):
    learner = onboard(client, "Ada")["learner"]["id"]
    activity = client.get(f"/api/learners/{learner}/diagnostic").json()["activities"][0]["id"]
    judge.verdict = "met"
    r = client.post(f"/api/learners/{learner}/attempts",
                    json={"activityId": activity, "response": "x", "helpUsed": 3}).json()
    assert all(c["score"] <= 0.65 for c in r["changes"])
    assert r["explanation"].startswith("You used guided help 3 times")
