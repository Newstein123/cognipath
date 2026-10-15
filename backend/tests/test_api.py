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
    "course": "backend-engineering",
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

    def generate(self, capability_id, hits, missed=(), avoid_prompt=None, focused=False, learner=""):
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


def test_learner_context_bands(client):
    from api.main import graph
    from cognith_learning.learner_context import learner_context
    from cognith_student.profile import CapabilityProfile

    new = client.post("/api/learners", json={**ONBOARDING, "name": "New", "technologies": [],
                                             "knows": "", "built": "", "level": "none"}).json()
    profile = CapabilityProfile.load(new["learner"]["id"], graph())
    assert learner_context(profile, "git").band == "new"
    learner = onboard(client, "Ada")["learner"]["id"]
    profile = CapabilityProfile.load(learner, graph())
    assert learner_context(profile, "git").band == "partial"  # self-rated intermediate
    answer_diagnostic(client, learner, "unmet")
    profile = CapabilityProfile.load(learner, graph())
    assessed = next(r for r in profile.all_rows() if r.mastery is not None)
    ctx = learner_context(profile, assessed.capability_id)
    assert ctx.band == "struggling" and "MISSED" in ctx.prompt


def test_missed_points_come_from_latest_attempt_only(client):
    learner = onboard(client, "Ada")["learner"]["id"]
    body = lambda v: {"capabilityId": "http", "concepts": [
        {"title": "Status codes", "verdict": v}, {"title": "Idempotency", "verdict": "unmet"}]}
    client.post(f"/api/learners/{learner}/lessons/result", json=body("unmet"))
    client.post(f"/api/learners/{learner}/lessons/result", json=body("met"))
    from api.main import graph
    from cognith_learning.knowledge import GapResolver
    from cognith_student.profile import CapabilityProfile

    gap = next(g for g in GapResolver(graph(), CapabilityProfile.load(learner, graph())).gaps()
               if g.capability_id == "http")
    assert gap.unmet == ("Understands: Idempotency",)


def test_after_mastering_one_topic_the_next_is_recommended(client):
    body = client.post("/api/learners", json={**ONBOARDING, "name": "One", "technologies": [],
                                              "knows": "", "built": "", "level": "none"}).json()
    learner = body["learner"]["id"]
    first = client.get(f"/api/learners/{learner}/next").json()["steps"][0]
    act = next(a for a in library().experiences.values()
               if a.capability_id == first["capabilityId"] and a.assessable)
    judge.verdict = "met"
    for _ in range(3):  # enough evidence to demonstrate it
        client.post(f"/api/learners/{learner}/attempts", json={"activityId": act.id, "response": "x"})
    nxt = client.get(f"/api/learners/{learner}/next").json()
    assert nxt["stage"] != "nothing outstanding"
    assert any(s["kind"] == "learn" and s["capabilityId"] != first["capabilityId"] for s in nxt["steps"])


def test_confidence_alone_leads_to_diagnosis(client):
    for level, stage in (("advanced", "claimed, unverified"), ("beginner", "claimed, unverified"),
                         ("none", "starting from scratch")):
        body = client.post("/api/learners", json={**ONBOARDING, "name": level, "technologies": [],
                                                  "knows": "", "built": "", "level": level}).json()
        nxt = client.get(f"/api/learners/{body['learner']['id']}/next").json()
        assert nxt["stage"] == stage, level
        if level != "none":
            assert body["initialEstimates"][0]["reason"].startswith("You rated yourself")
            assert client.get(f"/api/learners/{body['learner']['id']}/diagnostic").json()["activities"]


def test_courses_are_isolated(client):
    ids = [c["id"] for c in client.get("/api/courses").json()]
    assert {"rest-api", "mat221", "backend-engineering"} <= set(ids)
    made = {}
    for course in ("rest-api", "mat221"):
        body = client.post("/api/learners", json={**ONBOARDING, "course": course, "name": course,
                                                  "technologies": [], "level": "none"}).json()
        assert body["learner"]["course"]["id"] == course
        made[course] = body["learner"]["id"]
    caps = {c: {s["capabilityId"] for s in client.get(f"/api/learners/{lid}/profile").json()["skills"]}
            for c, lid in made.items()}
    assert "web-basics" in caps["rest-api"] and "sets" in caps["mat221"]
    assert not caps["rest-api"] & caps["mat221"]
    for c, lid in made.items():
        nxt = client.get(f"/api/learners/{lid}/next").json()["steps"]
        assert all(s["capabilityId"] in caps[c] for s in nxt if s["capabilityId"])


def test_goal_text_picks_the_course(client):
    body = {**ONBOARDING, "name": "Auto", "level": "none", "technologies": []}
    body.pop("course")
    r = client.post("/api/learners", json={**body, "goal": "pass my MAT221 discrete math midterm"}).json()
    assert r["learner"]["course"]["id"] == "mat221"
    r = client.post("/api/learners", json={**body, "goal": "build a REST API with authentication"}).json()
    assert r["learner"]["course"]["id"] == "rest-api"


def test_real_challenge_generator_uses_the_learners_course(client, monkeypatch):
    """Regression: the generator dependency was built before the learner's course was
    active, so a REST-course challenge looked up http-basics in the wrong course."""
    import json
    from types import SimpleNamespace

    import numpy as np

    import re

    monkeypatch.setattr("cognith_rag.embeddings.embed_query",
                        lambda text: np.ones(768, dtype=np.float32) / np.sqrt(768))
    learner = client.post("/api/learners", json={**ONBOARDING, "course": "rest-api", "name": "R",
                                                 "technologies": [], "level": "none"}).json()
    lid = learner["learner"]["id"]

    def create(**kw):  # a stand-in for Gemini that cites an excerpt it was actually sent
        chunk = re.search(r"EXCERPT id=(\S+) ---", kw["input"]).group(1)
        return SimpleNamespace(output_text=json.dumps({
            "title": "A new situation", "prompt": "p" * 80, "minutes": 6,
            "criteria": [{"criterion": f"c{i}", "excerpt_id": chunk} for i in range(3)]}))

    fake = SimpleNamespace(interactions=SimpleNamespace(create=create))
    monkeypatch.setattr("cognith_learning.generator.get_client", lambda: fake)
    r = client.post(f"/api/learners/{lid}/challenges", json={"capabilityId": "web-basics"})
    assert r.status_code == 201, r.text
    assert r.json()["capabilityId"] == "web-basics"


def test_unit_plan_covers_every_core_section():
    """Every core section of the material is a concept; summaries and exercises are not."""
    from cognith_course import using
    from cognith_learning.units import plan_for

    with using("rest-api"):
        plan = plan_for("authorization")
    titles = [c.title for c in plan.concepts]
    assert "Misconception: hide or randomise the ID" in titles
    assert not any(t.startswith(("Summary", "Exercise", "Worked example")) for t in titles)
    assert sum(len(p) for p in plan.parts) == len(plan.concepts)
    bola = next(c for c in plan.concepts if c.title.startswith("Broken Object"))
    assert any("alice-changes-123-to-456" in e for e in bola.example_ids)


def test_coverage_is_recorded_per_concept_and_gates_mastery(client):
    from cognith_course import using
    from cognith_learning.units import plan_for

    lid = client.post("/api/learners", json={**ONBOARDING, "course": "rest-api", "name": "C",
                                             "technologies": [], "level": "none"}).json()["learner"]["id"]
    with using("rest-api"):
        plan = plan_for("authorization")
    first = plan.parts[0]
    client.post(f"/api/learners/{lid}/lessons/result", json={"capabilityId": "authorization",
        "concepts": [{"conceptId": c.id, "title": c.title, "verdict": "met"} for c in first]})
    unit = client.get(f"/api/learners/{lid}/units/authorization").json()
    assert unit["covered"] == len(first) and unit["total"] == len(plan.concepts)
    assert unit["part"] == 2
    steps = client.get(f"/api/learners/{lid}/next").json()["steps"]
    assert any("Part 2 of" in s["title"] for s in steps if s["capabilityId"] == "authorization")


def test_an_unclear_concept_is_remembered_after_later_concepts(client):
    """'We'll come back to it' must be true: a concept left unclear stays a miss even after
    later concepts are saved, until a later check shows it."""
    from api.main import graph
    from cognith_learning.knowledge import GapResolver
    from cognith_student.profile import CapabilityProfile

    lid = onboard(client, "Ada")["learner"]["id"]
    save = lambda title, v: client.post(f"/api/learners/{lid}/lessons/result", json={
        "capabilityId": "http", "concepts": [{"title": title, "verdict": v}]})
    gap = lambda: next(g for g in GapResolver(graph(), CapabilityProfile.load(lid, graph())).gaps()
                       if g.capability_id == "http")
    save("Status codes", "unmet")
    save("Methods", "met")
    save("Headers", "met")
    assert "Understands: Status codes" in gap().unmet
    save("Status codes", "met")
    assert "Understands: Status codes" not in gap().unmet
