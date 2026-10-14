---
id: http-requests
concept: HTTP Requests and Methods
capability: http-requests
difficulty: beginner
prerequisites: [web-basics]
source: "Adapted from MDN Web Docs — HTTP messages (https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Messages), HTTP request methods (https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Methods), Idempotent glossary (https://developer.mozilla.org/en-US/docs/Glossary/Idempotent), Safe (HTTP Methods) glossary (https://developer.mozilla.org/en-US/docs/Glossary/Safe/HTTP), by Mozilla Contributors, CC BY-SA 2.5"
---

# HTTP Requests and Methods

## Why this matters

In the last unit we saw that a client sends a request and a server sends a response. Now we open the envelope and read the letter.

Think of filling in a form at the post office. There are boxes for *what you want done* (send, collect, return), *where* (the address), *special instructions* (fragile, signature required) and the *parcel itself*. Clerks process thousands of forms a day because every form has the same layout.

An HTTP request is that form. The **method** says what to do, the **path** says to which resource, the **headers** carry instructions, and the **body** carries the parcel. If you can read and write these messages by hand, you can debug any API, understand any framework, and design TaskFlow's endpoints so that clients — and retries — behave predictably.

## Anatomy of a request

An HTTP/1.1 request is plain text with up to four parts:

```http
POST /v1/tasks HTTP/1.1
Host: api.taskflow.example
Content-Type: application/json
Authorization: Bearer eyJhbGciOi...

{"title": "Buy milk", "due_date": "2026-10-20"}
```

1. **Request line**: `<method> <target> <version>`.
   - Method `POST` — the action.
   - Target `/v1/tasks` — the path, plus an optional query string. No scheme or host.
   - Version `HTTP/1.1`.
2. **Headers**: one `Name: value` per line. Names are case-insensitive.
3. **A blank line** marking the end of the headers.
4. **Optional body**: the data being sent. Normally only `POST`, `PUT` and `PATCH` carry one.

HTTP/2 and HTTP/3 send the same information as binary frames (with pseudo-headers like `:method` and `:path`), but the meaning is identical, so we write messages in the readable 1.1 form.

## Anatomy of a response

A response has the same shape, but starts with a **status line**:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /v1/tasks/42

{"id": 42, "owner_id": 123, "title": "Buy milk", "done": false,
 "due_date": "2026-10-20", "created_at": "2026-10-14T09:30:00Z"}
```

1. **Status line**: `<version> <status code> <reason phrase>`.
   - `201` — a number the client's code checks.
   - `Created` — human-readable text; programs should rely on the number.
2. **Headers**: e.g. `Content-Type` (format of the body), `Location` (where the new resource lives), `Date`, `Cache-Control`.
3. **Blank line.**
4. **Optional body**: the resource or an error message. Some responses, such as `204 No Content`, deliberately have no body.

Request and response share the header-plus-body format, so the same skills apply to both directions.

## The main methods at a glance

The **method** (sometimes called the "verb") tells the server what kind of action you intend. Here is what each one means for TaskFlow:

| Method | Meaning | TaskFlow example |
|---|---|---|
| `GET` | Fetch a representation of a resource | `GET /tasks` — list Alice's tasks; `GET /tasks/42` — read one |
| `POST` | Submit data, usually creating something new | `POST /tasks` — create a task; `POST /login` — sign in |
| `PUT` | Replace the resource entirely with the body | `PUT /tasks/42` — overwrite task 42 |
| `PATCH` | Apply a partial change | `PATCH /tasks/42` with `{"done": true}` |
| `DELETE` | Remove the resource | `DELETE /tasks/42` |
| `HEAD` | Like `GET`, but headers only, no body | Check that task 42 exists |
| `OPTIONS` | Ask which methods/options are allowed | `OPTIONS /tasks/42` |

The path names the *thing*; the method names the *action*. That is why `/tasks/42` can be read, replaced, patched or deleted — same path, different methods.

## PUT versus PATCH

Both change an existing task, but in different ways.

**`PUT` replaces.** The body is the *complete* new version of the resource. Anything you leave out is not kept.

```http
PUT /v1/tasks/42 HTTP/1.1
Content-Type: application/json

{"title": "Buy oat milk", "done": false, "due_date": "2026-10-21"}
```

**`PATCH` modifies.** The body describes only the *changes*; other fields stay as they are.

```http
PATCH /v1/tasks/42 HTTP/1.1
Content-Type: application/json

{"done": true}
```

Rule of thumb: if the client has the whole object and wants to save it, use `PUT`. If it wants to flip one field — tick a checkbox, rename a task — use `PATCH`. Sending `PUT` with only `{"done": true}` could wipe the title and due date, because PUT means "this is the entire task now".

Fields the server controls, like `id`, `owner_id` and `created_at`, are never taken from the client body in either case.

## HEAD and OPTIONS

Two less common methods are worth recognising.

**`HEAD`** asks for exactly the response a `GET` would produce, **minus the body**. It is useful for checking whether something exists or how large it is without downloading it.

```http
HEAD /v1/tasks/42 HTTP/1.1
Host: api.taskflow.example

HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 87
```

**`OPTIONS`** asks the server which communication options apply to a resource. A typical answer lists allowed methods in an `Allow` header:

```http
OPTIONS /v1/tasks/42 HTTP/1.1
Host: api.taskflow.example

HTTP/1.1 204 No Content
Allow: GET, PUT, PATCH, DELETE, HEAD, OPTIONS
```

Browsers send `OPTIONS` automatically as a "preflight" before some cross-site requests, so you will see it in server logs even if your own code never sends it. (Other methods such as `CONNECT` and `TRACE` exist but are rarely used in API work.)

## Safe and idempotent methods

Two properties describe how "risky" a method is.

A method is **safe** if it is **read-only**: the client is not asking the server to change anything. The server may still write logs, but no tasks change.

A method is **idempotent** if sending the same request **once or many times has the same intended effect** on the server.

| Method | Safe? | Idempotent? |
|---|---|---|
| `GET` | Yes | Yes |
| `HEAD` | Yes | Yes |
| `OPTIONS` | Yes | Yes |
| `PUT` | No | Yes |
| `DELETE` | No | Yes |
| `POST` | No | No |
| `PATCH` | No | Not guaranteed |

Every safe method is idempotent, but not the other way round. `PUT /tasks/42` changes data (unsafe), yet doing it twice leaves task 42 in the same final state (idempotent). `DELETE` is the same: after the first call the task is gone; later calls change nothing more.

These are **promises the server must keep**. Web servers cannot enforce them — your application code must, e.g. by never letting a `GET` modify data.

## Why idempotency matters for retries

Networks fail. Alice's phone sends a request in a lift, the signal drops, and the app never sees a response. Did the server receive it? The app cannot know.

The safe move depends on the method:

- **Idempotent request (`GET`, `PUT`, `DELETE`)** — just send it again. If the first copy arrived, the second has no extra effect. Many HTTP libraries and proxies retry these automatically.
- **Non-idempotent request (`POST`)** — retrying is risky. If the first `POST /tasks` succeeded, the retry creates a **second identical task**. With payments, it could charge twice.

Idempotency is about the *effect*, not the response. Deleting task 42 twice may return `204` then `404`, but the server ends up in the same state either way.

Because of this, careful APIs give POST a way to be retried safely, for example an `Idempotency-Key` header: the client attaches a unique key, and the server ignores a second request carrying the same key. We return to this pattern in later units.

## Query strings versus request bodies

A request can carry extra data in two places.

**Query string** — part of the URL, after `?`:

```http
GET /v1/tasks?done=false&sort=due_date HTTP/1.1
```

Use it for **options about what to fetch**: filtering, sorting, searching, paging. It is visible in logs and browser history, can be bookmarked, and has practical length limits.

**Body** — after the headers, described by `Content-Type`:

```http
POST /v1/tasks HTTP/1.1
Content-Type: application/json

{"title": "Buy milk", "due_date": "2026-10-20"}
```

Use it for **the data you are sending to be stored or processed**: a new task, an update, login credentials.

Guidelines:

- `GET` requests should not rely on a body; put options in the query string.
- Never put passwords or tokens in the query string — URLs end up in server logs. `POST /login` sends credentials in the body.

## Common request headers

Headers are labelled extra information. Four you will use constantly:

- **`Host`** — which site the request is for, e.g. `Host: api.taskflow.example`. Required in HTTP/1.1, because one IP address can host many sites and the request line only contains the path.
- **`Content-Type`** — the format of the **body you are sending**, e.g. `Content-Type: application/json`. Without it, the server may not know how to read your JSON.
- **`Accept`** — the format you **want back**, e.g. `Accept: application/json`. The server uses it to choose a representation.
- **`Authorization`** — your credentials, e.g. `Authorization: Bearer eyJhbGciOi...`. Because HTTP is stateless, it goes on every request that needs a logged-in user.

Easy way to remember the pair: `Content-Type` describes what *I am giving you*; `Accept` describes what *I would like to receive*. Others you will meet include `User-Agent`, `Content-Length` and `Cache-Control`.

## Sending a request with curl

**curl** is a command-line tool that sends HTTP requests and prints the response. It is the quickest way to test an API without writing an app.

```bash
# GET (the default method). -i shows the status line and headers too
curl -i https://api.taskflow.example/v1/tasks \
  -H "Authorization: Bearer eyJhbGciOi..."

# POST with a JSON body
curl -i -X POST https://api.taskflow.example/v1/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOi..." \
  -d '{"title": "Buy milk", "due_date": "2026-10-20"}'
```

Key options:

- `-X METHOD` — choose the method (`PATCH`, `DELETE`, ...). `-d` alone implies `POST`.
- `-H "Name: value"` — add a header.
- `-d 'data'` — send a body.
- `-i` — include response headers; `-I` — send a `HEAD` request.
- `-v` — verbose: print the exact request curl sent, great for debugging.

curl fills in `Host` from the URL automatically.

## Worked example: Creating a task with POST

**Task.** Alice (user 123) creates "Pay rent", due 1 November. Write the request and the response.

**Step 1 — choose the method.** Creating a new resource in a collection: `POST /tasks`.

**Step 2 — write the request.**

```http
POST /v1/tasks HTTP/1.1
Host: api.taskflow.example
Content-Type: application/json
Accept: application/json
Authorization: Bearer eyJhbGciOi...

{"title": "Pay rent", "due_date": "2026-11-01"}
```

Note: no `id`, `owner_id` or `done`. The server assigns the id, takes the owner from the token, and defaults `done` to false.

**Step 3 — server work.**

```sql
INSERT INTO tasks (owner_id, title, done, due_date, created_at)
VALUES (123, 'Pay rent', false, '2026-11-01', now()) RETURNING id;
```

**Step 4 — response.**

```http
HTTP/1.1 201 Created
Location: /v1/tasks/57
Content-Type: application/json

{"id": 57, "owner_id": 123, "title": "Pay rent", "done": false,
 "due_date": "2026-11-01", "created_at": "2026-10-14T10:05:00Z"}
```

## Worked example: Ticking a task as done

**Task.** Bob (user 456) ticks task 88 ("Book flights") as done. Its current state is:

```json
{"id": 88, "owner_id": 456, "title": "Book flights", "done": false, "due_date": "2026-12-01"}
```

**Option A — PATCH (recommended).** Send only the change:

```http
PATCH /v1/tasks/88 HTTP/1.1
Host: api.taskflow.example
Content-Type: application/json
Authorization: Bearer eyJhbGciOi...

{"done": true}
```

Server: `UPDATE tasks SET done = true WHERE id = 88 AND owner_id = 456;` Title and due date are untouched.

**Option B — PUT.** The app must send the whole task:

```http
PUT /v1/tasks/88 HTTP/1.1
Content-Type: application/json

{"title": "Book flights", "done": true, "due_date": "2026-12-01"}
```

**Trap.** If the app sends `PUT` with just `{"done": true}`, a correct server treats that as the complete task, so the title and due date are lost or the request is rejected. For a checkbox, PATCH is the natural fit.

## Worked example: The double-tap retry problem

**Situation.** Alice taps "Add task" for "Buy milk". The app sends `POST /v1/tasks`. The server inserts task 60, but the response is lost when her signal drops. The app times out and retries.

```http
POST /v1/tasks HTTP/1.1          -> server creates task 60 (response lost)
POST /v1/tasks HTTP/1.1          -> server creates task 61
```

Alice now has **two** "Buy milk" tasks. POST is not idempotent: each call creates another resource.

**Compare with DELETE.** If the app had been deleting task 42:

```http
DELETE /v1/tasks/42 HTTP/1.1     -> 204 No Content (deleted)
DELETE /v1/tasks/42 HTTP/1.1     -> 404 Not Found (already gone)
```

Different responses, same final state: task 42 does not exist. Retrying was harmless.

**Fix for POST.** The app generates a unique key once per tap and resends it on retries:

```http
POST /v1/tasks HTTP/1.1
Idempotency-Key: 7f3c9a2e-...
```

The server stores the key with task 60; a second request with the same key returns task 60 instead of inserting task 61.

## Worked example: Filtering tasks with a query string

**Task.** Alice's "Today" screen shows her unfinished tasks, soonest due first, 20 at a time.

**Step 1 — method.** Reading only, so `GET`: safe and idempotent.

**Step 2 — where do the options go?** They describe *which* tasks to return, so they belong in the query string, not a body.

```http
GET /v1/tasks?done=false&sort=due_date&limit=20 HTTP/1.1
Host: api.taskflow.example
Accept: application/json
Authorization: Bearer eyJhbGciOi...
```

**Step 3 — server work.** Each parameter becomes part of the query, always scoped to the caller:

```sql
SELECT id, title, done, due_date FROM tasks
WHERE owner_id = 123 AND done = false
ORDER BY due_date LIMIT 20;
```

**Step 4 — same thing in curl.** Quote the URL so the shell does not treat `&` specially:

```bash
curl -i "https://api.taskflow.example/v1/tasks?done=false&sort=due_date&limit=20" \
  -H "Authorization: Bearer eyJhbGciOi..."
```

## Worked example: Debugging a request with curl

**Situation.** A student's request to create a task returns `415 Unsupported Media Type`. They ran:

```bash
curl -i -X POST https://api.taskflow.example/v1/tasks \
  -H "Authorization: Bearer eyJhbGciOi..." \
  -d '{"title": "Water plants"}'
```

**Step 1 — look at what was really sent.** Adding `-v` prints the request:

```http
> POST /v1/tasks HTTP/1.1
> Host: api.taskflow.example
> Content-Type: application/x-www-form-urlencoded
```

**Step 2 — diagnose.** With `-d` and no `Content-Type`, curl labels the body as form data. The server expected JSON, so it refused to parse it.

**Step 3 — fix.** Declare the body format:

```bash
curl -i -X POST https://api.taskflow.example/v1/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOi..." \
  -d '{"title": "Water plants"}'
```

Response: `201 Created`. Lesson: `Content-Type` must describe the body you actually send.

## Common mistakes

**Using GET to change data**, e.g. `GET /tasks/42/delete`. Why it's wrong: GET must be safe; browsers prefetch links and crawlers follow them, which could delete tasks. Correct: `DELETE /v1/tasks/42`.

**Using PUT for a partial update**, sending only `{"done": true}`. Why it's wrong: PUT replaces the whole resource, so other fields may be lost. Correct: `PATCH` with `{"done": true}`, or `PUT` with every field.

**Blindly retrying POST.** Why it's wrong: POST is not idempotent, so a retry can create a duplicate task. Correct: retry only idempotent methods automatically, or use an `Idempotency-Key`.

**Mixing up `Content-Type` and `Accept`.** Why it's wrong: `Accept` does not describe your body. Correct: `Content-Type: application/json` for the body you send; `Accept: application/json` for what you want back.

**Putting secrets in the query string**, e.g. `/login?password=...`. Why it's wrong: URLs are logged. Correct: `POST /login` with credentials in the body.

## Summary

- A **request** = request line (method, path + query, version) + headers + blank line + optional body.
- A **response** = status line (version, status code, reason) + headers + blank line + optional body.
- **GET** reads, **POST** creates/submits, **PUT** replaces, **PATCH** partially updates, **DELETE** removes; **HEAD** is GET without a body; **OPTIONS** asks what is allowed.
- **Safe** = read-only (GET, HEAD, OPTIONS). **Idempotent** = repeating has the same effect (safe methods plus PUT and DELETE). POST is neither; PATCH is not guaranteed idempotent.
- Idempotent requests can be retried; retrying POST can create duplicates.
- **Query strings** carry options about what to fetch; **bodies** carry the data being sent.
- Key headers: `Host`, `Content-Type`, `Accept`, `Authorization`.
- **curl** sends requests from the terminal: `-X`, `-H`, `-d`, `-i`, `-v`.

## Exercise: Pick the method for each action

<!-- meta: kind=exercise, difficulty=beginner -->

For each TaskFlow action below, write the method and path you would use, say whether the request has a body (and what goes in it), and state whether the request is safe and whether it is idempotent:

1. Bob views all of his unfinished tasks.
2. Bob adds a new task "Renew passport" due 2026-11-30.
3. Bob changes only the due date of task 91 to 2026-12-05.
4. Bob removes task 91.

Then explain what could go wrong if the app automatically retried request 2 after a network timeout, and why automatically retrying request 4 is harmless.

## Exercise: Write the raw request and fix the bug

<!-- meta: kind=exercise, difficulty=beginner -->

Alice wants to rename task 42 to "Buy oat milk" without changing anything else.

1. Write the full raw HTTP/1.1 request her app should send: request line, the headers it needs (Host, Content-Type, Authorization) and the body.
2. Write the equivalent curl command.
3. A teammate instead sends `PUT /v1/tasks/42` with the body `{"title": "Buy oat milk"}`, and afterwards the task's due date is gone. Explain why this happened and give two ways to fix it.
