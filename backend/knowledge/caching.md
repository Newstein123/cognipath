---
id: caching
concept: Caching
capability: system-design
difficulty: beginner
prerequisites: [http]
source: "Martin Kleppmann, Designing Data-Intensive Applications — Ch. 1 (caching discussion)"
---

# Caching

## What a cache is

A cache is a small, fast store that holds copies of results that are expensive to
produce, so that repeat requests can be served without redoing the work. The expensive
work might be a database query, a call to another service, or a computation.

Caching pays off when the same data is requested repeatedly and changes less often than
it is read. If every request asks for different data, a cache adds latency and memory
cost while returning nothing useful.

## Cache hits and misses

A **cache hit** occurs when the requested data is already in the cache and can be
returned immediately, without touching the underlying source. A **cache miss** occurs
when the data is not present, so the system must fetch it from the original source —
typically the database — and usually store it in the cache on the way back, so the next
request for the same data is a hit.

The **hit rate** is the fraction of requests served as hits. It is the single most
important cache metric, because it determines how much of the expensive work is actually
avoided. Effective latency is roughly:

```
average latency = hit_rate × cache_latency + (1 − hit_rate) × source_latency
```

With a 1ms cache and a 50ms database, a 90% hit rate gives about 5.9ms average. Raising
it to 95% gives about 3.45ms. The relationship is nonlinear: at high hit rates, small
improvements in hit rate matter a great deal, because misses dominate the average.

A miss is slightly *more* expensive than having no cache at all, since the system pays
the cache lookup before the database read. Caches win on the average, not on every
request.

## Where caches live

Caching happens at several layers, and they compose.

- **Browser cache** — the client stores responses, governed by `Cache-Control` headers.
  The cheapest possible hit: no network at all.
- **CDN / edge cache** — shared geographic caches holding static assets and cacheable
  responses near users.
- **Application cache** — an in-process or shared store such as Redis or Memcached,
  holding query results, session data or computed values.
- **Database cache** — the database's own buffer pool, keeping hot pages in memory.

## Caching strategies

**Cache-aside (lazy loading)** is the most common. The application checks the cache
first; on a miss it reads the database and writes the result into the cache. Only
requested data is cached, but every first request pays a miss, and cache and database can
drift apart.

**Write-through** writes to the cache and the database together on every write. The cache
stays consistent, but writes are slower and data that is never read still gets cached.

**Write-behind** writes to the cache immediately and to the database asynchronously.
Writes are fast, but a crash before the flush loses data.

## Invalidation and eviction

Cached data goes stale as the underlying source changes, and a cache has finite memory.
Two mechanisms address these separately.

**Expiry (TTL)** attaches a lifetime to each entry; after it passes, the entry is treated
as a miss. TTL is the blunt but reliable tool: it bounds how stale data can be without
requiring the system to detect changes. A short TTL means fresher data and a lower hit
rate.

**Explicit invalidation** deletes or updates an entry when the source changes. Fresher
than TTL, but it requires every write path to know which cache keys it affects — and
missing one produces data that is wrong indefinitely.

**Eviction** is what happens when the cache fills up. LRU (least recently used) discards
the entry untouched for the longest, and is a good default because it approximates "what
is unlikely to be requested again."

## Failure modes
<!-- meta: kind=reference, difficulty=advanced -->

**Thundering herd (cache stampede).** A popular key expires and hundreds of concurrent
requests all miss and all hit the database at once. Mitigated by allowing only one
request to recompute while others wait, or by refreshing slightly before expiry.

**Cache penetration.** Requests for keys that do not exist in the source are never
cacheable, so every one reaches the database. Mitigated by caching the negative result.

## Exercise: Choose a strategy
<!-- meta: kind=exercise, difficulty=intermediate -->

A product page shows a price that changes at most twice a day and a stock count that
changes every few seconds. Both are read thousands of times per minute. Propose a caching
approach for each field, state the TTL you would choose, and explain what a user would
observe if you applied your price strategy to the stock count.
