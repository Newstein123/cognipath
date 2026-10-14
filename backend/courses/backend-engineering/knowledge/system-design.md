---
id: system-design
concept: System Design and Trade-offs
capability: trade-off-analysis
difficulty: intermediate
prerequisites: [caching, load-balancing, database-replication]
source: "Martin Kleppmann, Designing Data-Intensive Applications — Ch. 1, Reliable, Scalable, Maintainable Applications"
---

# System Design and Trade-offs

## There is no best architecture

System design questions rarely have a correct answer independent of context. They have
answers that are correct *given* a set of requirements, constraints and expected load.
The same design that is right for ten thousand users is wrong for ten million, and the
design that is right for ten million is wasteful and slow to build for ten thousand.

The skill being exercised is not recalling architectures. It is deciding which properties
matter for this system, and being explicit about what is being given up in exchange.

## The properties worth trading

Most backend decisions move along a small number of axes, and improving one usually costs
another.

- **Latency** — how long one request takes. Distinguish the average from the tail: p99
  latency determines what the unluckiest users experience, and averages hide it.
- **Throughput** — how much work the system handles per unit time. A system can have
  excellent throughput and terrible tail latency at the same time.
- **Cost** — machines, storage, bandwidth, and the engineering time to build and operate.
- **Reliability** — continuing to work correctly when parts fail. Usually bought with
  redundancy, which costs money and adds coordination.
- **Consistency** — whether everyone sees the same data at the same time. Often traded
  for latency and availability, as replication makes concrete.
- **Complexity** — the cost paid forever afterwards, in debugging, onboarding and
  operations. Frequently ignored in design discussions and frequently the one that hurts.

## How to reason about a design decision

A defensible decision follows a recognisable shape.

1. **State the requirement in numbers.** "Fast" is not a requirement; "p99 under 200ms at
   5,000 requests per second" is. Without numbers there is no way to tell whether a
   design succeeds.
2. **Find the actual bottleneck.** Measure before changing. The slow part is often not
   the part that looks slow.
3. **Name at least two options.** A decision with one option is not a decision.
4. **State what each option costs.** Every option has a cost; if you cannot name it, you
   have not understood the option.
5. **Choose, and record why.** The reasoning is more valuable later than the choice, both
   for the next engineer and for knowing when the decision should be revisited.
6. **Say what would change your mind.** Which metric crossing which threshold means this
   decision should be reopened.

## Common trade-offs in practice

**Caching** trades freshness for latency and load. You accept data that may be slightly
stale in exchange for speed, and pay in invalidation complexity.

**Replication** trades consistency for read capacity and availability. Asynchronous
replicas serve more reads and survive failures, but can return stale data.

**Indexing** trades write speed and storage for read speed, which is why databases do
not index every column by default.

**Horizontal scaling** trades simplicity for capacity and resilience. More machines mean
more capacity and no single point of failure, but also distribution, coordination and a
harder debugging story.

**Asynchronous processing** trades immediacy for responsiveness. Moving work into a
background job returns to the user faster, but the result is no longer available at the
moment of the request, and failures must be handled somewhere the user cannot see.

## Estimating before building
<!-- meta: kind=reference, difficulty=intermediate -->

Rough numbers eliminate whole designs early. If 10,000 daily active users each make 20
requests, that is 200,000 requests a day — about 2.3 per second on average, and perhaps
20 at peak. That fits comfortably on one modest server, and any design proposing a
distributed architecture for it is solving a problem that does not exist.

Order-of-magnitude estimates are usually enough. The purpose is not precision; it is
knowing whether the answer is 2 requests per second or 20,000.

## Exercise: Defend a decision
<!-- meta: kind=exercise, difficulty=advanced -->

A service serving 500 requests per second has a p99 latency of 800ms. Profiling shows 600
of those milliseconds in a database aggregate query on a table that grows daily. You have
two weeks and no budget for new infrastructure.

Propose two different approaches, state the cost of each along the axes above, choose
one, and name the metric that would tell you your choice was wrong.
