---
id: authorization
concept: "Authorization: What May You Do?"
capability: authorization
difficulty: beginner
prerequisites: [authentication, queries-safety]
source: "Adapted from OWASP API Security Top 10 2023 — API1:2023 Broken Object Level Authorization (https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/) and API5:2023 Broken Function Level Authorization (https://owasp.org/API-Security/editions/2023/en/0xa5-broken-function-level-authorization/), CC BY-SA 4.0; OWASP Cheat Sheet Series — Authorization (https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) and Insecure Direct Object Reference Prevention (https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html), CC BY-SA 4.0; MDN Web Docs — 403 Forbidden (https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/403), by Mozilla Contributors, CC BY-SA 2.5"
---

# Authorization: What May You Do?

## Why this matters

Back in the office building: at the entrance you got a badge that proves who you are. That was authentication. Now imagine the building **never checks the badge at individual doors**. Anyone with *any* badge can walk into the finance room, the server room, or the CEO's office. The badge is real; the security is still broken.

That is the most common serious flaw in real APIs, ranked **number one** in the OWASP API Security Top 10 (2023): the login works, the token is valid, yet one user can read, change or delete another user's data by changing a number in the URL.

Authorization is the set of **door rules**. Authentication tells TaskFlow "this is Alice"; authorization decides "Alice may read task 42, but not task 77, and she may not open the admin panel". This unit shows how the flaw happens, why popular quick fixes don't work, and how to write the check correctly.

## What authorization means

**Authorization** is the decision, made **on the server**, on **every request**, about whether **this** authenticated user may perform **this** action on **this** resource.

Each part matters:

- **This user** — the identity comes from the verified session or token (the previous unit), never from something the client typed into the URL or body.
- **This action** — reading is not the same as editing or deleting. `GET`, `PUT`, `PATCH` and `DELETE` each need a decision.
- **This resource** — not "tasks in general" but *task 77* specifically, with its own owner.
- **Every request** — being allowed yesterday, or on the previous request, proves nothing about this one.
- **On the server** — the only place the user cannot tamper with.

Mental test: *"If I were logged in as Bob and replayed Alice's request, what would stop me?"* If "nothing", there is no authorization.

## Never trust the client

The TaskFlow web app only shows Alice a "Delete" button on her own tasks, and it never shows the "Admin" menu to normal users. That is good **user experience**, but it is **not security**.

Why: the client is fully under the user's control. Alice can open her browser's developer tools, copy any request as curl, edit the URL, method, headers and body, and send it directly:

```bash
curl -X DELETE https://api.taskflow.example/v1/tasks/77 \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

OWASP's rule: **developers must never rely on client-side access control checks.** Hidden buttons, disabled form fields, greyed-out menus and JavaScript `if (user.isAdmin)` checks are all decoration. The real decision must happen in server code that runs for every request, whatever sent it.

## Deny by default

**Deny by default** means: unless a rule explicitly grants access, the answer is no.

Compare two ways to write the same rule in pseudocode:

```text
# Allow by default (fragile)
if user.role == "banned": deny()
allow()

# Deny by default (safe)
if task.owner_id == current_user.id: allow()
if current_user.role == "admin": allow()
deny()
```

With allow-by-default, every case you *forgot* (a new role, a null owner, a new endpoint) is silently allowed. With deny-by-default, forgotten cases fail closed: an annoying but safe and visible error.

The same applies to whole endpoints. When a developer adds `DELETE /v1/tasks/{id}` next week, it should start out requiring a permission check, not start out open. OWASP: an attacker only needs to find **one** way in, so checks must be applied consistently and globally, not on "most" requests.

## Worked example: Alice opens her own task list

Suppose TaskFlow has added an endpoint to list a given user's tasks, `GET /v1/users/{id}/tasks`. Alice (user 123) is logged in, and her app requests her list:

```http
GET /v1/users/123/tasks HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMi...

HTTP/1.1 200 OK
Content-Type: application/json

[
  {"id": 42, "owner_id": 123, "title": "Buy milk", "done": false},
  {"id": 43, "owner_id": 123, "title": "Book dentist", "done": true}
]
```

Everything looks correct: the token is valid and Alice sees her two tasks. A tester clicking through the app finds no problem.

Here is the handler the developer wrote:

```text
handle GET /v1/users/{id}/tasks:
    user = authenticate(request)          # 401 if token missing/invalid
    tasks = db.query("SELECT * FROM tasks WHERE owner_id = $1", path.id)
    return 200, tasks
```

`authenticate` returns `user.id = 123`, but the query **never uses it**. It uses `path.id`, from the URL the client chose.

## Worked example: Alice changes 123 to 456

Alice is curious. She edits one number in the URL and sends the request again with **her own, perfectly valid token**:

```http
GET /v1/users/456/tasks HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMi...

HTTP/1.1 200 OK
Content-Type: application/json

[
  {"id": 77, "owner_id": 456, "title": "Prepare salary negotiation", "done": false},
  {"id": 78, "owner_id": 456, "title": "Doctor: test results", "done": false}
]
```

She receives **Bob's** private tasks. Step by step:

1. Authentication succeeded: the token really is Alice's (`sub: "123"`).
2. The handler ran `SELECT * FROM tasks WHERE owner_id = 456` because 456 was in the path.
3. Nothing compared "who is asking" (123) with "whose data this is" (456).

No password was stolen and no token forged. A loop from 1 to 100000 would download every user's tasks in minutes.

## Broken Object Level Authorization (BOLA / IDOR)

What happened to Bob has a name: **Broken Object Level Authorization (BOLA)**, **API1:2023** in the OWASP API Security Top 10. The older, equivalent name is **Insecure Direct Object Reference (IDOR)**.

Definition: an API accepts an **object identifier** from the client (path, query, headers or body) and acts on that object **without checking that the logged-in user may act on it**. Three ingredients: an object, a reference to it, and a missing check.

Real cases from OWASP's descriptions:

- A shop platform served `/shops/{shopName}/revenue_data.json`; an attacker listed shop names and scripted requests for thousands of stores' sales.
- A car maker's API unlocked doors and started engines by Vehicle Identification Number without checking the VIN belonged to the caller.
- A document service deleted any document by ID with no further permission check.

Consequences: data disclosure, loss or manipulation, sometimes account takeover. "Object level" = the check concerns one specific record.

## Misconception: hide or randomise the ID

A common first reaction: "Let's make IDs hard to find." Variants: don't show IDs in the UI, use UUIDs like `/v1/tasks/9f1c2e7a-4b3d-4e8a-a6f2-0c5d7b1e9a34` instead of `/v1/tasks/77`, or "encrypt" the ID in the URL. None of these is access control.

Why hiding fails: IDs **leak**. They appear in shared links, emails and notifications, browser history, server and proxy logs, screenshots posted in support chats, other API responses (a task's `owner_id`, a list of team members), and the app's own network traffic, which any user can inspect.

Why randomising is not enough: a UUID makes **guessing** much harder, so OWASP recommends random, unpredictable IDs as **defence in depth**. But the moment an attacker *obtains* the ID by any route above, the request succeeds, because the server still never asks "is this yours?". OWASP's IDOR cheat sheet is explicit: access control is crucial even with complex identifiers.

Rule: an ID says **which** object. Only a server-side permission check says **whether you may** touch it.

## Writing the check: load, then compare

Compare **the identity from the verified token** with **the owner stored in the database**, on every request. Approach one: load, then check.

```text
handle GET /v1/tasks/{id}:
    user = authenticate(request)               # from session/token, 401 if invalid
    task = db.query_one("SELECT * FROM tasks WHERE id = $1", path.id)
    if task is null:
        return 404
    if task.owner_id != user.id:               # the authorization check
        return 404                              # or 403, see below
    return 200, task
```

For the list endpoint, the resource is "user {id}'s task list", so compare the path with the authenticated identity:

```text
handle GET /v1/users/{id}/tasks:
    user = authenticate(request)
    if path.id != user.id and user.role != "admin":
        return 403
    return 200, db.query("SELECT * FROM tasks WHERE owner_id = $1", user.id)
```

`user.id` comes from the verified token or session record. Client-chosen values (`path.id`, body fields, an `X-User-Id` header) never decide the answer.

## Writing the check: scope the query

A second approach, often safer, puts the ownership condition **inside the database query**, so a lookup for someone else's task simply finds nothing:

```sql
SELECT id, title, done, due_date
FROM tasks
WHERE id = $1          -- task id from the URL
  AND owner_id = $2;   -- user id from the verified token
```

```text
handle GET /v1/tasks/{id}:
    user = authenticate(request)
    task = db.query_one(
        "SELECT * FROM tasks WHERE id = $1 AND owner_id = $2",
        path.id, user.id)
    if task is null:
        return 404       # doesn't exist OR isn't yours: same answer
    return 200, task
```

No separate `if` to forget, and the same pattern works for `UPDATE` and `DELETE`. OWASP calls this **scoping lookups to the current user**. The `$1`, `$2` parameters keep values separate from the SQL text, as in the queries-safety unit, so it is also injection-safe.

The flat `GET /v1/tasks` does the same: user from the token, no user ID in the URL to tamper with.

## Worked example: The fixed /users/456/tasks request

After the fix, Alice repeats the attack:

```http
GET /v1/users/456/tasks HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMi...

HTTP/1.1 403 Forbidden
Content-Type: application/json

{"error": "forbidden", "message": "You do not have access to this resource."}
```

And for a single task of Bob's, using the scoped query:

```http
GET /v1/tasks/77 HTTP/1.1
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMi...

HTTP/1.1 404 Not Found
Content-Type: application/json

{"error": "not_found", "message": "Task not found."}
```

Her own request `GET /v1/users/123/tasks` still returns `200 OK` with tasks 42 and 43. Step by step: authentication still says 123; the server compares 123 with 456 (or with task 77's `owner_id` 456); they differ; the request is refused **before** any of Bob's data is read or returned. The error body names no titles, owners or other details.

## 403 or 404 for someone else's resource

When Alice asks for Bob's task, two answers are both widely used and both acceptable:

- **403 Forbidden** — "I know who you are, the resource exists, and you may not access it." Re-authenticating will not help (that is the difference from 401). It is honest and helps debugging, but it confirms that task 77 exists.
- **404 Not Found** — "As far as you are concerned, there is no such task." MDN and OWASP both note that servers may return 404 instead of 403 to **hide the existence** of a resource from users without access. The scoped query produces this naturally.

Guidance for TaskFlow: use **404** for individual private objects (`/v1/tasks/77`), so outsiders cannot even map which IDs exist; use **403** when the resource's existence is no secret but the action is off-limits, such as a normal user calling an admin endpoint. Whatever you choose, be **consistent**, and never return 200 with an empty or partial body for a forbidden object.

Quick map: **401** = who are you? **403** = I know you; no. **404** = nothing here for you.

## Worked example: Bob's task via PUT, PATCH and DELETE

A developer fixes `GET /v1/tasks/{id}` but leaves the other methods as they were. Alice tries them on Bob's task 77:

```http
PATCH /v1/tasks/77 HTTP/1.1
Authorization: Bearer eyJ...(Alice)
Content-Type: application/json

{"done": true}

HTTP/1.1 200 OK
{"id": 77, "owner_id": 456, "title": "Prepare salary negotiation", "done": true}
```

```http
DELETE /v1/tasks/77 HTTP/1.1
Authorization: Bearer eyJ...(Alice)

HTTP/1.1 204 No Content
```

Bob's task was changed, then deleted. Reading was protected; writing was not, which is arguably worse. OWASP explicitly asks: can a user perform sensitive actions just by **changing the HTTP method**?

Fix: every method on `/v1/tasks/{id}` carries the ownership condition:

```sql
UPDATE tasks SET done = $1 WHERE id = $2 AND owner_id = $3;
DELETE FROM tasks WHERE id = $1 AND owner_id = $2;
```

If zero rows were affected, return 404. Alice's `DELETE /v1/tasks/77` now gets `404 Not Found` and Bob's task survives.

## Function-level authorization and roles

So far: **object-level** authorization — may this user touch *this record*? **Function-level** authorization asks: may this user call *this endpoint or operation at all*? Some functions are meant only for certain **roles**. TaskFlow, for example, has support staff with `role = "admin"` who can call `GET /v1/admin/users` (list every account) or `DELETE /v1/users/{id}`.

When a normal user can reach such a function, OWASP calls it **Broken Function Level Authorization (BFLA), API5:2023**. Examples: an unprotected `GET /api/admin/v1/users/all` leaking every user, and a user switching `GET /api/invites/{guid}` to `POST /api/invites/new` to invite themselves as admin.

Prevention, from OWASP:

- Deny all access by default; grant each function explicitly to specific roles.
- Don't rely on a URL being undocumented; attackers guess paths.
- Read the role from the **server's** records (or a server-signed token), never from a client field.

Object-level and function-level checks are independent: an endpoint can need both.

## Worked example: An admin-only endpoint

Alice (role `user`) notices the web app's JavaScript mentions `/v1/admin/users` and tries it. She even adds a header she hopes will help:

```http
GET /v1/admin/users HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJ...(Alice, sub 123)
X-Role: admin

HTTP/1.1 403 Forbidden
Content-Type: application/json

{"error": "forbidden", "message": "This action requires the admin role."}
```

Step by step on the server:

```text
handle GET /v1/admin/users:
    user = authenticate(request)            # 401 if no valid token
    role = db.query_one("SELECT role FROM users WHERE id = $1", user.id)
    if role != "admin":                     # deny by default
        return 403
    return 200, db.query("SELECT id, email, name FROM users")
```

The `X-Role` header is ignored: the role comes from the database row for user 123. 403 fits here because the endpoint's existence is no secret; the point is that Alice's role is not allowed. Note that even the admin response leaves out `password_hash`.

## Worked example: Alice sends owner_id in a PATCH

A subtler attack: Alice edits her **own** task, but adds a field the app never sends:

```http
PATCH /v1/tasks/42 HTTP/1.1
Authorization: Bearer eyJ...(Alice)
Content-Type: application/json

{"title": "Buy milk", "owner_id": 456}
```

If the server copies every body field into the row (**mass assignment**), task 42 now belongs to Bob. The ownership check passed for the row she addressed, but she rewrote the very field the check depends on.

Fix: decide on the server which fields a client may change, and ignore or reject everything else.

```text
allowed = {"title", "done", "due_date"}
if any key in body not in allowed:
    return 400 {"error": "unknown_or_readonly_field", "field": "owner_id"}
UPDATE tasks SET title = $1 WHERE id = $2 AND owner_id = $3
```

On `POST /v1/tasks`, likewise, set `owner_id` from the token, never from the body. Fields like `owner_id`, `id`, `role` and `created_at` are server-controlled.

## Common mistakes

- **Trusting a user ID the client sends.** `GET /v1/tasks?user_id=123` or a header `X-User-Id: 123`. *Why wrong:* the client can send 456. *Correct:* take the identity only from the verified session or token.
- **"It's authenticated, so it's safe."** *Why wrong:* BOLA happens to logged-in users with valid tokens. *Correct:* authentication and an ownership/role check, on each request.
- **Protecting GET only.** *Correct:* check `PUT`, `PATCH` and `DELETE` (and `POST` to nested resources) the same way.
- **Hiding buttons, IDs or admin URLs instead of checking.** *Correct:* UI hiding and random IDs are extras; the server check is the control.
- **Checking in some handlers only.** *Correct:* one shared check or scoped query everywhere, plus tests that log in as Bob and try Alice's endpoints; don't ship if they fail.
- **Leaky errors.** `403 {"message": "Task 77 belongs to bob@example.com"}`. *Correct:* say only that access is denied or the item is not found.

## Summary

- **Authorization** = on the server, on every request, may **this** user do **this** action on **this** resource? It comes after authentication.
- **Never trust the client**: hidden buttons and client-side checks are UX, not security. **Deny by default.**
- The demo story: Alice (123) changes `/v1/users/123/tasks` to `/v1/users/456/tasks` and gets Bob's tasks with her own valid token. That is **BOLA** (OWASP **API1:2023**), also called **IDOR**.
- Hiding or randomising IDs is not access control: IDs leak; UUIDs only make guessing harder.
- Fix: compare `owner_id` with the authenticated user's id, or scope the query: `WHERE id = $1 AND owner_id = $2`.
- Someone else's object: **404** hides existence, **403** says "not allowed"; both are used. **401** is for missing or invalid credentials.
- Check **every method**, not just GET.
- **Function-level** authorization (OWASP **API5:2023**): admin-only endpoints need role checks from server-side data.
- **Mass assignment**: never accept `owner_id`, `role` or `id` from a request body.

## Exercise: Investigate the task-sharing bug report
<!-- meta: kind=exercise, difficulty=beginner -->

A TaskFlow user reports: "I copied the link to my task, `https://app.taskflow.example/tasks/77`, into a group chat. Someone in the chat opened it while logged in as themselves and could edit and delete my task."

The API handler for task 77 currently looks like this:

```text
handle PATCH /v1/tasks/{id}:
    user = authenticate(request)
    db.execute("UPDATE tasks SET title = $1, done = $2, owner_id = $3 WHERE id = $4",
               body.title, body.done, body.owner_id, path.id)
    return 200
```

Explain (1) what kind of vulnerability this is and why the attacker did not need to guess anything, (2) at least two separate problems in this handler, and (3) the corrected handler logic, including which status code the attacker should now receive and why. Also say whether switching task IDs to UUIDs would have prevented this report.

## Exercise: Design the checks for a new admin feature
<!-- meta: kind=exercise, difficulty=beginner -->

TaskFlow wants two new endpoints:

- `GET /v1/admin/tasks` — support staff (users with role `admin`) can list every task in the system.
- `DELETE /v1/users/{id}` — a user may delete their own account; an admin may delete any account.

For each endpoint, describe the authorization check the server must perform, where the user's identity and role come from, and which status code each of these callers receives: (a) a request with no token, (b) Alice (role `user`) calling `GET /v1/admin/tasks`, (c) Alice calling `DELETE /v1/users/456`, (d) Alice calling `DELETE /v1/users/123`, (e) an admin calling `DELETE /v1/users/456`. Name the OWASP categories the checks protect against.
