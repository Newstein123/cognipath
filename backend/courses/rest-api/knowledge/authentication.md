---
id: authentication
concept: "Authentication: Who Are You?"
capability: authentication
difficulty: beginner
prerequisites: [endpoint-design]
source: "Adapted from MDN Web Docs — HTTP authentication (https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Authentication), Using HTTP cookies (https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies), 401 Unauthorized (https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/401), by Mozilla Contributors, CC BY-SA 2.5; OWASP Cheat Sheet Series — Authentication (https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html), Password Storage (https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html), Session Management (https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), CC BY-SA 4.0"
---

# Authentication: Who Are You?

## Why this matters

Think of an office building. At the entrance you show ID and receive a badge. The badge proves **who you are**. Separately, each door has rules about whose badge opens it: everyone may enter the lobby, only the finance team may enter the finance room. Those door rules decide **which rooms you may enter**.

Before TaskFlow can show Alice "her" tasks, it must be sure the request really comes from Alice. If that step is weak, nothing built on it can be trusted.

This unit covers the badge: **authentication**. The next unit, Authorization, covers the door rules. They work together but answer different questions.

## Authentication vs authorization

Two words that sound alike and are constantly confused:

- **Authentication (authn)** — proving *who* is making the request. "This request comes from user 123, Alice."
- **Authorization (authz)** — deciding *what* that identity is allowed to do. "User 123 may read task 42 because she owns it."

Authentication always comes first: you cannot decide what someone may do until you know who they are. A request can pass authentication and still fail authorization (Alice is really Alice, but task 77 belongs to Bob).

**Credentials** are the things a client presents to prove identity: an email + password at login, and afterwards a session cookie or a token on each request.

HTTP status codes follow the same split. **401 Unauthorized** means "I don't know who you are" (an authentication problem, despite the name). **403 Forbidden** means "I know who you are, and you may not do this" (an authorization problem, covered in the next unit).

## Worked example: Logging in with a session cookie

Alice opens the TaskFlow web app and types her email and password. The app sends them in the request **body** of `POST /login`, never in the URL:

```http
POST /v1/login HTTP/1.1
Host: api.taskflow.example
Content-Type: application/json

{"email": "alice@example.com", "password": "correct horse battery"}
```

The server looks up the user by email, checks the password against the stored hash, and creates a **session**: a random ID it remembers on its side. It hands the ID to the browser in a cookie:

```http
HTTP/1.1 200 OK
Set-Cookie: __Host-tf_session=Gk3vQ9xL2pR7mWz8aT1yB4nC; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=1800
Content-Type: application/json

{"user": {"id": 123, "name": "Alice"}}
```

Step by step: `Secure` means the cookie only travels over HTTPS; `HttpOnly` means page JavaScript cannot read it; `SameSite=Strict` stops it being sent on requests started by other sites; `Max-Age=1800` makes it expire after 30 minutes. The browser now stores the cookie and attaches it automatically from here on.

## Worked example: Logging in with a token

A mobile app or a script often prefers a **token** instead of a cookie. The login request is identical; the response differs:

```http
POST /v1/login HTTP/1.1
Host: api.taskflow.example
Content-Type: application/json

{"email": "alice@example.com", "password": "correct horse battery"}

HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjMi...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

The client must keep this string and attach it to every later request itself. `expires_in: 3600` = valid for one hour. `Cache-Control: no-store` asks caches not to keep this credential-bearing response.

The same curl call from a terminal:

```bash
curl -X POST https://api.taskflow.example/v1/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"correct horse battery"}'
```

## Sending credentials on every request

HTTP is **stateless**: each request stands alone, and the server does not "remember" that Alice logged in a minute ago on the same connection. So the client must prove its identity on **every** request after login. There are two common places to put the credential.

With a session cookie, the browser adds a `Cookie` header automatically:

```http
GET /v1/tasks HTTP/1.1
Host: api.taskflow.example
Cookie: __Host-tf_session=Gk3vQ9xL2pR7mWz8aT1yB4nC
```

With a token, the client adds an `Authorization` header using the `Bearer` scheme ("whoever bears this token is the user"):

```http
GET /v1/tasks HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Either way, the server works out "this is user 123" before handling the request. General format: `Authorization: <scheme> <credentials>`.

## Sessions: the server remembers

With **sessions**, the server keeps a record and the client holds only a meaningless key to it.

What the server stores (for example in a `sessions` table or a fast store such as Redis):

```sql
-- id is the random value sent in the cookie
SELECT user_id, expires_at FROM sessions
WHERE id = 'Gk3vQ9xL2pR7mWz8aT1yB4nC';
-- user_id = 123, expires_at = 2026-10-14 10:30:00+00
```

How each request is checked: read the cookie, look up the session ID, reject it if it is missing or past `expires_at`, otherwise treat the request as user 123.

Rules from OWASP: the session ID must be random and unguessable (at least 64 bits of entropy from a cryptographically secure generator) and must contain no personal data; issue a **new** session ID at login (so an attacker cannot plant one in advance, called session fixation); and on logout **delete the session on the server**, not just the cookie in the browser. Because the server holds the record, it can end a session instantly.

## Tokens: the server verifies

With a **self-contained token** such as a JWT, the token itself carries the facts ("user 123, expires at 10:20") plus a **signature** that only the server can produce. The server does not need to look anything up; it checks the token mathematically.

How each request is checked:

1. Read the `Authorization: Bearer ...` header.
2. Verify the signature with the server's secret key. If anyone changed even one character, verification fails.
3. Check the expiry time (`exp`). If it is in the past, reject.
4. Read the user ID from the token (`sub: "123"`).

What the server stores: only its signing key, no record per login. The catch: a valid token keeps working until it expires, even after "log out", unless the server adds a deny-list. So access tokens are usually **short-lived** (minutes to an hour).

Not every token is self-contained: some are just random strings that the server looks up, which behaves like a session.

## Sessions vs tokens: expiry and logout

| | Session cookie | Self-contained token (JWT) |
|---|---|---|
| Client holds | random session ID | signed token with claims |
| Server stores | a session record per login | only its signing key |
| Checked by | lookup in session store | signature + `exp` check |
| Sent in | `Cookie` header (automatic) | `Authorization: Bearer` (by the app) |
| Logout | delete the record: works instantly | token stays valid until `exp` |

Both must **expire**. OWASP recommends two timeouts for sessions, enforced on the server: an **idle timeout** (for example 15–30 minutes of no activity for a low-risk app) and an **absolute timeout** (for example 4–8 hours, however active the user is). For tokens the expiry is written inside the token.

Neither is "the secure one"; both are fine when done properly.

## What a JWT is

A **JSON Web Token (JWT)**, pronounced "jot", is a token made of three Base64URL-encoded parts joined by dots: `header.payload.signature`. Here is a real one for Alice:

```text
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
.eyJzdWIiOiIxMjMiLCJuYW1lIjoiQWxpY2UiLCJpYXQiOjE3NjA0MzAwMDAsImV4cCI6MTc2MDQzMzYwMH0
.7yVeawaWH1Jsrl-Dj4ZG7blUxOQaA4sAueNx_kDA2E8
```

(Line breaks added for reading; the real token is one line.) Decoded:

```json
{"alg": "HS256", "typ": "JWT"}
{"sub": "123", "name": "Alice", "iat": 1760430000, "exp": 1760433600}
```

- **Header** — which algorithm signed it (`HS256` = HMAC with SHA-256).
- **Payload** — the **claims**: `sub` (subject, the user ID), `iat` (issued at) and `exp` (expires at), as Unix timestamps.
- **Signature** — computed from header + payload with the server's secret key. It proves the server issued the token and nobody edited it.

## JWTs are signed, not encrypted

The most important fact about a JWT: **anyone can read the payload.** Base64URL is an encoding, not encryption. Paste a JWT into any decoder and the claims appear in plain text.

The signature gives **integrity**, not secrecy. If Alice edits her payload to say `"sub": "456"` hoping to become Bob, the signature no longer matches and the server rejects the token. But she can still *read* everything inside.

Consequences:

- **Never put secrets in a JWT**: no passwords, no password hashes, no API keys, no private personal data.
- Put only what the server needs to identify the user: an ID, an expiry, perhaps a role.
- The server must actually **verify** the signature and the `exp` claim on every request; decoding without verifying is the same as trusting whatever the client wrote.
- A JWT is still a credential: whoever steals it can act as Alice until it expires.

## Storing passwords: never plain text

The server must **never** store the password itself (plain text), nor encrypt it (whoever gets the key gets every password).

Instead, store a **password hash**: the output of a one-way function. At login, hash what the user typed and compare. A stolen hash cannot be turned back into the password.

Two extra ingredients matter:

- **Salt** — a random value, unique per user, mixed in before hashing. Two users with the same password get different hashes, and precomputed "rainbow tables" become useless.
- **Slowness** — fast hashes (MD5, SHA-1, SHA-256) let an attacker with a GPU try billions of guesses per second against a stolen database. Password hashing algorithms are deliberately **slow** (and Argon2id is also memory-hard).

OWASP's recommendation: **Argon2id** (minimum m=19 MiB memory, t=2 iterations, p=1); scrypt if Argon2id is unavailable; **bcrypt** for legacy systems with a work factor of at least 10 (and note bcrypt only uses the first 72 bytes of the password).

## Worked example: What the users table stores

Alice signs up with the password `correct horse battery`. Here is what the `users` table should and should not hold.

Wrong (plain text — one database leak exposes every password):

```text
 id  | email             | password
 123 | alice@example.com | correct horse battery
```

Also wrong (fast, unsalted SHA-256 — same password, same hash; guessing is cheap):

```text
 123 | alice@example.com | 9028ea0d15decaa35b2da21c0290af3b1a5ba0a30a591906f89b5074e209ea72
```

Right (Argon2id in the standard "PHC string" format; values shortened):

```text
 id  | email             | password_hash
 123 | alice@example.com | $argon2id$v=19$m=19456,t=2,p=1$c2FsdHlTYWx0MTIz$Jx9k...Qw
```

Left to right: algorithm, version, cost parameters (memory, iterations, parallelism), the **salt**, then the hash. Keeping the parameters in the string lets the server raise the cost later and re-hash at the user's next login. At login it hashes the typed password with that salt and those parameters and compares.

## 401 Unauthorized and WWW-Authenticate

**401 Unauthorized** means: this request does not carry **valid authentication credentials**. Despite its name it is about authentication ("who are you?"), not permission. Typical causes on TaskFlow:

- **Missing** — no `Cookie` or `Authorization` header at all.
- **Invalid** — the token's signature is wrong, the session ID is unknown, or the login password was wrong.
- **Expired** — the token's `exp` has passed or the session timed out.

A 401 tells the client "authenticate (again) and retry", which might succeed. Contrast with 403, where re-authenticating changes nothing.

The HTTP standard says a 401 response carries a **`WWW-Authenticate`** header naming the scheme the server expects, so the client knows how to retry:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="taskflow"
```

For Bearer tokens, the header may add an `error` such as `invalid_token` with a short description. Keep descriptions brief and never echo the token back.

## Worked example: Missing, invalid and expired credentials

Three failed requests to the same endpoint, each answered 401.

1) No credentials at all:

```http
GET /v1/tasks HTTP/1.1
Host: api.taskflow.example

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="taskflow"
Content-Type: application/json

{"error": "authentication_required"}
```

2) Tampered token (someone edited the payload, so the signature fails):

```http
GET /v1/tasks HTTP/1.1
Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiI0NTYifQ.7yVeaw...

HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="taskflow", error="invalid_token"
```

3) Token past its `exp` (issued 09:20, valid one hour, now 10:45):

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="taskflow", error="invalid_token", error_description="token expired"
```

In every case the server does **not** run the handler or return partial data. The client's fix is the same: log in again (or refresh the token) and retry.

## HTTPS is required

Everything in this unit assumes **HTTPS** (HTTP over TLS). Without it, every byte travels in readable form across Wi-Fi networks, routers and proxies:

- The `POST /login` body exposes Alice's password.
- The `Cookie` or `Authorization` header exposes her session or token, and anyone who copies it **is** Alice until it expires (session hijacking).

OWASP: the login page and all authenticated pages must be served exclusively over TLS. In practice for an API:

- Serve `https://api.taskflow.example` only; refuse or redirect plain `http://` before any credential is sent.
- Mark session cookies `Secure` so the browser never sends them over plain HTTP.
- Remember that Basic authentication and Base64 are encodings, not protection: `Basic YWxpY2U6c2VjcmV0` decodes instantly to `alice:secret`.

HTTPS protects credentials **in transit**; it does not replace password hashing (**at rest**).

## Common mistakes: Credentials in URLs and browser storage

**Mistake: passwords or tokens in the URL.** `GET /v1/login?email=alice@example.com&password=correct+horse+battery` or `GET /v1/tasks?token=eyJ...`. *Why it's wrong:* URLs end up in server and proxy logs, browser history and bookmarks; HTTPS does not hide them there. *Correct:* send the password in the body of `POST /login`; send tokens in the `Authorization` header.

**Mistake: storing tokens in `localStorage` without thinking about XSS.** *Why it's risky:* any JavaScript running on the page can read `localStorage`. If an attacker manages to inject a script (a cross-site scripting bug), they can copy the token and use it elsewhere. OWASP advises against keeping session IDs or tokens in web storage. *Correct (careful version):* for browser apps, prefer an `HttpOnly; Secure; SameSite` session cookie, which scripts cannot read. Cookies bring their own concern (cross-site request forgery), handled by `SameSite` and CSRF protections; preventing XSS matters either way.

## Common mistakes: Login errors that leak information

**Mistake: different answers for "unknown email" and "wrong password".**

```json
{"error": "No account with email bob@example.com"}
{"error": "Wrong password for bob@example.com"}
```

*Why it's wrong:* an attacker can now test a list of emails and learn which ones have TaskFlow accounts (user enumeration), then focus password guessing on them. Different status codes, or a noticeably faster reply for unknown emails, leak the same fact.

*Correct:* one generic message and the same status for every failure, with similar response time:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{"error": "invalid_credentials", "message": "Invalid email or password."}
```

The same idea applies to password reset: "If that email address is registered, we have sent a reset link."

**Mistake: unlimited login attempts.** *Correct:* limit failed attempts per account, slow down repeated failures, and offer multi-factor authentication (OWASP calls MFA by far the best defence against most password attacks).

## Summary

- **Authentication** proves who you are (the badge); **authorization** decides what you may do (the door rules). Authentication comes first; this unit is that first half.
- Log in with `POST /login`, credentials in the JSON **body**; the server answers with a session cookie or a token.
- HTTP is stateless, so send the credential on **every** request: `Cookie:` header or `Authorization: Bearer`.
- **Sessions**: server stores a record, client holds a random ID, logout deletes the record. **Tokens**: server verifies a signature and `exp`, stores no per-login record, so keep them short-lived.
- A **JWT** is `header.payload.signature`: signed, **not** encrypted. Anyone can read it; never put secrets in it; always verify it.
- Store passwords as **slow, salted hashes** (Argon2id, or bcrypt for legacy), never plain text or fast SHA-256/MD5.
- **401** = missing, invalid or expired credentials, sent with `WWW-Authenticate`.
- Use **HTTPS** everywhere; keep credentials out of URLs; prefer `HttpOnly` cookies in browsers; give one generic login error.

## Exercise: Review the TaskFlow login design
<!-- meta: kind=exercise, difficulty=beginner -->

A new teammate proposes this design for TaskFlow and asks for your review:

1. Users log in with `GET /v1/login?email=...&password=...`.
2. Passwords are stored in the `users` table as unsalted SHA-256 hashes "because SHA-256 is secure".
3. A wrong password returns `404 {"error": "email not found"}` or `401 {"error": "wrong password"}` depending on the case.
4. After login the server returns a JWT whose payload contains `{"sub": "123", "email": "alice@example.com", "password_hash": "..."}` and which never expires.

For each of the four points, explain what is wrong and why, and describe the corrected version (method and where credentials go, how passwords are stored, what the error response looks like, and what the token should contain).

## Exercise: Sessions or tokens after logout
<!-- meta: kind=exercise, difficulty=beginner -->

Alice logs in to TaskFlow on a library computer, then clicks "Log out" and leaves. Ten minutes later, someone else uses a copy of the credential her browser sent.

Compare two versions of TaskFlow: (a) one that uses a server-side session in an `HttpOnly; Secure` cookie, and (b) one that uses a JWT valid for 24 hours. For each, explain what the server stores, how it checks the copied credential, and whether the attacker's request `GET /v1/tasks` succeeds or receives `401 Unauthorized`. Then recommend one change that would reduce the risk in version (b).
