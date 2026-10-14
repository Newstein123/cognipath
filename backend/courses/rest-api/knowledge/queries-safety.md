---
id: queries-safety
concept: Relationships, Queries and SQL Injection
capability: queries-safety
difficulty: beginner
prerequisites: [crud-databases]
source: "Adapted from PostgreSQL Documentation — Constraints (https://www.postgresql.org/docs/current/ddl-constraints.html), Tutorial: Joins Between Tables (https://www.postgresql.org/docs/current/tutorial-join.html), Tutorial: Transactions (https://www.postgresql.org/docs/current/tutorial-transactions.html) (PostgreSQL Licence); OWASP Cheat Sheet Series — SQL Injection Prevention Cheat Sheet (https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html), CC BY-SA 4.0; OWASP Community — SQL Injection (https://owasp.org/www-community/attacks/SQL_Injection), CC BY-SA 4.0"
---

# Relationships, Queries and SQL Injection

## Why this matters
Think of a library. Every loan slip names a library card number, and the desk refuses a slip whose card does not exist. Only the person holding the card can see their loans. And when you fill in the "title" box on a request form, the librarian reads it as a book title, never as an instruction like "also hand over everyone's records".

A database-backed API needs the same three protections. **Relationships** keep data consistent: every TaskFlow task must belong to a real user. **Correct queries** keep data private: Alice sees only Alice's tasks. **Parameterized queries** keep user input as data: whatever someone types into the search box, the database never runs it as SQL.

Getting these wrong is not a small bug. SQL injection has been one of the most damaging web vulnerabilities for decades, because one bad query can leak or destroy an entire database.

## Foreign keys: linking tasks to users
In the previous unit the `tasks` table had this column:

```sql
owner_id bigint NOT NULL REFERENCES users (id)
```

`REFERENCES users (id)` declares a **foreign key**: every value in `tasks.owner_id` must match an existing `users.id`. The `users` table is the **referenced** table; `tasks` is the **referencing** table. The referenced column must be a primary key or have a unique constraint.

This is a **one-to-many** relationship: one user, many tasks.

```
users                         tasks
 id  | name                    id | owner_id | title
-----+-------                 ----+----------+-----------
 123 | Alice  <-----------    42 |      123 | Buy milk
 456 | Bob    <-----------    43 |      456 | Fix bike
            <-----------    44 |      456 | Call mum
```

From the PostgreSQL docs: a NULL foreign key passes the check, hence `NOT NULL`; and the referencing column is not indexed automatically, so `CREATE INDEX ON tasks (owner_id);` makes "list my tasks" fast.

## What a foreign key guarantees
The database itself enforces the link, whatever bug your code has.

**1. You cannot create an orphan.** Inserting a task for a user who does not exist fails:

```sql
INSERT INTO tasks (owner_id, title) VALUES (999, 'Ghost task');
-- ERROR: insert or update on table "tasks" violates foreign key constraint
```

**2. You cannot silently delete a parent that still has children.** By default (`NO ACTION`), `DELETE FROM users WHERE id = 456;` fails while Bob still has tasks. You choose a different rule with `ON DELETE`:

```
ON DELETE NO ACTION  (default) refuse if children remain (checked at end of statement)
ON DELETE RESTRICT   refuse immediately
ON DELETE CASCADE    delete the children too
ON DELETE SET NULL   set the child's column to NULL
```

The docs suggest CASCADE when the child cannot exist without its parent (a task without an owner is meaningless) and RESTRICT when both things are independent. A foreign key guarantees **consistency**; it does not decide who may read the data. That is your query's job.

## Whose tasks? The owner comes from the login
`GET /v1/tasks` must return only the caller's tasks:

```sql
SELECT id, title, done, due_date
FROM tasks
WHERE owner_id = $1
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

The crucial question is where `$1` comes from. **Wrong:** from the request, e.g. `GET /v1/tasks?owner_id=456`. Bob just changes it to `?owner_id=123` and reads Alice's tasks; nothing in the request proves who he is. **Right:** from the authenticated user. The server verifies the token in `Authorization: Bearer ...`, finds it belongs to user 456, and uses 456. The client never gets a say.

```
user = verify_token(request.headers["Authorization"])   # -> 456 for Bob
rows = db.query("SELECT ... FROM tasks WHERE owner_id = $1 ...", [user.id])
```

The same rule applies to single tasks: `WHERE id = $1 AND owner_id = $2` with `$2` from the token, so Bob asking for task 42 gets 404. And on `POST /tasks` the `owner_id` is set from the token, never from the JSON body.

## Worked example: tasks with owner names
An admin screen needs each task with its owner's name. The data lives in two tables, so we **join** them on the foreign key:

```sql
SELECT tasks.id, tasks.title, users.name AS owner_name
FROM tasks
JOIN users ON tasks.owner_id = users.id
ORDER BY tasks.id;
```

```
 id | title    | owner_name
----+----------+-----------
 42 | Buy milk | Alice
 43 | Fix bike | Bob
 44 | Call mum | Bob
```

Step by step: for each task row, the database finds the user row whose `id` equals `tasks.owner_id` and glues the two together. Both tables have an `id` column, so we **qualify** names as `tasks.id` and `users.name`; the PostgreSQL docs call qualifying every column in a join good style.

`JOIN` is an **inner join**: rows with no match are dropped. To list every user with their task count, including users with none, use a **left outer join**, which keeps every left row and fills missing right columns with NULL:

```sql
SELECT users.name, count(tasks.id) AS task_count
FROM users LEFT JOIN tasks ON tasks.owner_id = users.id
GROUP BY users.id, users.name;
```

## Unique constraints
A **unique constraint** says no two rows may share a value in a column (or a combination of columns). TaskFlow declares:

```sql
email text NOT NULL UNIQUE
```

Now two accounts can never have the same email, because the database checks every INSERT and UPDATE against all existing rows. PostgreSQL builds an index for the constraint automatically, so the check is fast, and the same index makes `WHERE email = $1` fast for `POST /login`.

Details worth knowing:

- A primary key is UNIQUE plus NOT NULL; a table has one primary key but may have many unique constraints.
- By default NULLs count as distinct, so several rows may have NULL in a unique column. `email` is NOT NULL, so this does not arise.
- `UNIQUE (owner_id, title)` would make the *combination* unique: Alice could not have two tasks with the same title, but Alice and Bob could.
- "Alice@x.com" and "alice@x.com" are different strings. Normalise emails to lower case before storing, or the constraint will not catch that duplicate.

## Worked example: duplicate sign-up returns 409
Alice already has an account. Someone signs up again with her email (TaskFlow's sign-up endpoint is `POST /v1/users`):

```http
POST /v1/users HTTP/1.1
Host: api.taskflow.example
Content-Type: application/json

{"email": "alice@example.com", "password": "correct horse", "name": "Alice 2"}
```

The server hashes the password and simply tries the INSERT:

```sql
INSERT INTO users (email, password_hash, name)
VALUES ($1, $2, $3)
RETURNING id, email, name;
-- ERROR: duplicate key value violates unique constraint "users_email_key"
-- SQLSTATE 23505 (unique_violation)
```

The code catches exactly this error code and translates it:

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{"error": "email_already_registered"}
```

409 Conflict means the request clashes with the current state of the resource. It is not 400 (the JSON is valid) and certainly not 500 (nothing crashed). Any other database error still becomes 500. A first-time sign-up succeeds with 201 Created.

## Why check-then-insert is not enough
A tempting design is to look first, then insert:

```
row = db.query("SELECT 1 FROM users WHERE email = $1", [email])
if row exists: return 409
db.query("INSERT INTO users ...")
```

Now imagine two sign-up requests for the same new email arriving at the same moment, handled by two server copies:

```
time  request A                         request B
 1    SELECT ... -> no row
 2                                      SELECT ... -> no row
 3    INSERT -> ok
 4                                      INSERT -> ok   (duplicate!)
```

Both checks ran before either insert, so both passed: a **race condition**, triggered by double-clicks, retries or busy servers. The check is only a snapshot of a moment that has already passed.

The fix is to let the database be the single source of truth: keep the UNIQUE constraint, do the INSERT, and handle the unique-violation error (or use `INSERT ... ON CONFLICT (email) DO NOTHING RETURNING id` and reply 409 when no row comes back). The constraint is checked atomically inside the database, so exactly one request wins.

## What SQL injection is
**SQL injection** happens when an application builds a SQL query by gluing untrusted input into the query text. Because the database receives one string, it cannot tell which part the developer wrote and which part the user typed. Carefully crafted input can close a string early and add SQL of its own, changing what the query does.

OWASP lists the consequences:

- **Confidentiality**: reading data the attacker should never see, such as other users' tasks or password hashes.
- **Authentication**: a badly built login check can let someone log in as another user without the password.
- **Authorization**: if roles are stored in the database, the attacker may change them.
- **Integrity**: modifying or deleting data.

The root cause is always the same: **code and data mixed in one string**. Any request value can carry the attack: a query parameter, a JSON field, a header, even a cookie. Next we break a real TaskFlow endpoint.

## Worked example: the vulnerable search endpoint
TaskFlow adds search: `GET /v1/tasks?q=milk` returns Alice's tasks whose title contains "milk". A developer writes:

```
q = request.query["q"]                      # "milk"
sql = "SELECT id, title FROM tasks WHERE owner_id = " + user.id +
      " AND title ILIKE '%" + q + "%'"
rows = db.query(sql)
```

With the normal input `milk`, the string sent to the database is:

```sql
SELECT id, title FROM tasks WHERE owner_id = 123 AND title ILIKE '%milk%'
```

`ILIKE` is case-insensitive matching and `%` means "any characters", so this works and the tests pass:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"items": [{"id": 42, "title": "Buy milk"}]}
```

The flaw is invisible with friendly input. Whatever is in `q` becomes part of the SQL text, including quote characters, which end the string literal early. The developer meant `q` to be a value; the code lets it be code.

## Worked example: the malicious input
Bob (user 456) sends `q` = `' OR 1=1 --`, URL-encoded:

```http
GET /v1/tasks?q=%27%20OR%201%3D1%20-- HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...
```

After concatenation the database receives:

```sql
SELECT id, title FROM tasks WHERE owner_id = 456 AND title ILIKE '%' OR 1=1 --%'
```

Step by step: the quote closes the string after `%`; `OR 1=1` is added; `--` turns the leftover `%'` into a comment. Since AND binds tighter than OR, the condition is `(owner_id = 456 AND ...) OR 1=1`, which is true for **every row**. Bob receives every task of every user.

Worse, `q` = `' UNION SELECT id, email || ':' || password_hash FROM users --` appends a second query, and the "titles" in the response become every user's email and password hash. If the driver allows several statements per call, `'; DELETE FROM tasks; --` would delete all tasks. One search box, entire database.

## Worked example: the parameterized fix
The fix is a **parameterized query** (also called a prepared statement): the SQL text contains only placeholders, and the values travel separately.

```
sql = "SELECT id, title FROM tasks
       WHERE owner_id = $1 AND title ILIKE '%' || $2 || '%'
       ORDER BY id LIMIT 50"
rows = db.query(sql, [user.id, q])
```

`||` concatenates strings inside the database, after the query structure is fixed. Now Bob's input `' OR 1=1 --` is just a value. The database searches for task titles containing the literal characters `' OR 1=1 --`, finds none among Bob's tasks, and the server replies:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"items": []}
```

Why this works: the database parses the SQL **before** it sees the values, so a value can never change the query's shape. OWASP's words: the database can "always distinguish between code and data". Every TaskFlow query in this course uses `$1`-style placeholders for exactly this reason.

## Never build SQL from user input
The rule: **no request data ever becomes part of the SQL text.** Values go in placeholders. But some parts of a query cannot be placeholders: column names, table names and sort direction. For `GET /v1/tasks?sort=due_date&dir=desc`, use an **allow-list**, mapping input to fixed strings you wrote yourself:

```
SORTS = {"due_date": "due_date", "created": "created_at", "title": "title"}
column = SORTS.get(request.query["sort"])          # unknown -> None
if column is None: return 400 {"error": "invalid_sort"}
direction = "DESC" if request.query["dir"] == "desc" else "ASC"
sql = "SELECT ... WHERE owner_id = $1 ORDER BY " + column + " " + direction
```

The only strings concatenated are ones from your code, never from the user.

What does **not** work: escaping quotes by hand (OWASP strongly discourages it; it is database-specific and easy to get wrong), blocking "bad words" like `DROP`, or trusting that the front end validated input. Attackers call the API directly with curl.

## Transactions: all or nothing
A **transaction** groups several SQL statements into one all-or-nothing unit. Either every step takes effect, or none does.

```sql
BEGIN;        -- start the transaction
-- statement 1
-- statement 2
COMMIT;       -- make all changes permanent
-- or ROLLBACK;  to cancel everything since BEGIN
```

Key properties from the PostgreSQL tutorial:

- **Atomic**: if anything fails before COMMIT, the earlier steps are undone too. The PostgreSQL bank example: money is never taken from Alice without being added to Bob.
- **Invisible until committed**: other connections do not see half-finished changes; at COMMIT they all appear at once.
- **Durable**: once COMMIT succeeds, the changes are on disk and survive a crash.

Without an explicit `BEGIN`, PostgreSQL wraps each single statement in its own transaction. You need `BEGIN ... COMMIT` whenever **one API request makes several changes** that only make sense together. In code, always roll back if any step throws, before returning the error response.

## Worked example: deleting a user and their tasks
Bob deletes his account with `DELETE /v1/users/456`. The foreign key uses the default `NO ACTION`, so the user row cannot go while tasks still point at it. The server deletes the tasks first, then the user, in one transaction:

```sql
BEGIN;
DELETE FROM tasks WHERE owner_id = $1;     -- 456; reports DELETE 2
DELETE FROM users WHERE id = $1;           -- 456; reports DELETE 1
COMMIT;
```

If the second DELETE reports 0 rows, the user does not exist: the server issues `ROLLBACK` and replies 404 Not Found. If the database fails between the two statements, the transaction is rolled back automatically: Bob's tasks are **not** lost while his account remains half-deleted. On success:

```http
HTTP/1.1 204 No Content
```

Alternative design: declare `owner_id ... REFERENCES users (id) ON DELETE CASCADE`, and then a single `DELETE FROM users WHERE id = $1` removes the tasks too, atomically, because it is one statement. Either way, the user id comes from the token and must match the URL, or the server replies 403 Forbidden.

## Common mistakes: ownership, injection, races
**Mistake 1: owner id from the request.** `WHERE owner_id = $1` with `$1 = request.query["owner_id"]`. Why it's wrong: the client controls it, so Bob reads Alice's tasks. Correct: `$1` from the verified token.

**Mistake 2: string-building SQL "just for this one query".** `"... WHERE title ILIKE '%" + q + "%'"`. Why it's wrong: one concatenated value is enough for injection. Correct: `ILIKE '%' || $2 || '%'` with `q` as a parameter; allow-list column names.

**Mistake 3: relying on check-then-insert for uniqueness.** Why it's wrong: two concurrent requests both pass the check. Correct: a UNIQUE constraint, then map the unique-violation error to 409 Conflict.

## Common mistakes: errors and transactions
**Mistake 4: returning raw database errors.** Sending `ERROR: duplicate key ... "users_email_key"` or a syntax error to the client reveals table names and helps attackers probe for injection. Correct: log the detail on the server; send a clean 409 or 500 body.

**Mistake 5: multi-step changes without a transaction.** Deleting tasks and then the user as two independent statements can leave half the work done after a failure. Correct: wrap them in `BEGIN ... COMMIT`, or use one statement with `ON DELETE CASCADE`.

## Summary
- A foreign key (`tasks.owner_id REFERENCES users (id)`) guarantees every task points at a real user and blocks or cascades deletes of users with tasks.
- Foreign keys enforce consistency, not privacy: queries must filter with `owner_id = $1`, and `$1` must come from the authenticated user, never the request.
- `JOIN ... ON tasks.owner_id = users.id` combines tables; qualify column names; LEFT JOIN keeps unmatched left rows.
- A UNIQUE constraint on `users.email` turns duplicate sign-ups into a database error you map to 409 Conflict. Check-then-insert alone loses races.
- SQL injection = user input concatenated into SQL text; `' OR 1=1 --` can expose every row.
- Fix: parameterized queries for values, allow-lists for identifiers; never escape by hand.
- Transactions (`BEGIN`/`COMMIT`/`ROLLBACK`) make multi-step changes all-or-nothing.

## Exercise: Review the search endpoint
<!-- meta: kind=exercise, difficulty=beginner -->

A teammate adds a filter to TaskFlow: `GET /v1/tasks?owner=123&title=milk`. The server code is:

```
sql = "SELECT id, title, done FROM tasks WHERE owner_id = " + request.query["owner"] +
      " AND title ILIKE '%" + request.query["title"] + "%'"
rows = db.query(sql)
```

1. Identify the two separate security problems in this code.
2. Bob is user 456. Give one concrete request Bob could send to see Alice's tasks without any SQL tricks, and one request containing a `title` value that would return every task in the database. Write out the SQL the database would receive for the second.
3. Rewrite the query safely, saying where each value comes from.

## Exercise: Sign-up and account deletion
<!-- meta: kind=exercise, difficulty=beginner -->

TaskFlow's sign-up endpoint (`POST /v1/users`) currently runs `SELECT 1 FROM users WHERE email = $1`, returns 409 if a row is found, and otherwise runs the INSERT. The `users` table has no UNIQUE constraint on `email`.

1. Describe, step by step, how two simultaneous sign-ups with `bob@example.com` can create two accounts.
2. Propose a fix at the database level and describe what the server does when the duplicate is detected, including the status code and body.
3. Later, Bob deletes his account with `DELETE /v1/users/456`. Bob has 3 tasks and `tasks.owner_id` is a foreign key with the default `ON DELETE` behaviour. Explain what happens if the server only runs `DELETE FROM users WHERE id = $1`, and give two correct designs.
