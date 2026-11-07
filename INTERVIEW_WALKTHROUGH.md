# Multi-Agent Research Assistant — Technical Interview Guide & Source Code Walkthrough

Prepared for technical interviews and architecture evaluations with AI startup founders and engineering leads.

---

# TABLE OF CONTENTS
1. **PART 1: PROJECT INTRODUCTION & SPEAKING SCRIPTS**
   - 60-Second Elevator Pitch
   - 3-Minute Product & Engineering Summary
   - 5-Minute Technical Overview
   - 10-Minute Deep-Dive Presentation Script
2. **PART 2: ARCHITECTURE & SYSTEM DATA FLOW**
   - End-to-End Research Query Lifecycle
   - Document Ingestion & RAG Indexing Flow
   - Dual-Layer Fault Tolerance Architecture
   - Memory Optimization Strategy for Cloud Deployments
3. **PART 3: SOURCE-CODE WALKTHROUGH (FILE BY FILE)**
   - `backend/agents/pipeline.py`
   - `backend/agents/planner.py`
   - `backend/agents/researcher.py`
   - `backend/agents/summarizer.py`
   - `backend/agents/report_generator.py`
   - `backend/core/document_store.py`
   - `backend/core/llm.py`
   - `backend/api/routes.py`
   - `backend/api/schemas.py`
   - `backend/core/config.py`
   - `backend/main.py`
   - `frontend/src/App.jsx`
4. **PART 4: FOUNDER-LEVEL TECHNICAL QUESTIONS & ANSWERS (45 DETAILED QUESTIONS)**
   - Multi-Agent Orchestration & Agent Collaboration (Q1–Q7)
   - Retrieval-Augmented Generation (RAG) & Vector Storage (Q8–Q15)
   - LLM Reliability, Failover & Error Handling (Q16–Q22)
   - Backend Architecture, Concurrency & Security (Q23–Q29)
   - Frontend Engineering & User Experience (Q30–Q34)
   - System Design, Scalability & Production Operations (Q35–Q40)
   - Critical Scenario-Based Failure Drills (Q41–Q45)
5. **PART 5: 10-MINUTE LIVE DEMONSTRATION PLAN**
6. **PART 6: TOP 5 SOURCE FILES TO STUDY BEFORE THE INTERVIEW**

---

# PART 1: PROJECT INTRODUCTION & SPEAKING SCRIPTS

## 60-Second Elevator Pitch
> *"I built a production-grade Multi-Agent Research Assistant that transforms unstructured user questions into verified, publication-grade research reports. Unlike typical 'chat-with-PDF' wrappers that throw raw context into a single prompt, this application uses a sequential four-agent pipeline: a Planner agent decomposes queries into atomic sub-tasks using Pydantic structured output, a Researcher agent performs top-5 FAISS similarity retrieval over ingested documents, a Summarizer synthesizes findings without hallucinating, and a Report Generator formats a strict five-section Markdown report. To make it truly cloud-viable on Render's 512MB RAM tier, I used Gemini API embeddings instead of heavy local PyTorch models, and built dual-layer resilience: multi-provider failover across Gemini, OpenAI, Groq, and DeepSeek, alongside isolated step-level execution tracking. Every metric and status shown in the Linear-inspired React UI is authentic backend telemetry."*

## 3-Minute Product & Engineering Summary
> *"When looking at generative AI applications today, the most common anti-pattern is treating complex information synthesis as a single prompt problem. If you ask an LLM to read a 50-page document and deliver an authoritative analysis in one shot, it suffers from attention degradation, loses needle-in-the-haystack details, and frequently hallucinates citations.*
>
> *I designed this application to demonstrate how agentic decomposition solves that problem cleanly. The architecture is a sequential four-agent pipeline built with Python, FastAPI, React 19, and LangChain:*
>
> 1. *The **Planner** agent breaks down high-level queries into two to four focused sub-tasks using structured outputs. If structured output encounters a rate limit or malformed response, it gracefully degrades to a direct query execution rather than failing.*
> 2. *The **Researcher** agent receives those sub-tasks and conducts focused vector similarity searches against a session-isolated FAISS store. It grounds findings strictly in the retrieved excerpts. If no documents exist, it transparently shifts to foundational knowledge without pretending it retrieved document citations.*
> 3. *The **Summarizer** synthesizes the research findings, strictly retaining technical metrics, proper nouns, and citations.*
> 4. *The **Report Generator** compiles the final synthesis into a standardized 5-section Markdown report: Executive Summary, Findings, Key Takeaways, and Sources.*
>
> *From an infrastructure perspective, I optimized this specifically for lean production deployment on Render. Bundling local Hugging Face sentence transformers with PyTorch typically consumes 600MB on startup, crashing 512MB containers with an OOM error. By using Google Gemini’s embedding API (`models/gemini-embedding-001`) paired with FAISS-CPU, the backend runs comfortably under 250MB. Furthermore, our LLM factory uses LangChain's `with_fallbacks()` across Gemini, OpenAI, Groq, and DeepSeek to guarantee uptime."*

## 5-Minute Technical Overview
> *(Structure: Motivation → Architecture → RAG Details → Resilience & Telemetry → Demo Preview)*
>
> *"Hello! Today I'm demonstrating a Multi-Agent Research Assistant I designed and implemented. I want to walk you through the three core architectural decisions that make this system robust, reliable, and production-ready.*
>
> *First: **Deterministic Agentic Orchestration.** Many multi-agent frameworks like AutoGen or complex graph cycles introduce non-deterministic loops, unpredictable token consumption, and state-debugging nightmares. For analytical research reports, I chose a deterministic sequential pipeline of four specialized agents: Planner, Researcher, Summarizer, and Report Generator. The orchestrator in `pipeline.py` maintains an isolated audit step for each agent, recording execution durations via high-resolution timers and authentic execution statuses: `completed`, `fallback`, or `error`. If any individual agent hits an issue, downstream agents receive clean partial data, allowing the user to still receive a useful report.*
>
> *Second: **Engineered RAG & Resource Discipline.** The system ingests PDFs, DOCX, and TXT files. In `document_store.py`, documents are loaded, validated against 0-byte or unreadable text conditions, and split using `RecursiveCharacterTextSplitter` into 800-character chunks with 150-character overlap. Each chunk retains rich metadata: `source_file`, `session_id`, and `chunk_index`. To prevent Out-Of-Memory termination on cloud free tiers like Render (512MB limit), I chose Google Gemini's embedding API over local PyTorch models. Embeddings are stored in session-isolated FAISS indices. Uploading multiple files to a session cleanly merges into the existing vector store, while a session manifest prevents redundant re-indexing of duplicate files.*
>
> *Third: **Dual-Layer Resilience.** At the provider level, `llm.py` chains Gemini as the primary LLM with automatic fallback to OpenAI, Groq, and DeepSeek using LangChain's `with_fallbacks()`. If Gemini hits an HTTP 429 rate limit, the request seamlessly executes on the fallback provider. At the API level, all synchronous, CPU- or network-heavy operations (`run_pipeline`, `ingest_file`, `llm.invoke`) are dispatched via `asyncio.to_thread` to prevent blocking FastAPI’s event loop.*
>
> *Finally, the frontend is built in React 19 with a minimalist, Linear-inspired design system. It displays real agent durations, sub-task breakdowns, live document manifests, and a rendered Markdown report with working clipboard copy and `.md` file download."*

## 10-Minute Deep-Dive Presentation Script
> *"Good morning. Today I will provide a deep-dive walkthrough of my Multi-Agent Research Assistant. We'll cover the motivation, the data contracts between agents, the vector retrieval mechanics, the failover architecture, and the codebase design.*
>
> *[SLIDE / SCREEN SHARE: ARCHITECTURE DIAGRAM]*
>
> *Let's trace what happens when a user submits a query like 'Analyze transformer attention mechanisms versus recurrent state spaces in modern language models.'*
>
> *The request hits `POST /api/v1/research`. FastAPI validates the UUID session format and non-empty query string using Pydantic. Because the research pipeline involves multiple sequential network round-trips, the route dispatches execution to a worker thread using `asyncio.to_thread(run_pipeline, ...)`. This is crucial: in FastAPI, executing long-running synchronous code directly in an `async def` handler blocks the main asyncio event loop, preventing all concurrent requests from being processed.*
>
> *Inside `pipeline.py`, **Agent 1 (Planner)** starts. Its responsibility is query decomposition. We prompt the LLM using Pydantic structured output (`with_structured_output(Plan)`), requiring two to four atomic sub-tasks and a single sentence of decomposition reasoning. A Pydantic field validator strips whitespace, deduplicates sub-tasks, and asserts that at least two sub-tasks exist. If the model outputs invalid JSON or hits an API rate limit, `planner.py` catches the exception and returns the original query as a single task, setting `status="fallback"`. Notice that our orchestrator records this as `fallback`, rather than falsely reporting success.*
>
> *Next, **Agent 2 (Researcher)** receives those sub-tasks. If documents have been ingested for the session, it loads the FAISS index from `vectorstores/{session_id}/index.faiss`. For each sub-task, it invokes the similarity retriever (`k=5`). The retrieved chunks are formatted with source filename and page numbers into a strict context block. The LLM prompt explicitly commands: 'Base your answer solely on facts and statements present in the context excerpts. Do not speculate or invent citations.' If no chunks match a sub-task, it explicitly states that the document does not contain that information. If no documents exist in the session, the agent transparently uses foundational LLM knowledge while setting `grounding="general_knowledge"`.*
>
> *Next, **Agent 3 (Summarizer)** receives the raw answers. Its job is factual synthesis: it groups insights into coherent paragraphs while preserving exact quantitative metrics, technical terms, and source attributions. If the researcher's answers are empty, it gracefully reports that no findings were available.*
>
> *Finally, **Agent 4 (Report Generator)** takes the synthesized summary, original query, and verified list of source filenames. It compiles the report into an exact 5-section standard: Title, Executive Summary, Findings, Key Takeaways, and Sources. Crucially, the sources section only cites real uploaded filenames, or clearly states 'General knowledge (no documents uploaded)'.*
>
> *Now, let's look at the document ingestion pipeline. When a user uploads a PDF, DOCX, or TXT file through the UI, `routes.py` streams the file in 64KB chunks to `uploads/{session_id}/{sanitized_filename}`, enforcing a strict 20MB file size ceiling. It rejects legacy `.doc` files because binary Word 97-2003 formats require external COM/OLE parsers that are unreliable in Linux containers. Once saved, `ingest_file()` loads the document, splits it via `RecursiveCharacterTextSplitter` into 800-character chunks with 150-character overlap, and calls `GoogleGenerativeAIEmbeddings` using `models/gemini-embedding-001`. The resulting vectors are indexed in FAISS and saved to disk. When a second file is uploaded, FAISS merges the new vectors into the existing index, and an index manifest ensures that identical files are not re-embedded.*
>
> *Let's now inspect the source files directly to see how these abstractions are implemented in clean, idiomatic Python and React."*

---

# PART 2: ARCHITECTURE & SYSTEM DATA FLOW

## 1. End-to-End Research Query Lifecycle
```
User clicks "Run 4-Agent Research"
       │
       ▼
React Frontend (`App.jsx`)
       │ POST /api/v1/research {session_id, query, has_documents}
       ▼
FastAPI Gateway (`routes.py`)
       │ Session ID validated via regex/UUID
       │ Dispatched to threadpool: `asyncio.to_thread(run_pipeline, ...)`
       ▼
Pipeline Orchestrator (`pipeline.py`)
       │
       ├─► 1. `run_planner(query, has_documents)`
       │      • Calls `llm.with_structured_output(Plan)`
       │      • Pydantic validation: 2 <= len(sub_tasks) <= 4
       │      • Output: `sub_tasks`, `reasoning`, `status`, `error`
       │      • Audit: Records duration (e.g. 1.12s) and status
       │
       ├─► 2. `run_researcher(sub_tasks, session_id, has_documents)`
       │      • If docs: FAISS `retriever.invoke(task)` (k=5)
       │      • Formats excerpts: `[Excerpt N | Source: file.pdf (Page X)]`
       │      • Prompt: Strict RAG grounding (no hallucination)
       │      • If no docs: General LLM prompt
       │      • Output: `answers`, `retrieved_chunks`, `source_files`, `grounding`
       │      • Audit: Records duration (e.g. 2.45s) and status
       │
       ├─► 3. `run_summarizer(query, answers)`
       │      • Synthesizes multi-task findings
       │      • Preserves numbers, technical terms, and citations
       │      • Output: `summary`, `status`, `error`
       │      • Audit: Records duration (e.g. 1.05s) and status
       │
       └─► 4. `run_report_generator(query, summary, source_files)`
              • Assembles 5-section Markdown report
              • 1. # Research Report
              • 2. ## Executive Summary
              • 3. ## Findings
              • 4. ## Key Takeaways
              • 5. ## Sources
              • Output: `report`, `status`, `error`
              • Audit: Records duration (e.g. 1.30s) and status
       │
       ▼
PipelineResult constructed
       │ Returns final_report, plan, agent_steps, sources, overall_status
       ▼
FastAPI returns JSON response
       │
       ▼
React UI displays:
       • 4 agent cards with genuine duration and status badges
       • Planner sub-tasks
       • Rendered Markdown report
       • Verified source document pills
       • Working "Copy Markdown" and "Download .md" buttons
```

## 2. Document Ingestion & RAG Indexing Flow
```
User drops PDF / DOCX / TXT file in UI
       │
       ▼
`POST /api/v1/upload?session_id={UUID}`
       │
       ├─► Step 1: Validation & Sanitization
       │      • Filename sanitization (`sanitize_filename` removes traversal characters)
       │      • Format validation: Allows `.pdf`, `.docx`, `.txt`; rejects `.doc`
       │      • Size validation: Streams in 64KB chunks; aborts if > 20MB
       │      • Empty file validation: Rejects 0-byte uploads
       │
       ├─► Step 2: Threadpool Document Loading (`document_store.py`)
       │      • `.pdf`  -> `PyPDFLoader`
       │      • `.docx` -> `Docx2txtLoader`
       │      • `.txt`  -> `TextLoader` (UTF-8 with Latin-1 fallback)
       │      • Validates total extracted character count > 0
       │
       ├─► Step 3: Chunking
       │      • `RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)`
       │      • Attaches metadata: `source_file`, `session_id`, `chunk_index`, `page`
       │
       ├─► Step 4: Duplicate Check & Ingestion
       │      • Inspects `vectorstores/{session_id}/manifest.json`
       │      • If file already indexed: returns existing chunk count immediately
       │
       ├─► Step 5: Embeddings & FAISS Indexing
       │      • Calls Google Gemini API (`models/gemini-embedding-001`)
       │      • If `index.faiss` exists: `existing_vs.add_documents(chunks)`
       │      • If fresh session: `FAISS.from_documents(chunks, embeddings)`
       │      • Saves to `vectorstores/{session_id}/index.faiss`
       │      • Updates `manifest.json`
       │
       ▼
Returns `UploadResponse` with `num_chunks` and confirmation message
```

## 3. Dual-Layer Fault Tolerance Architecture
1. **Layer 1: Provider-Level Fallback (`backend/core/llm.py`)**
   - Configured via LangChain's `.with_fallbacks()` construct.
   - Primary: Gemini 2.5 Flash.
   - Failover 1: OpenAI `gpt-4o-mini`.
   - Failover 2: Groq `llama-3.3-70b-versatile`.
   - Failover 3: DeepSeek `deepseek-chat`.
   - Handles network timeouts, HTTP 429 quota exhaustion, and transient API downtime automatically.
2. **Layer 2: Step-Level Pipeline Isolation (`backend/agents/pipeline.py`)**
   - Every agent invocation is wrapped in an isolated `try/except` block.
   - If Planner fails: Falls back to using the raw query as a single task (`status="fallback"`).
   - If Researcher fails: Injects clear error notice; Summarizer synthesizes available context (`status="fallback"`).
   - If Summarizer fails: Passes raw findings to Report Generator.
   - If Report Generator fails: Deterministic fallback formats the 5-section report directly from the summary.
   - The user always receives an actionable response with an honest audit trace indicating where degradation occurred.

## 4. Memory Optimization Strategy for Cloud Deployments
- **The Problem:** Importing PyTorch (`import torch`) alongside Hugging Face `sentence-transformers` inflates process RSS (Resident Set Size) to ~550MB before running any code. On Render's free tier (512MB RAM cap), this triggers a SIGKILL (Out-Of-Memory) instantly.
- **The Solution:** Offload embedding generation to Google's managed Gemini Embedding API (`models/gemini-embedding-001`). The backend only needs lightweight `faiss-cpu`, NumPy, and HTTP clients.
- **Result:** Idle backend memory: ~110MB. Peak ingestion memory: ~180MB. This guarantees safe execution within Render's 512MB limit.

---

# PART 3: SOURCE-CODE WALKTHROUGH (FILE BY FILE)

### 1. `backend/agents/pipeline.py`
- **Purpose:** Central sequential orchestrator of the 4-agent system.
- **Key Data Structures:**
  - `AgentStep`: Dataclass holding `agent`, `status` (`completed`, `fallback`, `error`, `skipped`), `output_preview`, `duration_seconds`, and `error`.
  - `PipelineResult`: Final dataclass holding `session_id`, `query`, `plan`, `plan_reasoning`, `retrieved_chunks`, `source_files`, `summary`, `final_report`, `agent_steps`, `chat_history`, and `overall_status`.
- **`run_pipeline(...)` Function:**
  - Executes Planner, Researcher, Summarizer, and Report Generator sequentially.
  - Measures execution time using `time.perf_counter()`.
  - Computes `overall_status`: marked `completed` if all agents succeed; `fallback` if any step engaged a fallback; `error` if fatal issues occurred.
  - Updates conversation history in memory.

### 2. `backend/agents/planner.py`
- **Purpose:** Decomposes a research query into 2 to 4 atomic sub-tasks.
- **Key Classes & Functions:**
  - `Plan(BaseModel)`: Pydantic model with `sub_tasks: List[str]` and `reasoning: str`. Contains `@field_validator("sub_tasks")` ensuring non-empty, stripped, deduplicated tasks between 2 and 4 items.
  - `run_planner(query, has_documents)`: Invokes `llm.with_structured_output(Plan)`. If model invocation or validation fails, catches exception and returns `{"sub_tasks": [query], "reasoning": "...", "status": "fallback", "error": "..."}`.

### 3. `backend/agents/researcher.py`
- **Purpose:** Gathers factual evidence per sub-task via FAISS similarity retrieval or foundational knowledge.
- **Key Functions:**
  - `run_researcher(sub_tasks, session_id, has_documents)`:
    - Iterates over `sub_tasks`.
    - If documents exist: invokes `retriever.invoke(task)` (`k=5`). Prepares context block with source filename and page numbers. Calls LLM with `RAG_PROMPT`.
    - If no documents: invokes LLM with `GENERAL_PROMPT`.
    - Tracks unique `source_files` and `retrieved_chunks`.
    - Returns `answers`, `retrieved_chunks`, `source_files`, `grounding` (`document` vs `general_knowledge`), `status`, and `error`.

### 4. `backend/agents/summarizer.py`
- **Purpose:** Condenses raw findings across all sub-tasks into a coherent factual summary.
- **Key Functions:**
  - `run_summarizer(query, answers)`:
    - Validates that `answers` is non-empty.
    - Prompts LLM with `SUMMARIZER_PROMPT`, strictly forbidding unsupported claims and enforcing preservation of quantitative metrics and citations.
    - If LLM invocation fails, returns concatenated findings with `status="fallback"`.

### 5. `backend/agents/report_generator.py`
- **Purpose:** Assembles synthesized findings into a formal 5-section Markdown research report.
- **Key Functions:**
  - `run_report_generator(query, summary, source_files, **kwargs)`:
    - Formats prompt with strict 5-section structure: `# Research Report`, `## Executive Summary`, `## Findings`, `## Key Takeaways`, `## Sources`.
    - Verifies presence of `# Research Report`.
    - If LLM fails, executes deterministic fallback assembling the 5 sections directly from the summary.

### 6. `backend/core/document_store.py`
- **Purpose:** Manages document loaders, recursive text chunking, Gemini embeddings, and FAISS vector storage.
- **Key Functions:**
  - `validate_session_id(session_id)`: Enforces valid alphanumeric/UUID format, rejecting traversal characters like `..`, `/`, `\`.
  - `load_documents(file_path)`: Inspects extension. Dispatches `.pdf` to `PyPDFLoader`, `.docx` to `Docx2txtLoader`, `.txt` to `TextLoader`. Explicitly rejects `.doc` and empty files.
  - `ingest_file(file_path, session_id)`: Chunks text (`800` chars, `150` overlap). Inspects session `manifest.json` to skip duplicate files. Merges into existing FAISS index or creates a new one.
  - `get_retriever(session_id, k=5)`: Loads FAISS index from `vectorstores/{session_id}` and returns similarity retriever.
  - `session_has_documents(session_id)`: Checks for existence of `index.faiss`.
  - `get_session_documents(session_id)`: Reads `manifest.json` to return indexed document list.

### 7. `backend/core/llm.py`
- **Purpose:** Multi-provider fallback factory.
- **Key Functions:**
  - `get_configured_providers()`: Inspects environment settings and returns active provider names (`gemini`, `openai`, `groq`, `deepseek`).
  - `get_llm()`: Dynamically instantiates available LLM clients. Uses LangChain's `.with_fallbacks()` to chain primary model (Gemini) with secondary providers. Cached via `@lru_cache(maxsize=1)`.

### 8. `backend/api/routes.py`
- **Purpose:** FastAPI route definitions, request validation, and asynchronous execution.
- **Key Endpoints:**
  - `GET /health`: Returns version, primary provider, configured providers list, and embedding readiness.
  - `POST /session/new`: Generates UUID4 session ID.
  - `POST /upload`: Streams file to disk (enforcing 20MB limit), sanitizes filename, and runs `ingest_file` via `asyncio.to_thread`.
  - `GET /documents/{session_id}`: Returns session document manifest.
  - `POST /research`: Executes `run_pipeline` via `asyncio.to_thread` to maintain event-loop responsiveness.
  - `POST /chat`: Multi-turn conversational chat with optional RAG retrieval.
  - `GET /history/{session_id}` & `DELETE /history/{session_id}`: Manages in-memory conversation history.

### 9. `backend/api/schemas.py`
- **Purpose:** Pydantic request and response schemas.
- **Schemas:** `UploadResponse`, `QueryRequest`, `QueryResponse`, `AgentStep`, `ChatRequest`, `ChatResponse`, `HistoryResponse`, `ChatMessage`, `HealthResponse`, `DocumentItem`, `SessionDocumentsResponse`.

### 10. `backend/core/config.py`
- **Purpose:** Pydantic `BaseSettings` loading configuration from `.env`.
- **Fields:** API keys, model names, CORS origins, directories (`upload_dir`, `vectorstore_dir`), `max_upload_size_bytes` (20MB), `request_timeout_seconds` (90s).

### 11. `backend/main.py`
- **Purpose:** FastAPI application entry point, CORS middleware setup, router mounting, and static React SPA file serving.
- **Catch-All Handler:** `serve_frontend(full_path)` serves static files from `frontend/dist/` or falls back to `index.html` for client-side routing.

### 12. `frontend/src/App.jsx`
- **Purpose:** Single-page React 19 application providing a Linear-inspired interface.
- **Key Components & Workspaces:**
  - **Sidebar:** Navigation, active session ID with copy button, API connectivity status.
  - **4-Agent Research Workspace:** Research query input, sample prompt chips, live execution trace grid displaying all 4 agents with durations and statuses, rendered Markdown report viewer with copy and download actions.
  - **Documents Workspace:** Drag-and-drop file ingestion, file size and format validation, live table of indexed documents and chunk counts.
  - **Chat Workspace:** Conversational interface with cited source badges.
  - **History Workspace:** Session query audit trail.

---

# PART 4: FOUNDER-LEVEL TECHNICAL QUESTIONS & ANSWERS (45 QUESTIONS)

## Section A: Multi-Agent Architecture & Orchestration

#### Q1: Why did you choose a sequential multi-agent pipeline instead of LangGraph or AutoGen?
> **Answer:** For structured technical research reports, sequential pipeline orchestration is predictable, testable, and deterministic. Graph-based agent frameworks (like LangGraph or AutoGen) shine when agents require dynamic state looping, open-ended tool discovery, or autonomous peer debate. However, looping introduces non-deterministic latency, unpredictable token consumption, and debugging complexity. A deterministic sequence (Planner → Researcher → Summarizer → Report Generator) provides clear data contracts between stages, measurable step-by-step latency tracking, and straightforward unit testing.

#### Q2: How do you prevent errors in one agent from crashing the entire pipeline?
> **Answer:** Each agent stage in `backend/agents/pipeline.py` is isolated within its own `try/except` block. If an agent encounters an unhandled exception or returns a fallback dictionary:
> 1. The orchestrator records an `AgentStep` with `status="error"` or `status="fallback"` alongside the specific error message.
> 2. Safe fallback data is generated for downstream agents (e.g., if the Planner fails, the raw query is used as a single task; if Researcher fails, error context is passed so the Summarizer can explain the issue).
> 3. The final report is still produced, and `overall_status` is honestly marked as `fallback` or `error`. The API returns HTTP 200 with complete audit telemetry rather than an unhandled 500 error.

#### Q3: How does the Planner agent ensure it produces exactly 2 to 4 atomic sub-tasks?
> **Answer:** The Planner uses LangChain's `.with_structured_output(Plan)` backed by a Pydantic model (`Plan` in `planner.py`). The model defines `sub_tasks: List[str]` with a `@field_validator("sub_tasks")` method that:
> 1. Strips whitespace and filters out blank or non-string items.
> 2. Deduplicates items while preserving order.
> 3. Asserts that at least 2 distinct sub-tasks are present.
> 4. Slices the list to a maximum of 4 sub-tasks (`return deduped[:4]`).
> If the LLM generates malformed JSON or fewer than 2 tasks, the validator raises a `ValueError`, which `run_planner()` catches to trigger its single-task fallback.

#### Q4: How are execution durations measured, and why is this useful?
> **Answer:** In `backend/agents/pipeline.py`, each agent execution is bookended by `time.perf_counter()` calls: `duration = round(time.perf_counter() - t0, 3)`. This records precise execution times in seconds on each `AgentStep`. This data is sent to the frontend to help users understand where latency is concentrated (e.g., identifying whether the bottleneck is FAISS vector retrieval or LLM report generation).

#### Q5: Can the pipeline run sub-tasks in parallel? Why is it currently sequential?
> **Answer:** Currently, the Researcher agent evaluates sub-tasks sequentially in a loop. In a production environment with high-rate-limit enterprise API keys, sub-task retrievals can be parallelized using `asyncio.gather()` or a thread pool. It was kept sequential in this version to avoid triggering HTTP 429 rate limits on free-tier API quotas (such as Gemini's free tier limits of 15 Requests Per Minute).

#### Q6: How do you verify that downstream agents don't hallucinate missing research findings?
> **Answer:** The Summarizer and Report Generator prompts use strict negative constraints and grounding rules:
> 1. "Grounding: Rely strictly on the findings provided above. Do NOT introduce external data, statistics, or unsupported claims."
> 2. "If the context does not contain enough information, explicitly state that."
> 3. Sources are passed as an explicit programmatic list from the Researcher to the Report Generator, ensuring the model cannot invent source filenames.

#### Q7: What is the data contract between the Researcher and the Summarizer?
> **Answer:** The Researcher returns a dictionary containing `answers: List[str]`, `retrieved_chunks: List[str]`, `source_files: List[str]`, and `grounding: str`. The Summarizer receives `(query: str, answers: List[str])`. Each item in `answers` contains the sub-task header followed by the grounded findings. If `answers` is empty, the Summarizer immediately returns an error status without invoking the LLM.

---

## Section B: Retrieval-Augmented Generation (RAG) & Vector Storage

#### Q8: Why use Google Gemini Embeddings instead of a local Hugging Face model like `all-MiniLM-L6-v2`?
> **Answer:** Memory discipline on cloud deployments. Importing PyTorch and `sentence-transformers` inflates Python process memory to ~550MB on startup. On free or starter cloud tiers (such as Render's 512MB RAM limit), this causes an immediate OOM (Out Of Memory) crash. Offloading embeddings to Google's managed Gemini API (`models/gemini-embedding-001`) keeps the entire application's idle memory under 120MB and peak memory under 200MB.

#### Q9: What chunk size and overlap did you choose, and what was the rationale?
> **Answer:** We configured `chunk_size=800` characters with `chunk_overlap=150` characters using `RecursiveCharacterTextSplitter`.
> - **800 characters (~150–200 words):** Sized to capture a coherent paragraph containing complete technical arguments, code snippets, or definitions without diluting embedding density.
> - **150 characters overlap:** Preserves sentence context and semantic continuity across chunk boundaries, preventing split-sentence information loss.

#### Q10: How does the system prevent re-indexing the same file multiple times in a session?
> **Answer:** In `backend/core/document_store.py`, each session maintains a `manifest.json` file inside `vectorstores/{session_id}/`. Before chunking and embedding, `ingest_file()` checks if `file_path.name` exists in the manifest. If already present, it returns the existing chunk count with `is_duplicate=True`, bypassing redundant Gemini API embedding calls and preventing duplicate chunks in FAISS.

#### Q11: How does multi-document ingestion work for a single session?
> **Answer:** When the first file is uploaded, FAISS creates a new index via `FAISS.from_documents(chunks, embeddings)` and saves it to `vectorstores/{session_id}/index.faiss`. When subsequent files are uploaded, `ingest_file()` loads the existing index using `FAISS.load_local(...)`, calls `existing_vs.add_documents(chunks)`, and saves the merged index back to disk. Both documents are then queried simultaneously during research.

#### Q12: Why is `allow_dangerous_deserialization=True` used in FAISS, and how is it secured?
> **Answer:** LangChain's FAISS wrapper uses Python's `pickle` to serialize and deserialize document metadata alongside the vector index. LangChain flags this with `allow_dangerous_deserialization=True` because unpickling untrusted data can lead to arbitrary code execution. We secure this by:
> 1. Never allowing users to upload `.faiss` or `.pkl` index files directly.
> 2. Restricting `load_local()` strictly to application-created directories under `settings.vectorstore_dir`.
> 3. Enforcing strict UUID validation on `session_id` to block directory traversal attacks.

#### Q13: How does the system behave when uploaded documents do not contain the answer?
> **Answer:** If FAISS similarity retrieval returns empty chunks or low-relevance excerpts, the Researcher's system prompt explicitly instructs: *"If the context does not contain enough information, state: 'The provided document excerpts do not contain sufficient information to answer this sub-task.' Do not speculate or invent citations."* In the final report, the Sources section honestly reflects that no matching excerpts were identified.

#### Q14: Why did you reject `.doc` files while supporting `.docx`?
> **Answer:** `.docx` files are modern OpenXML ZIP archives that can be parsed reliably in pure Python using `docx2txt` without external system dependencies. In contrast, legacy `.doc` files (Word 97–2003) use proprietary binary Compound File Binary Format (CFBF). In Linux container environments, parsing `.doc` files requires heavy external C libraries (like `antiword` or LibreOffice in headless mode), which bloat container image size and introduce security vulnerabilities. Rejecting `.doc` with an explicit prompt to convert to `.docx` is standard practice in production RAG systems.

#### Q15: How would you evaluate and improve retrieval quality in production?
> **Answer:**
> 1. **Evaluation:** Implement automated RAG evaluation frameworks (such as Ragas or TruLens) to measure Context Precision, Context Recall, and Faithfulness against a gold-standard dataset.
> 2. **Hybrid Search:** Combine dense vector similarity (FAISS) with sparse lexical search (BM25) using Reciprocal Rank Fusion (RRF) to capture exact keyword matches (e.g. error codes, product model numbers).
> 3. **Re-ranking:** Introduce a lightweight cross-encoder re-ranker (e.g. Cohere Re-rank API) to re-order the top-20 retrieved candidates before sending the top-5 to the LLM.

---

## Section C: LLM Reliability, Failover & Error Handling

#### Q16: How does the multi-provider LLM fallback work?
> **Answer:** In `backend/core/llm.py`, `get_llm()` inspects the environment and instantiates client models for all configured providers: Gemini (primary), OpenAI, Groq, and DeepSeek. If more than one provider is configured, it calls `primary_model.with_fallbacks(models[1:])`. LangChain's fallback wrapper intercepts transient errors (HTTP 429 rate limits, connection timeouts, HTTP 500 server errors) and immediately retries the prompt with the next model in the chain.

#### Q17: What happens if an API key is missing or revoked?
> **Answer:** `backend/core/llm.py` dynamically builds the fallback list using only providers with non-empty API keys. If a key is invalid or revoked, the provider raises an authentication error on invocation, which `with_fallbacks()` catches to fail over to the next provider. If no API keys are provided at all, `get_llm()` raises a clear `ValueError` informing the developer to configure at least one key in `.env`.

#### Q18: What happens if all LLM providers fail or encounter rate limits simultaneously?
> **Answer:** If all models in the fallback chain fail:
> 1. The active agent catches the exception and logs it.
> 2. If the failure occurs in the Planner: it falls back to single-task mode.
> 3. If in the Researcher: it reports that research was unavailable.
> 4. If in the Summarizer: it outputs raw available text.
> 5. If in the Report Generator: a deterministic template formats the report directly from the summary.
> 6. The API returns the partial report with `overall_status="fallback"` and detailed error notes in `agent_steps`.

#### Q19: How do you handle HTTP 429 Rate Limits from LLM providers?
> **Answer:**
> 1. **Client-side Fallback:** LangChain's `with_fallbacks()` catches 429 errors and retries on the next provider.
> 2. **API Layer Exception Mapping:** In `routes.py`, if an uncaught 429 bubbles up, FastAPI catches it and returns HTTP 429 with an informative message advising the user to wait a moment or use single-turn Chat Mode.
> 3. **Retry Backoff:** Individual LangChain model clients are configured with `max_retries=2` and exponential backoff.

#### Q20: How does `/api/v1/health` report honest provider status?
> **Answer:** Previously, `/health` simply echoed `settings.llm_provider` without checking credentials. Now, `health_check()` calls `get_configured_providers()`, which dynamically checks which keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY`, `DEEPSEEK_API_KEY`) are present. It reports `configured_providers: List[str]`, the active `primary_provider`, and whether `embeddings_ready` is true.

#### Q21: Does the system support streaming agent responses?
> **Answer:** Currently, execution is returned as a complete completed response rather than streaming intermediate tokens. This was an intentional architectural choice: analytical multi-agent pipelines require intermediate validation gates (e.g. validating the Planner's Pydantic schema before invoking the Researcher). Returning genuine, completed execution telemetry is cleaner and more reliable than simulating pseudo-progress. Implementing true Server-Sent Events (SSE) or WebSockets is on the production roadmap.

#### Q22: How do you prevent internal tracebacks from leaking to end users?
> **Answer:** In `researcher.py`, `summarizer.py`, and `routes.py`, exceptions are caught and sanitized. Internal system tracebacks and file paths are logged server-side via `logger.exception()`, while the client receives clean, structured error notices (e.g., *"Notice: Could not retrieve findings for this sub-task due to an execution issue"*).

---

## Section D: Backend Architecture, Concurrency & Security

#### Q23: Why is calling synchronous code inside an `async def` FastAPI route problematic, and how did you resolve it?
> **Answer:** In FastAPI, `async def` routes execute on the main asyncio event loop thread. If an `async def` handler calls synchronous blocking operations (such as `llm.invoke()`, `FAISS.load_local()`, or file I/O), the entire event loop is blocked. While blocked, the server cannot accept new connections or process concurrent requests. We resolved this by wrapping all synchronous blocking calls in `asyncio.to_thread(...)`, which delegates execution to FastAPI's background thread pool, keeping the asyncio event loop responsive.

#### Q24: How does the application protect against directory traversal attacks during file uploads?
> **Answer:** We enforce three layers of protection:
> 1. `sanitize_filename()` strips all path traversal characters (`..`, `/`, `\`) and null bytes, extracting only the base filename via `Path(filename).name`.
> 2. `validate_session_id()` asserts that the session ID contains only alphanumeric characters and hyphens (`^[a-zA-Z0-9_\-]+$`), rejecting any attempts to inject `../` into directory paths.
> 3. Files are strictly saved inside isolated, application-controlled paths: `settings.upload_dir / session_id / safe_filename`.

#### Q25: How is file upload size restricted?
> **Answer:** Rather than buffering the entire file in RAM with `await file.read()`, `upload_document()` streams the file in 64KB chunks (`await file.read(1024 * 64)`). It maintains a running byte counter. If `total_bytes` exceeds `settings.max_upload_size_bytes` (20MB), it immediately deletes any partially written file and raises an HTTP 413 Payload Too Large exception.

#### Q26: What is the current session storage mechanism and its limitations?
> **Answer:** Session conversation history is stored in-memory in Python dictionaries (`_chat_store` and `_convo_store` in `routes.py`).
> - **Advantage:** Zero external database dependency, zero setup latency, sub-millisecond lookups.
> - **Limitation:** In-memory state does not persist across server restarts or horizontal scaling across multiple container instances. In production, this would be replaced with Redis or PostgreSQL.

#### Q27: How does CORS work in this application?
> **Answer:** Configured via FastAPI's `CORSMiddleware`. Allowed origins are loaded from `settings.cors_origin_list` (parsed from `CORS_ORIGINS` in `.env`). In development, Vite runs on `http://localhost:5173` while FastAPI runs on `http://localhost:8000`. In production Docker deployments, FastAPI serves the compiled React static files directly from the same origin, eliminating CORS overhead entirely.

#### Q28: How is session isolation guaranteed between different users?
> **Answer:** Every user session receives a unique UUID generated by `POST /api/v1/session/new`. Uploaded files are segregated into `uploads/{session_id}/`, and FAISS indices are saved in `vectorstores/{session_id}/`. Retrievers are parameterized strictly by `session_id`. One user's queries cannot access another user's vector store or conversation history.

#### Q29: What happens if a client sends an empty query or empty file?
> **Answer:**
> - An empty research query triggers Pydantic schema validation (`min_length=1`), returning HTTP 422 Unprocessable Entity immediately.
> - An empty file (0 bytes) is detected during upload streaming and rejected with HTTP 400 Bad Request before attempting chunking or embedding.

---

## Section E: Frontend Engineering & User Experience

#### Q30: Why redesign the interface in a Linear/Notion style instead of a flashy AI theme?
> **Answer:** Consumer-facing AI templates frequently use neon gradients, dark glowing borders, and floating robot illustrations. For technical founders and enterprise users, this aesthetic looks like an unvetted weekend hack. Adopting a Linear/Raycast/Notion aesthetic (neutral slate background, crisp hairline borders, Inter typography, structured cards, and restrained blue accents) communicates engineering maturity, clarity of information hierarchy, and enterprise readiness.

#### Q31: How does the frontend handle Render's free-tier cold starts?
> **Answer:** Render's free instances spin down after 15 minutes of inactivity and take 30 to 50 seconds to wake on the next incoming request. During this period, naive fetch calls time out or throw errors. We implemented:
> 1. `safeFetchJson()` which catches empty responses and displays clear cold-start guidance.
> 2. A top notification banner: *"Connecting to backend... On Render free tier, server instances spin down after inactivity and may take 30–50s to wake up."*
> 3. Real-time online/offline status pill in the sidebar.

#### Q32: How is the research report rendered and exported?
> **Answer:** The report is rendered using `react-markdown` with customized typography for headers, lists, code blocks, blockquotes, and tables. Two one-click export actions are provided:
> 1. **Copy Markdown:** Writes raw markdown to the system clipboard via `navigator.clipboard.writeText()` with immediate visual checkmark feedback.
> 2. **Download .md:** Generates a client-side `Blob` containing the markdown text and triggers an automatic browser download named `Research_Report_{timestamp}.md`.

#### Q33: How does the UI communicate genuine agent execution status?
> **Answer:** When research runs, the UI displays a dedicated 4-card grid for Planner, Researcher, Summarizer, and Report Generator. Upon completion, each card displays:
> - The agent's formal responsibility.
> - A color-coded status badge (`completed` in green, `fallback` in amber, `error` in red).
> - The exact execution duration (e.g. `1.14s`).
> - An expandable preview of the agent's actual output.

#### Q34: What accessibility and interaction standards are implemented?
> **Answer:** Keyboard shortcuts (`Ctrl+Enter` or `Cmd+Enter` to submit research), distinct focus rings (`:focus-within`), accessible contrast ratios (charcoal text on light backgrounds), responsive mobile layouts, and descriptive ARIA labels.

---

## Section F: System Design, Scalability & Production Operations

#### Q35: How would you scale this architecture to support 100 concurrent users?
> **Answer:**
> 1. **Stateless Backend:** Move session history and document manifests from in-memory dictionaries to a managed Redis cluster or PostgreSQL database.
> 2. **Managed Vector Database:** Migrate local FAISS files to a distributed vector database like Pinecone, Qdrant, or PostgreSQL with `pgvector`, removing local disk dependencies.
> 3. **Asynchronous Job Queue:** Replace immediate in-process execution with Celery or Temporal workers backed by RabbitMQ/Redis. The API returns a `task_id` (HTTP 202 Accepted), and the frontend polls or listens via WebSockets/SSE for completion.
> 4. **Horizontal Scaling:** Deploy multiple FastAPI worker replicas behind an Application Load Balancer (ALB) or Kubernetes cluster.

#### Q36: How does the Docker multi-stage build optimize image size and security?
> **Answer:** The `Dockerfile` separates the build environment from the runtime:
> - **Stage 1 (Node 20):** Copies `frontend/`, runs `npm install` and `npm run build`, and outputs compiled static assets.
> - **Stage 2 (Python 3.11-slim):** Copies only the compiled assets (`/app/frontend/dist`) and Python source code. Node.js, npm caches, and `node_modules` are completely excluded from the final image.
> - **Result:** The final image is significantly smaller, has a minimal attack surface, and serves both the React client and FastAPI API from a single container.

#### Q37: How do automated unit tests run without live API keys or network access?
> **Answer:** In `backend/tests/`, all external LLM calls and embedding instances are mocked using `pytest`'s `monkeypatch` fixture and `unittest.mock.MagicMock`. For example, `run_planner`, `run_researcher`, and `_get_embeddings` are patched with deterministic mock functions. This verifies the orchestration logic, data contracts, and fault isolation in 0.2 seconds without spending API credits or failing on network drops.

#### Q38: What are the security risks of user document uploads, and how are they mitigated?
> **Answer:**
> 1. **Malicious Executables:** Enforce strict file extension whitelisting (`.pdf`, `.docx`, `.txt`).
> 2. **Zip Bombs / Disk Exhaustion:** Stream file uploads with a strict 20MB limit.
> 3. **Path Traversal:** Filenames and session IDs are sanitized and validated with regex.
> 4. **Pickle Exploits:** FAISS deserialization is confined strictly to internal application directories.

#### Q39: How would you add streaming without breaking agent validation gates?
> **Answer:** Use Server-Sent Events (SSE) via FastAPI's `StreamingResponse`. When the pipeline starts, it yields SSE events for each agent transition:
> - `data: {"event": "agent_start", "agent": "Planner"}`
> - `data: {"event": "agent_complete", "agent": "Planner", "duration": 1.1}`
> During the final Report Generator stage, tokens can be streamed in real time to the frontend using LangChain's `astream()` callback.

#### Q40: What metrics would you track in production (APM & Observability)?
> **Answer:**
> 1. **Latencies:** End-to-end pipeline latency, individual agent step durations, and FAISS retrieval latency.
> 2. **Provider Failover Rates:** Frequency of fallbacks from Gemini to OpenAI/Groq/DeepSeek.
> 3. **Token Usage & Costs:** Input and output token counts per agent turn.
> 4. **Retrieval Quality:** Distribution of retrieved chunk counts and user copy/download conversion rates.

---

## Section G: Critical Scenario-Based Failure Drills

#### Q41: Scenario: The Planner LLM completely fails or outputs unparseable garbage. What happens?
> **Answer:**
> 1. `run_planner()` attempts to parse the output with Pydantic. If validation fails or an exception is thrown, it catches the error.
> 2. It returns:
>    ```python
>    {
>        "sub_tasks": [query],
>        "reasoning": "Direct query execution (structured planning fallback engaged).",
>        "status": "fallback",
>        "error": "Planner notice: <error message>",
>    }
>    ```
> 3. `pipeline.py` records the Planner step with `status="fallback"`.
> 4. The Researcher receives the original query as a single task and proceeds normally.
> 5. The final report is produced successfully with an honest trace indicating the Planner fallback.

#### Q42: Scenario: A user uploads an invoice PDF, but the Researcher finds 0 matching chunks for a sub-task. What happens?
> **Answer:**
> 1. The Researcher retrieves `docs = retriever.invoke(task)`. If `len(docs) == 0`, it does not crash.
> 2. It sets `context_block = "No matching excerpts found in the uploaded documents."`
> 3. The prompt explicitly commands the model to state clearly that the uploaded documents contain no information on this topic.
> 4. In `answers`, it notes: *"The provided document excerpts do not contain sufficient information to answer this sub-task."*
> 5. The final report reflects this honest limitation rather than fabricating an answer.

#### Q43: Scenario: Gemini returns an HTTP 429 quota exhaustion error during research. What happens?
> **Answer:**
> 1. LangChain's `.with_fallbacks()` intercepts the 429 error from `ChatGoogleGenerativeAI`.
> 2. It immediately retries the prompt on the secondary configured provider (OpenAI `gpt-4o-mini`).
> 3. If OpenAI succeeds, the agent execution completes seamlessly without user disruption.
> 4. If all fallback providers fail, the agent catches the exception, engages its local fallback handler, and records the error on the agent step.

#### Q44: Scenario: A user uploads a 50MB file or a malicious file named `../../../../etc/shadow`. What happens?
> **Answer:**
> - **Filename Attack:** `sanitize_filename("../../../../etc/shadow")` strips all `/` and `..` components, converting the name safely to `shadow`. `validate_session_id` ensures the parent folder is a clean UUID.
> - **Size Attack:** `upload_document()` streams the request in 64KB chunks. As soon as the byte counter exceeds 20MB, it aborts writing, unlinks the partial file, and returns HTTP 413 Payload Too Large.

#### Q45: Scenario: The Render free-tier instance restarts or spins down. What happens?
> **Answer:**
> 1. Because session histories and FAISS indices are stored in local container memory and ephemeral disk, a cold restart clears prior sessions.
> 2. When the user visits the frontend, `App.jsx` automatically requests a fresh UUID session via `POST /api/v1/session/new`.
> 3. If the backend is waking up, the frontend displays the cold-start helper notice rather than crashing.
> 4. To persist data across restarts in enterprise production, vector stores would be backed by persistent volume disks or a managed vector database (like Pinecone or Qdrant).

---

# PART 5: 10-MINUTE LIVE DEMONSTRATION PLAN

When demonstrating this application in a technical interview, follow this precise sequence:

| Minute | Stage | Action / Talking Point | Screen Focus |
|---|---|---|---|
| **00:00–01:30** | **Executive Context** | Open the application. Highlight the clean, Linear-inspired design. State the problem: why monolithic prompts fail and why 4-agent sequential decomposition is superior. | Main Dashboard |
| **01:30–03:00** | **Document Ingestion** | Navigate to **Documents**. Upload a technical document (`.pdf` or `.txt`). Point out the instant chunk count confirmation from FAISS and explain the Gemini API embedding strategy that keeps memory under 200MB. | Document Workspace |
| **03:00–06:00** | **Run 4-Agent Research** | Return to **4-Agent Research**. Click a sample prompt or enter a technical query. Hit **Run 4-Agent Research**. As the pipeline executes, walk through each stage: Planner → Researcher → Summarizer → Report Generator. | Pipeline Trace Cards |
| **06:00–07:30** | **Report Review & Attribution** | Walk through the rendered Markdown report. Point out the exact 5-section standard (Executive Summary, Findings, Key Takeaways, Sources). Show that sources match the uploaded file. Click **Copy Markdown** and **Download .md**. | Report Results Card |
| **07:30–08:30** | **Conversational Chat Mode** | Switch to **Chat Mode**. Ask a follow-up question. Show how the same session FAISS store provides context excerpts to direct chat. | Chat Workspace |
| **08:30–10:00** | **Code Inspection & Architecture Q&A** | Switch to VS Code. Open `pipeline.py` and `document_store.py`. Explain the error isolation, typing, and thread pool dispatch. Invite questions. | Code Editor |

---

# PART 6: TOP 5 SOURCE FILES TO STUDY CAREFULLY

To prepare for technical questions, review these five files in detail:

1. **`backend/agents/pipeline.py`**
   - *Why:* Core orchestrator file. Review how `AgentStep` and `PipelineResult` are constructed, how `time.perf_counter()` is measured, and how step failures are isolated.
2. **`backend/agents/planner.py`**
   - *Why:* Demonstrates structured output using Pydantic schemas (`Plan`), field validators, and graceful degradation when parsing fails.
3. **`backend/core/document_store.py`**
   - *Why:* Demonstrates RAG mechanics: loaders, chunking parameters, Gemini API embeddings, FAISS persistence, session isolation, and duplicate prevention.
4. **`backend/core/llm.py`**
   - *Why:* Demonstrates multi-provider failover using LangChain's `.with_fallbacks()` across Gemini, OpenAI, Groq, and DeepSeek.
5. **`backend/api/routes.py`**
   - *Why:* Shows production FastAPI architecture: thread pool offloading via `asyncio.to_thread`, streaming upload size limits, filename sanitization, and honest health reporting.

