---
id: api-testing
concept: API Testing
capability: api-testing
difficulty: beginner
prerequisites: [validation-errors, auth]
source: "Martin Fowler — The Practical Test Pyramid (https://martinfowler.com/articles/practical-test-pyramid.html); OWASP Web Security Testing Guide (https://owasp.org/www-project-web-security-testing-guide/); MDN Web Docs — HTTP"
---

# API Testing

## Why test an API

An automated test is a small program that uses your API and checks that it behaves the
way you intended. You write it once and can run it again after every change.

Tests earn their keep in three ways. They **catch regressions**: when a later change
quietly breaks something that used to work, a failing test tells you before your users
do. They **document behaviour**: a test named "returns 404 when the task does not exist"
is a precise, always-up-to-date description of what the API promises. And they give you
**confidence to change code**, because you can check the whole API in seconds.

Trying an endpoint once in the browser and seeing it work is not proof. It shows one
request, with one set of data, on one day. It says nothing about bad input, missing
records, logged-out users, or whether it still works after next week's change.

## What an API test checks

Almost every API test follows the same shape: send one HTTP request, then check the
response against what you expected. These checks are called **assertions**. If any
assertion is false, the test fails.

A good API test usually asserts on three things:

- **The status code.** Did a successful create return 201? Did a bad request return a
  4xx code rather than 200 or 500?
- **The response body.** Does the JSON contain the right fields and values? For an error,
  does it explain what went wrong?
- **Side effects.** Did the request change (or not change) the stored data as intended?
  After a successful `POST /tasks`, a follow-up `GET` should find the new task. After a
  rejected request, nothing should have been saved.

Checking only the status code is a common beginner gap: a 200 with the wrong data in the
body is still a bug.

## The happy path and the failure cases

The **happy path** is the case where everything is correct: a logged-in user sends valid
data for a resource that exists and that they own. It is the case you naturally try
first, and usually the one that already works.

Most bugs live in the **failure cases**, because they are easy to forget while building.
For almost any endpoint, ask these questions:

- **Invalid input:** what if a required field is missing, has the wrong type, or is too
  long?
- **Missing resource:** what if the id in the URL does not exist?
- **Not logged in:** what if the request has no token, or an expired one?
- **Someone else's resource:** what if a logged-in user asks for data that belongs to
  another user?

A useful rule of thumb: for each endpoint, write one happy-path test and at least one
test for each failure case that applies. A failure case should fail cleanly, with the
right 4xx status and a helpful error, never with a 500 or with someone else's data.

## Unit, integration and end-to-end tests

Tests come in different sizes. Martin Fowler's **test pyramid** describes a healthy mix:

- **Unit tests** (bottom, the most): test one small piece of code, such as a function
  that checks whether a title is valid, without a server or database. They are fast and
  pinpoint exactly what broke.
- **Integration tests** (middle): test several pieces together, such as sending a real
  HTTP request to your API and letting it talk to a test database. Most of the API tests
  in this lesson are this kind.
- **End-to-end tests** (top, the fewest): test the whole system as a user would, for
  example through the real front end. They give the most realistic confidence but are
  slow and more fragile.

The shape is the point: many small fast tests, fewer bigger slow ones. If a behaviour can
be checked by a lower-level test, prefer that.

## Arrange, act, assert

A clear test has three steps, often called **arrange, act, assert**:

1. **Arrange:** set up what the test needs (a user, a token, any existing data).
2. **Act:** send exactly one request.
3. **Assert:** check the status code, the body and any side effects.

Here is a happy-path test for creating a task, in plain pseudocode:

```
test "POST /tasks creates a task":
    # Arrange
    user  = create_test_user()
    token = log_in(user)

    # Act
    response = send POST /tasks
                 header Authorization: Bearer <token>
                 body   {"title": "Buy milk"}

    # Assert
    expect response.status == 201
    expect response.body.title == "Buy milk"
    expect response.body.id exists
    expect GET /tasks/<response.body.id> (as user) returns 200
```

Keeping one action per test means that when it fails, you know exactly which request
misbehaved.

## Testing validation

Validation tests check that the API rejects bad input clearly and saves nothing. Your API
should pick one status code for invalid input and use it consistently; many APIs use
**400 Bad Request**, others use **422 Unprocessable Content**. The test should expect
whichever your API documents.

```
POST /tasks
Authorization: Bearer <token>
Content-Type: application/json

{}
```

Expected response:

```
HTTP/1.1 422 Unprocessable Content
Content-Type: application/json

{"errors": [{"field": "title", "message": "title is required"}]}
```

Assert on the status code, on the fact that the error names the **title** field, and that
no task was created. Then test the edges of each rule: if titles may be at most 200
characters, send 201 characters (expect rejection) and exactly 200 (expect success).
Bugs often hide right at the boundary.

## Testing missing resources

When a request names a resource that does not exist, the API should say so with
**404 Not Found**, not crash with a 500 and not return 200 with an empty body.

```
GET /tasks/999
Authorization: Bearer <token>
```

Expected:

```
HTTP/1.1 404 Not Found
```

To make this test reliable, the arrange step must guarantee that task 999 really does not
exist, for example by starting from an empty test database, or by creating a task,
deleting it, and then requesting its id.

The same check applies to every endpoint that takes an id: `PUT /tasks/999` and
`DELETE /tasks/999` should also return 404, and should not create or change anything.

## Testing access control

Access control tests check who is allowed to do what. Two cases matter for almost every
endpoint:

- **No token (not authenticated):** send the request with no `Authorization` header.
  Expect **401 Unauthorized**.
- **Wrong user (not authorized):** user A logs in and requests a task owned by user B.
  Expect **403 Forbidden**, or **404 Not Found** if your API prefers not to reveal that
  the task exists. Either is fine if it is documented; 200 is never fine.

The second case catches **broken object level authorization (BOLA)**, the first item in
the OWASP API Security Top 10. It happens when the server checks that you are logged in
but forgets to check that the object you asked for is yours, so changing the id in the
URL exposes other people's data.

In the assert step, also check the side effect: after user A's rejected
`PUT /tasks/<B's id>`, user B's task must be unchanged.

## Test data and isolation

Each test should **set up its own data** in its arrange step and should not rely on data
left behind by another test. Tests must pass in any order and when run on their own.

Why it matters: imagine test 1 creates a task and test 2 assumes that task exists. Run
test 2 alone, or run the tests in a different order, and it fails even though the API is
fine. Failures like this waste time and teach people to ignore red tests.

Common habits that keep tests isolated:

- Use a separate **test database**, never real production data.
- Reset or clean up data between tests, so each starts from a known state.
- Create fresh users and tasks inside each test, and use the ids you get back instead of
  hard-coding ids like 1 or 2.
- For access-control tests, create **two** users so you have a genuine "someone else".

## Exercise: Write the test cases
<!-- meta: kind=exercise, difficulty=beginner -->

You are testing `PUT /tasks/{id}` in a task API where every task has an owner. A valid
request body looks like `{"title": "Buy milk", "done": false}`, and a title is required.
List at least five test cases. For each one, write the request (who sends it, with what
token and body, to which id), the expected status code, and what else you would assert.
Your list must cover: a successful update, invalid input, a task that does not exist, a
request with no token, and a request for another user's task. For each failure case,
say what should be true about the stored task afterwards.

## Exercise: Fix the flaky tests
<!-- meta: kind=exercise, difficulty=beginner -->

A teammate's test file has two tests. Test A logs in as Alice and creates a task. Test B
logs in as Bob and sends `GET /tasks/1`, expecting 403 because "task 1 is Alice's". Test
B passes when the whole file runs, but fails when run on its own. Explain why it fails,
which testing principle it breaks, and rewrite Test B's arrange, act and assert steps so
it is reliable.
