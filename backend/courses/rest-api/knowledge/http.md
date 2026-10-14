---
id: http
concept: HTTP Fundamentals
capability: http-basics
difficulty: beginner
prerequisites: []
source: "MDN Web Docs — HTTP overview (https://developer.mozilla.org/en-US/docs/Web/HTTP); MDN Web Docs — HTTP response status codes (https://developer.mozilla.org/en-US/docs/Web/HTTP/Status); MDN Web Docs — How the web works (https://developer.mozilla.org/en-US/docs/Learn/Getting_started_with_the_web/How_the_Web_works); RFC 9110 HTTP Semantics"
---

# HTTP Fundamentals

## Clients, servers and the request–response cycle

On the web, two programs talk to each other. The **client** is the program asking for
something: a browser, a mobile app, or another program. The **server** is a program
running on another computer that waits for requests and answers them.

Think of a restaurant. You (the client) place an order with the waiter. The kitchen (the
server) prepares it. The waiter brings back your dish, or tells you it is unavailable.

HTTP maps onto this precisely:

- **Your order is the HTTP request.** It says what you want to do (the method, such as
  `GET`), which thing you want (the path, such as `/menu/soup`), extra details (headers)
  and sometimes data (the body).
- **The kitchen's work is server processing.** The server reads the request, looks up or
  changes data, and decides how to answer.
- **What the waiter brings back is the HTTP response.** It has a status code saying how
  it went (`200 OK`, `404 Not Found`), headers, and usually a body with the data.

Each exchange is one request, then one response. The client always speaks first.

## What happens when you type a web address

Say you type `https://example.com/news` into your browser and press Enter.

1. **Find the server (DNS).** Computers find each other by numeric IP addresses, not
   names. The browser asks DNS, the internet's phone book, for the IP
   address of `example.com`.
2. **Connect.** The browser opens a network connection to that address. Because the
   address starts with `https`, the connection is also encrypted.
3. **Send a request.** The browser sends an HTTP request such as `GET /news`, meaning
   "please give me the page at `/news`".
4. **Get a response.** The server replies with a status code (for example `200 OK`),
   headers (for example `Content-Type: text/html`) and a body containing the page's HTML.
5. **Render.** The browser reads the HTML and draws the page. If the page needs images,
   styles or scripts, the browser sends more requests for each of them.

An app calling an API follows the same steps, except the body is usually data (often
JSON) for the app to display, instead of a page for the browser to draw.

## What an HTTP request is

HTTP is a request/response protocol. A client sends a request to a server, the server
returns a response, and the connection concern ends there. Every request carries four
things: a method, a path, a set of headers, and an optional body.

A minimal request looks like this:

```
GET /users/42 HTTP/1.1
Host: api.example.com
Accept: application/json
```

The method says what the client wants to do. The path identifies the resource. Headers
carry metadata such as content type, authentication and caching directives. The body
carries data, and is empty for methods like GET.

HTTP is stateless. The server does not remember anything about a previous request from
the same client. Any continuity — a login session, a shopping cart — has to be carried
explicitly in each request, usually in a cookie or an Authorization header.

## HTTP methods

GET retrieves a resource and must not change server state. POST submits data and
typically creates something. PUT replaces a resource entirely. PATCH modifies part of a
resource. DELETE removes it.

Two properties matter when reasoning about methods. A method is **safe** if it does not
modify state: GET is safe, POST is not. A method is **idempotent** if making the same
request many times has the same effect as making it once: GET, PUT and DELETE are
idempotent, POST is not. Idempotency is why a client can safely retry a failed PUT but
not a failed POST — retrying a POST may create a duplicate record.

## Status codes

Every response starts with a three-digit status code, grouped by its first digit.

- **2xx — success.** The request worked.
- **3xx — redirection.** The client should look elsewhere. 301 is a permanent move, 302
  a temporary one. 304 Not Modified tells the client its cached copy is still valid.
- **4xx — client error.** Something is wrong with the request itself.
- **5xx — server error.** The request may be fine, but the server failed to handle it.

The 4xx/5xx split matters operationally: 4xx means the client must change something
before trying again, 5xx means the server is at fault and the client may reasonably
retry later.

## Common success codes

- **200 OK** — the request succeeded; the body holds the result (for example, the user
  you asked for).
- **201 Created** — a new resource was created, typically after a POST; the response
  often includes the new resource and a `Location` header with its URL.
- **204 No Content** — the request succeeded and there is nothing to send back, common
  after a DELETE.

## Common error codes

- **400 Bad Request** — the request is malformed or invalid, such as broken JSON or a
  missing required field.
- **401 Unauthorized** — the client is not authenticated: no credentials, or invalid
  ones. Despite the name, it means "we don't know who you are".
- **403 Forbidden** — the client is authenticated, but is not allowed to do this. "We
  know who you are, and the answer is no."
- **404 Not Found** — the requested resource does not exist on the server.
- **409 Conflict** — the request conflicts with the current state of the resource, such
  as creating an account with an email that is already registered.
- **429 Too Many Requests** — the client is sending too many requests and is rate
  limited.
- **500 Internal Server Error** — an unexpected failure on the server, such as a bug or
  crash. 502 Bad Gateway and 503 Service Unavailable usually indicate a problem
  upstream or an overloaded service.

## Headers and content negotiation

Headers let client and server agree on the shape of the exchange without changing the
URL. `Accept` tells the server what formats the client can handle; `Content-Type` tells
the receiver what format the body actually is. `Authorization` carries credentials.
`Cache-Control` governs how long a response may be reused.

## Exercise: Read a failing request
<!-- meta: kind=exercise, difficulty=beginner -->

A client repeatedly sends `POST /orders` and receives `500 Internal Server Error`. The
client retries automatically five times. Answer three questions: Is it safe for the
client to retry this request? What would change if the endpoint returned 400 instead?
What single property of POST makes the retry risky here?

## Exercise: Choose the status code
<!-- meta: kind=exercise, difficulty=beginner -->

You are building the API for a small library app. For each situation below, say which
HTTP status code the server should return, and explain in one sentence why.

1. A logged-in librarian sends `POST /books` with a valid new book, and the server saves
   it.
2. A visitor who has not logged in sends `DELETE /books/12`.
3. A logged-in student (not a librarian) sends `DELETE /books/12`, but only librarians
   may delete books.
4. Someone sends `GET /books/9999`, and no book with id 9999 exists.

Bonus: in situation 3, why would 401 be the wrong answer?
