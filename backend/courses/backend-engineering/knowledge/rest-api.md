---
id: rest-api
concept: REST API Design
capability: api-design
difficulty: beginner
prerequisites: [http]
source: "Roy Fielding, Architectural Styles and the Design of Network-based Software Architectures, Ch. 5"
---

# REST API Design

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
