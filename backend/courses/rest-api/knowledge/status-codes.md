---
id: status-codes
concept: Status Codes and Responses
capability: status-codes
difficulty: beginner
prerequisites: [http-requests]
source: "Adapted from MDN Web Docs — HTTP response status codes; 201 Created; 401 Unauthorized; 403 Forbidden; 404 Not Found; 409 Conflict; 422 Unprocessable Content (https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status), by Mozilla Contributors, CC BY-SA 2.5"
---

# Status Codes and Responses

## Why this matters

When you hand a parcel to a courier, you get a short answer back: "delivered", "wrong address", "recipient refused", or "our van broke down". Each answer tells you what to do next. Fix the address? Try again tomorrow? Nothing at all?

An HTTP status code is that short answer. Every response from the TaskFlow API starts with a three-digit number such as `200`, `404` or `500`. Programs read this number before they read anything else. A mobile app decides from it whether to show the task, show a login screen, highlight a form field, or show "please try again later".

If the API picks the wrong code, every client gets confused. A good backend engineer picks the code on purpose.

## What a status code tells the client

A response has three parts: the **status line**, the **headers** and an optional **body**.

```http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"error": "task_not_found", "message": "Task 999 does not exist."}
```

The status line is `HTTP/1.1 404 Not Found`. The number (`404`) is meant for programs. The phrase (`Not Found`) is meant for humans reading logs. Clients must rely on the number.

The status code answers one question: **what happened to my request?** It succeeded, it needs another step, the client made a mistake, or the server failed. The body adds the details: which field was wrong, or what the new task looks like. The code is the headline and the body is the article. A client should be able to react correctly from the code alone.

## The five classes and the 4xx/5xx rule

The first digit gives the class.

| Class | Meaning | TaskFlow example |
|---|---|---|
| 1xx Informational | Interim reply; keep going | Rare in APIs |
| 2xx Success | Request received, understood, accepted | Task fetched |
| 3xx Redirection | Further action needed, often a new URL | API moved to /v2 |
| 4xx Client error | The request was wrong or can't be fulfilled as sent | Missing title |
| 5xx Server error | The server failed on a valid request | Database crashed |

The key rule: **4xx means the client must change something. 5xx means the server failed.** After a 4xx, sending the exact same request again will fail again. The client has to fix the body, log in, or pick another URL. After a 5xx, the request itself may be fine, so retrying later can work. This rule also tells you who gets paged at 3 a.m.: a spike of 5xx is the backend team's problem.

## Success codes: 200, 201, 204

- **200 OK**: the request succeeded. What "success" means depends on the method. For `GET /tasks/42` the body holds the task. For `PUT` or `PATCH` it usually holds the updated task.
- **201 Created**: the request succeeded **and a new resource was created**, typically after `POST`. Send a `Location` header with the URL of the new resource. Usually the body also holds the created object.
- **204 No Content**: success, and there is deliberately **no body**. This is common for `DELETE /tasks/42`, or for an update when the client doesn't need the result back.

```http
HTTP/1.1 201 Created
Location: https://api.taskflow.example/v1/tasks/43
Content-Type: application/json

{"id": 43, "title": "Pay rent", "done": false}
```

Pick the most specific one. "Created" says more than "OK", and the `Location` header lets the client find the new task without guessing its id.

## Redirects: 301 and 304 (briefly)

You will meet two 3xx codes in APIs.

- **301 Moved Permanently**: the resource's URL has changed for good. The new URL goes in the `Location` header. If TaskFlow retires `/v1/todo-items`, it can answer `301` with `Location: /v1/tasks`. Clients should then update their stored URL.
- **304 Not Modified**: used with caching. The client says "I have a copy from earlier" (for example with an `If-None-Match` header carrying an ETag). The server answers `304` with **no body**, meaning "nothing changed, keep using your cached copy". This saves bandwidth when the app refreshes the task list and nothing has changed.

```http
GET /v1/tasks/42 HTTP/1.1
If-None-Match: "v7"

HTTP/1.1 304 Not Modified
ETag: "v7"
```

Beginners rarely send these by hand, but you should recognise them in logs.

## Client errors: 400, 404, 405

- **400 Bad Request**: the server can't or won't process the request because of a client error, usually **malformed syntax**. Examples are broken JSON (`{"title": "Buy milk",}`) or a query parameter that can't be parsed.
- **404 Not Found**: the server cannot find the requested resource. In an API, the endpoint can be perfectly valid while the specific item doesn't exist, as in `GET /tasks/999` when there is no task 999. A 404 does not say whether the absence is temporary or permanent. (`410 Gone` exists for "deleted for good".)
- **405 Method Not Allowed**: the URL exists, but it doesn't support this method. For example, TaskFlow has no `DELETE /tasks` for wiping the whole collection. The response should include an `Allow` header listing what *is* supported:

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET, POST
```

Notice the difference: 404 means "nothing lives at this address". 405 means "something lives here, but you can't do that to it".

## 401 vs 403: the most confused pair

The names are misleading, so learn the meanings.

- **401 Unauthorized** really means **unauthenticated**. The request lacks valid credentials, because the token is missing, expired or invalid. The server doesn't know who you are. Logging in and retrying can fix it. A 401 should come with a `WWW-Authenticate` header naming the expected scheme, such as `WWW-Authenticate: Bearer`.
- **403 Forbidden** means **authenticated but not allowed**. The server knows exactly who you are, and the answer is still no. Logging in again won't help.

Quick test: *would a fresh, valid login change the outcome?* If yes, use 401. If no, use 403.

In TaskFlow, a request with no `Authorization` header gets 401. Bob, with a valid token, trying to delete Alice's task gets 403. Some servers deliberately return 404 instead of 403 to hide that the resource exists at all. That is an accepted privacy choice.

## Client errors: 409, 422, 429

- **409 Conflict**: the request conflicts with the **current state** of the resource. Examples: registering with an email that's already taken, or two people editing the same task at once when the client's version is out of date. The body should explain the conflict so the client can resolve it and resubmit.
- **422 Unprocessable Content**: the body was **parsed fine**, but its content fails the rules. Valid JSON with `"due_date": "yesterday"`, or an empty title, is a typical case. Remember **400 = can't read it, 422 = read it, but it's not acceptable**. Some APIs use 400 for both, but if you use 422, use it consistently.
- **429 Too Many Requests**: the client sent too many requests in a given time (rate limiting). Include `Retry-After: 30` so the client knows how long to wait.

All three are still 4xx. The client must change something: resolve the conflict, fix the data, or slow down.

## Server errors: 500, 503

- **500 Internal Server Error**: a generic error. The server hit a situation it doesn't know how to handle, like an unhandled exception, a bug, or a null pointer. The client did nothing wrong. Never put stack traces or SQL in the body, because they leak internals to attackers. Log the details on the server and return a short message, ideally with a request id for support.
- **503 Service Unavailable**: the server is **temporarily** unable to handle the request, for example during maintenance, overload, or when the database is down. It should be temporary, and a `Retry-After` header can say when to try again.

```http
HTTP/1.1 503 Service Unavailable
Retry-After: 120
Content-Type: application/json

{"error": "maintenance", "message": "TaskFlow is upgrading. Back in 2 minutes."}
```

A 5xx is never the user's fault. If your API returns 500 for a missing title, that's a bug: it should be 422 or 400.

## Choosing the code: a decision flow

Walk through these questions in order and stop at the first "yes".

```text
1. Did the server itself fail (crash, DB down, overload)?
      crash/bug -> 500     temporarily down/overloaded -> 503
2. Is the client sending too fast?                     -> 429
3. Can't parse the request (bad JSON, bad syntax)?     -> 400
4. No valid credentials (missing/expired token)?       -> 401
5. Does the URL point to nothing?                      -> 404
6. URL exists but the method isn't supported?          -> 405
7. Known user, but not allowed to do this?             -> 403
8. Parsed fine, but data breaks validation rules?      -> 422
9. Clashes with current state (duplicate, stale)?      -> 409
10. Success:
      created something -> 201 + Location
      nothing to return -> 204
      otherwise         -> 200
```

Real servers check authentication early, so 401 often comes before 404. That way an anonymous caller can't probe which task ids exist. The order is a guide, not a law. What matters is that each code matches what actually happened.

## Response bodies and headers that go with each code

Each code has a typical companion.

| Code | Body | Header to send |
|---|---|---|
| 200 | The resource or result | `Content-Type` |
| 201 | The created resource | `Location` |
| 204 | None, ever | |
| 304 | None | `ETag` |
| 401 | Short error | `WWW-Authenticate` |
| 405 | Short error | `Allow` |
| 429, 503 | Short error | `Retry-After` |
| other 4xx/5xx | Error object | `Content-Type` |

Use **one error shape** across the whole API so clients can parse every failure the same way:

```json
{
  "error": "validation_failed",
  "message": "The request body has invalid fields.",
  "details": [{"field": "title", "issue": "must not be empty"}]
}
```

The `error` field is a stable machine-readable code. `message` is for humans. `details` points at the exact field the client must change.

## Worked example: Creating a task

Alice (user 123) creates a task.

```http
POST /v1/tasks HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...
Content-Type: application/json

{"title": "Pay rent", "due_date": "2026-11-01"}
```

Step 1: Credentials are valid, so not 401. Step 2: The JSON parses, so not 400. Step 3: The title is non-empty and the date is real, so not 422. Step 4: The server inserts a row:

```sql
INSERT INTO tasks (owner_id, title, done, due_date, created_at)
VALUES (123, 'Pay rent', false, '2026-11-01', now())
RETURNING id;   -- returns 43
```

Step 5: Something new exists, so the answer is **201**, with its URL:

```http
HTTP/1.1 201 Created
Location: https://api.taskflow.example/v1/tasks/43
Content-Type: application/json

{"id": 43, "owner_id": 123, "title": "Pay rent", "done": false,
 "due_date": "2026-11-01", "created_at": "2026-10-14T09:12:00Z"}
```

Why not 200? 200 would work, but 201 tells the client precisely that a task was created and where to find it.

## Worked example: Deleting a task twice

Alice deletes task 43.

```http
DELETE /v1/tasks/43 HTTP/1.1
Authorization: Bearer eyJhbGciOi...

HTTP/1.1 204 No Content
```

The task is gone and there's nothing useful to return, so the answer is **204** with an empty body. (A `200` with a small confirmation body is also acceptable. Just be consistent.)

Her app has a flaky connection and sends the same `DELETE` again:

```http
DELETE /v1/tasks/43 HTTP/1.1
Authorization: Bearer eyJhbGciOi...

HTTP/1.1 404 Not Found
Content-Type: application/json

{"error": "task_not_found", "message": "Task 43 does not exist."}
```

Now the task doesn't exist, so **404** is honest. The app can treat "404 on delete" as "already gone". Then she tries `DELETE /v1/tasks` (the whole collection). TaskFlow doesn't support that, so the answer is **405** with `Allow: GET, POST`.

## Worked example: Bob and Alice's task

Task 42 belongs to Alice (owner_id 123). Three requests arrive.

**(a) No token at all:**

```http
GET /v1/tasks/42 HTTP/1.1

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

The server doesn't know who this is. Logging in could fix it, so the answer is **401**.

**(b) Bob (user 456) with a valid token:**

```http
DELETE /v1/tasks/42 HTTP/1.1
Authorization: Bearer <Bob's valid token>

HTTP/1.1 403 Forbidden
Content-Type: application/json

{"error": "forbidden", "message": "You can only delete your own tasks."}
```

The server knows it's Bob and checks `owner_id = 456`. That doesn't match 123. A new login won't change that, so the answer is **403**. (TaskFlow could choose 404 here to hide that task 42 exists.)

**(c) Bob's token has expired:** the answer is **401** again. Identity can't be confirmed, and refreshing the token fixes it.

## Worked example: Bad JSON vs bad data

Alice's app sends two broken requests.

**Request 1:** broken syntax, with a trailing comma.

```http
POST /v1/tasks HTTP/1.1
Content-Type: application/json

{"title": "Call mum",}
```

The server can't even parse it, so the answer is **400 Bad Request**: `{"error": "invalid_json", "message": "Unexpected '}' at position 21."}`

**Request 2:** perfect JSON, impossible content.

```http
POST /v1/tasks HTTP/1.1
Content-Type: application/json

{"title": "", "due_date": "2026-02-30"}
```

It parses fine, but the title is empty and February 30 doesn't exist. The answer is **422**, pointing at the fields:

```json
{"error": "validation_failed",
 "details": [{"field": "title", "issue": "must not be empty"},
             {"field": "due_date", "issue": "not a real date"}]}
```

In both cases the client must change the request. That's why both are 4xx. Only the kind of fix differs.

## Common mistake: 200 OK with an error inside

**Mistake:**

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"success": false, "error": "Task not found"}
```

**Why it's wrong:** the status line says "it worked" and the body says "it didn't". Every layer that only looks at the code now believes the request succeeded. HTTP libraries won't raise an error, monitoring dashboards show 100% success, retry logic never runs, and caches may store the "error" as a valid answer. Each client has to invent its own way to dig the truth out of the body.

**Correct version:** let the code tell the truth and keep the body for details.

```http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"error": "task_not_found", "message": "Task 999 does not exist."}
```

Rule of thumb: if the body contains the word "error", the status code should not be 2xx.

## Common mistakes: other mix-ups

- **401 for "not your task".** Bob is logged in, so this is 403 (or 404 to hide the task). 401 would make his app wrongly show a login screen.
- **500 for bad input.** An empty title crashing the server into a 500 is a bug. Validate input and return 422 (or 400). A 5xx should mean "our fault".
- **200 for creation without a Location.** Prefer 201 plus `Location: .../tasks/43`.
- **A body on 204.** 204 means no content. If you want to return the task, use 200.
- **404 for a wrong method.** If `/tasks` exists but `DELETE` isn't supported, that's 405 with `Allow`.
- **Leaking internals on 500.** Don't send stack traces or SQL errors to the client. Log them and send a short message with a request id.
- **Retrying a 4xx unchanged.** The same request will fail the same way. Retry 503 and 429 after `Retry-After`. Fix the request for other 4xx.

## Summary

- A status code is the machine-readable headline of a response. Clients act on it first.
- Classes: 1xx informational, 2xx success, 3xx redirection, 4xx client error, 5xx server error.
- **4xx = the client must change something. 5xx = the server failed.**
- Success: 200 (OK), 201 (created, plus `Location`), 204 (no body).
- Redirects: 301 (moved, plus `Location`), 304 (use your cached copy).
- Client errors: 400 (unparseable), 401 (not authenticated), 403 (authenticated but not allowed), 404 (doesn't exist), 405 (method not supported, plus `Allow`), 409 (conflicts with current state), 422 (parsed but invalid), 429 (too many, plus `Retry-After`).
- Server errors: 500 (unexpected failure), 503 (temporarily unavailable, plus `Retry-After`).
- Never return 200 with an error body. Use one consistent error shape.
- Choose the code by asking what actually happened, using the decision flow.

## Exercise: Choose the status code
<!-- meta: kind=exercise, difficulty=beginner -->

For each TaskFlow situation, give the status code, one important header (if any), and a one-sentence justification:

1. Alice sends `PATCH /v1/tasks/42` with `{"done": true}`, and the server returns the updated task.
2. Alice sends `POST /v1/tasks` with valid JSON whose `due_date` is `"next-ish week"`.
3. Bob, logged in, sends `GET /v1/tasks/42`, which belongs to Alice.
4. A script sends 500 requests in ten seconds and TaskFlow's limit is 100 per minute.
5. The PostgreSQL server is down for scheduled maintenance.

Then explain in two or three sentences why situations 2 and 5 belong to different classes.

## Exercise: Fix the error responses
<!-- meta: kind=exercise, difficulty=beginner -->

A junior developer wrote TaskFlow's error handling so that every response is `200 OK`, with bodies like `{"success": false, "error": "not logged in"}`, `{"success": false, "error": "task not found"}` and `{"success": false, "error": "database timeout"}`.

Explain what problems this causes for a mobile app, for monitoring, and for automatic retries. Then rewrite each of the three responses with the correct status code, any header that should go with it, and a body in a consistent error format.
