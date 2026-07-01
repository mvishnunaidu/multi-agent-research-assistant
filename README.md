# 🔬 Multi-Agent Research & Document Assistant

A full-stack Generative AI application that answers research questions by orchestrating **four specialized AI agents**, and can ground its answers in your own PDF/DOCX/TXT documents using Retrieval-Augmented Generation (RAG).

Built with **React**, **FastAPI**, **LangChain**, **FAISS**, and the **Gemini API** for both generation and embeddings.

---

## Why this project exists

Most "chat with your PDF" demos are a single prompt wrapped around an LLM call. This project instead treats a research question as a **pipeline**: a Planner agent breaks it into sub-tasks, a Researcher agent retrieves grounded evidence for each one, a Summarizer condenses the findings, and a Report Generator assembles a structured final report — with a full audit trail of what each agent did and why.

It also assumes LLM providers *will* fail (rate limits, outages, revoked keys) and is built to survive that: both at the **provider level** (automatic fallback across 4 LLM providers) and at the **pipeline level** (if one agent errors, the pipeline degrades gracefully instead of crashing the request).

---

## Architecture

```
┌─────────────┐     ┌──────────────────────────────────────────────────┐
│   React UI   │────▶│                   FastAPI Backend                 │
│ (Vite, SPA)  │◀────│                                                    │
└─────────────┘     │  /chat      → direct conversational mode           │
                     │  /research  → 4-agent pipeline                    │
                     │  /upload    → PDF/DOCX/TXT → chunk → embed → FAISS│
                     └───────────┬────────────────────────────────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                                ▼
      ┌─────────────────────┐         ┌─────────────────────────┐
      │  4-Agent Pipeline    │         │   FAISS Vector Store     │
      │                       │         │   (per-session, local)   │
      │ 1. Planner            │◀───────▶│   Gemini embeddings API  │
      │ 2. Researcher (RAG)   │         │   (all-MiniLM-L6-v2)     │
      │ 3. Summarizer         │         └─────────────────────────┘
      │ 4. Report Generator   │
      └──────────┬────────────┘
                 ▼
      ┌─────────────────────────────┐
      │  Multi-LLM Fallback Chain    │
      │  Gemini → OpenAI → Groq →    │
      │  DeepSeek                    │
      └─────────────────────────────┘
```

**The 4-agent pipeline:**

| Agent | Responsibility |
|---|---|
| **Planner** | Decomposes the query into 2–4 focused, atomic sub-tasks using structured output (Pydantic schema) |
| **Researcher** | Runs RAG retrieval per sub-task against the session's FAISS index; falls back to general LLM knowledge when no documents are uploaded |
| **Summarizer** | Condenses raw findings into a clean, factual summary without inventing new information |
| **Report Generator** | Assembles a structured Markdown report (Executive Summary → Findings → Key Takeaways → Sources) |

Every step is wrapped in its own try/except in `pipeline.py`, so a single agent failure produces a logged `AgentStep` with `status="error"` instead of a 500 response — the pipeline falls back to the best partial result it has.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite, react-markdown, lucide-react |
| Backend / API | FastAPI, Uvicorn, Pydantic v2 |
| Orchestration | LangChain (custom pipeline — no LangGraph dependency) |
| Vector store | FAISS (per-session, persisted to disk) |
| Embeddings | Gemini `gemini-embedding-001` via API (no local model — keeps RAM low on free-tier hosts) |
| LLMs | Gemini 2.5 Flash (primary) → OpenAI → Groq → DeepSeek (automatic fallback via `with_fallbacks`) |
| Testing | Pytest + FastAPI `TestClient`, mocked agent functions (no live API calls needed) |
| Deployment | Dockerfile (multi-stage: builds the React app, serves it from FastAPI) |

---

## Quick start

### 1. Clone and configure

```bash
git clone https://github.com/<your-username>/multi-agent-research-assistant.git
cd multi-agent-research-assistant
cp .env.example .env
```

Open `.env` and add at least one API key (`GEMINI_API_KEY` is enough to run everything — [get one free at Google AI Studio](https://aistudio.google.com/app/apikey)).

### 2. Backend

```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — the Vite dev server proxies `/api` to the backend automatically, so no CORS setup is needed locally.

### 4. Run the tests

```bash
pip install -r requirements-dev.txt
pytest
```

### 5. Run with Docker (optional)

```bash
docker build -t research-assistant .
docker run -p 8000:8000 --env-file .env research-assistant
```

This builds the React app and serves it directly from FastAPI at `http://localhost:8000`.

---

## Project structure

```
backend/
  agents/            # planner, researcher, summarizer, report_generator, pipeline orchestrator
  api/                # FastAPI routes + Pydantic request/response schemas
  core/               # settings, LLM factory (multi-provider fallback), document store (FAISS)
  tests/              # pytest suite — pipeline orchestration + API validation, fully mocked
  main.py             # FastAPI app entrypoint
frontend/
  src/App.jsx         # single-page React UI: chat, document upload, session history
  src/index.css
Dockerfile            # multi-stage build: React → static assets served by FastAPI
requirements.txt
requirements-dev.txt
```

---

## Design decisions worth calling out

- **Custom orchestration instead of LangGraph.** The 4-agent pipeline is a plain Python function chain (`pipeline.py`) rather than a graph framework. For a linear 4-step pipeline this is simpler to read, debug, and test, and avoids pulling in a framework whose abstractions aren't needed yet.
- **API embeddings, not a local model.** An earlier version used `sentence-transformers` locally. That pulls in `torch`, which alone uses several hundred MB of RAM just to import — reliably OOM-killed the app on free-tier hosts with a 512MB limit (Render, Railway, Fly.io free plans). Calling Gemini's embedding endpoint instead keeps the whole app comfortably under that limit, at the cost of one extra network call per chunk (batched, so ingestion is still fast). Trade-off: document upload now requires `GEMINI_API_KEY` specifically, even if you're running chat through a different provider.
- **Provider-level *and* pipeline-level fault tolerance.** `with_fallbacks()` handles a single LLM call failing over to another provider; the pipeline's per-agent try/except handles a *logic* failure (e.g. empty vector store) without cascading into a 500.
- **Lazy-loaded embeddings client.** The embeddings client only initializes on first actual use (a document upload), not at import time — so `/health` and other non-RAG endpoints stay fast, and the test suite doesn't need a live API key to run.

---

## Deploying (Render, or any free-tier host)

This app is sized to run on Render's **free 512MB web service tier**. A few things that matter if you deploy it there:

- **Set `GEMINI_API_KEY` in the Render dashboard's Environment tab** (Settings → Environment) — it's required for both chat and document embeddings.
- **Free instances spin down after inactivity** and take ~50s to wake on the next request. The frontend now shows a clear "server may be starting up" message instead of a cryptic error during that window (see below).
- If you see **"Ran out of memory"** in Render's Events tab: make sure you're on this version of `requirements.txt` (no `sentence-transformers`/`torch`). That combination alone routinely exceeds 512MB on import, before your app code even runs — it's the most common cause of OOM crashes on this kind of project.

### Troubleshooting: "Unexpected end of JSON input" in the UI

This means the backend returned an empty response — almost always because it crashed mid-request (OOM) or is still cold-starting behind Render's proxy. The frontend now parses responses defensively and shows *why* the request failed instead of that raw error. If you still see it after redeploying with the current `requirements.txt`, check the Render **Logs** tab for the actual backend stack trace.

## License

MIT — see [LICENSE](./LICENSE).
