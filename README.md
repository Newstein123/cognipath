# Cognith

Learn what you need, not everything. Google AI Builder Cup MVP — deadline 18 Oct 2026.

```text
backend/    Python engine + FastAPI (Cloud Run)     — docs/api.md is the contract
frontend/   Next.js app (simple UI, all 10 demo screens)
```

## Backend quick start

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
echo "GEMINI_API_KEY=..." > .env
.venv/bin/uvicorn api.main:app --reload      # http://localhost:8000/docs
.venv/bin/python -m pytest tests -q          # no API key needed
```

Seeded demo learners: `demo` (experienced) and `fresh` (beginner), both aiming at
Backend Software Engineer.

## Frontend quick start

```bash
cd frontend
npm install
npm run dev                                  # http://localhost:3000
```

Expects the backend on `http://localhost:8000` (override with `NEXT_PUBLIC_API_URL`).

## Deploying

Backend on Cloud Run, frontend on Firebase App Hosting, learners in Firestore: see
[DEPLOY.md](DEPLOY.md).

## Demo without touching the seeded data

```bash
cp -r backend/data /tmp/cognith-demo
COGNITH_DATA_DIR=/tmp/cognith-demo backend/.venv/bin/uvicorn api.main:app --app-dir backend
```

Delete the copy to reset the demo.

## Courses

Each course is a folder in `backend/courses/<id>/`: skill map, onboarding, diagnosis
questions, exercises, milestones and the course material (`knowledge/*.md`). The engine
has no course-specific code; each learner record names its course.

| Course | Folder | Notes |
|---|---|---|
| REST APIs from zero | `courses/rest-api` | Demo course, 6 skills, default |
| Backend Software Engineering | `courses/backend-engineering` | Original pack; used by the tests |
| MAT221 Discrete Mathematics | `courses/mat221` | Local only — built from lecture slides, not committed |

To add a course, create the folder (copy `courses/rest-api` as a template), write the
material and `parts/*.yaml` questions, then run:

```bash
cd backend && .venv/bin/python build_pack.py <course-id>   # merge questions, build index, validate
```
