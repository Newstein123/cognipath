# Firestore storage — handoff for Onyx

**Status:** built 16 Oct. `FirestoreStorage` in `cognith_student/storage.py` follows the
starting point below; the copy script is `seed_firestore.py`; deploy steps are in
[DEPLOY.md](../../DEPLOY.md). Both Testing commands below pass on the emulator
(emulator 1.22.0), and so does plain `pytest tests/`, apart from the two tests that need
the local-only `courses/mat221`. `seed_firestore.py` copies all five seed learners
unchanged. Not yet run against a real project's Firestore; DEPLOY.md Part F checks that.

## Why this matters

Learner data is saved as JSON files under `backend/data/`. That works on a laptop, but on
Cloud Run the filesystem is temporary: files vanish when an instance restarts or is
redeployed, and two instances don't share them. A learner's progress can disappear in
the middle of a demo. Firestore fixes this.

## What already exists

Every read and write of learner data goes through one interface, `Storage`, in
[`cognith_student/storage.py`](../cognith_student/storage.py). The rest of the engine
never touches files or Firestore directly. So this job is **one class with 7 methods**,
plus config. No other code changes.

- `get_storage()` already switches on `COGNITH_STORAGE=firestore`.
- `FirestoreStorage` is a stub with the agreed signature: `__init__(client=None, prefix="")`.
- [`tests/test_storage_contract.py`](../tests/test_storage_contract.py) is the contract.
  It runs against files today and against Firestore once you set an env var (see Testing).
- I checked the current records. They have no nested arrays and no reserved keys, and the
  largest is 7 KB, so they all store in Firestore as they are.

## The 7 methods

Store records **exactly as given** and return them unchanged. The engine reads them by
the same field names (camelCase inside, e.g. `createdAt`, `capabilityId`).

| Method | Input → output | Rules |
|---|---|---|
| `load_profile(sid)` | → `dict` or `None` | `None` if the learner doesn't exist (the API turns that into a 404) |
| `save_profile(sid, record)` | `{"student": {...}, "student_capabilities": [...]}` | Overwrites the whole record (the engine always saves the full profile) |
| `list_students()` | → `list[str]` | Learner ids, **sorted** |
| `load_evidence(sid)` | → `list[dict]` | **Oldest first**, in append order, even when two entries share a timestamp. Return `[]` if none. Strip any helper fields you added. |
| `append_evidence(sid, entry)` | `{"evidence": {...}, "assessment": {...}}` | Append-only; never rewrite earlier entries |
| `save_activity(record)` | generated challenge, has `record["id"]` | Overwrite if the id exists |
| `list_activities()` | → `list[dict]` | All generated challenges, sorted by id |

Evidence order really matters: retry detection, "what you missed last time" and the
history page all read the log in order.

## Suggested layout

```text
{prefix}students/{studentId}                       the whole profile record, one doc (~4 KB)
{prefix}students/{studentId}/evidence/{autoId}     one doc per entry, plus a _seq field for ordering
{prefix}learning_experiences/{activityId}          generated challenges
```

Keeping a profile in **one document** is deliberate. It's always rewritten whole and it's
small, so one `set()` is atomic and simple. Splitting `student_capabilities` into its
own collection (the CLAUDE.md §19 layout) is optional and not needed for the demo.

`prefix` goes in front of every top-level collection name. The tests use it to isolate
their data; production leaves it empty.

## A starting point

```python
import time
from typing import Any

from google.cloud import firestore


class FirestoreStorage:
    def __init__(self, client: Any = None, prefix: str = "") -> None:
        self.db = client or firestore.Client()   # project and credentials from ADC
        self.prefix = prefix

    def _col(self, name: str):
        return self.db.collection(f"{self.prefix}{name}")

    def _evidence(self, sid: str):
        return self._col("students").document(sid).collection("evidence")

    def load_profile(self, sid):
        snap = self._col("students").document(sid).get()
        return snap.to_dict() if snap.exists else None

    def save_profile(self, sid, record):
        self._col("students").document(sid).set(record)

    def list_students(self):
        return sorted(d.id for d in self._col("students").stream())

    def load_evidence(self, sid):
        out = []
        for d in self._evidence(sid).order_by("_seq").stream():
            e = d.to_dict()
            e.pop("_seq", None)
            out.append(e)
        return out

    def append_evidence(self, sid, entry):
        # time_ns keeps same-second entries in order. Clock skew between instances could
        # only reorder entries written within the same millisecond, which one learner
        # can't do.
        self._evidence(sid).add({**entry, "_seq": time.time_ns()})

    def save_activity(self, record):
        self._col("learning_experiences").document(record["id"]).set(record)

    def list_activities(self):
        return sorted((d.to_dict() for d in self._col("learning_experiences").stream()),
                      key=lambda r: r["id"])
```

Add `google-cloud-firestore` to `backend/requirements.txt`.

## Testing

Use the emulator, so tests never touch the real database:

```bash
gcloud emulators firestore start --host-port=localhost:8085      # terminal 1

cd backend                                                        # terminal 2
export FIRESTORE_EMULATOR_HOST=localhost:8085 GOOGLE_CLOUD_PROJECT=demo-cognith
COGNITH_TEST_STORAGE=firestore .venv/bin/python -m pytest tests/test_storage_contract.py   # the contract
COGNITH_TEST_STORAGE=firestore .venv/bin/python -m pytest tests/                           # the whole API on Firestore
```

**Done** means both commands pass, and plain `pytest tests/` (files) still passes.

## Copying the demo learners into Firestore

Run this once per environment after deploying. It copies only the seed learners, never
local test learners. Built as `seed_firestore.py`, which also skips learners already in
Firestore so a second run cannot duplicate evidence:

```python
from cognith_student.storage import FileStorage, FirestoreStorage

src, dst = FileStorage(), FirestoreStorage()
for sid in ["demo", "fresh", "003", "student-001", "student-002"]:   # the committed seeds
    dst.save_profile(sid, src.load_profile(sid))
    for e in src.load_evidence(sid):
        dst.append_evidence(sid, e)
for a in src.list_activities():
    dst.save_activity(a)
```

The team lead is adding two REST demo learners. Use whatever seed files are committed in
`backend/data/students/` when you run it.

## Cloud Run and project setup

1. Create Firestore in **Native mode**, in the same region as the Cloud Run service.
2. Give the Cloud Run service account the **Cloud Datastore User** role
   (`roles/datastore.user`). The client authenticates through it; no key file is needed.
3. Deploy with `--set-env-vars COGNITH_STORAGE=firestore`. On Cloud Run the project ID
   comes from the environment.
4. Check that `GET /health` returns `"storage": "firestore"`.

## Security rules

The browser never talks to Firestore. Only the backend does, through its service
account, which bypasses rules. So lock client access out completely:

```text
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} { allow read, write: if false; }
  }
}
```

## Also before deploying

Done. `backend/.dockerignore` now excludes `courses/mat221/`, `data/generated/` and every
learner file except the committed seeds. The seeds stay in the image so the file-storage
fallback still has the demo learners. Everything else under `courses/` ships unchanged:
it is the knowledge engine's read-only data.

## Fallback if this isn't ready by 17 Oct

Deploy with file storage on **one always-on instance**
(`--min-instances=1 --max-instances=1`). Progress survives refreshes and navigation, which
meets the persistence criterion, but resets on every redeploy. So redeploy before
recording, not during.
