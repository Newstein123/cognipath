# Cognith HTTP API — contract v0.1

Phase 15. The source of truth is [`api/schemas.py`](../api/schemas.py); this page is the
map. While the server runs, the generated spec is at `/openapi.json` and the interactive
docs at `/docs`. A snapshot of the spec is committed as [`openapi.json`](../openapi.json)
so the frontend can generate types without running the backend:

```bash
npx openapi-typescript backend/openapi.json -o frontend/src/api/types.ts
```

## Conventions

- JSON, camelCase field names.
- Errors are `{"detail": "..."}` with 400 (bad input), 404 (unknown learner, activity or
  capability) or 502 (Gemini failed — **nothing was saved**).
- **Activity ids contain `#` and `.`** (`http.md#exercise-read-a-failing-request`).
  Always `encodeURIComponent` them in paths, or the browser cuts the id at `#`.
- Endpoints that call Gemini take **10–15 s**. Show a working state.
- No auth yet. Every `/api/learners/{id}/…` route will gain an auth check that the caller
  owns `{id}` (backend owner).

## Skill states

| `state` | Meaning | UI wording |
|---|---|---|
| `mastered` | Evidence ≥ 70% | "Mastered" |
| `developing` | Evidence below 70% | "Developing" |
| `unknown` | No evidence. May still have a self-rating | "Not verified yet" — **never** shown as failure |

`mastery` is null when never assessed — that is not zero. `selfRated` is what the learner
claimed at onboarding and is never evidence. Every skill carries a ready-to-show
`explanation`.

## Endpoints

| Method | Path | Gemini | Purpose |
|---|---|---|---|
| GET | `/health` | | Liveness, storage backend, model |
| GET | `/api/onboarding/options` | | Goals, confidence levels, known technologies |
| POST | `/api/learners` | | Onboard → `LearnerCreated` (initial, unverified profile) |
| GET | `/api/learners` | | Learner switcher |
| GET | `/api/learners/{id}/profile` | | `SkillProfile` |
| GET | `/api/learners/{id}/next?limit=3` | | `NextActivities` — what to do and why |
| GET | `/api/learners/{id}/diagnostic` | | Targets chosen for verification + their activities |
| GET | `/api/activities/{activityId}` | | Prompt + explicit rubric criteria |
| POST | `/api/learners/{id}/attempts` | ✓ | Judge an answer → verdicts, skill changes, why, new profile, new next steps |
| POST | `/api/learners/{id}/lessons` | ✓ | Grounded explanation for one capability, with sources |
| POST | `/api/learners/{id}/tutor` | ✓ | Free question → grounded answer with sources, or abstention |
| GET | `/api/learners/{id}/evidence` | | Evidence log, oldest first |

### The main flow

```text
POST /api/learners                    goal + background  -> unverified profile
GET  /next                            step 1 is "diagnose"
GET  /diagnostic                      activities to answer
POST /attempts {activityId, response} -> verdicts, changes, explanation,
                                         updated profile, NEW next steps
     ↳ next.steps[0].kind
         learn     -> POST /lessons {capabilityId}
         practise  -> GET /activities/{activityId}, then POST /attempts
         apply     -> same as practise
         diagnose  -> same as practise
         mission   -> not exposed over HTTP yet
```

`AttemptResult` returns the updated profile and next steps, so the UI can show
"before → after → what next" without a second request.

### Example — `POST /api/learners`

```json
{
  "name": "Ada",
  "goal": "I want to build production-ready REST APIs",
  "technologies": ["python", "postgres", "redis", "docker"],
  "knows": "I have built APIs with authentication and caching",
  "built": "A booking system backend",
  "level": "intermediate"
}
```

`goal` is free text and is mapped to a goal key by keyword. `goal.supported` is false for
anything other than the backend demo domain; the learner is still created.

### Example — a `Step`

```json
{
  "kind": "learn",
  "title": "Read up on HTTP",
  "reason": "You demonstrated 48% here. Specifically: \"Says retrying is not safe here…\"",
  "capabilityId": "http",
  "capabilityName": "HTTP",
  "activityId": null,
  "minutes": 0
}
```

### Lessons and the tutor abstain on purpose

`answered: false` with the message *"I don't have enough information in the current
learning materials…"* is correct behaviour, not an error — the tutor only teaches from
the curated corpus. `gate` says which check refused. As of 2026-10-14, lessons for
`databases`, `scalability` and `reliability` abstain because the corpus does not cover
them yet.

## Storage

All learner state goes through [`cognith_student/storage.py`](../cognith_student/storage.py):
two documents per learner (profile, append-only evidence log). `COGNITH_STORAGE=file`
(default) uses `data/`. A Firestore backend implements the same five methods; the
suggested collection layout is in the `FirestoreStorage` docstring.

## Not exposed yet

- The flagship mission (stateful simulation) — CLI only (`mission.py`).
- Auth.
