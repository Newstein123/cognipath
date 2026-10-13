# Cognith

Learn what you need, not everything. Google AI Builder Cup MVP — deadline 18 Oct 2026.

```text
backend/    Python engine + FastAPI (Cloud Run)     — docs/api.md is the contract
frontend/   Next.js app                             — not started
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
