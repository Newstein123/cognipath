---
id: rest-api
concept: REST API Design
capability: rest-design
difficulty: beginner
prerequisites: [http]
source: "Roy Fielding, Architectural Styles and the Design of Network-based Software Architectures, Ch. 5; RFC 9110 HTTP Semantics; RFC 5789 PATCH Method for HTTP; RFC 7396 JSON Merge Patch; MDN Web Docs — HTTP request methods (https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods)"
---

# REST API Design

## What a REST API is

An **API** (Application Programming Interface) is a way for one program to ask another
for data or actions. A **REST API** is a style of web API built on plain HTTP, organised
around **resources**: the nouns of your system, such as tasks, users or orders.

- Each resource has a **URL**. `/tasks` is the collection of all tasks; `/tasks/7` is
  the one task with id 7.
- The **HTTP method** is the verb: what you want to do to that resource.
- Data travels as a **representation** of the resource, usually **JSON**, such as
  `{"id": 7, "title": "Buy milk", "done": false}`.

A to-do app's task API looks like this:

```
GET    /tasks        list all tasks
POST   /tasks        create a new task (body: the task's data)
GET    /tasks/{id}   fetch one task
PUT    /tasks/{id}   replace that task completely
PATCH  /tasks/{id}   change part of that task
DELETE /tasks/{id}   delete that task
```

`{id}` is a placeholder for a real id, such as `/tasks/7`. Notice that only two URLs
are needed: the method, not the path, says what happens.

## Resources and URL structure

A REST API models a system as a set of **resources**, each addressable by a URL. The
central design move is that URLs name things, not actions. `/users/42/orders` is a
resource. `/getUserOrders?id=42` is a remote procedure call wearing a URL costume.

Conventional structure uses plural nouns and nests to show ownership:

```
GET    /orders          list orders
POST   /orders          create an order
GET    /orders/42       fetch one order
PATCH  /orders/42       modify part of it
DELETE /orders/42       remove it
GET    /users/7/orders  orders belonging to user 7
```

The verb lives in the HTTP method, never in the path. If you find yourself writing
`/orders/42/cancel`, the question to ask is whether cancellation is really a state
change on the order (`PATCH /orders/42` with `{"status":"cancelled"}`) or genuinely a
new resource (`POST /orders/42/cancellations`). Both are defensible; `/cancel` as a verb
in the path is the option that breaks the model.

## PUT vs PATCH

Both update an existing resource, but in different ways. Suppose task 7 is currently:

```json
{ "id": 7, "title": "Buy milk", "done": false, "due": "2026-10-20" }
```

**PUT replaces the whole representation.** The client sends the complete new version:

```
PUT /tasks/7
{ "title": "Buy oat milk", "done": false, "due": "2026-10-20" }
```

Any field left out is treated as gone: had the client omitted `due`, the task would end
up with no due date. PUT is **idempotent**: sending the same PUT five times leaves the
task in exactly the same state as sending it once, so it is safe to retry.

**PATCH applies a partial change.** The client sends only what should change:

```
PATCH /tasks/7
{ "done": true }
```

The title and due date stay as they were. (This body format, "send only the fields to
change", is called JSON Merge Patch and is a common convention.) PATCH is not guaranteed
to be idempotent, though simple "set this field" patches like this one are in practice.

Rule of thumb: PATCH to change a field or two; PUT to replace the whole resource.

## Request and response design

Responses should be predictable in shape. A collection endpoint returns a list plus
pagination metadata; a single-resource endpoint returns the object. Keeping the envelope
consistent means clients can write one parsing path instead of one per endpoint.

Errors deserve as much design attention as success cases. An error response should carry
a machine-readable code, a human-readable message, and enough context to act on:

```json
{ "error": { "code": "insufficient_stock",
             "message": "Only 2 units of SKU-119 remain",
             "field": "items[0].quantity" } }
```

Returning `200 OK` with `{"success": false}` is a common mistake. It forces every client
to inspect the body to learn whether the call worked, and it defeats every piece of
infrastructure — proxies, monitoring, retry logic — that reasons about status codes.

## Versioning

Any API with external consumers will need to change incompatibly at some point.
Versioning in the path (`/v1/orders`) is the most common approach because it is visible,
easy to route, and easy to reason about in logs. Header-based versioning keeps URLs
stable but makes debugging harder because the version is invisible in a browser.

The important discipline is distinguishing breaking from non-breaking changes. Adding an
optional field is non-breaking. Removing a field, renaming one, or tightening validation
is breaking and needs a new version.

## Pagination

Returning an unbounded list is a latency and memory problem waiting to happen.
**Offset pagination** (`?limit=20&offset=40`) is simple but degrades on large offsets,
because the database must still walk past every skipped row, and it can skip or repeat
items when rows are inserted between requests.

**Cursor pagination** (`?limit=20&after=eyJpZCI6NDJ9`) passes an opaque pointer to the
last item seen. It stays fast at any depth and is stable under concurrent inserts, at the
cost of not being able to jump to an arbitrary page.

## Exercise: Critique an endpoint
<!-- meta: kind=exercise, difficulty=intermediate -->

An API exposes `POST /api/getUsersByStatus` which accepts `{"status": "active"}` and
returns `200 OK` with `{"success": true, "data": [...]}` — all 40,000 matching users.
List four separate design problems with this endpoint and give the corrected version of
each. State which single change you would make first and why.

## Exercise: Design a profile API
<!-- meta: kind=exercise, difficulty=beginner -->

A university app stores one profile per student, with fields such as `name`, `email`
and `programme`. Design the REST endpoints for these five operations. For each, give
the HTTP method, the path, and the status code the server returns on success:

1. Retrieve a student's profile.
2. Create a new profile.
3. Replace a profile completely with new data.
4. Update just the student's email address.
5. Delete a profile.

Finally: what should the API return if a client asks to retrieve, update or delete a
profile that does not exist? Explain why that is better than returning `200 OK` with an
error message in the body.
