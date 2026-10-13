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

## Demo without touching the seeded data

```bash
cp -r backend/data /tmp/cognith-demo
COGNITH_DATA_DIR=/tmp/cognith-demo backend/.venv/bin/uvicorn api.main:app --app-dir backend
```

Delete the copy to reset the demo.
