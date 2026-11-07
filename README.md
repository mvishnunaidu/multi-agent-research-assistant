# Multi-Agent Research & Document Assistant

A production-engineered agentic AI system that performs in-depth technical research by orchestrating **four specialised sequential agents** (Planner → Researcher → Summarizer → Report Generator), backed by Retrieval-Augmented Generation (RAG) over user-uploaded documents (PDF, DOCX, TXT) and resilient multi-provider LLM failover.

Built with **React 19**, **FastAPI**, **LangChain**, **FAISS**, and **Google Gemini** (for both LLM generation and vector embeddings), with automated fallback across **OpenAI**, **Groq**, and **DeepSeek**.

---

## 1. Problem Statement & Objectives

### The Problem
Most "Chat with your PDF" implementations in the industry are single-turn wrappers around a naive prompt: `prompt = context + question`. This pattern breaks down on complex research inquiries because:
1. **No Decomposition:** Complex analytical queries require exploring multiple distinct sub-facets rather than one surface-level retrieval pass.
2. **Brittle Execution:** If a single vector store retrieval yields no chunks or the LLM encounters a rate limit (HTTP 429), the entire user request crashes with a 500 error.
3. **Hallucination & Fabrication:** Without strict grounding instructions and agentic synthesis stages, models routinely fabricate citations, invent nonexistent statistics, or mix outside assumptions with document facts.
4. **Heavy Resource Ingestion:** Many RAG tutorials instruct developers to bundle local PyTorch weights and Hugging Face sentence transformers (`all-MiniLM-L6-v2`), causing the backend container to consume >600MB RAM merely on module import. On free or starter cloud tiers (e.g., Render 512MB RAM limit), this triggers immediate Out-Of-Memory (OOM) termination.

### Project Objectives
- **Architectural Determinism:** Implement an understandable four-stage sequential pipeline using custom Python orchestration without hidden framework abstractions.
- **Strict Evidence Grounding:** Ensure document-grounded research answers cite genuine document sources and never invent page numbers, references, or metrics.
- **Fail-Safe Robustness:** Provide dual-layer resilience: (1) provider-level LLM fallback chain via LangChain `with_fallbacks()`, and (2) step-level fault isolation in `pipeline.py` recording authentic execution statuses (`completed`, `fallback`, `error`).
- **Cloud-Ready Memory Footprint:** Leverage Gemini's embedding API (`models/gemini-embedding-001`) with FAISS CPU indexing to maintain runtime memory well under 250MB, perfectly supporting 512MB container deployments on Render.
- **Executive-Ready UX:** Deliver a Linear/Raycast/Notion-inspired minimalist interface that displays real-time agent execution traces, durations, sub-task breakdowns, and markdown reports.

---

## 2. Complete Architecture & Data Flow

```
┌────────────────────────────────────────────────────────────────────────┐
│                        React 19 Client (Vite SPA)                      │
│   • 4-Agent Research Workspace      • Document Ingestion Panel         │
│   • Agent Execution Trace View      • Direct Conversational Mode       │
│   • Render Cold-Start Detector      • Session Query Audit History      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / REST (JSON)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Application Gateway                     │
│   POST /api/v1/session/new         POST /api/v1/upload                 │
│   POST /api/v1/research            POST /api/v1/chat                   │
│   GET  /api/v1/documents/{session} GET  /api/v1/history/{session}      │
│   GET  /api/v1/health              DELETE /api/v1/history/{session}    │
└──────────────────┬─────────────────────────────────┬───────────────────┘
                   │ Ingestion Pipeline              │ Research Pipeline
                   ▼                                 ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────┐
│        Document Store (RAG)          │  │     4-Agent Orchestrator     │
│ 1. PyPDF / Docx2txt / TextLoader     │  │                              │
│ 2. Empty & File Size Validation      │  │  Agent 1: Planner            │
│ 3. Recursive Text Splitter           │  │     (Pydantic Structured Plan)│
│    (800 chars / 150 overlap)         │  │           │                  │
│ 4. Gemini Embeddings API             │  │           ▼                  │
│    (models/gemini-embedding-001)     │  │  Agent 2: Researcher         │
│ 5. Session FAISS Vector Index        │  │     (Top-5 FAISS Similarity) │
│    (Persisted to disk / session)     │  │           │                  │
└──────────────────┬───────────────────┘  │           ▼                  │
                   │ Top-5 Similarity     │  Agent 3: Summarizer         │
                   │ Chunks & Metadata    │     (Evidence Synthesis)     │
                   └─────────────────────▶│           │                  │
                                          │           ▼                  │
                                          │  Agent 4: Report Generator   │
                                          │     (5-Section Markdown Rep) │
                                          └───────────────┬──────────────┘
                                                          │
                                                          ▼
                                          ┌──────────────────────────────┐
                                          │   Multi-LLM Fallback Chain   │
                                          │   Primary: Google Gemini     │
                                          │   Fallback 1: OpenAI         │
                                          │   Fallback 2: Groq           │
                                          │   Fallback 3: DeepSeek       │
                                          └──────────────────────────────┘
```

---

## 3. Four-Agent Responsibilities & Data Contracts

Each agent is a focused, testable Python function adhering to a strict input/output contract:

| Stage | Agent | Input | Output Contract | Key Responsibility |
|---|---|---|---|---|
| **01** | **Planner** (`planner.py`) | `query: str`, `has_documents: bool` | `{"sub_tasks": List[str], "reasoning": str, "status": str, "error": Optional[str]}` | Validates and generates 2–4 atomic sub-tasks using Pydantic structured output (`Plan`). If model output fails validation or rate limits hit, gracefully falls back to direct query execution. |
| **02** | **Researcher** (`researcher.py`) | `sub_tasks: List[str]`, `session_id: str`, `has_documents: bool` | `{"answers": List[str], "retrieved_chunks": List[str], "source_files": List[str], "grounding": str, "status": str, "error": Optional[str]}` | Executes retrieval against the session's FAISS index (top-5 similarity). Grounds answers strictly on retrieved excerpts. When no documents are uploaded, relies on general knowledge and explicitly notes general knowledge grounding. |
| **03** | **Summarizer** (`summarizer.py`) | `query: str`, `answers: List[str]` | `{"summary": str, "status": str, "error": Optional[str]}` | Synthesizes raw findings across sub-tasks. Strictly preserves technical metrics, proper nouns, and citations without introducing external claims. |
| **04** | **Report Generator** (`report_generator.py`) | `query: str`, `summary: str`, `source_files: List[str]` | `{"report": str, "status": str, "error": Optional[str]}` | Assembles findings into a formal 5-section Markdown research report with genuine source attribution. |

### The 5-Section Report Standard
The Report Generator strictly generates reports with this format:
1. `# Research Report`
2. `## Executive Summary` (2–3 sentences answering the core query)
3. `## Findings` (In-depth analysis grouped into logical subheadings)
4. `## Key Takeaways` (3–5 bullet points capturing actionable takeaways)
5. `## Sources` (Explicit list of cited document filenames or "General knowledge")

---

## 4. Pipeline Orchestration & Fault Isolation

The pipeline orchestrator (`backend/agents/pipeline.py`) executes agents sequentially, measuring execution durations and recording real audit steps:

- **Meaningful Statuses:** Each step records one of `completed`, `fallback`, `error`, `running`, `pending`, or `skipped`.
- **Duration Tracking:** Timing is measured with `time.perf_counter()` to millisecond precision.
- **Fault Isolation:** An error in Planner, Researcher, or Summarizer does not crash the HTTP request. Instead, partial data is safely passed to downstream agents, and the overall status is honestly marked as `fallback` or `error`.
- **Honest Trace Reporting:** The user interface displays genuine execution data directly from the FastAPI response rather than hardcoded mock delays.

---

## 5. RAG Workflow & Document Processing

### Supported File Types
- **PDF Documents:** `.pdf` loaded via `PyPDFLoader` with page number metadata.
- **Word Documents:** `.docx` loaded via `Docx2txtLoader`.
- **Plain Text:** `.txt` loaded via `TextLoader` with multi-encoding fallback (UTF-8, Latin-1).
- **Legacy `.doc`:** Explicitly rejected with a 400 Bad Request error explaining that binary Word 97–2003 format is unsupported and prompting the user to convert to `.docx` or `.pdf`.

### Ingestion Pipeline
1. **Security & Validation:**
   - Validates `session_id` using regex/UUID checks to prevent path traversal.
   - Sanitizes filenames to eliminate directory traversal characters (`..`, `/`, `\`).
   - Rejects empty files (0 bytes) and files exceeding the 20MB limit.
2. **Text Chunking:**
   - Chunk size: **800 characters**
   - Chunk overlap: **150 characters**
   - Separators: `["\n\n", "\n", ". ", " ", ""]` via `RecursiveCharacterTextSplitter`.
3. **Embeddings:**
   - Computed remotely via Google Gemini Embeddings (`models/gemini-embedding-001`).
   - Requires zero local PyTorch weights or model files, keeping memory footprint low.
4. **FAISS Vector Indexing & Session Isolation:**
   - Indexes are isolated per session under `vectorstores/{session_id}/index.faiss`.
   - Index merging: when additional files are uploaded to the same session, chunks are added to the existing index without re-embedding old files.
   - Duplicate prevention: a session manifest tracks indexed files, preventing duplicate indexing of identical files.
5. **Safe Deserialization:**
   - FAISS local loading (`allow_dangerous_deserialization=True`) is restricted strictly to application-created indexes inside validated session directories.

---

## 6. Multi-LLM Fallback Architecture

Configured in `backend/core/llm.py`:

```
1. Google Gemini (Primary: gemini-2.5-flash)
        │ (on RateLimit / 429 / Outage)
        ▼
2. OpenAI (Secondary: gpt-4o-mini)
        │
        ▼
3. Groq (Tertiary: llama-3.3-70b-versatile)
        │
        ▼
4. DeepSeek (Final: deepseek-chat)
```

- Built using LangChain's native `.with_fallbacks()` construct.
- Dynamically discovers which providers have active API keys in the environment.
- The `/api/v1/health` endpoint reports the actual active primary provider and all configured fallback providers.

---

## 7. API Reference

All routes are prefixed with `/api/v1`:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Honest health check (version, active primary provider, configured providers, embeddings status, vector store) |
| `POST` | `/session/new` | Generates a fresh UUID4 session identifier |
| `POST` | `/upload` | Validates, chunks, embeds, and indexes a `.pdf`, `.docx`, or `.txt` file into the session's FAISS store |
| `GET` | `/documents/{session_id}` | Lists all documents and chunk counts indexed for the given session |
| `POST` | `/research` | Executes the full 4-agent research pipeline inside a worker thread pool |
| `POST` | `/chat` | Direct conversational mode with multi-turn memory and optional RAG grounding |
| `GET` | `/history/{session_id}` | Retrieves query and response audit history for the session |
| `DELETE` | `/history/{session_id}` | Clears in-memory session history |

---

## 8. Project Structure

```
Multi-Agent Research Assistant/
├── backend/
│   ├── agents/
│   │   ├── pipeline.py          # 4-agent sequential orchestrator & audit metrics
│   │   ├── planner.py           # Agent 1: Pydantic structured query decomposition
│   │   ├── researcher.py        # Agent 2: FAISS RAG retrieval & evidence extraction
│   │   ├── summarizer.py        # Agent 3: Factually grounded evidence synthesis
│   │   └── report_generator.py  # Agent 4: Formal 5-section Markdown report writer
│   ├── api/
│   │   ├── routes.py            # FastAPI endpoints, validation, threadpool execution
│   │   └── schemas.py           # Pydantic request/response schemas
│   ├── core/
│   │   ├── config.py            # Central settings, paths, limits from .env
│   │   ├── document_store.py    # Document loading, chunking, FAISS, Gemini embeddings
│   │   └── llm.py               # Dynamic LLM provider fallback factory
│   ├── tests/
│   │   ├── conftest.py          # Pytest fixtures and TestClient
│   │   ├── test_api.py          # API validation, security, and route integration tests
│   │   ├── test_document_store.py # Document loader, session isolation, and FAISS tests
│   │   └── test_pipeline.py     # Multi-agent orchestrator unit tests (fully mocked)
│   └── main.py                  # FastAPI app entry point & SPA static file serving
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Main React 19 application (4 workspaces, traces, reports)
│   │   ├── index.css            # Linear/Raycast/Notion minimalist design system
│   │   └── main.jsx             # React DOM root entry
│   ├── package.json             # React 19, Vite, Lucide React, React Markdown
│   └── vite.config.js           # Vite dev proxy configuration
├── Dockerfile                   # Multi-stage production build (Node 20 + Python 3.11)
├── requirements.txt             # Core production dependencies
├── requirements-dev.txt         # Development and testing dependencies
├── pytest.ini                   # Pytest configuration
├── .env.example                 # Environment variable template
├── .gitignore                   # Git exclusion rules
├── .dockerignore                # Container packaging exclusion rules
└── README.md                    # Technical documentation
```

---

## 9. Local Setup & Execution

### Prerequisites
- Python 3.10+
- Node.js 18+ and npm
- At least one LLM API key (`GEMINI_API_KEY` is recommended as it provides both generation and embeddings).

### Step 1: Environment Setup
```bash
cp .env.example .env
```
Edit `.env` to configure your keys:
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

### Step 2: Backend Installation & Run
```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate       # Windows
source venv/bin/activate    # macOS / Linux

# Install dependencies
pip install -r requirements-dev.txt

# Start FastAPI server
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```
- API Documentation: http://localhost:8000/docs
- Health Check: http://localhost:8000/api/v1/health

### Step 3: Frontend Installation & Run
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173 in your browser. Vite proxies `/api` directly to `http://localhost:8000`.

---

## 10. Automated Testing

The automated test suite runs completely offline without requiring live network calls, API keys, or GPU access:

```bash
# Run backend pytest suite
pytest -v
```

Expected output:
```
======================= 25 passed in 0.19s =======================
```

Frontend linting & production build:
```bash
cd frontend
npm run lint
npm run build
```

---

## 11. Docker & Render Deployment

### Multi-Stage Dockerfile
The included `Dockerfile` uses a multi-stage build:
1. **Stage 1 (Frontend Build):** Uses `node:20-slim` to compile the React 19 app into `/app/frontend/dist`.
2. **Stage 2 (Backend Runtime):** Uses `python:3.11-slim`, installs system build tools and `requirements.txt`, copies compiled frontend assets, and serves both via Uvicorn.

```bash
# Build Docker image
docker build -t research-assistant .

# Run Docker container
docker run -p 8000:8000 -e GEMINI_API_KEY=your_key research-assistant
```

### Render Deployment Instructions
1. Push repository to GitHub.
2. In Render Dashboard, click **New +** → **Web Service**.
3. Select your repository.
4. Set **Runtime** to **Docker**.
5. Set **Instance Type** to **Free** (512MB RAM).
6. Under **Environment Variables**, add:
   - `GEMINI_API_KEY`: `<your-gemini-api-key>`
   - `GEMINI_MODEL`: `gemini-2.5-flash`
   - `GEMINI_EMBEDDING_MODEL`: `models/gemini-embedding-001`
7. Click **Create Web Service**. Render will build the Docker container and route traffic to the container port defined by `${PORT}`.

---

## 12. Current Architectural Limitations & Future Roadmap

### Current Limitations
1. **In-Memory History:** Chat and query histories are stored in process memory. If the server instance restarts (e.g. Render spin-down), history is cleared.
2. **Synchronous Sequence:** Agents run sequentially (Planner → Researcher → Summarizer → Report Generator). Parallel sub-task research is not yet implemented.
3. **Document Grounding Only:** The system retrieves strictly from uploaded user documents or foundational LLM knowledge; live web search is not currently integrated.
4. **Local Ephemeral FAISS Storage:** Vector stores are written to local disk. On container restarts without persistent volume mounts, indices must be re-uploaded.

### Future Roadmap
- **Persistent Storage:** Integrate PostgreSQL with `pgvector` or Supabase for persistent conversation histories and vector storage.
- **Parallel Sub-Task Retrieval:** Execute Researcher RAG retrievals concurrently via `asyncio.gather()` for faster execution.
- **Hybrid Search:** Combine BM25 keyword search with dense vector similarity search (Reciprocal Rank Fusion) for improved retrieval precision.
- **Web Retrieval Agent:** Add an optional fifth agent for real-time web search verification.
- **Streaming Output:** Implement Server-Sent Events (SSE) or WebSockets to stream agent traces in real time.

---

## 13. License

MIT License. See [LICENSE](./LICENSE) for details.
