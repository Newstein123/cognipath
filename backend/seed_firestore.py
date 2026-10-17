#!/usr/bin/env python3
"""Copy the committed demo learners from data/ into Firestore. Run once per environment.

  python seed_firestore.py                 the five committed seed learners
  python seed_firestore.py demo fresh      only these

Credentials and project come from ADC: `gcloud auth application-default login` and
`gcloud config set project <id>` (or GOOGLE_CLOUD_PROJECT). Learners already in
Firestore are skipped, so running it twice never duplicates their evidence log.
Generated challenges are copied too and simply overwrite.
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  — must precede project imports

import sys

from cognith_student.storage import FileStorage, FirestoreStorage

#: The seed learners committed in data/students/ — never local test learners.
SEEDS = ["demo", "fresh", "003", "student-001", "student-002"]


def main(ids: list[str]) -> None:
    src, dst = FileStorage(), FirestoreStorage()
    print(f"  Firestore project: {dst.db.project}")
    for sid in ids:
        record = src.load_profile(sid)
        if record is None:
            print(f"  {sid:<12} no file in data/students — skipped")
            continue
        if dst.load_profile(sid) is not None:
            print(f"  {sid:<12} already in Firestore — skipped")
            continue
        if dst.load_evidence(sid):
            # The profile is written last, so this is an interrupted copy. Appending
            # again would duplicate the entries that did arrive.
            print(f"  {sid:<12} half-copied — delete students/{sid} in the Firestore "
                  "console, then run this again")
            continue
        evidence = src.load_evidence(sid)
        for e in evidence:
            dst.append_evidence(sid, e)
        dst.save_profile(sid, record)
        print(f"  {sid:<12} copied, {len(evidence)} evidence entries")
    activities = src.list_activities()
    for a in activities:
        dst.save_activity(a)
    print(f"  {len(activities)} generated challenges copied")


if __name__ == "__main__":
    main(sys.argv[1:] or SEEDS)
