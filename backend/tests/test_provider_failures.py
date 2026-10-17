"""Provider failures end quickly and change nothing.

Regression for the hang found 2026-10-16: on an exhausted free-tier quota Gemini answers 429
with `Retry-After: 31447`, and the SDK's default retry slept that long — 8h44m — inside
the request. Lessons, grading and the tutor stayed pending with no error.

These run the real SDK retry code against a mock transport: no key, no network.
"""

from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
from google import genai

import cognith_rag.embeddings as emb
from fastapi.testclient import TestClient

from api.main import app, evaluator, shared_lesson
from cognith_student.evidence import GeminiEvaluator
from cognith_student.storage import FileStorage, set_storage
from tests.test_api import ONBOARDING, onboard

RATE_LIMITED = {"error": {"message": "Rate limit exceeded for model gemini-3.8-flash "
                                     "(limit: 20 requests per day on Free Tier). Please retry in 8h44m7s.",
                          "code": "too_many_requests"}}


def mock_client(generation: Exception | None = None):
    """A real genai.Client with the app's options, over a fake network. Embeddings work;
    generation answers 429 with an 8-hour Retry-After, or raises `generation`."""
    calls = {"generation": 0, "embedding": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if "Embed" in req.url.path:
            calls["embedding"] += 1
            n = len(json.loads(req.content)["requests"])
            return httpx.Response(200, json={"embeddings": [{"values": [0.1] * 768}] * n})
        calls["generation"] += 1
        if generation is not None:
            raise generation
        return httpx.Response(429, headers={"retry-after": "31447"}, json=RATE_LIMITED)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return genai.Client(api_key="test", http_options=emb.http_options(httpx_client=http)), calls


def test_rate_limited_generation_fails_fast_without_retrying():
    c, calls = mock_client()
    started = time.monotonic()
    with pytest.raises(Exception) as err:
        c.interactions.create(model="gemini-3.8-flash", input="x")
    assert time.monotonic() - started < 3, "slept on Retry-After"
    assert calls["generation"] == 1, "a 429 must not be retried"
    assert "429" in str(err.value)


@pytest.mark.parametrize("failure, says", [(httpx.ConnectError("connection reset"), "Couldn't reach the AI service"),
                                            (httpx.ReadTimeout("no answer"), "took too long")])
def test_network_failures_are_one_attempt_with_a_clear_message(failure, says):
    from api.main import ai_failure

    c, calls = mock_client(generation=failure)
    with pytest.raises(Exception) as err:
        c.interactions.create(model="gemini-3.8-flash", input="x")
    assert calls["generation"] == 1
    assert says in ai_failure(err.value).detail


@pytest.fixture
def client(tmp_path):
    set_storage(FileStorage(tmp_path))
    yield TestClient(app)
    app.dependency_overrides.clear()
    set_storage(None)


@pytest.fixture
def rate_limited(monkeypatch):
    c, calls = mock_client()
    monkeypatch.setattr(emb, "_client", c)
    return calls


def test_attempt_on_rate_limit_is_actionable_and_saves_nothing(client, rate_limited, caplog):
    learner = onboard(client, "Ada")["learner"]["id"]
    activity = client.get(f"/api/learners/{learner}/diagnostic").json()["activities"][0]["id"]
    before = client.get(f"/api/learners/{learner}/profile").json()
    app.dependency_overrides[evaluator] = lambda: GeminiEvaluator()
    r = client.post(f"/api/learners/{learner}/attempts", json={"activityId": activity, "response": "x"})
    assert r.status_code == 503
    assert r.json()["detail"] == ("The AI service has reached its usage limit. Please try again later. "
                                  "Your answer wasn't marked, and your progress hasn't changed.")
    assert "Rate limit exceeded" in caplog.text  # the provider's own words: server log only
    assert client.get(f"/api/learners/{learner}/evidence").json() == []
    assert client.get(f"/api/learners/{learner}/profile").json() == before


def test_tutor_and_lesson_on_rate_limit_are_actionable(client, rate_limited, monkeypatch):
    import numpy as np

    import cognith_course as courses
    from cognith_rag.store import Store

    # A query that lands squarely on real material, so generation is actually reached.
    with courses.using("rest-api"):
        vector = np.array(next(c for c in Store.load().chunks if c.doc == "status-codes.md").embedding)
    monkeypatch.setattr(emb, "embed_query", lambda text: vector)
    learner = client.post("/api/learners", json={**ONBOARDING, "course": "rest-api", "name": "T",
                                                 "technologies": [], "level": "none"}).json()["learner"]["id"]
    r = client.post(f"/api/learners/{learner}/tutor",
                    json={"question": "What does a 404 status code mean?", "capabilityId": "status-codes"})
    assert r.status_code == 503 and "usage limit" in r.json()["detail"], r.text
    r = client.post(f"/api/learners/{learner}/lessons", json={"capabilityId": "status-codes"})
    assert r.status_code == 503 and "usage limit" in r.json()["detail"], r.text
    # Neither route saves anything, so neither says anything about saving.
    assert "progress" not in r.json()["detail"] and "saved" not in r.json()["detail"]
    assert client.get(f"/api/learners/{learner}/evidence").json() == []


def test_learner_message_is_safe_and_the_log_has_no_key(monkeypatch, caplog):
    from api.main import ai_failure

    key = "AIza" + "x" * 35
    monkeypatch.setenv("GEMINI_API_KEY", key)
    c, _ = mock_client()
    with pytest.raises(Exception) as err:
        c.interactions.create(model="gemini-3.8-flash", input="x")
    detail = ai_failure(err.value).detail
    assert "Free Tier" not in detail and "gemini" not in detail.lower()
    assert "Rate limit exceeded" in caplog.text  # the provider's words reach the log
    # A transport error naming the request URL, key included, is logged redacted.
    leaked = httpx.ConnectError(f"failed: https://example.test/v1beta/models?key={key}&alt=json")
    assert key not in ai_failure(leaked).detail
    assert key not in caplog.text and "key=[REDACTED]" in caplog.text


def test_identical_lesson_requests_share_one_generation():
    built = []

    def build():
        built.append(1)
        time.sleep(0.3)
        return SimpleNamespace(sections=["a guided lesson"])

    key = ("learner", "course", "request", 0)
    results = []
    threads = [threading.Thread(target=lambda: results.append(shared_lesson(key, build))) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(built) == 1 and results[0] is results[1], "StrictMode's second request generated again"
    assert shared_lesson(key, build) is results[0] and len(built) == 1, "refresh generated again"
    shared_lesson(key[:-1] + (1,), build)  # new evidence -> a new lesson
    assert len(built) == 2


def test_failed_lesson_generation_is_not_reused():
    calls = []

    def fail():
        calls.append(1)
        raise RuntimeError("provider down")

    key = ("learner", "course", "failing request", 0)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            shared_lesson(key, fail)
    assert len(calls) == 2, "a retry after a failure must try again"
