# The interactive session

**Status:** Phase 14 complete — one entry point.
**Last updated:** 2026-09-23 (Phase 14)

```bash
python app.py
```

Thirteen phases produced fifteen command-line tools, each correct and each requiring you to
know it existed. This is the same system as one conversation you can leave and come back to.

---

## 1. The rule this file follows

**`app.py` contains no logic.** Every screen calls an engine or a renderer that already
exists — selection, assessment, retrieval, the mission simulation, milestone progress.

If something in it looks like a decision being made, that is a bug: the decision belongs in
the layer that owns it. The file is a shell, and it is worth keeping it that way, because
the alternative is a second implementation of the loop that drifts from the first.

The individual CLIs remain. They are better for scripting, for debugging one layer, and for
the checks that should run without a human — `mission.py --calibrate`,
`onboard.py --verify`, `capabilities.py --validate`.

---

## 2. What it actually changed

Everything else was already reachable. **One thing was not: answering.**

```
before   write your answer to a file, then
         python assess.py --item ID --response-file answer.txt --gemini --save

now      type it
```

That is the difference between a set of tools and something a learner can use.

```
══════════════════════════════════════════════════════════════════════════
  Read a failing request   [exercise]
══════════════════════════════════════════════════════════════════════════

  about 6 minutes · evidences HTTP, Reliability

  A client repeatedly sends `POST /orders` and receives `500 Internal Server
  Error`. The client retries automatically five times. …

  Your answer:
  (end with '.' on its own line, or two blank lines · 'cancel' to go back)

  ▊
```

---

## 3. Two blank lines, not one

The obvious rule is that a blank line ends the answer. It is wrong.

A scenario answer is prose, prose has paragraphs, and people paste. Ending on the first
blank line would **silently truncate a pasted answer at its first paragraph break** —
losing most of it, with nothing to indicate anything was lost.

So: `.` alone, or two consecutive blank lines. The first version of this file documented
"finish with an empty line" while requiring two, which is worse than either rule — the
prompt now says what the code does.

---

## 4. The shape of the session

```
  Demo Student  —  Backend Software Engineer

  0 of 17 demonstrated, 2 assessed, 12 still taken on trust.
  Backend Foundations: 0 of 6 demonstrated, 5 claimed but unverified.

  Suggested next: [read] Read up on HTTP
      You demonstrated 20% here. You have missed this more than once:
      "Says retrying is not safe here, because a 500 does not tell the
      client whether the order was created".

  What would you like to do?  [enter = the suggestion above]

    1. Do the suggested next thing      6. Practise one capability
    2. My capability map                7. Apply several together
    3. My milestones                    8. The mission
    4. Take a diagnostic                9. What you have learned about me
    5. Learn something I am weak at     q. quit
```

**Enter alone does the suggestion**, so the common path is pressing return. Numbers and
word prefixes both work (`map`, `mi`, `4`).

Nothing is a mode you can get stuck in: every screen has `back`, and `q` exits from the
menu. Ctrl-C and Ctrl-D exit cleanly rather than with a traceback — state is already
persisted after every assessment, so leaving loses nothing.

---

## 5. Network calls are always confirmed

Assessment and explanation cost Gemini calls. Neither happens without a yes:

```
  This will be judged against 4 criteria by Gemini. That is a network call.
  Assess it now? [y/N]
```

Defaulting to **no**. An accidental return should not spend anything.

Everything else — the map, milestones, the diagnostic selection, the whole mission
simulation, the learner history — is offline, which is most of the system.

---

## 6. The mission has its own loop

A mission is stateful, so it gets a sub-session rather than a single screen: investigate,
act, review, submit. It reuses `mission.py`'s own session file, so a mission started at the
command line continues in the app and the other way round.

---

## 7. What a retry looks like from inside

The most compelling thing the app shows, because it is the one thing a single screen cannot:

```
  SINCE YOUR LAST ATTEMPT
──────────────────────────────────────────────────────────────────────────

  fixed    ✗ ✗ ✓  Says retrying is not safe here, because a 500 does not
  fixed    △ ✓ ✓  Explains that a 400 means the request itself was rejec
  fixed    ✗ ✗ ✓  Names non-idempotency as the property of POST that mak
  fixed    ✗ △ ✓  Connects it to the real consequence — five retries can

  score 38% -> 100% (+88%)
```

Three attempts, per criterion, in order. Both blind spots cleared on the third, and the
learner signal moved from *"has not been able to act on the feedback given"* (25%) to
*"acts on feedback reliably"* (100%).

---

## 8. How to test it

```bash
python app.py
```

Scriptable, which is how it was tested:

```bash
printf '1\nmap\nq\n' | python app.py          # pick student 1, show map, quit
printf '1\n6\n4\n…\n.\ny\nq\n' | python app.py  # practise, answer, assess
```

All nine menu options were exercised this way, plus clean exit on `q`, on EOF, and on
unrecognised input.
