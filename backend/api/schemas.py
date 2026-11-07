"""
schemas.py — Pydantic request/response models for all API endpoints.
"""

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


# ── Upload ─────────────────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    session_id: str
    filename: str
    num_chunks: int
    message: str
    is_duplicate: bool = False


class DocumentItem(BaseModel):
    filename: str
    num_chunks: int
    uploaded_at: str
    file_size_bytes: int


class SessionDocumentsResponse(BaseModel):
    session_id: str
    documents: List[DocumentItem]


# ── Research ───────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    session_id: str = Field(
        ..., description="Valid UUID4 Session ID from /session/new or /upload"
    )
    query: str = Field(..., min_length=1, max_length=5000)
    has_documents: bool = Field(default=False)


class AgentStep(BaseModel):
    agent: str
    status: str
    output_preview: Optional[str] = None
    duration_seconds: Optional[float] = 0.0
    error: Optional[str] = None


class QueryResponse(BaseModel):
    session_id: str
    query: str
    plan: List[str]
    plan_reasoning: str
    sources: List[str]
    final_report: str
    agent_steps: List[AgentStep]
    overall_status: str = "completed"
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


# ── Chat ───────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Valid UUID4 Session ID")
    message: str = Field(..., min_length=1, max_length=5000)
    has_documents: bool = Field(default=False)


class ChatResponse(BaseModel):
    session_id: str
    message: str
    reply: str
    sources: List[str] = []
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


# ── History ────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str
    query: Optional[str] = None
    timestamp: Optional[str] = None
    overall_status: Optional[str] = None
    sources: Optional[List[str]] = None


class HistoryResponse(BaseModel):
    session_id: str
    messages: List[ChatMessage]


# ── Health ─────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    llm_provider: str
    configured_providers: List[str]
    vector_store: str
    embeddings_ready: bool
