# SwingScout

AI trading advisor. Autonomous daily reports, thesis-based recommendations, paper account tracking.

- **Frontend:** swing-scout.netlify.app
- **Backend:** Railway (FastAPI)
- **DB:** Supabase

## Dev setup

```bash
# Backend
cd backend
cp .env.example .env   # fill in your keys
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
cp .env.example .env   # fill in VITE_* vars
npm install
npm run dev
```

## Local Docker backend

```bash
# Uses backend/.env for Supabase/AI keys and runs Redis locally in Docker
docker compose up --build
```

- Backend bude na `http://localhost:8000`
- Redis poběží lokálně v Compose a backend dostane `REDIS_URL=redis://redis:6379/0`
- Supabase zůstává externí, takže `backend/.env` pořád musí mít vyplněné `SUPABASE_*` klíče
- Frontend můžeš dál pustit normálně přes `cd frontend && npm run dev`

## Agent runner

```bash
# Daily deep run
python -m app.agent.runner --type daily

# Intraday light run
python -m app.agent.runner --type intraday
```

## Search providers

- `Alpha Vantage` je jedna ze Stage 1 discovery vrstev pro US movers/actives.
- `Tavily` + `Google News RSS` běží i pro rozšíření signálů: earnings, analyst moves, momentum a regionální news.
- Konfigurace: `ALPHA_VANTAGE_API_KEY`, `TAVILY_API_KEY`, `SEARCH_PROVIDER`, `SEARCH_FALLBACK_PROVIDER`, `SEARCH_MAX_CONCURRENCY`.
