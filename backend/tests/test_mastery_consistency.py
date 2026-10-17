"""One mastery rule everywhere: summary counts, skill badges and the plan's claims agree.

Regression for the seeded `demo` learner, whose stored scores predate D62: the header said
"8 mastered", the skill list showed 2, and the plan said "You have mastered Scalability,
Load Balancing, Caching" beside three Developing badges. cognith_learning.mastery is now
the single rule (decisions.md D61, D62 and D64); no threshold or stored record changed.

No network: a fixed judge, and seed data copied into a temp dir.
"""

from __future__ import annotations

import re
import shutil
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import cognith_course as courses
from api.main import app, evaluator, library
from cognith_student.evidence import ManualEvaluator
from cognith_student.profile import CapabilityProfile
from cognith_student.storage import FileStorage, set_storage

SEED = Path(__file__).resolve().parent.parent / "data"


class MetJudge:
    def evaluate(self, item, response):
        return ManualEvaluator({c.id: "met" for c in item.rubric}, justification="test").evaluate(item, response)


@pytest.fixture
def client(tmp_path):
    yield TestClient(app)
    app.dependency_overrides.clear()
    set_storage(None)


def agree(client, learner):
    """Counts == badges, and every "you have mastered X" claim names Mastered badges only."""
    profile = client.get(f"/api/learners/{learner}/profile").json()
    badges = Counter(s["state"] for s in profile["skills"])
    counts = profile["learner"]["counts"]
    assert (counts["mastered"], counts["developing"], counts["unknown"]) == \
        (badges["mastered"], badges["developing"], badges["unknown"]), learner
    state = {s["name"]: s["state"] for s in profile["skills"]}
    plan = client.get(f"/api/learners/{learner}/next?limit=10").json()
    for step in plan["steps"] + [profile["nextStep"] or {"reason": ""}]:
        claim = re.search(r"You(?:'ve| have) mastered (.+?)(?:, and|\. |$)", step["reason"])
        if claim:
            named = [n for n in state if n in claim.group(1)]
            assert named and all(state[n] == "mastered" for n in named), (learner, step["reason"])
    return profile, plan


def test_every_seeded_learner_agrees_with_itself(client, tmp_path):
    shutil.copytree(SEED, tmp_path / "data")
    set_storage(FileStorage(tmp_path / "data"))
    learners = [l["id"] for l in client.get("/api/learners").json()]
    assert "demo" in learners
    for learner in learners:
        agree(client, learner)
    profile, plan = agree(client, "demo")
    # demo's stored 0.70s from before D62 are evidence, not mastery: Developing, and the
    # capstone that needs them is held back rather than offered as "you have mastered".
    assert profile["learner"]["counts"]["mastered"] == 2
    assert not any(s["kind"] == "apply" and "Scalability" in s["reason"] for s in plan["steps"])


def test_evidence_without_the_challenge_is_not_mastery_until_the_challenge(client, tmp_path):
    set_storage(FileStorage(tmp_path))
    app.dependency_overrides[evaluator] = lambda: MetJudge()
    lid = client.post("/api/learners", json={"name": "T", "course": "rest-api", "goal": "build a REST API",
                                             "technologies": [], "knows": "", "built": "", "level": "none"}).json()["learner"]["id"]
    with courses.using("rest-api"):
        library.cache_clear()
        capstone = library().get("capstone-secure-task-api")
        from api.main import graph
        profile = CapabilityProfile.load(lid, graph())
        for cap in capstone.requires:  # strong evidence, but no unit taught and no challenge passed
            profile.record_assessment(cap, 0.85, evidence_added=2)
        profile.save()
    before, plan = agree(client, lid)
    assert all(s["state"] == "developing" for s in before["skills"] if s["capabilityId"] in capstone.requires)
    assert not any(s["kind"] == "apply" for s in plan["steps"])
    assert any("Capstone" in h["reason"] for h in plan["heldBack"])

    with courses.using("rest-api"):
        library.cache_clear()
        exercises = {c: next(e.id for e in library().experiences.values()
                             if e.capability_id == c and e.type.value == "exercise") for c in capstone.requires}
    for activity in exercises.values():  # each skill's own challenge, passed
        assert client.post(f"/api/learners/{lid}/attempts", json={"activityId": activity, "response": "x"}).status_code == 200
    after, plan = agree(client, lid)
    assert all(s["state"] == "mastered" for s in after["skills"] if s["capabilityId"] in capstone.requires)
    offered = next((s for s in plan["steps"] if s["kind"] == "apply"), None)
    assert offered and offered["reason"].startswith("You have mastered")


# --- the plan settles raw-high but Developing skills -------------------------------------------
def learner_with(client, tmp_path, course, raw: dict[str, float], judge=None):
    set_storage(FileStorage(tmp_path))
    app.dependency_overrides[evaluator] = lambda: judge or MetJudge()
    lid = client.post("/api/learners", json={"name": "T", "course": course, "goal": "build a REST API",
                                             "technologies": [], "knows": "", "built": "", "level": "none"}).json()["learner"]["id"]
    client.get(f"/api/learners/{lid}/profile")  # activates the course
    from api.main import graph
    with courses.using(course):
        profile = CapabilityProfile.load(lid, graph())
        for cap, m in raw.items():  # strong evidence, but no unit covered and no challenge passed
            profile.record_assessment(cap, m, evidence_added=2)
        profile.save()
    return lid


def state_of(client, lid, cap):
    return next(s["state"] for s in client.get(f"/api/learners/{lid}/profile").json()["skills"] if s["capabilityId"] == cap)


def test_raw_high_but_developing_skill_is_offered_its_own_challenge(client, tmp_path):
    lid = learner_with(client, tmp_path, "rest-api", {"web-basics": 0.85})
    assert state_of(client, lid, "web-basics") == "developing"
    profile, plan = agree(client, lid)
    step = next((s for s in plan["steps"] if s["capabilityId"] == "web-basics"), None)
    assert step and step["kind"] == "practise", plan["steps"]  # verification, not forced lessons
    assert "counts as mastered only once" in step["reason"] and "settles it" in step["reason"]


def test_without_a_challenge_the_unit_settles_it_and_no_material_is_not_forced(client, tmp_path):
    # Scalability has unit material but no exercise of its own; Git has neither, so by the
    # rule its number alone decides — it is mastered, and nothing is invented for it.
    lid = learner_with(client, tmp_path, "backend-engineering", {"scalability": 0.85, "git": 0.85})
    profile, plan = agree(client, lid)
    assert state_of(client, lid, "scalability") == "developing" and state_of(client, lid, "git") == "mastered"
    step = next((s for s in plan["steps"] if s["capabilityId"] == "scalability"), None)
    assert step and step["kind"] == "learn" and "no challenge yet" in step["reason"]
    assert not any(s["capabilityId"] == "git" for s in plan["steps"])


def test_prerequisites_follow_the_rule_not_the_number(client, tmp_path):
    # How the Web Works is the prerequisite of HTTP Requests: at 0.85 without its challenge
    # it is Developing, so no reason may call it mastered (agree() checks every claim).
    lid = learner_with(client, tmp_path, "rest-api", {"web-basics": 0.85})
    profile, plan = agree(client, lid)
    assert not any("mastered How the Web Works" in s["reason"] for s in plan["steps"])


# --- feedback labels match the profile either side of an attempt --------------------------------
def test_feedback_labels_match_the_profile_before_and_after(client, tmp_path):
    lid = learner_with(client, tmp_path, "rest-api", {"web-basics": 0.85})
    with courses.using("rest-api"):
        library.cache_clear()
        diag = next(e.id for e in library().experiences.values() if e.capability_id == "web-basics" and e.type.value == "diagnostic")
        own = next(e.id for e in library().experiences.values() if e.capability_id == "web-basics" and e.type.value == "exercise")
    r = client.post(f"/api/learners/{lid}/attempts", json={"activityId": diag, "response": "x"}).json()
    c = next(x for x in r["changes"] if x["capabilityId"] == "web-basics")
    assert (c["stateBefore"], c["stateAfter"]) == ("developing", "developing")  # the number was 0.85 throughout
    assert c["stateAfter"] == state_of(client, lid, "web-basics")
    r = client.post(f"/api/learners/{lid}/attempts", json={"activityId": own, "response": "x"}).json()
    c = next(x for x in r["changes"] if x["capabilityId"] == "web-basics")
    assert (c["stateBefore"], c["stateAfter"]) == ("developing", "mastered")  # its own challenge, passed
    assert c["stateAfter"] == state_of(client, lid, "web-basics")


def test_a_neighbouring_point_does_not_label_that_skill_mastered(client, tmp_path):
    lid = learner_with(client, tmp_path, "backend-engineering", {})
    with courses.using("backend-engineering"):
        library.cache_clear()
        http = next(e.id for e in library().experiences.values() if e.capability_id == "http" and e.type.value == "exercise")
    r = client.post(f"/api/learners/{lid}/attempts", json={"activityId": http, "response": "x"}).json()
    rel = next(x for x in r["changes"] if x["capabilityId"] == "reliability")
    assert rel["masteryAfter"] >= 0.7 and rel["stateAfter"] == "developing" == state_of(client, lid, "reliability")


def test_failed_or_incomplete_grading_changes_no_state(client, tmp_path):
    from cognith_student.evidence import EvaluationError

    class Incomplete:
        def evaluate(self, item, response):
            raise EvaluationError("incomplete judgement — not judged: ['x']")

    lid = learner_with(client, tmp_path, "rest-api", {"web-basics": 0.85}, judge=Incomplete())
    before = client.get(f"/api/learners/{lid}/profile").json()
    with courses.using("rest-api"):
        library.cache_clear()
        own = next(e.id for e in library().experiences.values() if e.capability_id == "web-basics" and e.type.value == "exercise")
    r = client.post(f"/api/learners/{lid}/attempts", json={"activityId": own, "response": "x"})
    assert r.status_code == 502
    after = client.get(f"/api/learners/{lid}/profile").json()
    assert after["learner"]["counts"] == before["learner"]["counts"]
    assert [s["state"] for s in after["skills"]] == [s["state"] for s in before["skills"]]
    assert client.get(f"/api/learners/{lid}/evidence").json() == []
