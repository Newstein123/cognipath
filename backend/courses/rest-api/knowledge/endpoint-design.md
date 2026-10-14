---
id: endpoint-design
concept: Designing REST Endpoints
capability: endpoint-design
difficulty: beginner
prerequisites: [status-codes, json-resources]
source: "Adapted from MDN Web Docs — REST (https://developer.mozilla.org/en-US/docs/Glossary/REST), PUT (https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Methods/PUT), PATCH (https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Methods/PATCH), POST (https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Methods/POST), DELETE (https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Methods/DELETE), by Mozilla Contributors, CC BY-SA 2.5; design conventions informed by Microsoft Azure Architecture Center — RESTful web API design (reference) (https://learn.microsoft.com/en-us/azure/architecture/best-practices/api-design)"
---

# Designing REST Endpoints

## Why this matters
Think of a well-run library. Every book has a shelf address, and there are only a few things you can do at the desk: look a book up, add one, replace one, fix a label, or remove one. You never need a special form called "PleaseFindMeABookAboutCats". A REST API works the same way: every thing has an address (a URL), and a small set of standard verbs (HTTP methods) acts on it.

Good endpoint design means a developer who has seen one of your endpoints can guess the rest. Bad design means every endpoint is a surprise: `/getTasks`, `/task_delete`, `/updateTaskNow`. In this unit you design the complete TaskFlow task API, learn the exact difference between PUT and PATCH, add filtering and pagination, and then critique and fix a badly designed API.

## REST in plain words
REST (Representational State Transfer) is a set of design constraints for building reliable, scalable distributed systems. In everyday speech, a "REST API" is an HTTP service you can call with ordinary web tools such as curl or `fetch()`. Four ideas carry most of the weight:

- **Resources**: the things your API is about. In TaskFlow these are tasks and users. Each one has a URL, such as `/v1/tasks/42`.
- **Standard methods**: you act on resources with HTTP's own verbs. GET reads, POST creates, PUT replaces, PATCH partly changes, DELETE removes. You do not invent new verbs.
- **Representations**: the client never touches the database row itself. It receives and sends a representation of the resource, usually JSON.
- **Stateless**: every request carries everything the server needs, including the `Authorization` token. The server does not remember "what Alice did last request". That is why any server in a cluster can answer any request.

Strictly, many "REST APIs" do not follow every constraint, but these four are what you design around.

## Resources, URLs and representations
A URL names a resource; the method says what to do with it. Use **nouns, in the plural**, for collections and add the id for one member:

- `/v1/tasks` is the collection of Alice's tasks.
- `/v1/tasks/42` is one task in it.

The response body is a JSON representation of task 42:

```http
GET /v1/tasks/42 HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...

HTTP/1.1 200 OK
Content-Type: application/json

{"id": 42, "owner_id": 123, "title": "Buy milk", "done": false,
 "due_date": "2026-10-20", "created_at": "2026-10-14T09:00:00Z"}
```

Notice what the representation leaves out: nothing from the users table, and certainly not `password_hash`. A representation is a public view, not a database dump.

**Versioning**: the `/v1` prefix lets you ship breaking changes (renaming or removing a field, changing a type) as `/v2` while `/v1` keeps working for old apps. Adding an optional field is not breaking, so it stays in v1.

## The TaskFlow task API at a glance
Six endpoints cover everything a client can do with tasks. The token identifies the user, so `owner_id` is never sent by the client.

| Method | Path | Request body | Success | Response body |
|---|---|---|---|---|
| GET | /v1/tasks | none | 200 OK | page of tasks |
| POST | /v1/tasks | new task (title, due_date) | 201 Created + Location | created task |
| GET | /v1/tasks/{id} | none | 200 OK | one task |
| PUT | /v1/tasks/{id} | full task (title, done, due_date) | 200 OK | updated task |
| PATCH | /v1/tasks/{id} | only changed fields | 200 OK | updated task |
| DELETE | /v1/tasks/{id} | none | 204 No Content | none |

Two URL shapes and five methods: that is the whole API. Failures use the codes from earlier units: 400 or 422 for a bad body, 401 without a valid token, 404 when the task does not exist (or is not yours).

## Worked example: Creating a task with POST
Alice wants a new task. She POSTs to the **collection**, because she does not know the new id yet; the server assigns it.

```http
POST /v1/tasks HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...
Content-Type: application/json

{"title": "Pay rent", "due_date": "2026-11-01"}

HTTP/1.1 201 Created
Location: /v1/tasks/43
Content-Type: application/json

{"id": 43, "owner_id": 123, "title": "Pay rent", "done": false,
 "due_date": "2026-11-01", "created_at": "2026-10-14T10:05:00Z"}
```

Step by step: (1) the server validates the body; (2) it fills server-controlled fields: `id`, `owner_id` from the token, `done` defaults to false, `created_at`; (3) it answers **201 Created**, not 200, because a new resource exists; (4) the `Location` header gives its address so the client can GET it later; (5) the body returns the full task, saving an extra request.

POST is **not idempotent**: if Alice's app sends this twice, she gets tasks 43 and 44.

## PUT replaces the whole representation
PUT means "make the resource at this URL look exactly like this body". The body is the **complete** client-editable representation of the task. Whatever you leave out is not "kept as before"; the server treats the new body as the whole truth.

For a TaskFlow task, the client-editable fields are `title`, `done` and `due_date`. (`id`, `owner_id` and `created_at` are controlled by the server; they are ignored or rejected if sent.) So with PUT:

- Omit an optional field such as `due_date` and it becomes `null`: the due date is wiped.
- Omit a required field such as `title` and the server must reject the request with 400 or 422, because a task without a title is not valid.

MDN describes PUT as idempotent: sending the same PUT once or ten times leaves the task in the same state. On success the server returns 200 OK with the updated task (or 204 No Content with no body). PUT can also create a resource at a client-chosen URL (201 Created), but TaskFlow lets the server pick ids, so it uses POST for creation.

## PATCH changes only what you send
PATCH means "apply these changes to the resource". The body describes a partial modification, not a replacement. Fields you do not mention stay exactly as they were.

TaskFlow accepts a JSON object listing just the fields to change (this style is called a JSON merge patch):

```http
PATCH /v1/tasks/42 HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...
Content-Type: application/json

{"done": true}

HTTP/1.1 200 OK
Content-Type: application/json

{"id": 42, "owner_id": 123, "title": "Buy milk", "done": true,
 "due_date": "2026-10-20", "created_at": "2026-10-14T09:00:00Z"}
```

The title and due date survive untouched. To clear a field on purpose with a merge patch, send it as `null`, for example `{"due_date": null}`.

PATCH is **not guaranteed to be idempotent**. `{"done": true}` happens to give the same result every time, but a patch like "add one to `reminder_count`" changes the task again on every repeat.

## Worked example: PUT vs PATCH on the same task
Task 42 starts as `{"title": "Buy milk", "done": false, "due_date": "2026-10-20"}`. Bob's app sends the same small body two ways.

```http
PATCH /v1/tasks/42
{"done": true}
-> 200 {"title": "Buy milk", "done": true, "due_date": "2026-10-20"}

PUT /v1/tasks/42
{"title": "Buy milk", "done": true}
-> 200 {"title": "Buy milk", "done": true, "due_date": null}

PUT /v1/tasks/42
{"done": true}
-> 422 {"error": {"code": "validation_failed",
        "message": "title is required"}}
```

(Headers are trimmed to fit.) Reading the results:

1. PATCH changed one field; everything else was kept.
2. PUT without `due_date` replaced the task and the due date was wiped, because the body is the new whole.
3. PUT without `title` was rejected: a complete task must have a title.

Rule of thumb: use PATCH for small edits such as ticking a checkbox; use PUT when the client has the full edited form and wants to save all of it.

## Idempotency: which requests are safe to retry
A method is **idempotent** if sending the same request many times has the same effect on the server as sending it once. It is **safe** if it does not change anything at all.

| Method | Safe | Idempotent |
|---|---|---|
| GET | yes | yes |
| PUT | no | yes |
| DELETE | no | yes |
| POST | no | no |
| PATCH | no | not guaranteed |

Why it matters: on a phone with a flaky connection, the app often cannot tell whether a request arrived. If the request was a GET, PUT or DELETE, it can simply resend it. If it was a POST, resending may create a duplicate task.

Idempotency is about the **state of the server**, not the response. Two identical DELETEs leave the same state (the task is gone) even though the second one gets a different status code, as the next example shows.

## Worked example: Deleting a task twice
Alice deletes task 43.

```http
DELETE /v1/tasks/43 HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...

HTTP/1.1 204 No Content
```

**204 No Content** says "done, and there is nothing to send back". A DELETE request should not carry a body. (MDN also allows 200 OK with a body describing the result, or 202 Accepted if deletion will happen later.)

Her train enters a tunnel and the app retries the same request:

```http
DELETE /v1/tasks/43 HTTP/1.1
...

HTTP/1.1 404 Not Found
Content-Type: application/json

{"error": {"code": "not_found", "message": "Task 43 not found"}}
```

Is that a contradiction of idempotency? No. After one DELETE or after two, the server state is identical: task 43 does not exist. Only the response differs. The client should treat a 404 on a retried DELETE as "already gone", not as a failure.

## Filtering, sorting and pagination
Alice may have 500 tasks. Returning them all in one response is slow and wasteful. Instead, the **same** collection URL takes **query parameters** that narrow and slice the result. They modify how you read `/v1/tasks`; they do not create new endpoints.

```
GET /v1/tasks?done=false&sort=due_date&limit=20&offset=40
```

- `done=false` is a **filter**: only open tasks.
- `sort=due_date` orders by due date (a common convention is `sort=-due_date` for descending).
- `limit=20` is the **page size**: at most 20 items.
- `offset=40` **skips** the first 40 matches, so this is the third page (items 41 to 60).

Design rules: give `limit` a sensible default (say 20) and a maximum (say 100) so no one can request a million rows; reject unknown sort fields with 400; and always apply the filter for the current user's tasks first, so `done=false` never reveals Bob's tasks to Alice.

## Worked example: A paginated task list
Alice has 57 open tasks and asks for the third page of 20.

```http
GET /v1/tasks?done=false&sort=due_date&limit=20&offset=40 HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...

HTTP/1.1 200 OK
Content-Type: application/json

{
  "data": [
    {"id": 88, "title": "Renew passport", "done": false, "due_date": "2026-12-01"},
    {"id": 91, "title": "Book dentist",   "done": false, "due_date": "2026-12-03"}
  ],
  "pagination": {"limit": 20, "offset": 40, "total": 57,
                 "next": null,
                 "prev": "/v1/tasks?done=false&sort=due_date&limit=20&offset=20"}
}
```

(The `data` array is shortened; it would hold 17 tasks, items 41 to 57.) The list sits under `data`, and paging information sits under `pagination`. `next` is `null` because there is no fourth page. An empty page is still **200 OK** with `"data": []`, not 404: the collection exists, it just has nothing in that range.

## Nested vs flat routes
When one resource belongs to another, you can express it in the path. Suppose TaskFlow adds comments on tasks.

- **Nested**: `GET /v1/tasks/42/comments` lists comments of task 42; `POST /v1/tasks/42/comments` adds one. The parent id lives in the URL, which reads naturally.
- **Flat**: `GET /v1/comments/7` reads, and `DELETE /v1/comments/7` removes, one comment. A comment id is unique on its own, so it does not need its parent in the path.

A good default: **nest one level** to list or create children, and use a **flat** URL for an individual child. Avoid deep chains like `/users/123/tasks/42/comments/7/likes`: they are long, break if a relationship changes, and force the client to know every parent id.

TaskFlow's own `/v1/tasks` is flat, not `/v1/users/123/tasks`, because the token already says who the user is. Putting 123 in the path would invite Bob to try `/v1/users/123/tasks`.

## Verbs in URLs are an anti-pattern
The HTTP method is already the verb. Putting another verb in the path duplicates it, and the two can disagree.

| Anti-pattern | Problem | RESTful fix |
|---|---|---|
| `POST /getTasks` | reading with POST: not safe, not cacheable, not retryable | `GET /v1/tasks` |
| `GET /deleteTask?id=42` | a GET that deletes; a link preview or crawler could delete data | `DELETE /v1/tasks/42` |
| `POST /createTask` | verb repeats what POST already says | `POST /v1/tasks` |
| `POST /updateTaskTitle` | one endpoint per field does not scale | `PATCH /v1/tasks/42` with `{"title": ...}` |
| `GET /tasks/markDone/42` | a state change through GET | `PATCH /v1/tasks/42` with `{"done": true}` |

The test: read the path aloud without the method. It should name a **thing** ("tasks", "task 42"), never an action.

## Consistent response and error shapes
Clients are written once and called thousands of times, so the same kind of response should always have the same shape.

- **One resource**: the resource object itself (as in every task example above).
- **A collection**: always `{"data": [...], "pagination": {...}}`, even when the list is empty.
- **An error**: always one envelope, whatever went wrong:

```json
{"error": {
   "code": "validation_failed",
   "message": "The request body is invalid.",
   "details": [{"field": "due_date", "issue": "must be a date like 2026-11-01"}]
}}
```

`code` is a stable machine-readable string the app can switch on; `message` is for humans; `details` pinpoints fields. The status code still carries the category (422 here, 404 for `not_found`, 401 for `unauthenticated`). Also keep naming consistent: TaskFlow uses snake_case everywhere (`due_date`, `created_at`), never `dueDate` in one place and `due_date` in another. Never return 200 with an error inside the body.

## Worked example: Design review of a messy API
A teammate proposes this task API. Review each line, name the problem, then fix it.

```
1. POST   /getAllTasks           body {"page": 3}
2. POST   /task/new              -> 200 {"result": "ok"}
3. GET    /task/delete?id=42     -> 200 {"status": "error", "msg": "no such task"}
4. POST   /task/42/update        body {"done": true}
5. GET    /users/123/tasks       (any logged-in user)
```

Fixes:

1. Read via POST, verb in path. Fix: `GET /v1/tasks?limit=20&offset=40` returning `{"data", "pagination"}`.
2. Singular noun, verb, 200 with no task. Fix: `POST /v1/tasks` returns 201, `Location: /v1/tasks/43`, and the task.
3. GET that deletes; error hidden in a 200. Fix: `DELETE /v1/tasks/42` returns 204; a missing task returns 404 with the standard error envelope.
4. Vague "update" verb. Fix: `PATCH /v1/tasks/42` with `{"done": true}`, 200 with the task.
5. User id in the path invites Bob to read Alice's tasks. Fix: `/v1/tasks`, scoped by the token.

Finally, add the missing `/v1` prefix to every path.

## Common mistakes
- **Sending a partial body with PUT.** Bob's app PUTs `{"done": true}` expecting a small edit. Why wrong: PUT replaces the whole task, so missing fields are wiped or the request is rejected. Correct: PATCH `{"done": true}`, or PUT the full task.
- **Returning 200 for a create.** Why wrong: the client cannot tell a new resource was made or where it lives. Correct: 201 Created with `Location: /v1/tasks/43` and the task in the body.
- **Treating a second DELETE's 404 as a crash.** Why wrong: the task is gone either way; DELETE is idempotent in effect. Correct: the client treats 404 after a retry as "already deleted".
- **Returning 404 for an empty filtered list.** Why wrong: `/v1/tasks` exists; it just has no matches. Correct: 200 with `"data": []`.
- **Using GET for anything that changes data.** Why wrong: GET must be safe; browsers, caches and crawlers repeat GETs freely. Correct: POST, PUT, PATCH or DELETE.
- **Trusting `owner_id` in the body.** Why wrong: Bob could create tasks for Alice. Correct: take the owner from the token.

## Summary
- REST: resources with URLs, standard HTTP methods, JSON representations, stateless requests.
- Paths are plural nouns: `/v1/tasks` and `/v1/tasks/{id}`. The method is the verb.
- POST /tasks creates: 201 Created + `Location` + the task. Not idempotent.
- GET reads: 200. Safe and idempotent.
- PUT replaces the whole representation: omitted optional fields are cleared, omitted required fields cause 400/422. Idempotent.
- PATCH changes only the fields sent. Not guaranteed idempotent.
- DELETE removes: 204 No Content; a repeat gets 404, yet the server state is the same.
- Lists use query parameters: `?done=false&sort=due_date&limit=20&offset=40`, returning `{"data": [...], "pagination": {...}}`; an empty page is 200.
- Nest one level for children; keep individual resources flat; never put user ids where the token decides.
- Version in the path (`/v1`); only breaking changes need `/v2`.
- One error envelope everywhere: `{"error": {"code", "message", "details"}}` with a matching status code.

## Exercise: Design the endpoints for task comments
<!-- meta: kind=exercise, difficulty=beginner -->

TaskFlow is adding comments to tasks. A comment has `id`, `task_id`, `author_id`, `body` and `created_at`. Users must be able to list the comments of a task (newest first, in pages), add a comment to a task, edit the text of their own comment, and delete their own comment.

Design the endpoints. For each one give the method, the path, the request body (if any), the success status code and what the response body contains. Explain your choice between nested and flat routes, say which fields the client must not send and why, show the shape of a paginated list response, and state what a client receives when it deletes the same comment twice.

## Exercise: Fix Bob's disappearing due dates
<!-- meta: kind=exercise, difficulty=beginner -->

Bob reports a bug in the TaskFlow mobile app: whenever he ticks a task as done, its due date vanishes. The app's network log shows:

```http
PUT /v1/tasks/7 HTTP/1.1
Content-Type: application/json

{"title": "Call the bank", "done": true}

HTTP/1.1 200 OK
{"id": 7, "title": "Call the bank", "done": true, "due_date": null}
```

Explain exactly why the due date disappeared and whether the server behaved correctly. Give two different correct requests the app could send instead, with their responses. Then explain what would happen if the app retried your preferred request after a timeout, using the idea of idempotency, and what would happen if the app had sent PUT with only `{"done": true}`.
