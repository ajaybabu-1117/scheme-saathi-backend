# SCHEME SAATHI Backend

AI-powered Government Scheme Assistant backend for India, built with FastAPI and designed to work with any frontend including Flutter, React, Next.js, Android, iOS, and web clients.

## Highlights
- REST-first backend
- Anonymous, Google, and email-style login flows for hackathon demo mode
- User profile storage
- Scheme search with semantic + lexical hybrid retrieval
- RAG chat with citations
- Eligibility checking
- Recommendation engine
- Voice query endpoint with Whisper + gTTS fallback hooks
- Dataset auto-discovery for CSV, TXT, JSON, and PDF
- Admin ingestion and reindex APIs
- Firebase-friendly architecture with local JSON fallback for quick demos

## Tech Stack
- Python 3.12
- FastAPI
- Firebase-ready repository layer
- ChromaDB
- OpenRouter DeepSeek model
- Sentence Transformers embeddings
- LangChain text splitters
- Redis optional

## Project Structure
```text
app/
├── api/v1/
├── core/
├── database/
├── models/
├── schemas/
├── repositories/
├── services/
├── middleware/
├── utils/
├── scripts/
└── main.py
```

## Quick Start
### 1) Clone and configure
```bash
cp .env.example .env
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Start locally
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3) Open docs
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/health

## Embeddings and Dataset Commands
### Build or refresh embeddings
```bash
python -m app.scripts.rebuild_embeddings
```

### Import datasets incrementally
```bash
python -m app.scripts.import_json_to_chroma
python -m app.scripts.import_csv_to_chroma
python -m app.scripts.import_txt_to_chroma
```

### View dataset stats
```bash
python -m app.scripts.dataset_stats
```

## Docker
### Build and run
```bash
cp .env.example .env
docker compose up --build
```

## Dataset Layout
```text
datasets/
├── central/
├── andhra-pradesh/
├── assam/
├── bihar/
└── uploads/
```

The backend discovers all supported files recursively and derives state metadata from folder names. File uploads via admin APIs land inside `datasets/uploads/`.

## Hackathon Notes
- If Firebase is not configured, the app automatically uses a local JSON store in `data/mock_db.json`.
- If an OpenRouter key is not configured, chat falls back to a deterministic demo answer built from retrieved context.
- A sample central dataset is included so the APIs work immediately after startup.
- Translation service is a no-op hook by default; replace with IndicTrans2 service wiring when ready.

## Suggested Frontend Integration Flow
1. Call `/api/v1/auth/anonymous` or `/api/v1/auth/login`
2. Save bearer token in the frontend
3. Update `/api/v1/profile`
4. Use `/api/v1/chat` for text assistant
5. Use `/api/v1/voice/query` for speech flow
6. Use `/api/v1/schemes/search` and `/api/v1/recommendations` for discovery UX

## Core Endpoints
- `GET /health`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/anonymous`
- `GET /api/v1/profile`
- `PUT /api/v1/profile`
- `POST /api/v1/chat`
- `GET /api/v1/schemes/search`
- `GET /api/v1/schemes/{id}`
- `GET /api/v1/recommendations`
- `POST /api/v1/eligibility/check`
- `POST /api/v1/voice/query`
- `POST /api/v1/notifications`
- `POST /api/v1/admin/upload-dataset`
- `POST /api/v1/admin/rebuild-embeddings`
- `POST /api/v1/admin/reindex`
- `GET /api/v1/admin/dataset-stats`

## Production Hardening Suggestions
- Replace demo login with full Firebase auth verification
- Add Redis caching for search and conversation state
- Add background job queue for ingestion
- Replace no-op translation with IndicTrans2 inference service
- Add rate limiting and API gateway
- Add role-based admin auth and audit logs
