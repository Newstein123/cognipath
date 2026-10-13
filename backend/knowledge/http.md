---
id: http
concept: HTTP Fundamentals
capability: http-fundamentals
difficulty: beginner
prerequisites: []
source: "MDN Web Docs — HTTP overview (https://developer.mozilla.org/en-US/docs/Web/HTTP)"
---

# HTTP Fundamentals

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

Status codes are grouped by their first digit.

- **2xx — success.** 200 OK is a successful request. 201 Created means a new resource
  was made. 204 No Content means success with nothing to return.
- **3xx — redirection.** 301 is a permanent move, 302 a temporary one. 304 Not Modified
  tells the client its cached copy is still valid.
- **4xx — client error.** 400 Bad Request means the request was malformed. 401
  Unauthorized means the client is not authenticated. 403 Forbidden means it is
  authenticated but not allowed. **404 Not Found means the requested resource does not
  exist on the server.** 429 Too Many Requests means the client is rate limited.
- **5xx — server error.** 500 Internal Server Error is an unhandled failure on the
  server. 502 Bad Gateway and 503 Service Unavailable usually indicate a problem
  upstream or an overloaded service.

The 4xx/5xx split matters operationally: 4xx means the client must change something,
5xx means the server is at fault and the client may reasonably retry.

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
