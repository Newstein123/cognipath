---
id: web-basics
concept: How the Web Works
capability: web-basics
difficulty: beginner
prerequisites: []
source: "Adapted from MDN Web Docs — How the web works (https://developer.mozilla.org/en-US/docs/Learn_web_development/Getting_started/Web_standards/How_the_web_works), Overview of HTTP (https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Overview), What is a URL? (https://developer.mozilla.org/en-US/docs/Learn_web_development/Howto/Web_mechanics/What_is_a_URL), DNS glossary (https://developer.mozilla.org/en-US/docs/Glossary/DNS), API glossary (https://developer.mozilla.org/en-US/docs/Glossary/API), by Mozilla Contributors, CC BY-SA 2.5"
---

# How the Web Works

## Why this matters

Every time you open an app, check the weather, or load a web page, two computers have a short conversation. One asks for something; the other answers. A backend engineer builds the side that answers.

Think of a restaurant. You (the customer) do not walk into the kitchen. You tell the waiter what you want, the kitchen prepares it, and the waiter brings it back. You never need to know how the kitchen is organised — only how to order.

The web works the same way. In this course we build the "kitchen" for TaskFlow, a task-management app whose server lives at `https://api.taskflow.example/v1`. Before we can design its API, we need a clear picture of who asks, who answers, how they find each other, and what the messages look like. Everything later in the course — methods, status codes, JSON, authentication — sits on top of the ideas in this unit.

## Clients and servers

A **client** is the program that starts a conversation by asking for something. Examples: Chrome or Firefox on a laptop, the TaskFlow app on Alice's phone, or a script running on another company's computer.

A **server** is a computer (and the software on it) that waits for requests and answers them. It stores web pages, files, or data — for TaskFlow, the server stores users and tasks in a database.

Key facts:

- The **client always starts**. A server does not suddenly send Alice a page she did not ask for; it responds to requests.
- One server talks to **many clients**. Alice (user 123) and Bob (user 456) both send requests to the same TaskFlow server.
- "Server" describes a **role**, not a special kind of machine. Your own laptop can run a server while you develop.

MDN calls the program acting for the user the **user agent** — usually a browser, but it can also be an app, a command-line tool, or a web crawler.

## The request–response cycle

All communication on the web follows one pattern, the **request–response cycle**:

1. The client sends a **request**: "Please give me X" or "Please do Y".
2. The server **processes** it: looks things up, checks permissions, changes data.
3. The server sends back a **response**: the result, plus a code saying whether it worked.
4. The cycle ends. The next thing the client wants needs a new request.

Back to the restaurant:

- **You order** ("one pasta, no cheese") — that is the request.
- **The kitchen prepares** the dish — that is the server processing.
- **The waiter brings your order** (or says "sorry, we are out of pasta") — that is the response.

Each order is a complete round trip. If you want dessert, you order again. Requests and responses are individual **messages**, not a continuous stream of data.

## Mapping the restaurant to HTTP

The language that web clients and servers speak is **HTTP** (Hypertext Transfer Protocol). Here is the restaurant mapped onto it:

| Restaurant | HTTP / TaskFlow |
|---|---|
| Customer | Client (browser, TaskFlow app) |
| Kitchen | Server at `api.taskflow.example` |
| Restaurant address | Domain name, found through DNS |
| "I'd like…" | Method, e.g. `GET` (fetch) or `POST` (create) |
| Which dish | Path, e.g. `/v1/tasks/42` |
| "No cheese, please" | Headers and body (extra details) |
| "Here you go" / "Sorry, sold out" | Status code, e.g. `200 OK` or `404 Not Found` |
| The plate of food | Response body, e.g. JSON |

The waiter is the network: it carries messages but does not decide what to cook. HTTP messages travel over **TCP/IP**, the lower-level rules for moving data across the internet in small chunks called **packets**.

## What a URL is

A **URL** (Uniform Resource Locator) is the address of one resource on the web. Its general shape is:

```
scheme://host:port/path?query#fragment
```

Take this TaskFlow URL:

```
https://api.taskflow.example/v1/tasks?done=false&sort=due_date
```

- **Scheme** `https` — the protocol to use. HTTPS is HTTP with encryption.
- **Host** (domain) `api.taskflow.example` — which server to contact.
- **Port** — omitted here, so the default is used: 443 for HTTPS, 80 for HTTP.
- **Path** `/v1/tasks` — which resource on that server. Today a path is usually not a real file; the server decides what it means.
- **Query** `?done=false&sort=due_date` — extra key=value parameters, separated by `&`.
- **Fragment** `#...` — points inside a page and is **never sent to the server**.

## DNS: the internet's address book

Computers find each other using **IP addresses**, numbers like `192.0.2.172`. Humans prefer names like `api.taskflow.example`. The **Domain Name System (DNS)** translates one into the other.

A **DNS lookup** works like looking up a contact on your phone: you tap "Pizza Place" and the phone dials the number stored for it. The client asks a DNS resolver "what is the IP address of `api.taskflow.example`?" and gets back an address it can connect to.

Useful facts:

- DNS is **hierarchical and decentralised** — no single computer holds every name.
- Results are **cached**, so repeated visits skip the lookup.
- Big services may have **several servers**, so the IP you receive can depend on where you are.
- DNS only finds the server. It does not carry your request or know anything about tasks.

## What happens when you type a web address

When you type `https://taskflow.example` into a browser and press Enter:

1. **Parse the URL.** The browser splits out scheme `https`, host `taskflow.example`, path `/`.
2. **DNS lookup.** The browser finds the server's IP address (or uses a cached one).
3. **Connect.** It opens a TCP connection to that IP on port 443 and sets up encryption (TLS) because the scheme is HTTPS.
4. **Send the request.** For example `GET / HTTP/1.1` with a `Host: taskflow.example` header.
5. **Server responds.** If all is well: `200 OK` plus an HTML page, sent as a series of packets.
6. **Render.** The browser reassembles the packets, reads the HTML, and sends *more* requests for the CSS, JavaScript, and images the page needs.
7. **Close or reuse** the connection for later requests.

One page view can therefore mean dozens of request–response cycles.

## What happens when an app loads data

A mobile app or a JavaScript front end does not want a whole web page. It wants **data**, which it then displays in its own screens.

When Alice opens the TaskFlow app:

1. The app already knows the base URL `https://api.taskflow.example/v1`.
2. It does a DNS lookup for `api.taskflow.example` and connects on port 443.
3. It sends `GET /v1/tasks` with a header proving it is Alice.
4. The server checks who she is, queries the database for tasks where `owner_id = 123`, and builds a reply.
5. The server responds `200 OK` with a **JSON** body — a list of tasks, not HTML.
6. The app turns that JSON into the task list on screen.

The plumbing (DNS, TCP, HTTP) is identical to the browser case. The difference is what travels in the body: structured data meant for a program, not a page meant for a human.

## HTTP is stateless

HTTP is **stateless**: each request is handled on its own, with no built-in memory of earlier requests — even ones sent over the same connection.

Restaurant version: imagine a waiter with no memory. If you say "same again", they have no idea what you had. You must say the full order every time.

Consequences for TaskFlow:

- Every request must carry **everything the server needs**: who the user is (usually an `Authorization` header) and which resource is meant.
- The server does not "remember" that Alice logged in a minute ago unless she sends proof again.
- Because no request depends on server memory of the previous one, **any** of several identical servers can answer it. This makes scaling much easier.

Stateless does not mean "sessionless". Sites build sessions *on top* of HTTP by having the client resend a cookie or token with each request.

## What an API is

An **API** (Application Programming Interface) is a set of rules that lets one piece of software use another. A web page is an interface for **people**; an API is an interface for **programs**.

MDN describes an API as a **contract**: the application offering it promises "if you send me a request shaped like this, I will answer like that."

A **web API** is an API reached over HTTP. TaskFlow's API is a list of URLs and methods with agreed meanings:

```
GET    /tasks          list my tasks
POST   /tasks          create a task
GET    /tasks/{id}     read one task
PUT    /tasks/{id}     replace a task
PATCH  /tasks/{id}     change part of a task
DELETE /tasks/{id}     delete a task
POST   /login          sign in
```

The app on Alice's phone does not read HTML; it calls these endpoints and gets JSON back. The word **endpoint** means one method + path combination of an API.

## Three kinds of clients

The same TaskFlow API can serve very different clients:

- **Browser.** A person visits `https://taskflow.example`. The browser downloads HTML, CSS, and JavaScript; then the JavaScript calls `https://api.taskflow.example/v1/tasks` to fetch data.
- **Mobile app.** The TaskFlow iOS/Android app has its screens built in. It only needs data, so it calls the API directly and receives JSON.
- **Server-to-server.** No human is involved at all. For example, a calendar company's server calls TaskFlow's API every night to copy due dates into users' calendars, or TaskFlow's own server calls an email service's API to send reminders.

To the TaskFlow server these all look the same: an HTTP request arrives, and a response goes back. That is why one well-designed API can support a website, two phone apps, and partner integrations at once.

## Worked example: Reading a TaskFlow URL

**Problem.** Bob's app requests this URL. Name each part and say what the server receives.

```
https://api.taskflow.example:443/v1/tasks/42?fields=title,done#notes
```

**Step 1 — scheme.** `https`: use HTTP over an encrypted connection.

**Step 2 — host.** `api.taskflow.example`: the client runs a DNS lookup on this name.

**Step 3 — port.** `443`: the default for HTTPS, so writing it is optional.

**Step 4 — path.** `/v1/tasks/42`: version 1 of the API, the tasks collection, task with id 42.

**Step 5 — query.** `fields=title,done`: a parameter asking for only some fields.

**Step 6 — fragment.** `#notes`: stays in the client; it is **not** sent.

**What actually goes over the wire:**

```http
GET /v1/tasks/42?fields=title,done HTTP/1.1
Host: api.taskflow.example
```

Notice the request line holds only path + query; the host travels in the `Host` header, and the fragment is gone.

## Worked example: Alice's app loads her tasks

**Situation.** Alice (user 123) opens TaskFlow on her phone. Trace the exchange.

**Step 1 — DNS.** The phone resolves `api.taskflow.example` to an IP address, say `203.0.113.10`.

**Step 2 — connect.** TCP connection to `203.0.113.10:443`, then TLS encryption.

**Step 3 — request.**

```http
GET /v1/tasks HTTP/1.1
Host: api.taskflow.example
Accept: application/json
Authorization: Bearer eyJhbGciOi...
```

**Step 4 — server work.** It verifies the token belongs to user 123, then runs:

```sql
SELECT id, title, done, due_date FROM tasks WHERE owner_id = 123;
```

**Step 5 — response.**

```http
HTTP/1.1 200 OK
Content-Type: application/json

[{"id": 42, "title": "Buy milk", "done": false, "due_date": "2026-10-20"},
 {"id": 43, "title": "Call dentist", "done": true, "due_date": null}]
```

**Step 6 — display.** The app draws two rows. One request, one response, cycle complete.

## Worked example: Bob's second request

**Situation.** Bob (user 456) signs in, then a moment later opens task 77. His app sends:

```http
GET /v1/tasks/77 HTTP/1.1
Host: api.taskflow.example
```

The server replies:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{"error": "missing credentials"}
```

**Why?** Bob is confused: "I just logged in!" But HTTP is stateless. The login was a separate request; this new request contains nothing saying who is asking, so the server must treat it as an anonymous stranger.

**Fix.** The app keeps the token it received from `POST /login` and sends it with **every** request:

```http
GET /v1/tasks/77 HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...
```

Now the server can identify user 456 and check that task 77 is his. The rule: each request must stand on its own.

## Worked example: Page versus API response

**Question.** Alice visits `https://taskflow.example/tasks` in a browser, and her phone app calls `https://api.taskflow.example/v1/tasks`. How do the responses differ?

**Browser (web page for a human):**

```http
HTTP/1.1 200 OK
Content-Type: text/html

<!doctype html><html><body><h1>My tasks</h1><ul><li>Buy milk</li>...
```

The browser renders this into a visible page. The data is mixed with layout.

**App (API for a program):**

```http
HTTP/1.1 200 OK
Content-Type: application/json

[{"id": 42, "title": "Buy milk", "done": false}]
```

**Analysis.**

- Both are HTTP responses with a status line, headers, and a body.
- `Content-Type` tells the client what kind of body to expect.
- The JSON has no layout; it is pure data that any program can parse and display in its own way.

This is the core idea of an API: the server delivers data, and each client decides how to present it.

## Worked example: A server as a client

**Situation.** TaskFlow wants to email Alice when a task is due tomorrow. It uses an email company, MailCo, which offers an API.

**Step 1.** A scheduled job on the TaskFlow server finds due tasks:

```sql
SELECT t.title, u.email FROM tasks t JOIN users u ON u.id = t.owner_id
WHERE t.done = false AND t.due_date = CURRENT_DATE + 1;
```

**Step 2.** For each row, the TaskFlow server — now acting as a **client** — calls MailCo:

```http
POST /v3/send HTTP/1.1
Host: api.mailco.example
Content-Type: application/json
Authorization: Bearer mc_live_...

{"to": "alice@example.com", "subject": "Due tomorrow: Buy milk"}
```

**Step 3.** MailCo responds `202 Accepted`.

**Lesson.** "Client" and "server" are roles in one conversation. The same machine is a server to Alice's phone and a client to MailCo. No browser or human is involved in Step 2.

## Common mistakes

**Mistake: "The server pushes pages to me."**
Why it's wrong: in HTTP the client always starts. Correct: the browser or app sends a request; the server only responds.

**Mistake: "DNS sends my request to the server."**
Why it's wrong: DNS only translates a name into an IP address. Correct: after the lookup, the client connects to that IP and sends the HTTP request itself.

**Mistake: "The server remembers I'm logged in."**
Why it's wrong: HTTP is stateless. Correct: the client resends a token or cookie with every request, e.g. `Authorization: Bearer ...`.

**Mistake: "The `#section` part of the URL is sent to the server."**
Why it's wrong: fragments stay in the client. Correct: only the path and query (`/v1/tasks?done=false`) appear in the request line.

**Mistake: "An API is a website."**
Why it's wrong: a website is for people to read; an API is for programs. Correct: an API returns data such as JSON that a client program uses.

## Summary

- A **client** asks; a **server** answers. The client always starts the conversation.
- Every interaction is a **request–response cycle**: order, kitchen prepares, waiter brings the result.
- **HTTP** is the language of these messages; it travels over **TCP/IP** in packets.
- A **URL** has a scheme, host, optional port, path, query, and fragment; the fragment is never sent.
- **DNS** turns a name like `api.taskflow.example` into an IP address — nothing more.
- Loading a page or app screen means: parse URL → DNS → connect → request → response → display.
- HTTP is **stateless**: each request must carry who you are and what you want.
- An **API** is a contract that lets programs talk to a server; TaskFlow's API returns JSON.
- Browsers, mobile apps, and other servers can all be clients of the same API.

## Exercise: Trace a TaskFlow request

<!-- meta: kind=exercise, difficulty=beginner -->

Alice taps the TaskFlow app to see only her unfinished tasks. The app uses the URL `https://api.taskflow.example/v1/tasks?done=false#top`.

1. Name each part of this URL and say which parts appear in the HTTP request the app sends.
2. Describe, step by step, what happens from the tap until the tasks appear on screen. Include where DNS fits in and what the server sends back.
3. Map at least three of your steps onto the restaurant analogy (customer, kitchen, waiter, order, plate).

## Exercise: Why did the second request fail

<!-- meta: kind=exercise, difficulty=beginner -->

A student writes a nightly job that runs on their company's server and backs up Bob's TaskFlow tasks. It sends `POST /v1/login` with Bob's credentials and receives a token. It then sends `GET /v1/tasks` with only a `Host` header and gets `401 Unauthorized`. The student says: "The server is broken — I already logged in."

Using the idea that HTTP is stateless, explain what is really happening and how the job should change. Give one reason statelessness helps a service like TaskFlow. Finally, say which kind of client this job is (browser, mobile app, or server-to-server) and why.
