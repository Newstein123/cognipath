# Authoring brief — "REST APIs from zero" (Cognith)

You are writing LECTURE NOTES for one unit of a beginner course. Students may know
nothing about backend development. An adaptive tutor (Gemini) teaches ONLY from these
notes: it reuses their explanations and, above all, their WORKED EXAMPLES. Thin notes make
the tutor sound like a generic chatbot; rich, concrete notes make it feel like a real
course. Aim for the density of good university lecture notes.

## Sources — fetch them, then adapt

Use the WebFetch tool to read the source pages listed for your unit (MDN Web Docs, OWASP).
Adapt and explain in your own words for a beginner; do not paste long passages verbatim.
Facts must agree with the sources. MDN and OWASP content is CC BY-SA; attribute it in the
frontmatter `source:` line, for example:

    source: "Adapted from MDN Web Docs — <page titles> (https://developer.mozilla.org/...), by Mozilla Contributors, CC BY-SA 2.5; OWASP <page> (https://...), CC BY-SA 4.0"

If a page fails to load, use your own accurate knowledge and say so in your reply.

## The running example — use it in EVERY unit

TaskFlow, a task-management app.

- Base URL: `https://api.taskflow.example/v1`
- Users: id, email, password_hash, name
- Tasks: id, owner_id (→ users.id), title, done (boolean), due_date, created_at
- Endpoints: `GET /tasks`, `POST /tasks`, `GET /tasks/{id}`, `PUT /tasks/{id}`,
  `PATCH /tasks/{id}`, `DELETE /tasks/{id}`, `POST /login`
- Characters: Alice (user 123) and Bob (user 456).

Show literal HTTP exchanges, for example:

```http
GET /v1/tasks/42 HTTP/1.1
Host: api.taskflow.example
Authorization: Bearer eyJhbGciOi...

HTTP/1.1 200 OK
Content-Type: application/json

{"id": 42, "title": "Buy milk", "done": false}
```

plus JSON, SQL (PostgreSQL) or curl where relevant. Keep code language-agnostic (no
framework tutorials); a tiny pseudocode snippet is fine where it helps.

## Material file — `knowledge/<doc-id>.md`

```
---
id: <doc-id>
concept: <Unit title>
capability: <capability-id>
difficulty: beginner
prerequisites: [<doc-ids of earlier units>]
source: "<attribution>"
---

# <Unit title>

## <Section heading>
<body>
```

- 14–20 `## ` sections. Each section is ONE retrieval chunk and must stay under ~1100
  characters — split long topics into clearly titled parts.
- Structure it like a lecture:
  1. "Why this matters" — one short section with an everyday analogy.
  2. The core ideas, one per section, with precise definitions.
  3. 4–6 sections titled "Worked example: …" — a concrete TaskFlow situation solved step
     by step, with the literal request / response / JSON / SQL.
  4. "Common mistakes" — one or two sections: mistake → why it's wrong → correct version.
  5. "Summary" — one section, bullet list.
  6. Exactly 2 exercise sections:

```
## Exercise: <short title>
<!-- meta: kind=exercise, difficulty=beginner -->

<an exam-style TaskFlow question answerable in prose in 5–10 minutes>
```

- About 1,800–2,500 words. Plain Markdown, code in fenced blocks, NO LaTeX.

## Questions file — `parts/<doc-id>.yaml`

```yaml
diagnostics:
  - id: <short>-diag-001
    capability: <capability-id>
    also_exercises: []
    level: foundation
    minutes: 6
    probes: [application, reasoning]
    prompt: |
      <accessible beginner question; a concrete TaskFlow situation; answerable in a few sentences>
    rubric:
      - id: <short>-d1-<slug>
        criterion: <what a good answer does — judgeable from a typed prose answer>
        capability: <capability-id>
        weight: 1.0
  - id: <short>-diag-002      # a second, slightly harder one
exercises:
  - chunk: <doc-id>.md#exercise-<slug>
    title: <title>
    capabilities: [<capability-id>]
    level: foundation
    minutes: 8
    rubric:
      - id: <short>-e1-<slug>
        criterion: <...>
        capability: <capability-id>
        weight: 1.0
```

- 3–5 criteria per item; ids unique, lowercase-hyphenated.
- Chunk id = `<doc-id>.md#` + the full heading lowercased, every run of characters other
  than [a-z0-9] replaced by "-", trimmed. "## Exercise: Choose the status code" →
  `<doc-id>.md#exercise-choose-the-status-code`.
- Validate: `/Users/applegarden/Desktop/Hackethon/Cognipath/backend/.venv/bin/python -c "import yaml,sys;yaml.safe_load(open(sys.argv[1]))" <file>`

Write both files under `/Users/applegarden/Desktop/Hackethon/Cognipath/backend/courses/rest-api/`.
Reply briefly: files written, section and word count per unit, exercise chunk ids,
diagnostic ids, and any source page you could not fetch.
