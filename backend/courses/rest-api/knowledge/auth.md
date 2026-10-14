---
id: auth
concept: Authentication and Authorization
capability: authn-authz
difficulty: beginner
prerequisites: [rest-api, databases-crud]
source: "OWASP API Security Top 10 2023 — API1:2023 Broken Object Level Authorization (https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/); OWASP Authorization Cheat Sheet (https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html); OWASP Authentication Cheat Sheet; MDN Web Docs — HTTP authentication"
---

# Authentication and Authorization

## Authentication vs authorization

These two words sound alike but answer different questions.

- **Authentication** answers "who are you?" The server checks that you really are the
  person or program you claim to be, for example by checking a password.
- **Authorization** answers "what are you allowed to do?" Once the server knows who you
  are, it decides whether you may read, change or delete a particular thing.

Think of an office building. Your badge proves who you are: that is authentication. The
door rules decide which rooms your badge opens: that is authorization. Having a valid
badge does not mean every door opens for you.

Authentication always comes first, because you cannot decide what someone is allowed to
do until you know who they are. But passing authentication is only half the job. Many
real security bugs happen when a server checks *who* you are and then forgets to check
*what* you are allowed to touch.

## How an API knows who you are

HTTP is stateless: the server does not remember you between requests. So the usual flow
is:

1. You log in once, for example by sending your email and password to `POST /login`.
2. If they are correct, the server gives you a credential: either a **session cookie**
   (a random ID the server links to your account) or a **token** (a string the server
   can verify, such as a signed JWT).
3. Your client sends that credential with **every** later request. A token usually goes
   in a header:

```
GET /users/123 HTTP/1.1
Authorization: Bearer eyJhbGciOi...
```

4. On every request, the server verifies the credential and works out which user it
   belongs to. That user is the **authenticated user** for this request.

Credentials should only travel over HTTPS, so nobody on the network can copy them.

## Passwords are never stored in plain text

A server must never save your actual password. If the database leaked, every password
would be exposed, and people reuse passwords on other sites. Instead the server stores a
**hash**: the result of a one-way function that turns the password into a fixed string
that cannot practically be turned back. At login, the server hashes the password you
typed and compares the result with the stored hash.

The hashing algorithm should be deliberately **slow** and **salted** (a random value is
mixed in for each user), so an attacker who steals the hashes cannot quickly try
billions of guesses. OWASP recommends algorithms built for this, such as **Argon2id** or
**bcrypt**. Fast general-purpose hashes like MD5 or plain SHA-256 are not suitable for
passwords.

## 401 vs 403

Two status codes cover the two questions, and beginners often mix them up.

- **401 Unauthorized** means "I don't know who you are." The credential is missing,
  expired or invalid. Despite its name, 401 is about **authentication**. The fix for the
  client is to log in (again) and send a valid credential.
- **403 Forbidden** means "I know who you are, and you are not allowed to do this." The
  credential is fine, but the user lacks permission. This is about **authorization**.
  Logging in again will not help.

A quick test: if sending a valid login would fix the problem, it is a 401. If the user
is already logged in and still should not get in, it is a 403.

## Authorization checks happen on the server, on every request

The client — a browser, a mobile app, a script — is under the user's control. Anyone can
open developer tools, edit a URL, or send requests with a tool like `curl`, skipping
your app entirely. So the server must **never trust the client** to enforce rules.

Hiding a "Delete" button for regular users makes the UI nicer, but it is **not
security**. If the server accepts `DELETE /projects/7` from anyone who is logged in, an
attacker simply sends that request directly.

The rule from the OWASP Authorization Cheat Sheet: enforce access control on the server,
check permissions on **every** request (not only the first one), and **deny by default**
— if no rule says the user is allowed, the answer is no.

## Object-level authorization: does THIS user own THIS resource?

Here is a very common bug. A student logs in and opens their profile:

```
GET /users/123
Authorization: Bearer <student 123's token>
```

They notice the `123` in the URL, change it to `456`, and the server returns another
student's private data. The server checked that the token was valid (authentication
passed) but never checked whether user 123 is allowed to see user 456.

This is **Broken Object Level Authorization (BOLA)**, number one on the OWASP API
Security Top 10 2023 (API1:2023). It is also known as **IDOR** (Insecure Direct Object
Reference). It is common because APIs put object IDs right in the URL, and because each
endpoint needs its own check — forgetting one is easy.

The fix is an **object-level check**: on every request that touches a specific object,
the server asks "is the authenticated user allowed to access *this* object?"

## The misconception: "hide or randomise the ID"

A common first reaction to the `/users/456` bug is "we should hide the user ID" or "use
random IDs so nobody can guess them". This does **not** fix the problem.

- IDs **leak**. They appear in links people share, browser history, server logs,
  screenshots, emails and other API responses.
- IDs get **guessed or collected**. Sequential numbers are trivial to guess, and even
  random ones can be found once they leak.
- Random IDs such as UUIDs make guessing **harder**, which is a reasonable extra layer,
  but OWASP is clear that unpredictable IDs are not a replacement for an authorization
  check.

Hiding the ID only makes the door harder to find. It does not lock it. The real fix is
always the same: the server checks, on every request, that the authenticated user is
allowed to access that specific resource.

## Writing the check

The key idea: take the user's identity from the **verified credential**, never from the
URL or request body, then compare it with the resource.

Option 1, load then compare:

```
current_user = verify_token(request)        # 401 if missing or invalid
task = db.find_task(task_id)
if task is None:
    return 404
if task.owner_id != current_user.id:
    return 403   # or 404, see next section
return task
```

Option 2, put the check inside the query, so another user's row is never even loaded:

```sql
SELECT * FROM tasks WHERE id = $1 AND owner_id = $2;
-- $1 = task id from the URL, $2 = id of the authenticated user
```

If no row comes back, the user either asked for something that does not exist or
something that is not theirs. Do the same for updates and deletes, not only for reads.

## 403 or 404 for someone else's resource?

When a user asks for an object that exists but belongs to someone else, APIs use one of
two answers, and both are accepted practice:

- **403 Forbidden** is the literal meaning: "you are not allowed". It is clear and
  helpful when debugging.
- **404 Not Found** pretends the object is not there for this user. This avoids
  revealing that the object exists at all, which can matter when existence itself is
  sensitive (for example, whether an account exists).

Choose one approach and use it consistently. What matters far more than which code you
pick is that the data is **not returned**. Returning 200 with someone else's data is the
bug, whatever the code would otherwise have been.

## Roles and permissions

Not every user is equal. A **role** groups permissions: an `admin` might be allowed to
delete any account, while a regular `student` may only edit their own profile.

Two kinds of checks work together:

- **Role (or function-level) checks** decide whether a user may perform an *action* at
  all: "only admins may call `DELETE /users/{id}`".
- **Ownership (object-level) checks** decide whether a user may act on a *specific
  object*: "a student may update `/tasks/42` only if task 42 is theirs".

A role check alone is not enough. Two students have the same role, yet neither should
read the other's tasks. Most endpoints need both: "is this kind of user allowed to do
this action?" and "is this user allowed to do it to this object?"

## Exercise: Find the broken access control
<!-- meta: kind=exercise, difficulty=beginner -->

A task-management API lets each user keep private to-do lists. User Alice (id 123) logs
in and receives a valid token. She calls `GET /users/123/tasks` and sees her tasks. Out
of curiosity she changes the URL to `GET /users/456/tasks`, sending the same token, and
receives `200 OK` with Bob's private tasks.

The server code for this endpoint verifies the token and then runs
`SELECT * FROM tasks WHERE user_id = <id from the URL>`.

Answer four questions: What exactly is wrong, and which authentication or authorization
step is missing? What check must the server perform, and where does the user's identity
for that check come from? What status code should Alice receive instead of 200? A
teammate suggests switching to random UUIDs instead of numbers — would that fix it?

## Exercise: Authentication or authorization?
<!-- meta: kind=exercise, difficulty=beginner -->

For each situation, say whether it is an authentication problem or an authorization
problem, and which status code the API should return.

1. A request to `GET /me` arrives with no `Authorization` header at all.
2. A logged-in regular user calls `DELETE /users/88`, an endpoint only admins may use.
3. A user sends a token that expired yesterday.
4. A logged-in student requests `GET /grades/991`, which is another student's grade
   record.
