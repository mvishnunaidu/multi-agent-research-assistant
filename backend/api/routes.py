"""
routes.py — FastAPI route handlers for all endpoints.
Uses the simple function-chain pipeline (no LangGraph).
"""
import uuid
import shutil
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, UploadFile, File, HTTPException, Query

from backend.core.config import settings
from backend.core.document_store import ingest_file, session_has_documents
from backend.agents.pipeline import run_pipeline
from backend.api.schemas import (
    UploadResponse,
    QueryRequest,
    QueryResponse,
    AgentStep,
    HistoryResponse,
    ChatMessage,
    HealthResponse,
)

router = APIRouter()

# In-memory chat history store: {session_id: [dict]}
_chat_store: Dict[str, List[dict]] = {}

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}


# ── Health ─────────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        llm_provider=settings.llm_provider,
        vector_store=settings.vector_store,
    )


# ── Session ────────────────────────────────────────────────────────────────────

@router.post("/session/new", tags=["Session"])
async def new_session():
    """Generate a fresh session ID."""
    return {"session_id": str(uuid.uuid4())}


# ── Upload ─────────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse, tags=["Documents"])
async def upload_document(
    file: UploadFile = File(...),
    session_id: str = Query(default=None),
):
    """Upload a PDF, DOCX, or TXT file and build its FAISS vector store."""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{suffix}' not supported. Allowed: {ALLOWED_EXTENSIONS}",
        )

    if not session_id:
        session_id = str(uuid.uuid4())

    save_dir = settings.upload_dir / session_id
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / file.filename

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        result = ingest_file(file_path, session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

    return UploadResponse(
        session_id=session_id,
        filename=file.filename,
        num_chunks=result["num_chunks"],
        message=f"'{file.filename}' ingested into session '{session_id}'.",
    )


# ── Research ───────────────────────────────────────────────────────────────────

@router.post("/research", response_model=QueryResponse, tags=["Research"])
async def run_research(request: QueryRequest):
    """Run the full multi-agent research pipeline for a query."""
    session_id = request.session_id
    has_docs = request.has_documents and session_has_documents(session_id)

    # Load prior conversation history for this session
    history = _chat_store.get(session_id, [])

    try:
        result = run_pipeline(
            session_id=session_id,
            query=request.query,
            has_documents=has_docs,
            chat_history=history,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")

    # Persist updated chat history
    _chat_store[session_id] = result.chat_history

    # Convert dataclass agent steps to schema
    agent_steps = [
        AgentStep(
            agent=step.agent,
            status=step.status,
            output_preview=step.output_preview,
        )
        for step in result.agent_steps
    ]

    return QueryResponse(
        session_id=session_id,
        query=request.query,
        plan=result.plan,
        plan_reasoning=result.plan_reasoning,
        sources=result.source_files,
        final_report=result.final_report,
        agent_steps=agent_steps,
    )


# ── History ────────────────────────────────────────────────────────────────────

@router.get("/history/{session_id}", response_model=HistoryResponse, tags=["History"])
async def get_history(session_id: str):
    messages = _chat_store.get(session_id, [])
    return HistoryResponse(
        session_id=session_id,
        messages=[ChatMessage(**m) for m in messages],
    )


@router.delete("/history/{session_id}", tags=["History"])
async def clear_history(session_id: str):
    _chat_store.pop(session_id, None)
    return {"message": f"History cleared for session '{session_id}'."}
