---
id: validation-errors
concept: Validation and Error Handling
capability: validation-errors
difficulty: beginner
prerequisites: [rest-api]
source: "RFC 9110 HTTP Semantics — status codes (https://www.rfc-editor.org/rfc/rfc9110); RFC 9457 Problem Details for HTTP APIs (https://www.rfc-editor.org/rfc/rfc9457); OWASP Input Validation Cheat Sheet (https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html)"
---

# Validation and Error Handling

## Never trust input

Everything that arrives in a request comes from the client: the body, the path, query
parameters and headers. The server cannot control any of it. A person can mistype, a
buggy app can send the wrong shape, and an attacker can send whatever they like using a
tool such as curl, skipping your website entirely.

So the rule is simple: treat all input as untrusted until the server has checked it.

Checks in the browser or mobile app (client-side validation) are still useful. They give
the user instant feedback, like "please enter your email", without a round trip. But
they are a convenience, not protection, because anyone can bypass the client and call
the API directly. The server must repeat every check that matters.

## What to validate

For each field the server accepts, decide what "valid" means and check it:

- **Required fields** — is it present at all? A task without a title makes no sense.
- **Type** — is `title` a string, is `priority` a number, is `done` a true/false value?
- **Length and range** — a title of 1–200 characters; an age of 0–150, not -5.
- **Format** — does an email look like an email, is a date a real date?
- **Allowed values** — `status` must be one of `"todo"`, `"doing"` or `"done"`.

Example rules for creating a task:

```
title     required, string, 1-200 characters
status    optional, one of "todo" | "doing" | "done", default "todo"
due_date  optional, a valid date such as "2026-03-01"
```

Where possible, describe what is allowed (an allowlist) rather than trying to list every
bad input. OWASP recommends allowlists because the list of bad inputs is never complete.

## Validate early on the server and reject bad input

Run validation at the start of the request handler, before you save anything or call
other services. If the input is invalid, stop and return an error response. Nothing
should be half-written to the database.

Do not silently "fix" bad input. If a client sends `"age": -5`, quietly changing it to
`0`, or cutting a 500-character title down to 200, hides a bug in the client and stores
data the user never meant. Reject it and say what is wrong, so the client can correct it.

Light, predictable normalisation is fine when it is part of your documented rules, for
example trimming spaces around a title before checking its length. The difference is
that the rule is published and consistent, not a guess about what the client meant.

## 400 Bad Request vs 422 Unprocessable Content

Two status codes are used for bad input, and they mean slightly different things.

**400 Bad Request** means the server could not process the request because it is
malformed. A classic case is a body that is not valid JSON at all:

```
{"title": "Buy milk",
```

**422 Unprocessable Content** means the request is well-formed — the JSON parses fine —
but the values break the rules. For example `{"title": ""}` is valid JSON, but an empty
title is not allowed.

In practice, many APIs use 400 for both cases, and that is a common, acceptable choice.
Other APIs (and frameworks such as FastAPI) use 422 for validation failures. Either way,
the key points are: use a 4xx code, because the client must change the request, and be
consistent across your whole API.

## 404, 409 and 405

A few other 4xx codes cover common situations.

**404 Not Found** — the resource does not exist. `GET /tasks/999` when there is no task
999 returns 404. It is also correct for `PATCH` or `DELETE` on a task that does not exist.

**409 Conflict** — the request conflicts with the current state of the resource. A common
example is trying to create something that must be unique and already exists, such as
signing up with a username that is already taken.

**405 Method Not Allowed** — the URL exists but does not support that method, such as
`DELETE /tasks` when the API does not allow deleting the whole collection. A 405 response
must include an `Allow` header listing the methods that are supported, for example
`Allow: GET, POST`.

## 500 errors: unexpected failures

**500 Internal Server Error** means something went wrong on the server that was not the
client's fault: the database is down, a bug threw an exception, a dependency crashed. The
client did nothing wrong, so this belongs in the 5xx range, not 4xx.

When this happens, never send the internal details to the client. A stack trace, an SQL
error message, file paths or library versions tell an attacker how your system is built
and help them find weaknesses. They also mean nothing to a normal user.

Instead:

- **Log** the full error on the server, with enough detail to debug it later.
- **Return** a short, generic message, for example "An unexpected error occurred".
- Optionally include a request or error ID, so a user can report it and you can find the
  matching log entry.

## A good error response body

Error bodies should have one consistent JSON shape across the whole API, so clients can
handle every error with the same code. RFC 9457, "Problem Details for HTTP APIs", defines
a standard shape, sent with the content type `application/problem+json`:

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Your request contains invalid fields",
  "status": 422,
  "detail": "2 fields failed validation.",
  "errors": [
    { "field": "title", "message": "Title is required." },
    { "field": "status", "message": "Must be one of: todo, doing, done." }
  ]
}
```

`type` is a URI identifying the kind of problem, `title` a short summary, `status` the
HTTP status code, and `detail` an explanation of this specific occurrence. RFC 9457 also
allows extra members, so a list of field-level errors like `errors` is a common addition.

## Error messages that help without leaking

A good error message tells the client exactly what to fix: which field is wrong and why.
"Title must be 1–200 characters" is useful. "Invalid input" or `{"error": "bad"}` is not.

But helpful must not become revealing. Some details help attackers more than users:

- **Login:** say "Invalid email or password" whether the email is unknown or the password
  is wrong. Saying "No account with this email" lets anyone discover who has an account.
- **Internals:** no stack traces, SQL, table names or server paths in messages.
- **Echoing input:** be careful repeating the client's raw input back, especially into
  web pages, where it could be used to inject scripts.

A good test: would this message help a legitimate user fix their request, without
teaching an attacker anything about your system or your users?

## Missing resources vs empty results

Two situations look similar but get different answers.

**A specific resource that does not exist.** `GET /tasks/42` when there is no task 42 is
an error: the client asked for one thing and it is not there. Return **404 Not Found**.

**A collection that happens to be empty.** `GET /tasks` when the user has no tasks yet is
not an error. The collection `/tasks` exists; it just has nothing in it. Return
**200 OK** with an empty list:

```json
{ "items": [] }
```

The same goes for a search or filter with no matches, such as
`GET /tasks?status=done`: 200 with an empty list. Returning 404 here would make clients
treat a normal situation as a failure, and they could not tell "no tasks" apart from a
wrong URL.

## Exercise: Fix the error responses
<!-- meta: kind=exercise, difficulty=beginner -->

A to-do API has an endpoint `POST /tasks`. The title is required and must be 1–200
characters. The endpoint behaves like this:

1. When the client sends `{}` (no title), it returns **200 OK** with the body
   `{"error": "bad"}`.
2. When the database is down, it returns **500 Internal Server Error** with a body
   containing the full stack trace, including the line
   `psycopg.OperationalError: connection to server at "10.0.3.7", port 5432 failed`.

For each case, explain what is wrong with the current response, and describe what the
status code and the response body should be instead.

## Exercise: Pick the right response
<!-- meta: kind=exercise, difficulty=beginner -->

For each request to a to-do API, choose the status code and briefly say why:

1. `GET /tasks/999`, and there is no task 999.
2. `GET /tasks`, and the user has no tasks yet.
3. `POST /tasks` with the body `{"title": "Buy milk",` (cut off, not valid JSON).
4. `POST /tasks` with `{"title": "Buy milk", "status": "maybe"}`, where status must be
   `todo`, `doing` or `done`.
5. `POST /users` with a username that is already taken.
