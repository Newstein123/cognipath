# Cognith — documentation

`Claude.md` in the repo root is **the plan** — the build contract, phases, and product
thesis. It is the source of truth for what we intend to build.

This directory is **the record** — what was actually built, how it works, and why the
non-obvious choices were made.

## The update rule

> Docs are a **phase-completion artifact**. They are written or updated at the *end* of a
> completed phase, as part of that phase's `Claude.md` §20 Step 5 explanation — not
> continuously, and not mid-phase.

Every completed phase does three things:

1. Writes or updates the doc it owns (table below).
2. Updates the **phase log** in [architecture.md](architecture.md) §12.
3. Appends any non-obvious decision to [decisions.md](decisions.md).

## Current docs

| Doc | Covers | Status |
|---|---|---|
| [architecture.md](architecture.md) | The system as built: entry points, data model, embeddings, storage, retrieval, generation, abstention, config, data flow | Phase 0 — current |
| [firestore-handoff.md](firestore-handoff.md) | Handoff: the Firestore storage class, layout, tests, Cloud Run setup | Not built — owner Onyx |
| [api.md](api.md) | The HTTP contract for the frontend, storage seam, skill-state mapping | Phase 15 — current |
| [decisions.md](decisions.md) | Decision record, append-only. 8 entries + 2 open questions | Phase 0 — current |

## Planned docs

Created by the phase that owns them. Not stubbed in advance.

| Doc | Owning phase | Will cover |
|---|---|---|

All ten phases are complete. Phases 7 and 10 are recorded in
[architecture.md](architecture.md) §§13–14 rather than in their own file, because both are
changes to the overall architecture rather than isolated layers.

Start with **`python app.py`** — one interactive session covering everything. The
individual CLIs remain for scripting and debugging.

## Open questions

Q1 is resolved. Two remain deferred and recorded in
[decisions.md](decisions.md#open-questions):

- **Q1** — ~~capability ids vs knowledge tags~~ **resolved in Phase 1** (D9): two
  vocabularies, joined by `knowledge_docs`. The corpus's `capability:` tags proved too
  coarse to join on.
- **Q2** — ~~no HTTP layer~~ **resolved in Phase 15** (D47): the hackathon needs a
  deployed web app, so `api/` exposes the engine over FastAPI for Cloud Run.
- **Q3** — ~~document `prerequisites` vs capability prerequisites~~ **resolved in Phase 7**
  (D26): the capability graph is the only prerequisite graph. The frontmatter field stays
  inert rather than becoming a second, competing source of truth.

## Also in the repo

[`README.md`](../README.md) is the original RAG spike report. It argues the abstention
finding and is worth reading for that, but it documents a *spike*, not the architecture —
start with [architecture.md](architecture.md) instead.
