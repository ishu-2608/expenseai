# ExpenseAI

ExpenseAI is a polished personal finance assistant for understanding spending, not just recording it. It combines a FastAPI/SQLAlchemy API with a responsive React dashboard and deterministic financial intelligence.

## Features
- Dashboard balance, income, expenses, savings, budget health and recent activity
- Searchable transactions with categories, filters, CSV preview/import, and add form
- Spending trend and category analytics (week/month/year)
- Overall monthly budgets with progress tracking
- Savings goals and contributions API
- Deterministic insights and safe natural-language expense queries (no arbitrary SQL)
- Secure JWT registration/login, bcrypt password hashing, per-user data isolation, and logout
- Seeded demo data only when explicitly enabled, CORS, input validation, responsive dark/light UI

## Run locally
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
# in another terminal
cd frontend
npm install
npm run dev
```
Open http://localhost:5173. API docs: http://localhost:8000/docs.

## Environment
Backend: `DATABASE_URL`, `CORS_ORIGINS` (include the exact frontend origin, such as both `http://localhost:5173` and `http://127.0.0.1:5173` during local development), `APP_ENV`, `JWT_SECRET`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `SEED_DEMO_DATA`, optional `LLM_API_KEY` (local deterministic service works without it). Frontend: `VITE_API_URL`.

For production, set `APP_ENV=production`, provide a stable long-random `JWT_SECRET`, set `DATABASE_URL` to the PostgreSQL connection URL, and set `CORS_ORIGINS` to the exact HTTPS frontend origin. The frontend production build requires `VITE_API_URL` and must point to the deployed API, such as `https://your-render-service.onrender.com/api`; it never falls back to localhost in production.

### Render backend

Create a Render Web Service with root directory `backend`:

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Set these Render environment variables:

```text
APP_ENV=production
DATABASE_URL=<Render PostgreSQL connection URL>
CORS_ORIGINS=https://<your-vercel-domain>
JWT_SECRET=<long-random-production-secret>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=10080
SEED_DEMO_DATA=false
```

### Vercel frontend

Create a Vercel project with root directory `frontend`, build command `npm run build`, and output directory `dist`. Set:

```text
VITE_API_URL=https://<your-render-service>.onrender.com/api
```

The backend includes the PostgreSQL driver and creates the current SQLAlchemy schema at startup. The existing SQLite path remains available for local development.

New accounts start with no financial data. Set `SEED_DEMO_DATA=true` only for local development; demo data is assigned to `demo@expenseai.local` and is never shared with newly registered users.

## Architecture
`backend/app/main.py` contains the API composition, SQLAlchemy models, validation schemas and service-style analytical functions. SQLite is used by default and can be replaced with PostgreSQL via `DATABASE_URL`. `frontend/src/main.jsx` provides reusable page/components and API integration; CSS is responsive and theme-aware.

## Testing
```bash
cd backend && PYTHONPATH=. pytest -q
cd frontend && npm run build
```

## Future improvements
Alembic migrations, OCR adapter for receipts, recurring transaction automation, and optional hosted LLM provider.
