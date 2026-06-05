# SwingScout

SwingScout is an AI-assisted swing trading app focused on:

- daily market reports
- thesis-based stock recommendations
- portfolio and watchlist tracking
- lightweight intraday monitoring for open positions

## Stack

- Frontend: React + Vite + TypeScript
- Backend: FastAPI
- Database/Auth: Supabase
- Cache/queue layer: Redis
- Deployment: Railway (backend) + Netlify (frontend)

## Project Structure

```text
swing-scout/
├── backend/      # FastAPI app, agent logic, market services
├── frontend/     # React app
├── docker-compose.yml
└── railway.toml
```

## Environment Variables

Backend variables live in `backend/.env` and are based on [backend/.env.example](/Users/jakubmares/Documents/Projects/swing-scout/backend/.env.example).

Required backend values:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `SUPABASE_ANON_KEY`
- `REDIS_URL`
- `ANTHROPIC_API_KEY`
- `TAVILY_API_KEY`
- `ALPHA_VANTAGE_API_KEY`
- `AGENT_USER_ID`

Optional backend tuning:

- `AI_MODEL`
- `SEARCH_PROVIDER`
- `SEARCH_FALLBACK_PROVIDER`
- `SEARCH_MAX_CONCURRENCY`
- `ENVIRONMENT`
- `FRONTEND_URL`

Frontend variables live in `frontend/.env` and are based on [frontend/.env.example](/Users/jakubmares/Documents/Projects/swing-scout/frontend/.env.example).

Required frontend values:

- `VITE_API_URL`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

## Local Development

### Backend

```bash
cd backend
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend runs on `http://localhost:8000`.

### Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Frontend runs on `http://localhost:5173`.

## Local Docker Backend

For local backend testing with Redis in Docker:

```bash
docker compose up --build
```

This setup:

- starts the backend on `http://localhost:8000`
- starts Redis locally inside Docker
- keeps Supabase external, so `backend/.env` still needs valid `SUPABASE_*` values

You can keep running the frontend separately with:

```bash
cd frontend
npm run dev
```

## Agent Runs

Run the agent from the `backend/` directory.

### Daily Run

```bash
python -m app.agent.runner --type daily
```

This is the full run. It:

- builds market context
- scans for candidates
- validates and ranks recommendations
- generates the daily markdown report
- stores results in Supabase

### Intraday Run

```bash
python -m app.agent.runner --type intraday
```

This is the lighter monitoring run. It:

- checks open portfolio positions
- looks for add / sell / exit alerts
- does not run full market-wide discovery

## Discovery and Market Data

Current discovery flow is multi-source:

- `Alpha Vantage` for movers and active names
- `Tavily` and search/news enrichment for catalysts and context
- `Google News RSS` as search fallback

Current market sentiment source:

- `CNN Fear & Greed` is used as the sentiment score source
- market regime is still derived separately from index technical trends

## Deployment Notes

### Backend

Railway is configured through [railway.toml](/Users/jakubmares/Documents/Projects/swing-scout/railway.toml) and [backend/Dockerfile](/Users/jakubmares/Documents/Projects/swing-scout/backend/Dockerfile).

### Cron Jobs

Production scheduling is expected to run as separate Railway cron services:

- one service for `daily`
- one service for `intraday`

They should run the same backend image with different start commands:

```bash
python -m app.agent.runner --type daily
python -m app.agent.runner --type intraday
```

## Frontend Notes

The frontend currently includes:

- dashboard with latest run and report
- recommendations workflow
- portfolio and thesis views
- watchlist
- history

Recommendations can originate from either:

- `daily`
- `intraday`

and the UI distinguishes the source.
