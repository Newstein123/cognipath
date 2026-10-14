---
id: load-balancing
concept: Load Balancing
capability: system-design
difficulty: intermediate
prerequisites: [http]
source: "NGINX — HTTP Load Balancing guide (https://nginx.org/en/docs/http/load_balancing.html)"
---

# Load Balancing

## Why load balancing exists

A single server has a ceiling: CPU, memory, connections. Once traffic approaches it,
latency climbs and the server eventually fails. There are two responses. **Vertical
scaling** makes the machine bigger — simple, but bounded by the largest machine money can
buy, and it leaves a single point of failure. **Horizontal scaling** adds more machines,
which is effectively unbounded but requires something to distribute traffic across them.

That something is a load balancer: it accepts incoming requests and forwards each to one
of several backend servers. It delivers two benefits at once — capacity, because work is
spread out, and availability, because a failed server can be removed from rotation while
the rest keep serving.

## Distribution algorithms

**Round robin** sends each request to the next server in sequence. Simple and fair when
servers are identical and requests cost about the same.

**Weighted round robin** assigns each server a share proportional to its capacity, for
when the fleet is not uniform.

**Least connections** sends each request to the server with the fewest active
connections. Better than round robin when request durations vary widely, because it
responds to actual load rather than assuming uniformity.

**Hash-based (e.g. by client IP or request path)** sends the same key to the same server
consistently. Useful when a server holds local state or a warm local cache for that key.
The cost is that adding or removing a server reshuffles assignments — which is what
consistent hashing is designed to limit.

## Health checks

A load balancer must know which backends are usable, or it will keep routing traffic into
a failed server.

**Passive** checks observe real traffic and remove a backend after repeated errors or
timeouts. No extra load, but detection requires real requests to fail first.

**Active** checks poll a dedicated endpoint (`GET /healthz`) on a fixed interval and
remove backends that stop responding correctly. Failures are detected before users see
them, at the cost of constant background traffic.

A good health endpoint checks that the instance can actually serve — including its
database connection — but must not be so thorough that a slow dependency takes the whole
fleet out of rotation at once.

## Layer 4 and Layer 7

**Layer 4** balancing routes on TCP information — IP address and port — without reading
the request. It is fast and protocol-agnostic, but cannot make decisions based on content.

**Layer 7** balancing reads the HTTP request and can route on path, header, cookie or
method: `/api/*` to one pool, `/images/*` to another. It enables TLS termination,
per-route rate limiting and request rewriting, at the cost of more work per request.

## Sessions and statelessness

Round-robin distribution breaks if a server keeps session state in local memory, because
the user's next request may land elsewhere and appear logged out.

**Sticky sessions** pin a user to one server. This works but undermines even
distribution, and the session is lost when that server dies. The better answer is to make
backends **stateless**: keep session data in a shared store such as Redis, or in a signed
token held by the client. Then any server can serve any request, and losing a server
costs nothing but capacity.

## Exercise: Diagnose uneven load
<!-- meta: kind=exercise, difficulty=intermediate -->

A fleet of six identical servers sits behind a round-robin load balancer. Two servers run
at 90% CPU while four sit near 20%. All health checks pass. Give two distinct
explanations consistent with these symptoms, say what you would measure to tell them
apart, and propose the change you would make for each.
