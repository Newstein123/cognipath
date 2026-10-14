---
id: validation-errors
concept: Validation and Error Responses
capability: validation-errors
difficulty: beginner
prerequisites: [status-codes, endpoint-design]
source: "Adapted from MDN Web Docs — 400 Bad Request (https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/400) and 422 Unprocessable Content (https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/422), by Mozilla Contributors, CC BY-SA 2.5; OWASP Input Validation Cheat Sheet (https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html) and OWASP Error Handling Cheat Sheet (https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html), CC BY-SA 4.0. Reference (not copied): RFC 9457 Problem Details for HTTP APIs (https://www.rfc-editor.org/rfc/rfc9457), © IETF Trust."
---

# Validation and Error Responses

## Why this matters

Think of a post office counter. The clerk checks that your parcel has an address, a stamp, and is not too heavy before accepting it. If something is wrong, the clerk tells you exactly what to fix: "the postcode is missing". The clerk does not quietly guess a postcode, and does not hand you the sorting office's internal paperwork.

An API is that counter, and every request is a parcel from a stranger. Validation is the check; the error response is what the clerk says when refusing. Weak validation lets bad data into the database (a task with no title, a due date of "banana"). Weak error responses leave clients unable to fix mistakes, or tell attackers how the server is built. This unit covers both: what to check, and how to say "no" clearly and safely.

## Never trust input

**Input** is anything the client controls: the JSON body, the URL path (`/tasks/42`), query parameters (`?done=true`), and headers. The server must treat all of it as untrusted.

A common beginner thought is: "The TaskFlow web form already stops empty titles, so the server doesn't need to." That is wrong. Client-side checks (in the browser or mobile app) exist to **help honest users** with instant feedback. They do not **protect the server**, because anyone can skip the form entirely:

```bash
curl -X POST https://api.taskflow.example/v1/tasks \
  -H "Authorization: Bearer eyJhbGciOi..." \
  -H "Content-Type: application/json" \
  -d '{"title": ""}'
```

This request never touched the form. OWASP's rule: validate on the server even when the browser checks the same fields. Browser checks are for usability; server checks are for protection.

## What to validate for TaskFlow

Write the rules down per field before writing any code. For `POST /tasks`:

| Field | Rule |
|---|---|
| `title` | Required. A string. 1–200 characters after trimming spaces. |
| `due_date` | Optional. A string in `YYYY-MM-DD` form that is a real calendar date (no `2026-02-30`) and is in the future. |
| `done` | Optional, default `false`. Must be a JSON boolean: `true` or `false`, not `"yes"` or `1`. |
| anything else | Not allowed. `id`, `owner_id` and `created_at` are set by the server. |

OWASP distinguishes two levels. **Syntactic** validation checks type and format: is `due_date` shaped like a date? **Semantic** validation checks meaning: is that date in the future? Both are needed. A type check alone only proves a value is the right kind of thing, not that it is acceptable. Note also that `owner_id` is never read from the body; the server takes it from the authenticated user.

## Allowlist validation

There are two ways to write rules.

- **Denylist**: list what is forbidden ("reject titles containing `<script>`") and accept everything else. Attackers only need one input you didn't think of.
- **Allowlist**: list exactly what is permitted and reject everything else. OWASP recommends this: define what you accept instead of trying to recognise every malicious string.

For TaskFlow, the allowlist is the table from the previous section. The body may contain only `title`, `done` and `due_date`; each must have the stated type, length or range. A body with an extra `owner_id` field fails the allowlist, so a sneaky client cannot assign a task to someone else.

Allowlisting does not replace other defences. A valid title can still contain an apostrophe, so SQL must still use parameterised queries:

```sql
INSERT INTO tasks (owner_id, title, done, due_date)
VALUES ($1, $2, $3, $4) RETURNING id, created_at;
```

## Validate early, reject, don't silently fix

**Validate early** means checking the request at the edge of the server, before any business logic or database work. OWASP adds that size limits should apply even before the body is parsed, so a 500 MB body is refused without being read.

**Reject, don't silently fix** means that if input is wrong, the server says so and changes nothing. Tempting "helpful" fixes cause real bugs:

- Cutting a 250-character title down to 200: the user loses text without knowing.
- Turning `"done": "yes"` into `true`: what would `"maybe"` become?
- Replacing a past due date with today: the user's plan is now wrong.

A clear rejection lets the client fix the real problem. Also, reject the whole request, not part of it: OWASP advises against processing invalid requests partially. Either the task is created exactly as asked, or nothing is created and the client gets an explanation.

```text
parse body -> check allowlist -> check each field -> only then INSERT
```

## 400 vs 422

Two status codes cover most bad request bodies.

- **400 Bad Request**: the server cannot even understand the request. MDN gives malformed syntax as the classic cause, for example JSON with a trailing comma. The server cannot read the fields at all.
- **422 Unprocessable Content**: the request is well-formed (correct content type, valid JSON) but the values inside break the rules, such as an empty title or a past due date. The code began in WebDAV and is now part of core HTTP semantics (RFC 9110).

| Body sent | Problem | TaskFlow returns |
|---|---|---|
| `{"title": "Buy milk",}` | not valid JSON | 400 |
| `{"title": ""}` | valid JSON, invalid value | 422 |

Be aware that many well-known APIs use 400 for both cases, and that is also acceptable. What matters is that the API documents its choice and is consistent. In both cases, MDN notes that repeating the identical request will fail again: the client must change it first.

## Worked example: a missing task vs an empty list

**Step 1. A specific item.** Alice asks for task 99999, which does not exist. **404 Not Found** means "the thing you named does not exist":

```http
GET /v1/tasks/99999 HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...

HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{"type": "https://api.taskflow.example/problems/not-found",
 "title": "Resource not found", "status": 404,
 "detail": "No task with id 99999 exists."}
```

**Step 2. A collection.** `GET /tasks?done=true` asks "list my finished tasks". If Alice has none, the collection still exists; it is just empty:

```http
HTTP/1.1 200 OK
Content-Type: application/json

[]
```

**Step 3. The rule.** A missing *item* is 404; a filter that matches nothing is 200 with `[]`. A 404 there would make clients treat "no results" as an error.

## 409 Conflict

**409 Conflict** means the request is valid on its own but clashes with the current state of the server. Nothing is wrong with the fields; the problem is what already exists.

Example: suppose TaskFlow adds a sign-up endpoint and `bob@example.com` is already registered (user 456). A new request tries to register the same email:

```http
POST /v1/users HTTP/1.1
Host: api.taskflow.example
Content-Type: application/json

{"email": "bob@example.com", "name": "Robert", "password": "..."}

HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{"type": "https://api.taskflow.example/problems/email-taken",
 "title": "Email already registered", "status": 409,
 "detail": "An account with this email already exists."}
```

Compare with 422: `"email": "not-an-email"` is invalid by itself (422). `"bob@example.com"` is perfectly valid but conflicts with an existing row (409). In the database, a `UNIQUE` constraint on `users.email` is the final safety net that catches this.

## 405, 413 and 415

Three more codes appear at the edge of the server.

**405 Method Not Allowed**: the URL exists but does not support that method. TaskFlow has no "delete all tasks" operation, so `DELETE /tasks` gets 405. The response must include an `Allow` header listing the methods that do work:

```http
HTTP/1.1 405 Method Not Allowed
Allow: GET, POST
```

**413 Content Too Large**: the body is bigger than the server accepts. TaskFlow might cap bodies at 100 KB; a task never needs more. This is "validate early" in action, refused before parsing.

**415 Unsupported Media Type**: the body's format is not one the server handles. TaskFlow accepts `Content-Type: application/json`; a request sent as `text/plain` or `application/xml` gets 415.

None of these depend on the field values, so the server can check them before looking inside the body.

## 500 errors: log inside, say little outside

**500 Internal Server Error** means the server failed, not the client. Example: the database is down when Alice creates a task. The client did nothing wrong, so a 4xx would be a lie.

OWASP's guidance: catch unexpected errors in one global handler, log the full details on the server, and return a generic message. Never send this to the client:

```text
ERROR: relation "tasks" does not exist at character 13
  at PgPool.query (/srv/taskflow/db.js:41)
```

That leaks the database type, table names and file paths, all useful to an attacker. Instead:

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json

{"type": "about:blank", "title": "Internal Server Error",
 "status": 500, "detail": "Something went wrong on our side. Please try again later.",
 "instance": "/errors/7f3a9c"}
```

The server log stores the stack trace under reference `7f3a9c`, so support staff can find it if Alice reports the error. OWASP also advises monitoring 5xx rates: a spike can mean some input is crashing the server.

## A consistent error body: Problem Details

If every endpoint invents its own error shape, clients need special code for each. **RFC 9457, Problem Details for HTTP APIs**, defines one standard JSON shape, served with `Content-Type: application/problem+json`. Its members:

- `type`: a URI identifying the *kind* of problem; clients act on this. Omitted, it means `about:blank` (a generic problem described by the status code).
- `title`: a short human summary of that kind of problem; the same every time it occurs.
- `status`: the HTTP status code, repeated; it must match the real status line.
- `detail`: a human explanation of *this* occurrence, aimed at helping the client fix it. Clients should not parse it.
- `instance`: a URI identifying this specific occurrence, such as an error reference.

A problem type may add **extension members**. RFC 9457's validation example adds an `errors` array, one entry per broken field, each with a `detail` and a JSON Pointer `pointer` such as `#/title`. Clients ignore extensions they don't know. TaskFlow uses this shape for all 4xx and 5xx responses.

## Messages that help without leaking

A good error message tells an honest client what to change, and tells an attacker nothing useful about the internals.

| Helpful and safe | Leaky or useless |
|---|---|
| "title must be 1–200 characters; got 250." | "Error." |
| "due_date must be a future date in YYYY-MM-DD form." | "Invalid input." |
| "Unknown field: owner_id." | "column owner_id violates foreign key constraint fk_users" |
| "No task with id 99999 exists." | "SELECT * FROM tasks WHERE id=99999 returned 0 rows" |

Guidelines:

- Name the field and the rule; give the allowed range or format.
- Never include SQL, stack traces, library versions, file paths or server names. RFC 9457's security section also warns to vet what problem details reveal.
- Be careful about echoing input back; it can end up displayed in a web page.
- For login, keep messages vague on purpose ("email or password is incorrect") so attackers cannot discover which emails are registered.

## Worked example: malformed JSON

Alice's app has a bug and sends a body with a trailing comma.

```http
POST /v1/tasks HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...
Content-Type: application/json

{"title": "Buy milk", "done": false,}
```

**Step 1. Can the server parse it?** No. A trailing comma is not legal JSON, so the server cannot know which fields were sent. Field rules cannot even run.

**Step 2. Choose the status.** The body is malformed, so 400 Bad Request.

**Step 3. Write the body.**

```http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{"type": "https://api.taskflow.example/problems/malformed-json",
 "title": "Request body is not valid JSON",
 "status": 400,
 "detail": "The body could not be parsed as JSON near character 36. Check for trailing commas or missing quotes."}
```

**Step 4. Side effects.** None. No row is inserted. Note the message gives a position and a hint but does not quote the parser's internal exception text.

## Worked example: invalid field values

Now the JSON is valid, but two values break the rules (today is 2026-10-14):

```json
{"title": "", "due_date": "2025-01-10", "done": false}
```

**Step 1. Parse.** Succeeds, so this is not a 400.
**Step 2. Allowlist.** Only allowed fields are present. Good.
**Step 3. Field rules.** `title` is empty (needs 1–200 chars). `due_date` is in the past. `done` is fine.
**Step 4. Respond with every field error at once**, so the client fixes both in one go:

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{"type": "https://api.taskflow.example/problems/validation-error",
 "title": "Your request is not valid",
 "status": 422,
 "detail": "2 fields failed validation.",
 "errors": [
   {"pointer": "#/title", "detail": "must be 1-200 characters"},
   {"pointer": "#/due_date", "detail": "must be a future date"}
 ]}
```

The `errors` array is the RFC 9457 extension pattern. An API that uses 400 for all validation would send the same body with status 400.

## Worked example: an unknown field

Third problem: Alice's request is valid JSON with a good title, but includes a field she must not set.

```json
{"title": "Pay rent", "owner_id": 456}
```

**Step 1. Parse.** Fine.
**Step 2. Allowlist.** `owner_id` is not on the list for `POST /tasks`. If the server copied the body straight into the database, Alice could create tasks in Bob's account (a "mass assignment" bug).
**Step 3. Decide.** Some APIs silently ignore unknown fields. TaskFlow rejects them, so mistakes and tampering are visible:

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{"type": "https://api.taskflow.example/problems/validation-error",
 "title": "Your request is not valid",
 "status": 422,
 "detail": "The body contains fields that are not allowed.",
 "errors": [{"pointer": "#/owner_id", "detail": "unknown or read-only field"}]}
```

**Step 4. Remember the rule.** Even with a correct body, `owner_id` is always taken from the token (Alice, 123), never from the client.

## Common mistakes

**Mistake: validating only in the browser.** Why wrong: curl or a script bypasses the form. Correct: validate on the server; keep browser checks for usability.

**Mistake: returning 200 with `{"error": "title missing"}`.** Why wrong: clients, caches and monitoring read the status code and think it succeeded. Correct: 422 (or 400) with a Problem Details body.

**Mistake: returning 500 for bad input.** Why wrong: 5xx says the server is broken; it hides client mistakes and triggers false alarms. Correct: input problems are 4xx. A 500 should mean an actual bug or outage.

**Mistake: leaking internals.** Why wrong: a stack trace or SQL message maps your system for attackers. Correct: log details server-side, return a generic message with a reference id.

**Mistake: reporting only the first error.** Why wrong: the client fixes one field, resubmits, and hits the next. Correct: list all field errors in `errors`.

## Summary

- All input (body, path, query, headers) is untrusted. Client-side checks help users; only server-side checks protect the server.
- Write per-field rules (required, type, length, format, range) and validate with an **allowlist**; reject unknown fields such as `owner_id`.
- Validate early, reject the whole request, and never silently "fix" data.
- 400 = malformed (cannot parse); 422 = well-formed but invalid. Many APIs use 400 for both; be consistent and document it.
- 404 = a named item is missing; an empty collection is 200 with `[]`.
- 409 = valid request that clashes with current state. 405 needs an `Allow` header; 413 = body too large; 415 = wrong content type.
- 500 = the server's fault: log details internally, return a generic message.
- Use RFC 9457 Problem Details (`type`, `title`, `status`, `detail`, `instance`) with an `errors` extension for field-level problems.
- Messages should name the field and rule, never SQL, stack traces or paths.

## Exercise: Respond to three bad requests
<!-- meta: kind=exercise, difficulty=beginner -->

Bob (user 456) sends three separate requests to TaskFlow. For each, give the status code you would return, explain why in one or two sentences, and write the Problem Details response body (including an `errors` array where appropriate). Assume today is 2026-10-14.

1. `POST /tasks` with body `{"title": "Call the bank", "done": "no"}`
2. `POST /tasks` with body `{"title": "Call the bank"` (the closing brace is missing)
3. `POST /tasks` with a title of 250 characters and `"due_date": "2026-13-01"`

Finally, a teammate suggests fixing case 3 by cutting the title to 200 characters and ignoring the bad date. Explain why that is a bad idea.

## Exercise: Review an error-handling design
<!-- meta: kind=exercise, difficulty=beginner -->

A teammate's TaskFlow pull request behaves as follows:

- `GET /tasks?done=true` returns `404 Not Found` when Alice has no finished tasks.
- When the database connection fails, the API returns `400 Bad Request` with the body `{"error": "connection refused to postgres://10.0.3.7:5432/taskflow"}`.
- `DELETE /tasks` returns `404 Not Found`.
- Validation errors return `200 OK` with `{"ok": false, "msg": "bad title"}`.

For each behaviour, say what is wrong, give the correct status code (and any required header), and describe what the response body should look like instead. Explain one security risk in this design.
