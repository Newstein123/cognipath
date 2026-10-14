---
id: crud-databases
concept: Tables and CRUD
capability: crud-databases
difficulty: beginner
prerequisites: [endpoint-design]
source: "Adapted from PostgreSQL Documentation — Tutorial: The SQL Language, Creating a New Table, Populating a Table With Rows, Querying a Table, Updates, Deletions (https://www.postgresql.org/docs/current/tutorial-sql.html) (PostgreSQL Licence); MDN Web Docs — CRUD (https://developer.mozilla.org/en-US/docs/Glossary/CRUD), by Mozilla Contributors, CC BY-SA 2.5"
---

# Tables and CRUD

## Why this matters
Imagine a waiter who memorises every order but never writes anything down. When the shift ends, every order is gone. An API server is that waiter: anything it keeps in variables lives inside one running process, and a restart, a crash or a new deploy wipes it. If you run two copies of the server, each has its own memory and they disagree.

A database is the order book. It stores data on disk, outlives any single server process, and is shared by every copy of the server. When Alice creates the task "Buy milk" on Monday, it must still be there on Friday after three deploys. That is why almost every real API sits in front of a database.

In this unit you learn how TaskFlow's data is laid out in PostgreSQL tables, the four basic operations on stored data (CRUD), and exactly which SQL statement and which HTTP status code each TaskFlow endpoint uses.

## Tables, rows and columns
A relational database such as PostgreSQL stores data in **tables**. A table holds data about one kind of thing: TaskFlow has a `users` table and a `tasks` table.

- A **column** is a named field with a fixed data type, for example `title` (text) or `done` (boolean). Every value in a column has that type.
- A **row** is one record: one value for each column. Alice's task "Buy milk" is one row in `tasks`.

You can picture a table like a spreadsheet:

```
 id | owner_id | title      | done  | due_date   | created_at
----+----------+------------+-------+------------+---------------------
 42 |      123 | Buy milk   | false | 2026-10-20 | 2026-10-14 09:00:00
 43 |      456 | Fix bike   | true  |            | 2026-10-14 09:05:00
```

Row 43 has an empty `due_date`: the value is NULL, meaning "no value". Unlike a spreadsheet, the database enforces the types: you cannot store the word "maybe" in `done`.

You talk to the database in **SQL**, a language of statements such as `CREATE TABLE`, `INSERT`, `SELECT`, `UPDATE` and `DELETE`.

## Data types and primary keys
Each column is declared with a **data type**. The ones TaskFlow needs:

- `bigint` / `int` — whole numbers (ids).
- `text` or `varchar(N)` — strings; `varchar(200)` allows up to 200 characters.
- `boolean` — `true` or `false`.
- `date` — a calendar date, written `'2026-10-20'` (the unambiguous YYYY-MM-DD form).
- `timestamptz` — a date and time with time zone.

A **primary key** is the column that identifies each row. In PostgreSQL a primary key is automatically both UNIQUE (no two rows share it) and NOT NULL (every row has one). A table has at most one primary key.

The primary key is what your URL points at: `GET /v1/tasks/42` means "the row in `tasks` whose primary key `id` is 42". Using `GENERATED ALWAYS AS IDENTITY` lets the database pick the next id itself, so the client never invents ids.

## The TaskFlow tables
Here are the two tables as `CREATE TABLE` statements. `--` starts a comment.

```sql
CREATE TABLE users (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email         text NOT NULL UNIQUE,
    password_hash text NOT NULL,     -- never the real password
    name          text NOT NULL
);

CREATE TABLE tasks (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id    bigint NOT NULL REFERENCES users (id),
    title       varchar(200) NOT NULL,
    done        boolean NOT NULL DEFAULT false,
    due_date    date,                -- may be NULL: "no due date"
    created_at  timestamptz NOT NULL DEFAULT now()
);
```

Notes: `NOT NULL` forbids empty values; `DEFAULT` fills a column when the INSERT leaves it out, so a new task starts with `done = false` and the current time. `due_date` has no NOT NULL, so it is optional. `REFERENCES users (id)` links each task to its owner; the next unit explains that link.

## CRUD and its SQL
**CRUD** stands for **Create, Read, Update, Delete**: the four basic operations on stored data. Every resource endpoint you designed in the previous unit is one of them, and each has a matching SQL statement and a usual HTTP method:

```
CRUD    | SQL                    | HTTP method
--------+------------------------+--------------------------
Create  | INSERT INTO ...        | POST
Read    | SELECT ... FROM ...    | GET
Update  | UPDATE ... SET ...     | PUT (replace), PATCH (part)
Delete  | DELETE FROM ...        | DELETE
```

The basic shapes, using the PostgreSQL tutorial's style of always listing columns explicitly:

```sql
INSERT INTO tasks (owner_id, title) VALUES (123, 'Buy milk');
SELECT id, title, done FROM tasks WHERE id = 42;
UPDATE tasks SET done = true WHERE id = 42;
DELETE FROM tasks WHERE id = 42;
```

The `WHERE` clause chooses which rows a statement touches. Without it, `UPDATE` changes every row and `DELETE` removes every row, with no confirmation.

## Placeholders and RETURNING
In real code you never paste request values into the SQL text. You write **placeholders** `$1`, `$2`, … and send the values separately; the database treats them strictly as data. (The next unit shows the attack this prevents.)

```sql
SELECT id, title, done, due_date FROM tasks
WHERE id = $1 AND owner_id = $2;
-- $1 = 42 (from the URL), $2 = 123 (the logged-in user)
```

`AND owner_id = $2` makes sure Alice can only see her own tasks; the next unit explains why the owner comes from the login, not from the request.

PostgreSQL's `RETURNING` clause makes `INSERT`, `UPDATE` and `DELETE` hand back the rows they changed, so you get the new id and default values without a second query:

```sql
INSERT INTO tasks (owner_id, title) VALUES ($1, $2)
RETURNING id, title, done, due_date, created_at;
```

The database also reports a **row count**: how many rows the statement affected. Your code uses it to decide between success and 404.

## Worked example: POST /tasks creates a row
Alice (user 123) creates a task.

```http
POST /v1/tasks HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...
Content-Type: application/json

{"title": "Buy milk", "due_date": "2026-10-20"}
```

Step 1: validate the body (title present, date valid). Step 2: run an INSERT with the owner taken from the token:

```sql
INSERT INTO tasks (owner_id, title, due_date)
VALUES ($1, $2, $3)            -- 123, 'Buy milk', '2026-10-20'
RETURNING id, title, done, due_date, created_at;
```

Step 3: the database fills `id` (42), `done` (false) and `created_at` from the defaults and returns the row. Step 4: reply 201 Created with a Location header:

```http
HTTP/1.1 201 Created
Location: /v1/tasks/42
Content-Type: application/json

{"id": 42, "title": "Buy milk", "done": false,
 "due_date": "2026-10-20", "created_at": "2026-10-14T09:00:00Z"}
```

## Worked example: GET /tasks/{id} and the missing row
Alice asks for task 42, then for task 999, which does not exist.

```http
GET /v1/tasks/42 HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...
```

```sql
SELECT id, title, done, due_date, created_at
FROM tasks WHERE id = $1 AND owner_id = $2;   -- 42, 123
```

One row comes back, so the server replies:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id": 42, "title": "Buy milk", "done": false,
 "due_date": "2026-10-20", "created_at": "2026-10-14T09:00:00Z"}
```

For `GET /v1/tasks/999` the same SELECT returns **zero rows**. That is not a database error; the query worked and found nothing. The server must turn "no row" into:

```http
HTTP/1.1 404 Not Found
Content-Type: application/json

{"error": "task_not_found"}
```

The same happens if Bob asks for Alice's task 42: the `owner_id` condition filters it out, so Bob gets 404.

## Worked example: GET /tasks with ordering and limits
Alice lists her tasks, newest first, 20 at a time.

```http
GET /v1/tasks?limit=20&offset=0 HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...
```

```sql
SELECT id, title, done, due_date, created_at
FROM tasks
WHERE owner_id = $1                 -- 123
ORDER BY created_at DESC, id DESC
LIMIT $2 OFFSET $3;                 -- 20, 0
```

- **ORDER BY**: without it PostgreSQL guarantees no row order, so pages could shuffle between calls. The second key `id DESC` breaks ties when two tasks share a `created_at`, making the order fully determined.
- **LIMIT** caps the rows returned; the server should also enforce a maximum (say 100) so nobody requests a million rows.
- **OFFSET** skips rows for the next page (`offset=20`).

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"items": [{"id": 42, "title": "Buy milk", "done": false}], "limit": 20, "offset": 0}
```

An empty list is still 200 with `"items": []`, not 404: the collection exists, it is just empty.

## Worked example: PUT /tasks/{id} replaces the task
PUT sends the full new state of the task. Every editable column is set.

```http
PUT /v1/tasks/42 HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...
Content-Type: application/json

{"title": "Buy oat milk", "done": false, "due_date": null}
```

```sql
UPDATE tasks
SET title = $1, done = $2, due_date = $3   -- 'Buy oat milk', false, NULL
WHERE id = $4 AND owner_id = $5            -- 42, 123
RETURNING id, title, done, due_date, created_at;
```

Check the row count. One row updated:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id": 42, "title": "Buy oat milk", "done": false,
 "due_date": null, "created_at": "2026-10-14T09:00:00Z"}
```

Zero rows updated means no task 42 belongs to Alice, so the answer is 404 Not Found. Note that `id`, `owner_id` and `created_at` are never taken from the body: the client cannot reassign a task to someone else by sending `"owner_id": 456`.

## Worked example: PATCH /tasks/{id} updates some columns
PATCH changes only the fields that are present. Alice ticks the task off:

```http
PATCH /v1/tasks/42 HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...
Content-Type: application/json

{"done": true}
```

The server builds the SET list from the fields present in the body, using only column names from a fixed allow-list (`title`, `done`, `due_date`). Values still go in as placeholders:

```sql
UPDATE tasks SET done = $1           -- true
WHERE id = $2 AND owner_id = $3      -- 42, 123
RETURNING id, title, done, due_date, created_at;
```

`title` and `due_date` are not mentioned, so they keep their values. If the body were `{"title": "Buy bread", "due_date": null}`, the SET list would be `title = $1, due_date = $2`. An empty body or an unknown field such as `"owner_id"` is rejected with 400 Bad Request. As with PUT: one row updated gives 200 with the task; zero rows gives 404.

## Worked example: DELETE /tasks/{id}
Alice deletes task 42.

```http
DELETE /v1/tasks/42 HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...
```

```sql
DELETE FROM tasks
WHERE id = $1 AND owner_id = $2;     -- 42, 123
```

The database reports `DELETE 1`: one row removed. There is nothing useful to send back, so:

```http
HTTP/1.1 204 No Content
```

If Alice sends the same request again, the statement reports `DELETE 0`. No row matched, so the server replies 404 Not Found. (Some APIs reply 204 again because the end state, "task 42 is gone", is the same; TaskFlow chooses 404 so clients learn the id was wrong. Pick one rule and document it.)

Never let the `WHERE` clause become empty: `DELETE FROM tasks;` removes every task of every user, immediately and without asking.

## Endpoint-to-SQL map
The whole TaskFlow API on one page (`me` = the authenticated user's id):

```
Endpoint              SQL                                          Success  No row
--------------------  -------------------------------------------  -------  ------
POST   /tasks         INSERT INTO tasks ... RETURNING ...          201      -
GET    /tasks         SELECT ... WHERE owner_id=me ORDER BY LIMIT  200      200 []
GET    /tasks/{id}    SELECT ... WHERE id=$1 AND owner_id=me       200      404
PUT    /tasks/{id}    UPDATE ... SET all fields WHERE id, owner    200      404
PATCH  /tasks/{id}    UPDATE ... SET given fields WHERE id, owner  200      404
DELETE /tasks/{id}    DELETE ... WHERE id=$1 AND owner_id=me       204      404
POST   /login         SELECT id, password_hash FROM users          200      401
                      WHERE email=$1
```

For `POST /login`, zero rows (unknown email) and a wrong password must both give the same 401 Unauthorized, so attackers cannot learn which emails are registered. Invalid input on any endpoint gives 400 before any SQL runs.

## When no row matches
A beginner trap: a SQL statement that matches nothing **succeeds**. It does not throw an error. Your code has to look at the result and decide.

- `SELECT` returns zero rows → the resource does not exist (for this user) → **404 Not Found**.
- `UPDATE` reports 0 rows affected → nothing was changed → **404 Not Found**.
- `DELETE` reports 0 rows affected → nothing was deleted → **404 Not Found**.
- A list `SELECT` that returns zero rows → **200 OK** with an empty list.

In pseudocode:

```
row = db.query("UPDATE tasks SET done = $1 WHERE id = $2 AND owner_id = $3 RETURNING ...",
               [true, 42, me])
if row is empty:
    return 404 {"error": "task_not_found"}
return 200 row
```

Do not run a SELECT first "to check it exists" and then the UPDATE: it doubles the work, and the row could be deleted in between. Run the change once and read the row count.

## NULL versus missing
These look similar in JSON but mean different things:

- **Missing**: the field is absent. `{"done": true}` says nothing about `due_date`.
- **null**: the field is present with no value. `{"due_date": null}` says "remove the due date".

In SQL, `NULL` means "no value". It is not zero, not `false` and not an empty string, and `NULL = NULL` is not true: test with `due_date IS NULL`.

For **PATCH** the difference is crucial:

```
{"done": true}            ->  UPDATE tasks SET done = true ...      (due_date kept)
{"due_date": null}        ->  UPDATE tasks SET due_date = NULL ...  (due_date cleared)
```

A common shortcut, `SET due_date = COALESCE($1, due_date)`, keeps the old value whenever the parameter is NULL. That makes it impossible to clear a due date, because null and missing become the same thing. For **PUT**, a missing optional field is usually treated as null, since PUT replaces the whole task. NOT NULL columns such as `title` must reject null with 400.

## Common mistakes: forgetting WHERE and ORDER BY
**Mistake 1: UPDATE or DELETE without a full WHERE.**
`UPDATE tasks SET done = true WHERE id = $1;` — why it's wrong: it ignores the owner, so Bob can tick off Alice's task 42 just by knowing the id. Worse, a bug that drops the WHERE entirely marks every task in the system done. Correct: `UPDATE tasks SET done = true WHERE id = $1 AND owner_id = $2;`

**Mistake 2: listing without ORDER BY.**
`SELECT ... FROM tasks WHERE owner_id = $1 LIMIT 20;` — why it's wrong: SQL promises no order without ORDER BY, so page 1 and page 2 can overlap or skip tasks. Correct: `ORDER BY created_at DESC, id DESC LIMIT 20`, with a tie-breaker so the order is fully determined.

**Mistake 3: no maximum LIMIT.**
Passing `?limit=1000000` straight to the query lets one client make the database read huge result sets. Correct: cap it on the server, e.g. `limit = min(requested, 100)`.

## Common mistakes: wrong status and leaking columns
**Mistake 4: 500 or 200 when no row matched.**
Treating "zero rows" as a crash (500 Internal Server Error) or replying 200 with an empty body. Why it's wrong: the client did ask for something that does not exist; that is a client-side situation. Correct: check the row count and reply 404 Not Found.

**Mistake 5: `SELECT *` on users.**
`SELECT * FROM users WHERE id = $1` and returning the row as JSON. Why it's wrong: it sends `password_hash` to the client, and any column added later leaks automatically. The PostgreSQL tutorial itself calls `SELECT *` bad style in production code. Correct: `SELECT id, email, name FROM users WHERE id = $1`.

**Mistake 6: trusting ids from the body.**
Copying `"id"` or `"owner_id"` from a PUT body into the UPDATE. Correct: the id comes from the URL, the owner from the token, and the body only supplies editable fields.

## Summary
- Data in server memory dies with the process; a database keeps it on disk and shares it across server copies.
- A table has typed columns and rows; the primary key (UNIQUE + NOT NULL) identifies each row and is the `{id}` in the URL.
- CRUD = Create/Read/Update/Delete = INSERT/SELECT/UPDATE/DELETE = POST/GET/PUT-PATCH/DELETE.
- Use placeholders (`$1`) for every value and `RETURNING` to get the changed row back.
- Success codes: POST 201 + Location, GET/PUT/PATCH 200, DELETE 204.
- Zero rows from SELECT, UPDATE or DELETE on one item → 404; an empty list → 200 with `[]`.
- PATCH sets only the fields present; `null` means "clear it", missing means "leave it".
- Lists need ORDER BY with a tie-breaker, plus a capped LIMIT.
- Always include `owner_id = me` in the WHERE, and never `SELECT *` on users.

## Exercise: Map the request to SQL
<!-- meta: kind=exercise, difficulty=beginner -->

Bob (user 456) sends this request to TaskFlow:

```http
PATCH /v1/tasks/77 HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...
Content-Type: application/json

{"title": "Fix bike brakes", "due_date": null}
```

1. Write the SQL statement the server should run, using placeholders, and say what value goes into each placeholder and where that value comes from.
2. Which columns change and which stay the same? What happens to the task's `done` value, and why?
3. Give the response status (and briefly the body) when task 77 belongs to Bob, and when task 77 belongs to Alice.
4. Explain why `SET due_date = COALESCE($2, due_date)` would be a bug here.

## Exercise: Design the list endpoint
<!-- meta: kind=exercise, difficulty=beginner -->

Alice has 250 tasks. The mobile app calls `GET /v1/tasks?limit=50&offset=50` to show the second page, sorted by due date with the soonest first.

1. Write the SELECT statement, with placeholders, that returns this page. Say what you put in ORDER BY and why one sort column is not enough.
2. What should the server do if the app sends `limit=5000`?
3. A teammate's version has no ORDER BY at all. Describe what bug users might see when scrolling between pages.
4. What status and body should the server return if Alice has no tasks at all? Explain why it is not 404.
