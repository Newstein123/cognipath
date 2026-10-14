---
id: api-testing
concept: Testing Your API
capability: api-testing
difficulty: beginner
prerequisites: [validation-errors, authorization]
source: "Adapted from MDN Web Docs — HTTP response status codes (https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status), by Mozilla Contributors, CC BY-SA 2.5; OWASP Web Security Testing Guide — Insecure Direct Object References, WSTG-ATHZ-04 (https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/05-Authorization/04-Insecure_Direct_Object_References), CC BY-SA 4.0. Reference (not copied): Ham Vocke, The Practical Test Pyramid (https://martinfowler.com/articles/practical-test-pyramid.html)."
---

# Testing Your API

## Why this matters

A pilot runs through a checklist before every flight, even though the plane flew fine yesterday. Something might have changed overnight, and the checklist catches it before take-off rather than in the air.

Automated API tests are that checklist. You write them once, and they run on every change. They catch **regressions**: features that used to work and silently broke when someone edited nearby code. They also act as **living documentation**: a test called "Alice cannot delete Bob's task" states the rule precisely and proves it still holds.

"It worked when I tried it in the browser" is not proof. You tried one request, as one user, on one day, and probably only the case where everything goes right. A test suite tries dozens of cases, including the nasty ones, every time, in seconds.

## What an API test asserts

An API test sends a real HTTP request and then **asserts** (checks) facts about what happened. There are four things worth checking:

1. **Status code**: `201`, `404`, `401`... The most basic check, and never enough on its own.
2. **Body**: the JSON contains the right fields and values, e.g. `title` is `"Buy milk"` and `done` is `false`; error responses have the expected Problem Details `type` and field errors.
3. **Headers**: e.g. `Content-Type: application/json`, a `Location` header after a `201`, or `Allow` on a `405`.
4. **Side effects**: what changed (or did not change) in the database. A `201` response is meaningless if no row was written, and a rejected request is a bug if it wrote a row anyway.

```text
assert status == 201
assert body.title == "Buy milk"
assert header "Content-Type" starts with "application/json"
assert database has 1 task with title "Buy milk" and owner_id 123
```

## Happy path vs failure cases

The **happy path** is the case where everything is correct: a valid user sends a valid request and it succeeds. Beginners test this and stop.

**Failure cases** (sometimes called sad paths or edge cases) are everything else: missing fields, wrong types, values at the limit, the wrong user, no token, an expired token, an id that does not exist. Most real bugs hide here, because developers write code thinking about the happy path, and failure cases are the ones they forgot. Attackers live entirely in the failure cases.

For one endpoint, `POST /tasks`, a fair split looks like this:

| Happy path | Failure cases |
|---|---|
| valid title, no due date | title missing, empty, 201 characters |
| valid title, future due date | due date in the past, `2026-02-30` |
| | `done` is `"yes"`; body is not JSON |
| | no token; expired token; extra `owner_id` field |

Expect several failure tests for each happy-path test.

## Unit, integration and end-to-end tests

Tests differ in how much of the system they exercise.

- **Unit test**: checks one small piece of logic in isolation, without HTTP or a real database. Example: a function `validate_task(body)` returns an error for a 201-character title. Very fast; thousands run in seconds.
- **Integration test**: checks that your code works together with a real external part, such as the PostgreSQL database. Example: send `POST /tasks` to a running TaskFlow server backed by a test database, then query the `tasks` table. Slower, but proves the pieces fit.
- **End-to-end (E2E) test**: drives the whole deployed system the way a user does, for example a browser opening the TaskFlow web app, logging in as Alice and creating a task through the form. Slowest and most fragile, but closest to reality.

Most tests in this unit are integration tests at the API level: they send real HTTP requests and check the database.

## The test pyramid

The **test pyramid** (popularised by Mike Cohn and explained in Martin Fowler's site article "The Practical Test Pyramid") is a guide to how many tests of each kind to write:

```text
        /\        few   end-to-end   (slow, fragile, realistic)
       /  \
      /----\      some  integration  (real HTTP + test database)
     /      \
    /--------\    many  unit         (fast, focused)
```

Why this shape? Unit tests are cheap to write, fast to run and point straight at the broken line. E2E tests are slow, break for unrelated reasons (a button moved) and are expensive to maintain, so keep only a few for the most important journeys, such as "sign in and create a task".

The opposite shape, mostly manual or E2E tests and few unit tests, is sometimes called the "ice-cream cone" and leads to slow, unreliable feedback. A useful rule: test each thing at the lowest level that can catch the bug.

## Arrange, act, assert

Good tests share one simple structure, called **arrange–act–assert** (or given–when–then):

1. **Arrange**: set up the world the test needs. Create users, tasks and tokens.
2. **Act**: do exactly one thing, usually send one HTTP request.
3. **Assert**: check the status, body, headers and side effects.

```text
test "deleting a task removes it":
    # Arrange
    alice = create_user(id=123, email="alice@example.com")
    task  = create_task(owner=alice, title="Old note")
    token = login_token(alice)

    # Act
    res = DELETE "/v1/tasks/{task.id}" with Bearer token

    # Assert
    assert res.status == 204
    assert db.count("SELECT count(*) FROM tasks WHERE id = $1", task.id) == 0
```

Keeping the three parts visibly separate makes a failing test easy to read: you can see what was set up, what was done, and which expectation failed. One test should check one behaviour.

## Worked example: creating a task

Goal: prove that `POST /tasks` creates a task owned by the caller.

**Arrange.** Insert Alice into an empty test database and get her a token:

```sql
INSERT INTO users (id, email, password_hash, name)
VALUES (123, 'alice@example.com', '<hash>', 'Alice');
```

**Act.** Send one request:

```http
POST /v1/tasks HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer <alice-token>
Content-Type: application/json

{"title": "Buy milk"}
```

**Assert** on what came back and what changed:

```http
HTTP/1.1 201 Created
Location: /v1/tasks/1
Content-Type: application/json

{"id": 1, "title": "Buy milk", "done": false, "due_date": null, "created_at": "2026-10-14T09:00:00Z"}
```

```text
assert status == 201
assert body.title == "Buy milk" and body.done == false
assert header Location == "/v1/tasks/" + body.id
row = SELECT owner_id, title FROM tasks WHERE id = body.id
assert row exists and row.owner_id == 123
```

The final check is the important one: the default `done = false` and `owner_id = 123` came from the server, not the client.

## Worked example: testing validation boundaries

Validation bugs cluster at the **boundaries** of a rule. TaskFlow's rule is "title is 1–200 characters", so test just inside and just outside each edge:

| Test | Title sent | Expected |
|---|---|---|
| missing title | (field absent) | 422, error at `#/title` |
| empty | `""` | 422 |
| minimum | `"a"` (1 char) | 201 |
| maximum | 200 × `"a"` | 201 |
| one over | 201 × `"a"` | 422 |

A classic bug is writing `length < 200` instead of `length <= 200`; only the 200-character test catches it.

```text
test "title of 201 characters is rejected":
    # Arrange
    alice = create_user(123); token = login_token(alice)
    # Act
    res = POST "/v1/tasks" {"title": repeat("a", 201)} with token
    # Assert
    assert res.status == 422
    assert res.body.errors[0].pointer == "#/title"
    assert db.count("SELECT count(*) FROM tasks") == 0
```

The last line matters: a rejected request must not leave a half-created row behind.

## Testing 404s

A missing resource must give `404 Not Found`, not a `500` crash and not a `200` with `null`. Pick an id that certainly does not exist in the test database:

```text
test "getting a task that does not exist returns 404":
    alice = create_user(123); token = login_token(alice)
    res = GET "/v1/tasks/999999" with token
    assert res.status == 404
    assert res.header "Content-Type" starts with "application/problem+json"
    assert res.body.type == "https://api.taskflow.example/problems/not-found"
```

Repeat for every method that takes an id: `PUT`, `PATCH` and `DELETE` on `/tasks/999999` should also return 404, and none should create a row (a `PUT` to a missing id in TaskFlow does not create a task).

Also test the contrast case: `GET /tasks?done=true` for a user with no finished tasks must return `200` with `[]`, not 404. A malformed id such as `/tasks/abc` is another useful test: it should be a clean 4xx, never a 500 caused by a database type error.

## Worked example: testing authentication

Authentication tests check that the API refuses requests that don't prove who the caller is. **401 Unauthorized** means "not authenticated": no valid credentials.

**Case 1: no token.**

```http
GET /v1/tasks HTTP/1.1
Host: api.taskflow.example

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

**Case 2: an expired token.** Arrange a token for Alice whose expiry time is in the past (most test setups can mint one directly, rather than waiting for real time to pass).

```text
test "expired token is rejected":
    alice = create_user(123)
    token = make_token(alice, expires_at = now - 1 minute)
    res = POST "/v1/tasks" {"title": "Sneaky"} with token
    assert res.status == 401
    assert db.count("SELECT count(*) FROM tasks") == 0
```

Add a third case for a token whose signature has been tampered with. Every protected endpoint needs these tests, not just one; a forgotten check on `DELETE` is exactly the kind of bug they exist to catch.

## Worked example: Alice tries Bob's task

Authorization tests check that an authenticated user can only touch their own data. OWASP's testing guide for **insecure direct object references (IDOR)** recommends using at least two test users and swapping an object id from one user into the other user's request.

**Arrange.** Alice (123) and Bob (456) each exist. Bob owns task 77:

```sql
INSERT INTO tasks (id, owner_id, title, done)
VALUES (77, 456, 'Bob''s secret plan', false);
```

**Act.** With Alice's valid token, try every method on task 77:

```http
GET /v1/tasks/77 HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer <alice-token>
```

then `PATCH /v1/tasks/77` with `{"done": true}` and `DELETE /v1/tasks/77`.

**Assert.** Each must be refused. TaskFlow's documented choice is **404 Not Found**, which hides that task 77 exists (unit 9 explains why some APIs use 403 instead). The test asserts that exact code. It must never be `200` or `204`, and the GET body must not contain Bob's title.

## Checking side effects: Bob's task is unchanged

A refusal status is not enough. A buggy handler could write to the database first and only then return 403. So after Alice's PATCH and DELETE attempts, assert directly on Bob's row:

```sql
SELECT owner_id, title, done FROM tasks WHERE id = 77;
```

```text
assert row exists                       -- DELETE did not remove it
assert row.owner_id == 456              -- still Bob's
assert row.title == "Bob's secret plan"
assert row.done == false                -- PATCH did not apply
```

Then the positive control: with **Bob's** token, `GET /v1/tasks/77` returns `200` and his title. This proves the 404/403 for Alice was due to authorization, not because the task was missing or the test was set up wrongly.

Also test the list: `GET /v1/tasks` with Alice's token must not include task 77. Leaks through list endpoints are a common IDOR variant.

## Test data and isolation

Each test must be **independent**: it creates the data it needs, and its result does not depend on which tests ran before it or in what order.

Bad: test A creates Alice's task; test B assumes the task exists. Run B alone, or in a different order, and it fails for no real reason. Tests that pass or fail depending on order are called **flaky**, and teams soon stop trusting them.

Practical habits:

- **Fresh data per test**: start each test from an empty test database, or wrap each test in a transaction that is rolled back afterwards.
- **Arrange explicitly**: create Alice, Bob and their tasks inside the test, so a reader sees everything that matters.
- **Never use production data**. Use a separate test database with fake users like `alice@example.com`.
- **Avoid hidden time dependence**: "due date in the future" should be computed from a controlled "today", not a hard-coded date that expires next year.

## Worked example: a test plan for PUT /tasks/{id}

Before writing code, list the cases. `PUT` **replaces** the whole task, so `title`, `done` and `due_date` must all be sent. Arrange for every row: Alice (123) owns task 42; Bob (456) owns task 77.

| # | Case | Request | Expect |
|---|---|---|---|
| 1 | Happy path | Alice, PUT 42, all valid fields | 200, body matches, row updated |
| 2 | Idempotent | same PUT sent twice | 200 both times, same row |
| 3 | Missing field | body without `title` | 422, row unchanged |
| 4 | Max title | 200-char title | 200 |
| 5 | Over max | 201-char title | 422, row unchanged |
| 6 | Bad type | `"done": "yes"` | 422 |
| 7 | Past date | `due_date` yesterday | 422 |
| 8 | Malformed | `{"title": "x",` | 400 |

Note how "row unchanged" appears on failure rows: a rejected PUT must not partly apply.

## Test plan for PUT /tasks/{id}, continued

The remaining rows cover resources, identity and permission:

| # | Case | Request | Expect |
|---|---|---|---|
| 9 | Not found | Alice, PUT 999999 | 404, no row created |
| 10 | No token | PUT 42, no `Authorization` | 401, row unchanged |
| 11 | Expired token | Alice's expired token | 401, row unchanged |
| 12 | Other user | Alice's token, PUT 77 | 404 (TaskFlow hides other users' tasks), Bob's row unchanged |
| 13 | Owner swap | Alice, PUT 42 with `"owner_id": 456` | 422, owner still 123 |
| 14 | Wrong media type | `Content-Type: text/plain` | 415 |
| 15 | Control | Bob's token, PUT 77 | 200 |

Fifteen tests for one endpoint, and only two are happy paths (rows 1 and 15). That ratio is normal. Each row becomes one independent arrange–act–assert test.

## Common mistakes

**Mistake: asserting only the status code.** Why wrong: a `201` with the wrong `owner_id` saved still passes. Correct: also check the body and the database row.

**Mistake: testing only the happy path.** Why wrong: most bugs and all attacks are in failure cases. Correct: several failure tests per endpoint, including boundaries and auth.

**Mistake: testing authorization with one user.** Why wrong: you cannot detect IDOR without a second user's object. Correct: Alice and Bob, swap ids, and check Bob's row afterwards.

**Mistake: tests that depend on each other.** Why wrong: order changes make them fail randomly. Correct: each test arranges its own data from a clean state.

**Mistake: only testing invalid values far from the limit** (e.g. a 5,000-character title). Why wrong: off-by-one bugs live at the edge. Correct: test 200 and 201.

**Mistake: mostly E2E browser tests.** Correct: many unit tests, fewer integration tests, a handful of E2E.

## Summary

- Tests catch regressions and document behaviour; "it worked in the browser" proves one case once.
- Assert four things: status, body, headers, and database side effects.
- Most bugs hide in failure cases; write several per happy path.
- Unit tests check small logic in isolation; integration tests check real HTTP plus a real database; E2E tests drive the whole system. Use the pyramid: many unit, some integration, few E2E.
- Structure every test as arrange–act–assert, one behaviour per test.
- Test validation at the boundaries (1, 200, 201 characters) and confirm rejected requests write nothing.
- Test 404 for missing ids on every method; empty lists stay 200 `[]`.
- No token or expired token → 401.
- Authorization: two users, swap ids; expect 403/404 on GET, PATCH, DELETE and verify the other user's row is unchanged.
- Each test sets up its own data; no order dependence.

## Exercise: Find the gaps in a test suite
<!-- meta: kind=exercise, difficulty=beginner -->

A teammate's entire test suite for `DELETE /tasks/{id}` is one test: it creates Alice (user 123) and her task 42, sends `DELETE /v1/tasks/42` with Alice's token, and asserts that the status is `204`. They say the endpoint is "fully tested".

Explain why this is not enough. List at least five additional tests you would add (covering side effects, missing resources, authentication and authorization), and for each give the arrange step, the request, and the expected status plus any database check. Explain why one of your tests needs Bob (user 456).

## Exercise: Design tests for PATCH /tasks/{id}
<!-- meta: kind=exercise, difficulty=beginner -->

`PATCH /tasks/{id}` updates only the fields sent. Rules: `title`, if present, must be 1–200 characters; `done`, if present, must be a boolean; no other fields are allowed.

Write a test plan table with at least eight rows (case, request, expected status, and what to check in the database) covering the happy path, boundary values for `title`, a wrong type, an unknown field, a missing task, a missing token, and Alice trying to patch Bob's task 77. Then explain how you would keep these tests independent of each other, and which level of the test pyramid a pure check of the 200-character rule belongs to.
