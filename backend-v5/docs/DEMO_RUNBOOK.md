# Demo Runbook (Local) — Nepal OSINT v5

## 1) Start infrastructure

```bash
cd backend-v5
docker compose up -d postgres redis
```

## 2) Backend (API + scheduler)

```bash
cd backend-v5
source venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

### Optional toggles (safe by default)

- Increase/decrease clustering merges (event detection):
  - `CLUSTERING_SMART_THRESHOLD=0.70` (default; lower = more recall, higher = more precision)
- Enable RL priority influence at ingestion-time (still only escalates severity, never downgrades):
  - `ML_ENABLE_PRIORITY_BANDIT=1`
- Keep trained embedding classifier off unless you explicitly want it:
  - `ML_ENABLE_EMBEDDING_CLASSIFIER=0`

## 3) Frontend

```bash
cd frontend
npm i
npm run dev
```

Make sure `frontend/.env.development` has:
```env
VITE_API_URL=http://localhost:8001
```

## 4) Feed + clustering refresh (demo actions)

Trigger ingestion:
```bash
curl -X POST http://localhost:8001/api/v1/ingest/trigger
```

Trigger clustering (event detection):
```bash
curl -X POST "http://localhost:8001/api/v1/stories/cluster?hours=72&min_cluster_size=2"
```

## 5) Analyst workflow

- Open `/ops` in the frontend
- Review an event → verify/override if needed → click **Publish**
- Customers then see the published event in their dashboard feed

