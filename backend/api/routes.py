"""
routes.py — FastAPI route handlers for all endpoints.

Endpoints:
- GET  /api/v1/health              (Honest system & provider status)
- POST /api/v1/session/new         (Generate fresh UUID4 session)
- POST /api/v1/upload              (Validate & ingest document into FAISS)
- GET  /api/v1/documents/{session} (List ingested documents for session)
- POST /api/v1/research            (Run 4-agent research pipeline via thread pool)
- POST /api/v1/chat                (Direct conversational mode with optional RAG)
- GET  /api/v1/history/{session}   (Retrieve session message history)
- DELETE /api/v1/history/{session} (Clear session history)
"""

import re
import uuid
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from backend.core.config import settings
from backend.core.document_store import (
    ingest_file,
    session_has_documents,
    validate_session_id,
    get_session_documents,
    get_retriever,
)
from backend.core.llm import get_llm, get_configured_providers
from backend.agents.pipeline import run_pipeline
from backend.api.schemas import (
    UploadResponse,
    DocumentItem,
    SessionDocumentsResponse,
    QueryRequest,
    QueryResponse,
    AgentStep,
    ChatRequest,
    ChatResponse,
    HistoryResponse,
    ChatMessage,
    HealthResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory session stores (document limitation: in-memory state does not persist across server restarts)
_chat_store: Dict[str, List[dict]] = {}   # research pipeline history
_convo_store: Dict[str, List[dict]] = {}  # conversational chat mode history

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

CHAT_SYSTEM = """You are an objective, professional research assistant.
Answer the user's question clearly, thoroughly, and factually.
When document context excerpts are provided, ground your answer directly in them.
Format your answer with clean Markdown (headers, bullet points, code blocks where appropriate).
If document excerpts do not provide enough information, clearly note the limitation."""


def sanitize_filename(filename: str) -> str:
    """Sanitize uploaded filename to prevent directory traversal attacks."""
    clean_name = Path(filename).name
    # Remove control characters and null bytes
    clean_name = re.sub(r"[\x00-\x1f\x7f/\\]", "", clean_name).strip()
    if not clean_name or clean_name in (".", ".."):
        clean_name = f"upload_{uuid.uuid4().hex[:8]}.txt"
    return clean_name


# ── Health ──────────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Returns verified runtime health information, including all configured
    LLM providers, active primary provider, embedding readiness, and vector store.
    """
    configured = get_configured_providers()
    primary = configured[0] if configured else "none (unconfigured)"
    embeddings_ready = bool(settings.gemini_api_key.strip())

    return HealthResponse(
        status="ok",
        version=settings.app_version,
        llm_provider=primary,
        configured_providers=configured,
        vector_store="faiss",
        embeddings_ready=embeddings_ready,
    )


# ── Session ─────────────────────────────────────────────────────────────────────

@router.post("/session/new", tags=["Session"])
async def new_session():
    """Generate a cryptographically fresh UUID4 session identifier."""
    new_id = str(uuid.uuid4())
    return {"session_id": new_id}


# ── Upload ──────────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse, tags=["Documents"])
async def upload_document(
    file: UploadFile = File(...),
    session_id: Optional[str] = Query(default=None),
):
    """
    Upload a PDF, DOCX, or TXT file, chunk it, embed it via Gemini,
    and persist/merge into the session's isolated FAISS vector store.
    """
    if not file.filename or not file.filename.strip():
        raise HTTPException(status_code=400, detail="No filename provided in upload.")

    raw_filename = file.filename.strip()
    suffix = Path(raw_filename).suffix.lower()

    if suffix == ".doc":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Legacy binary Word format (.doc) is not supported for '{raw_filename}'. "
                "Please convert the file to .docx or .pdf before uploading."
            ),
        )

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{suffix}' is not supported. Allowed formats: {sorted(ALLOWED_EXTENSIONS)}",
        )

    # Validate or generate session_id
    if session_id:
        try:
            valid_session = validate_session_id(session_id)
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
    else:
        valid_session = str(uuid.uuid4())

    safe_filename = sanitize_filename(raw_filename)

    save_dir = settings.upload_dir / valid_session
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / safe_filename

    # Stream file to disk while enforcing max file size limit
    total_bytes = 0
    max_bytes = settings.max_upload_size_bytes

    try:
        with open(file_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 64)  # 64 KB chunks
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum allowed size limit of {max_bytes // (1024 * 1024)} MB.",
                    )
                f.write(chunk)
    except HTTPException:
        if file_path.exists():
            file_path.unlink()
        raise
    except Exception as e:
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    if total_bytes == 0:
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=400, detail="Uploaded file is empty (0 bytes).")

    # Run blocking ingestion in worker thread
    try:
        result = await asyncio.to_thread(ingest_file, file_path, valid_session)
    except ValueError as ve:
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("Ingestion failed for %s: %s", safe_filename, e)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")

    is_dup = result.get("is_duplicate", False)
    msg = (
        f"'{safe_filename}' was already indexed for this session ({result['num_chunks']} chunks)."
        if is_dup
        else f"'{safe_filename}' successfully ingested ({result['num_chunks']} chunks)."
    )

    return UploadResponse(
        session_id=valid_session,
        filename=safe_filename,
        num_chunks=result["num_chunks"],
        message=msg,
        is_duplicate=is_dup,
    )


# ── Documents Listing ───────────────────────────────────────────────────────────

@router.get("/documents/{session_id}", response_model=SessionDocumentsResponse, tags=["Documents"])
async def list_documents(session_id: str):
    """Retrieve all ingested documents for a specific session."""
    try:
        valid_session = validate_session_id(session_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    raw_docs = get_session_documents(valid_session)
    items = [
        DocumentItem(
            filename=d["filename"],
            num_chunks=d.get("num_chunks", 0),
            uploaded_at=d.get("uploaded_at", datetime.now().isoformat()),
            file_size_bytes=d.get("file_size_bytes", 0),
        )
        for d in raw_docs
    ]
    return SessionDocumentsResponse(session_id=valid_session, documents=items)


# ── Chat (direct conversational mode) ──────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest):
    """
    Direct conversational chat endpoint.
    Maintains multi-turn context in memory.
    Optionally retrieves document chunks via FAISS when documents are present.
    """
    try:
        valid_session = validate_session_id(request.session_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message must not be empty.")

    try:
        llm = get_llm()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM initialization error: {e}")

    history = _convo_store.get(valid_session, [])
    sources: List[str] = []
    doc_context = ""

    # Document retrieval if session has documents
    if request.has_documents and session_has_documents(valid_session):
        try:
            def retrieve_chunks():
                retriever = get_retriever(valid_session, k=4)
                return retriever.invoke(message)

            docs = await asyncio.to_thread(retrieve_chunks)
            if docs:
                chunks = []
                for d in docs:
                    src = d.metadata.get("source_file", "")
                    if src and src not in sources:
                        sources.append(src)
                    chunks.append(d.page_content.strip())

                doc_context = (
                    "\n\n--- Relevant Document Excerpts ---\n\n"
                    + "\n\n---\n\n".join(chunks)
                    + "\n\n--- End of Document Excerpts ---\n"
                )
        except Exception as e:
            logger.warning("RAG retrieval failed in chat mode for session %s: %s", valid_session, e)
            doc_context = ""

    # Build conversation history
    conv_turns = history[-6:] if len(history) > 6 else history
    chat_history = []
    for m in conv_turns:
        if m.get("role") == "user":
            chat_history.append(HumanMessage(content=m.get("content", "")))
        else:
            chat_history.append(AIMessage(content=m.get("content", "")))

    system_msg = CHAT_SYSTEM
    if doc_context:
        system_msg += f"\n\n{doc_context}"

    messages = [SystemMessage(content=system_msg)] + chat_history + [HumanMessage(content=message)]

    try:
        resp = await asyncio.to_thread(llm.invoke, messages)
        reply = resp.content.strip() if hasattr(resp, "content") else str(resp)
    except Exception as e:
        err = str(e)
        if "429" in err or "rate_limit" in err.lower() or "quota" in err.lower():
            raise HTTPException(
                status_code=429,
                detail="Rate limit reached on your LLM API. Please wait a moment and try again.",
            )
        raise HTTPException(status_code=500, detail=f"LLM error: {e}")

    updated = list(history) + [
        {"role": "user", "content": message, "timestamp": datetime.now().isoformat()},
        {"role": "assistant", "content": reply, "sources": sources, "timestamp": datetime.now().isoformat()},
    ]
    _convo_store[valid_session] = updated

    return ChatResponse(
        session_id=valid_session,
        message=message,
        reply=reply,
        sources=sources,
    )


# ── Research (4-Agent sequential pipeline) ─────────────────────────────────────

@router.post("/research", response_model=QueryResponse, tags=["Research"])
async def run_research(request: QueryRequest):
    """
    Run the full 4-agent research pipeline (Planner → Researcher → Summarizer → Report Generator)
    executed via a non-blocking thread pool worker.
    """
    try:
        valid_session = validate_session_id(request.session_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Query must not be empty.")

    has_docs = bool(request.has_documents and session_has_documents(valid_session))
    history = _chat_store.get(valid_session, [])

    try:
        result = await asyncio.to_thread(
            run_pipeline,
            session_id=valid_session,
            query=query,
            has_documents=has_docs,
            chat_history=history,
        )
    except Exception as e:
        err = str(e)
        if "429" in err or "rate_limit" in err.lower() or "quota" in err.lower():
            raise HTTPException(
                status_code=429,
                detail=(
                    "Rate limit reached on your LLM API. The 4-agent pipeline makes multiple sequential calls. "
                    "Wait 1-2 minutes or switch to Chat Mode for a single-call interaction."
                ),
            )
        logger.exception("Pipeline failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {e}")

    _chat_store[valid_session] = result.chat_history

    agent_steps = [
        AgentStep(
            agent=step.agent,
            status=step.status,
            output_preview=step.output_preview or "",
            duration_seconds=step.duration_seconds,
            error=step.error,
        )
        for step in result.agent_steps
    ]

    return QueryResponse(
        session_id=valid_session,
        query=query,
        plan=result.plan,
        plan_reasoning=result.plan_reasoning or "",
        sources=result.source_files,
        final_report=result.final_report,
        agent_steps=agent_steps,
        overall_status=result.overall_status,
    )


# ── History ─────────────────────────────────────────────────────────────────────

@router.get("/history/{session_id}", response_model=HistoryResponse, tags=["History"])
async def get_history(session_id: str):
    """Retrieve conversation history for a given session."""
    try:
        valid_session = validate_session_id(session_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    raw_messages = _chat_store.get(valid_session, [])
    messages = []
    for m in raw_messages:
        try:
            messages.append(
                ChatMessage(
                    role=m.get("role", "user"),
                    content=m.get("content", ""),
                    query=m.get("query"),
                    timestamp=m.get("timestamp"),
                    overall_status=m.get("overall_status"),
                    sources=m.get("sources"),
                )
            )
        except Exception:
            pass
    return HistoryResponse(session_id=valid_session, messages=messages)


@router.delete("/history/{session_id}", tags=["History"])
async def clear_history(session_id: str):
    """Clear in-memory history for a given session."""
    try:
        valid_session = validate_session_id(session_id)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    _chat_store.pop(valid_session, None)
    _convo_store.pop(valid_session, None)
    return {"message": f"History cleared for session '{valid_session}'."}
