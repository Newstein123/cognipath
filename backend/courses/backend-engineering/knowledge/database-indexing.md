---
id: database-indexing
concept: Database Indexing
capability: database-reasoning
difficulty: beginner
prerequisites: [how-databases-store-data]
source: "Markus Winand, Use The Index, Luke — Ch. 1 (https://use-the-index-luke.com/)"
---

# Database Indexing

## Why queries get slow without an index

To answer `SELECT * FROM users WHERE email = 'a@b.com'` without an index, the database
has no way to know where matching rows live. Its only option is a **full table scan**:
read every row in the table and test each one against the condition. On a table of ten
million rows, that means reading ten million rows to return one.

The cost grows linearly with table size. A query that returns in 5ms on a development
database with a thousand rows can take several seconds in production against the same
code and the same query, purely because the table grew. This is the single most common
cause of a query that "suddenly" became slow without anyone changing it.

## What an index is and why it speeds queries up

An index is a separate, sorted data structure that maps column values to the locations
of the rows containing them. Most relational databases use a **B-tree**, a balanced tree
kept in sorted order.

Because the tree is sorted, the database can find a value by comparison instead of by
scanning: check the root, follow the one child whose range contains the target, repeat.
Each step discards most of the remaining data. This makes lookup cost **logarithmic**
rather than linear — O(log n) instead of O(n).

The practical difference is large. Finding one row among ten million takes roughly 23
comparisons in a B-tree, versus ten million row reads in a full scan. **This is why
adding an index improves query performance: it converts a linear scan of every row into
a small number of targeted reads.**

A B-tree index also keeps values in sorted order, so the same structure accelerates
range queries (`WHERE created_at > '2024-01-01'`), sorting (`ORDER BY`), and finding
minimum or maximum values — not just exact-match lookups.

## What indexes cost

Indexes are not free, which is why databases do not simply index everything.

- **Write cost.** Every INSERT, UPDATE and DELETE must update every affected index as
  well as the table. A table with six indexes does roughly seven times the write work.
- **Storage.** An index duplicates the indexed columns plus row pointers. Indexes on a
  heavily indexed table can exceed the size of the table itself.
- **Planner cost.** More indexes means more options for the query planner to evaluate,
  and more opportunities for it to choose badly.

The trade-off is therefore read speed against write speed and storage. Indexing is a
decision about a workload, not a universal improvement. A write-heavy audit log and a
read-heavy product catalogue deserve opposite answers.

## When an index will not help

An index on a column is only usable if the query lets the database compare against the
indexed values directly.

- **Functions on the column.** `WHERE LOWER(email) = 'a@b.com'` cannot use a plain index
  on `email`, because the index stores the original values, not the lowercased ones.
- **Leading wildcards.** `WHERE name LIKE '%smith'` cannot use a B-tree, because sorted
  order tells you nothing about suffixes.
- **Low selectivity.** An index on a boolean `is_active` column where 95% of rows are
  true saves little: the database still reads most of the table, and may reasonably
  decide a scan is cheaper than the index lookup plus row fetches.
- **Wrong column order in a composite index.** An index on `(country, city)` supports
  filtering by `country`, or by `country` and `city` together, but not by `city` alone.
  The leftmost columns must be used for the rest to be reachable.

## Reading a query plan
<!-- meta: kind=reference, difficulty=intermediate -->

`EXPLAIN ANALYZE <query>` shows what the database actually did. The distinction to look
for is the access method: `Seq Scan` means a full table scan, `Index Scan` means the
index was used to find specific rows, and `Index Only Scan` means the query was answered
from the index alone without touching the table at all.

A `Seq Scan` on a large table in a query that filters to a few rows is the signature of a
missing or unusable index.

## Exercise: Diagnose the slow query
<!-- meta: kind=exercise, difficulty=intermediate -->

An `orders` table has 12 million rows and an index on `(customer_id, created_at)`. This
query takes 4 seconds:

```sql
SELECT * FROM orders WHERE created_at > '2024-01-01' ORDER BY created_at;
```

Explain why the existing index does not help. State what you would add. Then explain
what the write-path cost of your change would be, and name one situation in which you
would decide not to add it.
