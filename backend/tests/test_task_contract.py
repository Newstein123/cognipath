"""The applied task a lesson ends with must be markable fairly.

Regression for the browser QA of 2026-10-17: a generated task asked the learner to
"identify the two errors" in a mapping that contained three. Its first criterion also
required naming the network as "the waiter", which the task never asked for. The learner
corrected all three errors and was marked Partly met.

Two halves, both checked here with fixtures and no Gemini:
  - generation: a task whose criteria are not quoted from its prompt, or whose stated count
    disagrees with its answer, is rejected (retried once, then the plain explanation);
  - grading: the marker accepts any technically correct explanation and requires an
    analogy only when the question asks for it.

These checks are structural. They cannot prove that a criterion asks no more than the
words it quotes, or that a scenario really contains the errors it claims; the generation
instruction asks for that, and only a reader (or a real model run) can confirm it.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import cognith_rag.embeddings as emb
import cognith_learning.microlesson as ml
from api import schemas as s
from cognith_learning.microlesson import (AppliedTask, Diagram, QuizQuestion, Section,
                                          StructuredLesson, asked_counts, task_problems, validate)
from cognith_student import evidence
from tests.test_assessment_rules import client, learner, reply  # noqa: F401 — client is a fixture

# The task as generated in the QA run (prompt and criteria verbatim from the page). The
# example in the prompt contains three errors; the criteria ask for two and add "the waiter".
QA_PROMPT = (
    'A junior developer writes this note explaining an HTTP request: "In our setup, the network '
    "acts as the kitchen deciding what to cook, the method specifies which dish like /v1/tasks/42, "
    'and the response body is a status code like 200 OK." Identify the two errors in their mapping '
    "and provide the correct HTTP concepts according to the restaurant model.")
QA_CRITERIA = [
    "Identifies that the server (not the network) is the kitchen that decides/cooks, while the "
    "network is just the waiter carrying messages",
    "Identifies that the path (not the method) is the dish /v1/tasks/42, OR that 200 OK is a "
    "status code rather than the response body",
]
THREE_ERRORS = [
    "The server, not the network, is the kitchen that prepares the result",
    "The path, not the method, picks the dish /v1/tasks/42",
    "200 OK is the status code, not the response body",
]


def task(**over) -> AppliedTask:
    """A well-formed debug task in another domain; override one field to break it."""
    base = dict(
        kind="debug",
        prompt=("A student says: \"A ∩ B keeps every element in either set, so {1,2} ∩ {2,3} = "
                "{1,2,3}.\" Find the error and give the correct result."),
        criteria=["Says intersection keeps only elements in BOTH sets (union keeps either)",
                  "Gives {1,2} ∩ {2,3} = {2}"],
        asks=["Find the error", "give the correct result"],
        answer_points=["∩ keeps only shared elements", "The result is {2}"],
        model_answer="Intersection keeps elements in both sets, so the result is {2}; {1,2,3} is the union.")
    return AppliedTask(**{**base, **over})


def test_a_well_formed_task_passes():
    assert task_problems(task()) == []


def test_the_qa_task_is_rejected_for_its_count():
    qa = task(prompt=QA_PROMPT, criteria=QA_CRITERIA,
              asks=["Identify the two errors in their mapping"] * 2,
              answer_points=THREE_ERRORS, model_answer="…")
    problems = task_problems(qa)
    assert problems == ["task asks for 2 items but its answer has 3; the scenario, the "
                        "prompt's count and the answer must agree"]


def test_the_same_task_with_an_agreeing_count_passes():
    prompt = QA_PROMPT.replace("the two errors", "the three errors")
    fixed = task(prompt=prompt,
                 criteria=["Says the server, not the network, prepares the result",
                           "Corrects both other errors: the path picks the resource, and 200 OK "
                           "is a status code, not the body"],
                 asks=["Identify the three errors in their mapping"] * 2,
                 answer_points=THREE_ERRORS, model_answer="…")
    assert task_problems(fixed) == []


def test_a_criterion_the_prompt_does_not_ask_for_is_rejected():
    # The waiter requirement could only be tied to a request the prompt never makes.
    qa = task(prompt=QA_PROMPT, criteria=QA_CRITERIA,
              asks=["Identify the two errors in their mapping", "describe the network as the waiter"],
              answer_points=THREE_ERRORS[:2], model_answer="…")
    assert task_problems(qa) == ["task criterion 2 is not something the prompt asks for "
                                 "('describe the network as the waiter' is not quoted from the prompt)"]


@pytest.mark.parametrize("over, says", [
    (dict(asks=["Find the error"]), "2 criteria but 1 asks"),
    (dict(asks=["Find the error", "error"]), "criterion 2 is not something the prompt asks for"),
    (dict(answer_points=[]), "needs its answer points"),
    (dict(model_answer=" "), "needs a model answer"),
    (dict(criteria=[], asks=[]), "1–3 criteria"),
    (dict(prompt="Name the two laws and give three examples.", asks=["Name the two laws", "give three examples"]),
     "several different counts"),
])
def test_a_structurally_invalid_task_is_rejected(over, says):
    assert any(says in p for p in task_problems(task(**over))), task_problems(task(**over))


def test_quotes_are_matched_ignoring_case_spacing_and_curly_quotes():
    t = task(prompt="Explain why the  server answers “404” here, in one sentence.",
             criteria=["Says the resource does not exist"], asks=['why the server answers "404"'],
             answer_points=["The resource does not exist"])
    assert task_problems(t) == []


@pytest.mark.parametrize("prompt, counts", [
    ("Identify the two errors in their mapping", {2}),
    ("Find both mistakes", {2}),
    ("Name 3 status codes", {3}),
    ("What are the three steps?", {3}),
    ("Explain the two key differences", {2}),
    ("Fix all three bugs", {3}),
    ("List at least two reasons", set()),          # not an exact count
    ("Explain how two servers share load.", set()),  # a number in the scenario, not the answer
    ("A table has 4 rows. Predict the result.", set()),
])
def test_only_an_exact_requested_count_is_read(prompt, counts):
    assert asked_counts(prompt) == counts


@pytest.mark.parametrize("prompt", [
    "A client sends 3 requests to port 8000 and two of them return 404. Explain why.",
    "A cache holds 5 entries and the server has two replicas. Predict what the next read returns.",
    "Choose between a 301 and a 302 redirect for a page moved for 2 weeks, and justify it.",
])
@pytest.mark.parametrize("points", [1, 3])
def test_scenario_numbers_and_unnumbered_prompts_do_not_constrain_the_answer(prompt, points):
    t = task(prompt=prompt, criteria=["Gives the correct conclusion with a reason"],
             asks=[prompt.rstrip(".").split(". ")[-1].split(",")[0]],
             answer_points=[f"point {n}" for n in range(points)])
    assert task_problems(t) == []


def test_a_reply_without_the_new_fields_is_rejected_not_defaulted(monkeypatch):
    # An older-style task (no quotes, no answer points) is not trusted: it is retried, then
    # the lesson falls back. Nothing fills the fields in on the model's behalf.
    old = json.loads(lesson(task()).model_dump_json())
    for f in ("asks", "answer_points"):
        del old["sections"][0]["task"][f]
    inputs = generation_replies(monkeypatch, json.dumps(old), json.dumps(old))
    assert ml.generate(CAP, "", HITS, concepts=[("Sets", ["c1"])]) is None
    assert len(inputs) == 2 and "not valid JSON (ValidationError)" in inputs[1]


def lesson(t: AppliedTask) -> StructuredLesson:
    q = QuizQuestion(question="q", options=["a", "b", "c", "d"], answer_index=0, explanation="e")
    return StructuredLesson(answerable=True, hook="h", sections=[Section(
        title="Sets", probe=q, explanation="x", example="y", diagram=Diagram(type="none"),
        check=q, task=t, excerpt_ids=["c1"])])


def test_a_lesson_with_an_invalid_task_fails_validation():
    bad = task(asks=["Find the error", "describe the waiter"])
    assert validate(lesson(task()), {"c1"}, (1, 1)) == []
    assert validate(lesson(bad), {"c1"}, (1, 1))[0].startswith("section 1 task criterion 2")


def generation_replies(monkeypatch, *texts):
    """Gemini answers each generation call with the next text; returns the calls' inputs."""
    replies, inputs = list(texts), []

    def create(**kw):
        inputs.append(kw["input"])
        return SimpleNamespace(output_text=replies.pop(0))

    monkeypatch.setattr(ml, "get_client", lambda: SimpleNamespace(interactions=SimpleNamespace(create=create)))
    return inputs


HITS = [SimpleNamespace(chunk=SimpleNamespace(id="c1", doc="sets.md", section="Intersection",
                                              metadata={}, text="A ∩ B is the set of elements in both."),
                        score=1.0)]
CAP = SimpleNamespace(name="Sets", statement="Can apply set operations")


def test_a_mismatched_task_is_retried_with_the_reason_then_accepted(monkeypatch):
    bad = lesson(task(prompt=task().prompt.replace("Find the error", "Find the two errors"),
                      asks=["Find the two errors", "give the correct result"],
                      answer_points=["∩ keeps only shared elements"])).model_dump_json()
    inputs = generation_replies(monkeypatch, bad, lesson(task()).model_dump_json())
    got = ml.generate(CAP, "", HITS, concepts=[("Sets", ["c1"])])
    assert got is not None and got.sections[0].task == task()
    assert len(inputs) == 2
    assert "YOUR PREVIOUS ATTEMPT WAS REJECTED" in inputs[1]
    assert "task asks for 2 items but its answer has 1" in inputs[1]


def test_a_task_still_invalid_after_the_retry_gives_no_lesson(monkeypatch):
    bad = lesson(task(asks=["Find the error", "describe the waiter"])).model_dump_json()
    inputs = generation_replies(monkeypatch, bad, bad)
    assert ml.generate(CAP, "", HITS, concepts=[("Sets", ["c1"])]) is None
    assert len(inputs) == 2  # one retry, no more


def test_the_api_task_is_unchanged():
    # The quotes and answer points are for checking the task; the page is sent what it was.
    api = s.AppliedTask(**task().model_dump())
    assert set(api.model_dump(by_alias=True)) == {"kind", "prompt", "criteria", "modelAnswer"}


def test_the_instruction_text_states_the_contract():
    """A wording guard only: it stops the rules being edited away, but it says nothing
    about whether the model follows them. The tests above check behaviour."""
    gen, grade = ml.SYSTEM_INSTRUCTION, evidence.SYSTEM_INSTRUCTION
    assert "EXPLICITLY asks for" in gen and "Never require anything the prompt does not ask" in gen
    assert "Do not require the lesson's analogy" in gen
    assert "exactly that many and `answer_points` lists exactly that many" in gen
    assert "only facts from the excerpts" in gen
    assert "Any technically correct explanation of the idea\ncounts" in grade
    assert "unless the question itself\nasks for it" in grade
    # The rest of grading is unchanged: vocabulary without reasoning is still partial.
    assert "names the right\nterm without justifying it is `partial`" in grade


def test_the_lesson_marker_sees_the_task_and_its_criteria_and_records_nothing(client, monkeypatch):
    lid = learner(client, "rest-api")
    before = (client.get(f"/api/learners/{lid}/profile").json(),
              client.get(f"/api/learners/{lid}/evidence").json())
    sent = {}
    fake = SimpleNamespace(interactions=SimpleNamespace(
        create=lambda **kw: sent.update(kw) or SimpleNamespace(output_text=reply(("t0", "met")))))
    monkeypatch.setattr(emb, "get_client", lambda: fake)
    t = {"kind": "debug", "prompt": "A note says 200 OK is the response body. Find the error.",
         "criteria": ["Says 200 OK is a status code, not the body"], "modelAnswer": "…"}
    r = client.post(f"/api/learners/{lid}/lessons/judge", json={
        "capabilityId": "web-basics", "concept": "Status codes", "answer": "It's the status code.", "task": t})
    assert r.status_code == 200 and r.json()["outcome"] == "met", r.text
    assert t["prompt"] in sent["input"] and t["criteria"][0] in sent["input"]
    assert sent["system_instruction"] == evidence.SYSTEM_INSTRUCTION
    assert (client.get(f"/api/learners/{lid}/profile").json(),
            client.get(f"/api/learners/{lid}/evidence").json()) == before



def test_a_lesson_whose_task_stays_invalid_falls_back_and_records_nothing(client, monkeypatch):
    """End to end: every concept's task fails the contract on both tries. The learner gets
    the plain explanation (no guided sections), and no coverage, evidence or mastery is
    recorded — the guided lesson, the only thing that saves concept outcomes, never starts.
    The same request with a valid task gets its guided sections (the control)."""
    import re

    import numpy as np

    import cognith_course as courses
    from cognith_rag.store import Store

    with courses.using("rest-api"):
        vector = np.array(next(c for c in Store.load().chunks if c.doc == "status-codes.md").embedding)
    monkeypatch.setattr(emb, "embed_query", lambda text: vector)
    reply_with = {"task": task(asks=["Find the error", "describe the waiter"])}
    lesson_inputs = []

    def create(**kw):
        if kw.get("system_instruction") != ml.SYSTEM_INSTRUCTION:
            raise RuntimeError("no plain explanation in this test")
        lesson_inputs.append(kw["input"])
        out = lesson(reply_with["task"])
        out.sections[0].excerpt_ids = re.findall(r"--- EXCERPT id=(\S+) ---", kw["input"])[:1]
        return SimpleNamespace(output_text=out.model_dump_json())

    fake = SimpleNamespace(interactions=SimpleNamespace(create=create))
    monkeypatch.setattr(ml, "get_client", lambda: fake)
    monkeypatch.setattr(emb, "get_client", lambda: fake)
    lid = learner(client, "rest-api")
    state = lambda: [client.get(f"/api/learners/{lid}/{p}").json()  # noqa: E731
                     for p in ("profile", "evidence", "units/status-codes")]
    before = state()

    r = client.post(f"/api/learners/{lid}/lessons", json={"capabilityId": "status-codes"})
    assert r.status_code == 200, r.text
    assert r.json()["sections"] is None
    retries = [i for i in lesson_inputs if "YOUR PREVIOUS ATTEMPT WAS REJECTED" in i]
    assert lesson_inputs and len(retries) * 2 == len(lesson_inputs)  # one retry per concept, no more
    assert all("task criterion 2 is not something the prompt asks for" in i for i in retries)
    assert state() == before

    reply_with["task"] = task()  # the control: a valid task is taught
    lesson_inputs.clear()
    r = client.post(f"/api/learners/{lid}/lessons", json={"capabilityId": "status-codes"})
    assert r.status_code == 200 and r.json()["sections"], r.text
    assert not any("REJECTED" in i for i in lesson_inputs)
    assert set(r.json()["sections"][0]["task"]) == {"kind", "prompt", "criteria", "modelAnswer"}
