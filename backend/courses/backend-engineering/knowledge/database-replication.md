---
id: database-replication
concept: Database Replication
capability: database-reasoning
difficulty: intermediate
prerequisites: [database-indexing]
source: "Martin Kleppmann, Designing Data-Intensive Applications — Ch. 5, Replication"
---

# Database Replication

## What replication is and why it is used

Replication keeps copies of the same data on more than one database machine. It serves
three distinct purposes, and confusing them leads to bad designs:

- **Read capacity** — reads can be spread across copies.
- **Availability** — if one machine dies, another holds the data.
- **Locality** — a copy near users in another region reduces latency.

Replication does not help with write capacity. Every write must eventually reach every
replica, so the write load on each machine is unchanged. Scaling writes is what
partitioning (sharding) is for, and the two are solutions to different problems.

## Leader and follower

The most common arrangement is **leader–follower** (also called primary–replica). One
node is the leader and accepts all writes. Every write is recorded in a replication log
and sent to the followers, which apply the changes in the same order. Followers accept
reads but never writes.

This arrangement is popular because it is simple and avoids write conflicts entirely:
with exactly one writer, there is never a question of which of two concurrent writes to
the same row wins.

## Read replicas: when to use one

A **read replica** is a follower used to serve read traffic. It is the right tool when
the workload is read-heavy and the reads can tolerate slightly stale data.

Good candidates: analytics and reporting queries, dashboards, search result pages,
recommendation feeds, exports and any expensive aggregate that would otherwise compete
with production traffic on the leader.

Poor candidates: reading a value immediately after writing it, anything where a user
must see the effect of their own action, and financial or inventory checks where a stale
read causes a real error. These reads should go to the leader.

A read replica is also not the fix for a slow query. If a query is slow because it scans
a large table, it will be equally slow on the replica; the replica only stops it from
slowing down everything else. Fix the query or the index first, then decide whether to
move the traffic.

## Synchronous and asynchronous replication

In **synchronous** replication, the leader waits for a follower to confirm the write
before reporting success. No data is lost if the leader fails, but write latency now
includes the follower, and if the follower stalls, writes stall with it.

In **asynchronous** replication, the leader reports success immediately and ships changes
to followers afterwards. Writes are fast and follower problems do not block them, but
writes confirmed to the client can be lost if the leader fails before they propagate.

**Semi-synchronous** is the common compromise: wait for one follower, let the rest catch
up asynchronously.

## Replication lag and what it looks like

Asynchronous replicas are behind the leader by some amount of time — the **replication
lag**. Usually milliseconds; under heavy write load or a long-running query on the
replica, it can reach seconds or minutes.

Lag produces specific, confusing bugs:

- **Read-your-own-writes.** A user updates their profile, the next page reads a replica
  that has not caught up, and their change appears to have vanished. Fix: route reads
  that follow a user's own write to the leader for a short window.
- **Monotonic reads.** Two successive reads hit replicas with different lag, and the
  user sees time move backwards. Fix: pin a user's reads to one replica.

Replication lag is a metric to alert on, not an implementation detail. A replica lagging
by minutes is serving data that may be wrong enough to matter.

## Failover
<!-- meta: kind=reference, difficulty=advanced -->

If the leader fails, a follower must be promoted. This requires detecting the failure,
choosing a replacement, and redirecting writes. With asynchronous replication, the new
leader may be missing the most recent writes, which are then lost. Automatic failover can
also produce **split brain**, where two nodes both believe they are the leader and accept
conflicting writes.

## Exercise: Route the reads
<!-- meta: kind=exercise, difficulty=intermediate -->

An e-commerce backend has one leader and two asynchronous read replicas lagging about
200ms. Decide where each of these reads should go, and justify each in one sentence:
(a) the homepage product listing, (b) a user's cart immediately after they add an item,
(c) the monthly revenue report, (d) the stock check during checkout.
