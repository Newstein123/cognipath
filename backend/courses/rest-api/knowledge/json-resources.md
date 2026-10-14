---
id: json-resources
concept: JSON and Resources
capability: json-resources
difficulty: beginner
prerequisites: [http-requests]
source: "Adapted from MDN Web Docs — Working with JSON (https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/Scripting/JSON); Content-Type (https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Type); URIs (https://developer.mozilla.org/en-US/docs/Web/URI); REST glossary (https://developer.mozilla.org/en-US/docs/Glossary/REST), by Mozilla Contributors, CC BY-SA 2.5"
---

# JSON and Resources

## Why this matters

Picture a library. Every book has a fixed place on a shelf, its address, and a catalogue card that describes it in a standard format: title, author, year. Anyone who knows the format can read any card, in any library.

A REST API works the same way. Each thing the API manages (a task, a user) is a **resource** with its own **address** (a URL like `/tasks/42`). When you ask for it, you get a description in a standard format, which is almost always **JSON**.

If the addresses are messy or the JSON is malformed, clients can't find or read anything. In this unit you learn to write correct JSON and to design clean, predictable URLs for TaskFlow.

## What JSON is

**JSON** (JavaScript Object Notation) is a **text format** for structured data. It borrows JavaScript's object syntax, but it is just a string, so any language can produce and read it. Python, Java, Go and PHP all have JSON libraries. That's why APIs use it to send data across the network.

Two operations matter:

- **Serialize** (stringify): turn in-memory data into a JSON string to send.
- **Parse**: turn a received JSON string back into data your program can use.

In JavaScript these are `JSON.stringify()` and `JSON.parse()`. Other languages have equivalents.

```text
server memory: task{id=42, title="Buy milk"}
   --serialize-->  '{"id": 42, "title": "Buy milk"}'  --network-->
   --parse-->      client memory: task.id == 42
```

Because JSON is text, a single misplaced comma makes the whole document unreadable. JSON is strict, and that strictness is what makes it reliable.

## JSON value types

JSON has exactly six kinds of value:

| Type | Example | Notes |
|---|---|---|
| string | `"Buy milk"` | Always **double** quotes |
| number | `42`, `3.5`, `-1` | Decimal only; no `NaN`, no `Infinity` |
| boolean | `true`, `false` | Lowercase, no quotes |
| null | `null` | "No value", e.g. no due date |
| object | `{"id": 42}` | Unordered key/value pairs; keys are double-quoted strings |
| array | `[1, 2, 3]` | Ordered list of values |

There is **no date type**. Dates travel as strings, usually ISO 8601 such as `"2026-11-01"` or `"2026-10-14T09:12:00Z"`. There is no `undefined`, and there are no functions or comments.

Note the difference between `"done": false` and `"done": "false"`. The first is a boolean. The second is a five-letter string, and code that checks `if (task.done)` will treat it as true.

## A TaskFlow task and a list of tasks as JSON

One task is an **object**:

```json
{
  "id": 42,
  "owner_id": 123,
  "title": "Buy milk",
  "done": false,
  "due_date": "2026-10-20",
  "created_at": "2026-10-14T08:00:00Z"
}
```

A list of tasks is an **array of objects**. It's often wrapped in an object so there's room for extra information:

```json
{
  "data": [
    {"id": 42, "title": "Buy milk", "done": false, "due_date": null},
    {"id": 43, "title": "Pay rent", "done": true, "due_date": "2026-11-01"}
  ],
  "total": 2
}
```

Values can nest: objects inside arrays inside objects. A JSON document's top level may be an object, an array, or even a single primitive. For APIs an object at the top level is the safest choice, because you can add fields later (like `total` or `next_page`) without breaking clients.

## Content-Type and Accept

HTTP needs to know what format a body is in. Two headers handle this.

- **`Content-Type`** describes the body **being sent in this message**. In a request (`POST`, `PUT`, `PATCH`) it tells the server what the client is sending. In a response it tells the client what came back. For JSON: `Content-Type: application/json`, sometimes with `; charset=utf-8`.
- **`Accept`** is sent by the client to say **which formats it would like in the response**: `Accept: application/json`.

```http
POST /v1/tasks HTTP/1.1
Host: api.taskflow.example
Content-Type: application/json
Accept: application/json

{"title": "Water plants"}
```

If the client sends a body in a format the server doesn't support, a strict server answers `415 Unsupported Media Type`. If it can't produce any format the client accepts, it can answer `406 Not Acceptable`. A `GET` has no body, so it needs `Accept` but not `Content-Type`.

## Resources and representations

In REST, a **resource** is any named thing the API manages: task 42, user 123, or "all of Alice's tasks". A resource is a concept. It lives in the database as a row, but clients never touch the row directly.

What travels over the wire is a **representation**: a snapshot of the resource's current state in some format. The same task 42 could be represented as JSON:

```json
{"id": 42, "title": "Buy milk", "done": false}
```

or, if the API supported it, as CSV (`42,Buy milk,false`). Same resource, different representations, chosen through `Accept` and `Content-Type`.

A representation also doesn't have to show every column. Task 42's database row has `owner_id` and `created_at`. User rows have `password_hash`, which **must never** appear in any representation. The API decides what to expose. That's the "Representational" in REST (Representational State Transfer): clients transfer representations of state, not the database itself.

## Collections vs single items

TaskFlow's URLs come in two shapes.

- **Collection**: `/tasks`, the set of all tasks (that the caller can see).
- **Single item** (member): `/tasks/42`, one specific task inside that collection.

The method means something different on each:

| Request | Meaning | Typical success |
|---|---|---|
| `GET /tasks` | List tasks | 200 + array |
| `POST /tasks` | Add a new task to the collection | 201 + Location |
| `GET /tasks/42` | Fetch task 42 | 200 + object |
| `PUT /tasks/42` | Replace task 42 | 200 |
| `PATCH /tasks/42` | Partly update task 42 | 200 |
| `DELETE /tasks/42` | Remove task 42 | 204 |

Notice that you `POST` to the **collection**, because the client doesn't know the new id yet. The server assigns it and reports it in `Location: /v1/tasks/43`. A collection returns an array (often wrapped). A single item returns one object.

## Identifiers in URLs

The `42` in `/tasks/42` is the task's **identifier**: a value that picks out exactly one resource. Here it is the task's `id` column.

Recall the parts of a URL:

```text
https://api.taskflow.example/v1/tasks/42?fields=title#notes
scheme  authority (host)     path        query        fragment
```

The **path** (`/v1/tasks/42`) identifies the resource. Identifier rules:

- **Stable.** Task 42 is always `/tasks/42`, even if its title changes. Don't build URLs from titles (`/tasks/buy-milk`) when titles can be edited.
- **Unique** within the collection.
- **Opaque to the client.** Clients copy ids, they don't compute them. Some APIs use UUIDs (`/tasks/9f1c2e...`) so ids can't be guessed by counting upwards.

An identifier says *which* resource. It does **not** grant permission. Bob guessing `/tasks/42` must still be refused if the task isn't his.

## Nested resources vs query parameters

**Nested paths** express ownership or containment: `/users/123/tasks` means "the tasks belonging to user 123". Use nesting when the child only makes sense inside the parent, and keep it to **one level**. `/users/123/tasks/42/comments/7` gets hard to work with. Once you have the task id, `/tasks/42` is enough.

**Query parameters** (after `?`) **filter, sort, search or paginate** a collection without naming a new resource:

```text
GET /tasks?done=false
GET /tasks?due_before=2026-11-01&sort=due_date
GET /tasks?page=2&limit=20
```

Rule of thumb: **path = which resource, query = which subset or view of it.** "Alice's tasks" is a relationship, so `/users/123/tasks` reads well. "Unfinished tasks" is a filter, so use `?done=false`, not `/tasks/unfinished`. You can combine them: `/users/123/tasks?done=false`.

## Naming conventions

Most REST APIs follow the same conventions, and following them makes your API predictable.

- **Plural nouns for collections**: `/tasks`, `/users`. The item is then `/tasks/42`, which reads as "task 42 of tasks".
- **Lowercase**, with words separated by hyphens if needed: `/task-lists`, not `/TaskLists` or `/task_lists`. URL paths can be case-sensitive, so mixed case invites bugs.
- **No verbs in paths.** The HTTP method is the verb.

| Avoid | Use |
|---|---|
| `GET /getTasks` | `GET /tasks` |
| `POST /createTask` | `POST /tasks` |
| `POST /deleteTask?id=42` | `DELETE /tasks/42` |
| `GET /task/42` | `GET /tasks/42` |

- **No file extensions** (`/tasks.json`). Use `Accept` instead.
- **Version prefix** at the start: `/v1/tasks`.

TaskFlow's `POST /login` is a common, accepted exception. It's an action rather than a thing. Some teams model it as a resource instead, for example `POST /sessions`.

## Worked example: Reading Alice's task list

Alice's app fetches her unfinished tasks.

```http
GET /v1/tasks?done=false HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...
Accept: application/json
```

Step 1: The path `/v1/tasks` names the **collection**. The query `done=false` is a **filter**. Step 2: The server works out that the caller is user 123 and runs:

```sql
SELECT id, title, done, due_date
FROM tasks
WHERE owner_id = 123 AND done = false
ORDER BY due_date NULLS LAST;
```

Step 3: It serializes the rows into a JSON **representation**:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"data": [
  {"id": 42, "title": "Buy milk", "done": false, "due_date": "2026-10-20"},
  {"id": 44, "title": "Book dentist", "done": false, "due_date": null}
], "total": 2}
```

Notice `null` for the missing date (SQL `NULL` becomes JSON `null`), `false` as a real boolean, and dates as strings. If nothing matched, the answer would still be `200` with `"data": []`. An empty collection isn't an error.

## Worked example: Creating a task with a JSON body

Alice creates a task.

```http
POST /v1/tasks HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...
Content-Type: application/json
Accept: application/json

{"title": "Water plants", "due_date": "2026-10-18"}
```

Step 1: `Content-Type: application/json` tells the server to parse the body as JSON. Step 2: The client sends only what it knows. `id`, `owner_id`, `done` and `created_at` are set by the server, so a client sending `"owner_id": 456` should be ignored or rejected. Step 3: The server inserts the row and answers with the full representation:

```http
HTTP/1.1 201 Created
Location: https://api.taskflow.example/v1/tasks/45
Content-Type: application/json

{"id": 45, "owner_id": 123, "title": "Water plants", "done": false,
 "due_date": "2026-10-18", "created_at": "2026-10-14T10:05:00Z"}
```

With curl:

```bash
curl -X POST https://api.taskflow.example/v1/tasks \
  -H "Authorization: Bearer eyJhbGciOi..." \
  -H "Content-Type: application/json" \
  -d '{"title": "Water plants", "due_date": "2026-10-18"}'
```

## Worked example: Fixing broken JSON

A teammate's request body is rejected with `400 Bad Request`:

```text
{
  // new task
  'title': 'Call mum',
  done: "false",
  "due_date": 2026-10-21,
}
```

Go line by line:

1. `// new task`: JSON has **no comments**. Remove it.
2. `'title': 'Call mum'`: **single quotes** aren't allowed. Use `"title": "Call mum"`.
3. `done:`: keys must be **double-quoted strings**, so `"done"`. Also `"false"` is a string. Use the boolean `false`.
4. `2026-10-21`: not a valid number and not a string. Dates are strings: `"2026-10-21"`.
5. The comma after the last value is a **trailing comma**. Remove it.

Corrected:

```json
{
  "title": "Call mum",
  "done": false,
  "due_date": "2026-10-21"
}
```

Tip: paste JSON into a validator or your editor's JSON mode before sending it. Most of these errors are highlighted at once.

## Worked example: Designing URLs for new features

The TaskFlow team wants four features. Here's how each maps to a URL.

1. *"Show all tasks belonging to Bob."* That's an ownership relationship, so `GET /v1/users/456/tasks`. (Equivalent: `GET /v1/tasks?owner_id=456`.)
2. *"Show tasks due this week that aren't done."* That's filtering a collection, so `GET /v1/tasks?done=false&due_before=2026-10-19`. Not `/tasks/due-this-week/undone`.
3. *"Mark task 42 as done."* Don't add a verb endpoint like `POST /completeTask/42`. Update the resource: `PATCH /v1/tasks/42` with body `{"done": true}`.
4. *"Add comments to tasks."* Comments live inside a task, so `POST /v1/tasks/42/comments` to create one, and `GET /v1/tasks/42/comments` to list them. One level of nesting is enough.

In every case the path names a **noun** (a resource or collection), the method supplies the **verb**, and the query narrows **which items** you see.

## Common mistakes: JSON

- **Trailing comma**: `{"title": "A", "done": false,}`. Strict parsers reject it. Remove the last comma.
- **Single quotes**: `{'title': 'A'}`. JSON only allows double quotes, for keys and for strings.
- **Unquoted keys**: `{title: "A"}`. That's valid JavaScript but **not** JSON. Write `{"title": "A"}`.
- **Comments**: `// ...` or `/* ... */` break parsing. Put explanations in documentation instead.
- **Wrong types**: `"done": "false"` or `"id": "42"` when clients expect a boolean or a number. Keep types consistent across the API.
- **Missing Content-Type**: sending a JSON body with no `Content-Type: application/json` header. The server may not parse it, or may answer 415.
- **Leaking fields**: serializing the whole user row, `password_hash` included. Choose the fields in the representation deliberately.

## Common mistakes: URLs and resources

- **Verbs in paths**: `/getTasks`, `/deleteTask/42`. The method is the verb. Use `GET /tasks` and `DELETE /tasks/42`.
- **Singular/plural mix**: `/task/42` in one place and `/tasks` in another. Pick plural everywhere.
- **Filters as paths**: `/tasks/done` or `/tasks/unfinished`. These aren't new resources, they are views of `/tasks`. Use `/tasks?done=true`.
- **Deep nesting**: `/users/123/tasks/42/comments/7/likes`. Stop at one level and use `/comments/7/likes`.
- **Mutable identifiers**: `/tasks/buy-milk` breaks as soon as the title changes. Use the stable id.
- **Treating an id as permission**: just because `/tasks/42` exists doesn't mean Bob may read it. Always check ownership.

## Summary

- **JSON** is a strict text format with six value types: string, number, boolean, null, object, array.
- Double quotes only. No comments, no trailing commas. Dates are strings.
- `Content-Type` describes the body being sent. `Accept` says which response format the client wants. For APIs, both are `application/json`.
- A **resource** is a named thing. A **representation** is a snapshot of it (e.g. JSON) that the API chooses what to include in.
- `/tasks` is a **collection** (GET to list, POST to create). `/tasks/42` is an **item** (GET, PUT, PATCH, DELETE).
- Identifiers in paths should be stable and unique. They don't grant access.
- Nest for ownership (`/users/123/tasks`, one level). Use query parameters to filter, sort or paginate (`/tasks?done=false`).
- Use plural, lowercase nouns, no verbs, and a version prefix.

## Exercise: Design the TaskFlow URLs
<!-- meta: kind=exercise, difficulty=beginner -->

A teammate proposes these endpoints for TaskFlow:

1. `GET /getAllTasks`
2. `GET /Task/42`
3. `POST /tasks/create`
4. `GET /tasks/completed`
5. `GET /users/123/tasks/42/details`

For each one, explain what is wrong with it and give a better method and URL. Then write the request you would use for "Alice's unfinished tasks, soonest due first", and explain why you used a path segment for one part and query parameters for the rest.

## Exercise: Repair and explain a JSON body
<!-- meta: kind=exercise, difficulty=beginner -->

Bob's app sends this to `POST /v1/tasks`, with no `Content-Type` header, and gets an error:

```text
{ title: 'Renew passport', 'done': 'no', "due_date": 2026-12-01, "owner_id": 123, }
```

List every problem: JSON syntax, value types, headers, and anything that's a security concern. Write the corrected request, including headers and body. Then describe the JSON representation of the new task that TaskFlow should send back, and say which fields came from the server rather than from Bob.
