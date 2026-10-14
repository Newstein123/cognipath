---
id: databases-crud
concept: Databases and CRUD
capability: databases-crud
difficulty: beginner
prerequisites: [rest-api]
source: "PostgreSQL Documentation — Tutorial: The SQL Language (https://www.postgresql.org/docs/current/tutorial-sql.html); MDN Web Docs — CRUD (https://developer.mozilla.org/en-US/docs/Glossary/CRUD)"
---

# Databases and CRUD

## Why an API needs a database

An API server is a program, and anything it keeps in memory (a list in a variable, for
example) disappears when that program stops, crashes or is redeployed. Real data — users,
tasks, orders — has to outlive the server process, so the API stores it in a database.

A database also gives you one source of truth. Large APIs often run several copies of the
server at once behind a load balancer. If each copy kept its own in-memory list, a task
created through one copy would be invisible to the others. When every copy reads and
writes the same database, every request sees the same data.

In this lesson the database is a relational (SQL) database such as PostgreSQL. The API
receives an HTTP request, runs a query against the database, and turns the result into an
HTTP response.

## Tables, rows, columns and primary keys

A relational database stores data in **tables**. A table describes one kind of thing —
one resource. Each **column** is a named field with a type; each **row** is one record.

```sql
CREATE TABLE tasks (
    id         serial PRIMARY KEY,
    owner_id   integer NOT NULL REFERENCES users(id),
    title      text NOT NULL,
    done       boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

| id | owner_id | title          | done  | created_at             |
|----|----------|----------------|-------|------------------------|
| 1  | 7        | Buy milk       | false | 2026-10-01 09:00:00+00 |
| 2  | 7        | Write report   | true  | 2026-10-02 14:30:00+00 |

The **primary key** (`id`) uniquely identifies each row: no two rows can share it and it
cannot be empty. `serial` makes the database pick the next number automatically. The
primary key is what appears in the URL: the row with `id = 2` is the resource
`/tasks/2`.

## CRUD: Create, Read, Update, Delete

Almost everything an API does to stored data is one of four operations, known as
**CRUD**. Each maps to one SQL statement.

```sql
-- Create: add a new row
INSERT INTO tasks (owner_id, title) VALUES (7, 'Buy milk');

-- Read: fetch rows
SELECT id, title, done FROM tasks WHERE id = 1;

-- Update: change columns of existing rows
UPDATE tasks SET done = true WHERE id = 1;

-- Delete: remove rows
DELETE FROM tasks WHERE id = 1;
```

Notice the `WHERE` clause on SELECT, UPDATE and DELETE. It chooses which rows the
statement affects. An `UPDATE` or `DELETE` with no `WHERE` applies to **every row in the
table** — a classic and painful mistake.

In PostgreSQL you can add `RETURNING` to INSERT, UPDATE or DELETE to get the affected
row back, for example `INSERT ... RETURNING id, title, done, created_at;`. That is handy
for sending the created resource in the response.

## Mapping REST endpoints to CRUD

Each REST endpoint for a resource lines up with one CRUD operation and one SQL statement.
`$1`, `$2` are placeholders the server fills with real values (see parameterized
queries below).

```
POST   /tasks       Create  INSERT INTO tasks (owner_id, title)
                            VALUES ($1, $2) RETURNING *            -> 201 Created
GET    /tasks       Read    SELECT * FROM tasks WHERE owner_id = $1 -> 200 OK
GET    /tasks/{id}  Read    SELECT * FROM tasks WHERE id = $1      -> 200 OK
PATCH  /tasks/{id}  Update  UPDATE tasks SET done = $1
                            WHERE id = $2 RETURNING *              -> 200 OK (or 204)
DELETE /tasks/{id}  Delete  DELETE FROM tasks WHERE id = $1        -> 204 No Content
```

PUT maps to UPDATE too; it just sets every editable column instead of a few. Return 200
with the updated task in the body, or 204 if you send no body. A 201 usually includes
the new task and a `Location: /tasks/{id}` header.

## When the row doesn't exist

A client can ask for an id that was never created or was already deleted. The database
does not treat this as an error — the query simply matches nothing — so the API must
check and respond with **404 Not Found**.

- `SELECT ... WHERE id = $1` returns **zero rows** → respond 404.
- `UPDATE ... WHERE id = $1` or `DELETE ... WHERE id = $1` reports **0 rows affected**
  → respond 404. Database drivers expose this as a row count (for example
  `cursor.rowcount` in Python), or you can use `RETURNING` and check whether a row came
  back.

A common bug is to run the UPDATE, ignore the row count, and return 200 anyway. The client
then believes it changed a task that does not exist.

## Relationships and foreign keys

Resources are related: every task belongs to a user. Instead of copying the user's name
and email into each task, the `tasks` table stores the user's primary key in an
`owner_id` column.

```sql
CREATE TABLE users (
    id    serial PRIMARY KEY,
    email text NOT NULL UNIQUE
);
-- in tasks:  owner_id integer NOT NULL REFERENCES users(id)
```

`REFERENCES users(id)` makes `owner_id` a **foreign key**. The database then refuses to
insert a task whose `owner_id` does not match an existing user, and by default refuses to
delete a user who still has tasks. This is called referential integrity.

The `owner_id` column is also what makes authorization possible later: to decide whether
a request may see or change a task, the API compares the task's `owner_id` with the id of
the logged-in user.

## Filtering by owner: the "my tasks" query

A "my tasks" endpoint such as `GET /tasks` must return only the tasks of the user making
the request, never everyone's. The server takes the user id from the authenticated
request (not from a value the client can freely edit) and filters on it:

```sql
SELECT id, title, done, created_at
FROM tasks
WHERE owner_id = $1
ORDER BY created_at DESC;
```

The same idea protects single-task endpoints. Adding the owner to the `WHERE` clause means
another user's task simply isn't found:

```sql
SELECT * FROM tasks WHERE id = $1 AND owner_id = $2;
UPDATE tasks SET done = $1 WHERE id = $2 AND owner_id = $3;
DELETE FROM tasks WHERE id = $1 AND owner_id = $2;
```

If this returns no row, the API can respond 404, which also avoids revealing that the
task exists. Forgetting the owner filter is one of the most common API security bugs.

## Parameterized queries vs string concatenation

Never build SQL by gluing user input into a string. Suppose the server does this
(Python):

```python
# BAD: user input becomes part of the SQL text
sql = "SELECT * FROM tasks WHERE title = '" + title + "'"
```

If a client sends the title `x' OR '1'='1`, the query becomes
`SELECT * FROM tasks WHERE title = 'x' OR '1'='1'`, which matches every row in the table.
Cleverer inputs can read other tables or delete data. This attack is **SQL injection**.

Use a **parameterized query** instead: the SQL text contains placeholders, and the values
are sent to the database separately.

```python
# GOOD: the value is passed separately and never parsed as SQL
cur.execute("SELECT * FROM tasks WHERE title = %s", (title,))
```

The placeholder style depends on the driver (`%s` in psycopg, `$1` in node-postgres and
asyncpg), but the rule is the same: the database treats the value only as data, so
quotes and SQL keywords inside it are harmless.

## Unique constraints and 409 Conflict

Some columns must never repeat — two accounts cannot share an email. Declaring the column
`UNIQUE` makes the database enforce this:

```sql
email text NOT NULL UNIQUE
```

If `POST /users` tries to insert an email that already exists, the INSERT fails with a
unique-violation error (SQLSTATE `23505` in PostgreSQL). The API should catch that
specific error and respond **409 Conflict** with a clear message such as
"email already registered" — not let it bubble up as a 500, which wrongly says the
server is broken.

Checking first with a SELECT and then inserting is not enough on its own: two requests
can both see "no such email" and both insert. The constraint is the reliable guard,
because the database checks it at the moment of the write.

## Transactions

Sometimes one API request needs several writes that must succeed or fail together — for
example, creating an order and reducing the stock count. A **transaction** groups them:
`BEGIN`, then the statements, then `COMMIT` to make them permanent. If anything fails,
`ROLLBACK` undoes every statement since `BEGIN`, so the database is never left
half-updated. Other requests do not see the uncommitted changes.

```sql
BEGIN;
INSERT INTO orders (user_id, product_id) VALUES (7, 3);
UPDATE products SET stock = stock - 1 WHERE id = 3;
COMMIT;
```

## Exercise: Back the task API with a table
<!-- meta: kind=exercise, difficulty=beginner -->

You are given this table:

```sql
CREATE TABLE tasks (
    id       serial PRIMARY KEY,
    owner_id integer NOT NULL REFERENCES users(id),
    title    text NOT NULL,
    done     boolean NOT NULL DEFAULT false
);
```

The logged-in user's id is available to the server. For each of these four endpoints,
write the SQL query it should run (use `$1`, `$2` placeholders, not pasted-in values),
the status code on success, and the status code when the task doesn't exist:

1. `POST /tasks` with body `{"title": "Buy milk"}`
2. `GET /tasks/{id}`
3. `PATCH /tasks/{id}` with body `{"done": true}`
4. `DELETE /tasks/{id}`

Then explain in one or two sentences how your server knows that the task in 2–4 didn't
exist, and why your queries should also mention `owner_id`.

## Exercise: Spot the bugs in a signup endpoint
<!-- meta: kind=exercise, difficulty=beginner -->

A teammate wrote `POST /users` like this:

```python
sql = "INSERT INTO users (email) VALUES ('" + body["email"] + "')"
cur.execute(sql)
return 201
```

The `email` column is `UNIQUE`. When someone signs up twice with the same email, the
client receives `500 Internal Server Error`. Name two problems with this code, explain
what could go wrong with each, and say what status code a duplicate signup should
return and how the server should detect it.
