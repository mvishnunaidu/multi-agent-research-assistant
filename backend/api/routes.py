"""
routes.py — FastAPI route handlers for all endpoints.
"""

import uuid
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pydantic import BaseModel, Field

from backend.core.config import settings
from backend.core.document_store import ingest_file, session_has_documents
from backend.core.llm import get_llm
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

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

router = APIRouter()

# In-memory stores
_chat_store: Dict[str, List[dict]]    = {}   # research history
_convo_store: Dict[str, List[dict]]   = {}   # chat-mode conversation history

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}

CHAT_SYSTEM = """You are a knowledgeable, friendly AI assistant — like ChatGPT.
Answer the user's question clearly and helpfully. If documents have been uploaded
as context, use them. Format your answer in clean Markdown when helpful
(use headers, bullet points, bold text). Be concise but complete."""


# ── Health ──────────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        llm_provider=settings.llm_provider,
        vector_store="faiss",
    )


# ── Session ─────────────────────────────────────────────────────────────────────

@router.post("/session/new", tags=["Session"])
async def new_session():
    """Generate a fresh session ID."""
    return {"session_id": str(uuid.uuid4())}


# ── Upload ──────────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse, tags=["Documents"])
async def upload_document(
    file: UploadFile = File(...),
    session_id: str = Query(default=None),
):
    """Upload a PDF, DOCX, or TXT file and build its FAISS vector store."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{suffix}' not supported. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    if not session_id:
        session_id = str(uuid.uuid4())

    save_dir  = settings.upload_dir / session_id
    save_dir.mkdir(parents=True, exist_ok=True)
    file_path = save_dir / file.filename

    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    try:
        result = ingest_file(file_path, session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")

    return UploadResponse(
        session_id=session_id,
        filename=file.filename,
        num_chunks=result["num_chunks"],
        message=f"'{file.filename}' ingested into session '{session_id}'.",
    )


# ── Chat (direct conversational mode) ──────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Session ID")
    message: str    = Field(..., min_length=1, max_length=5000)
    has_documents: bool = Field(default=False)


class ChatResponse(BaseModel):
    session_id: str
    message: str
    reply: str
    sources: List[str] = []
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


@router.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest):
    """
    Direct conversational chat endpoint — like ChatGPT.
    Maintains conversation history. Optionally uses uploaded documents via RAG.
    """
    session_id = request.session_id
    message    = request.message.strip()

    if not message:
        raise HTTPException(status_code=422, detail="Message must not be empty.")

    llm      = get_llm()
    history  = _convo_store.get(session_id, [])
    sources: List[str] = []

    # Build context from documents if available
    doc_context = ""
    if request.has_documents and session_has_documents(session_id):
        try:
            from backend.core.document_store import get_retriever
            retriever = get_retriever(session_id, k=4)
            docs      = retriever.invoke(message)
            if docs:
                chunks = [d.page_content for d in docs]
                for d in docs:
                    src = d.metadata.get("source_file", "")
                    if src and src not in sources:
                        sources.append(src)
                doc_context = (
                    "\n\n--- Relevant document excerpts ---\n\n"
                    + "\n\n---\n\n".join(chunks)
                    + "\n\n--- End of document excerpts ---\n"
                )
        except Exception:
            doc_context = ""

    # Build conversation history using LangChain message types
    conv_turns = history[-6:] if len(history) > 6 else history
    chat_history = []
    for m in conv_turns:
        if m['role'] == 'user':
            chat_history.append(HumanMessage(content=m['content']))
        else:
            chat_history.append(AIMessage(content=m['content']))

    system_msg = CHAT_SYSTEM
    if doc_context:
        system_msg += f"\n\n{doc_context}"

    try:
        messages = [SystemMessage(content=system_msg)] + chat_history + [HumanMessage(content=message)]
        resp = llm.invoke(messages)
        reply = resp.content.strip()
    except Exception as e:
        err = str(e)
        if "rate_limit" in err.lower() or "429" in err or "tokens per minute" in err.lower():
            raise HTTPException(
                status_code=429,
                detail=(
                    "Rate limit reached on your LLM API. "
                    "Wait a moment and try again, or upgrade your API plan."
                ),
            )
        raise HTTPException(status_code=500, detail=f"LLM error: {e}")

    # Save to conversation history
    updated = list(history) + [
        {"role": "user",      "content": message, "timestamp": datetime.now().isoformat()},
        {"role": "assistant", "content": reply,   "timestamp": datetime.now().isoformat()},
    ]
    _convo_store[session_id] = updated

    return ChatResponse(
        session_id=session_id,
        message=message,
        reply=reply,
        sources=sources,
    )


# ── Research (full pipeline mode) ───────────────────────────────────────────────

@router.post("/research", response_model=QueryResponse, tags=["Research"])
async def run_research(request: QueryRequest):
    """Run the full multi-agent research pipeline for a query."""
    session_id = request.session_id
    query      = request.query.strip()

    if not query:
        raise HTTPException(status_code=422, detail="Query must not be empty.")

    has_docs = request.has_documents and session_has_documents(session_id)
    history  = _chat_store.get(session_id, [])

    try:
        result = run_pipeline(
            session_id=session_id,
            query=query,
            has_documents=has_docs,
            chat_history=history,
        )
    except Exception as e:
        err = str(e)
        if "rate_limit" in err.lower() or "429" in err or "tokens per minute" in err.lower():
            raise HTTPException(
                status_code=429,
                detail=(
                    "Rate limit reached. The research pipeline uses multiple LLM calls. "
                    "Try Chat Mode for a lighter request, wait 1-2 minutes, or upgrade your API plan."
                ),
            )
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {e}")

    _chat_store[session_id] = result.chat_history

    agent_steps = [
        AgentStep(
            agent=step.agent,
            status=step.status,
            output_preview=step.output_preview or "",
            error=step.error,
        )
        for step in result.agent_steps
    ]

    return QueryResponse(
        session_id=session_id,
        query=query,
        plan=result.plan,
        plan_reasoning=result.plan_reasoning or "",
        sources=result.source_files,
        final_report=result.final_report,
        agent_steps=agent_steps,
    )


# ── History ─────────────────────────────────────────────────────────────────────

@router.get(
    "/history/{session_id}", response_model=HistoryResponse, tags=["History"]
)
async def get_history(session_id: str):
    raw_messages = _chat_store.get(session_id, [])
    messages = []
    for m in raw_messages:
        try:
            messages.append(
                ChatMessage(
                    role=m.get("role", "user"),
                    content=m.get("content", ""),
                    query=m.get("query"),
                    timestamp=m.get("timestamp"),
                )
            )
        except Exception:
            pass
    return HistoryResponse(session_id=session_id, messages=messages)


@router.delete("/history/{session_id}", tags=["History"])
async def clear_history(session_id: str):
    _chat_store.pop(session_id, None)
    _convo_store.pop(session_id, None)
    return {"message": f"History cleared for session '{session_id}'."}
