"""
schemas.py — Pydantic request/response models for all API endpoints.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# ── Upload ─────────────────────────────────────────────────────────────────────


class UploadResponse(BaseModel):
    session_id: str
    filename: str
    num_chunks: int
    message: str


# ── Research ───────────────────────────────────────────────────────────────────


class QueryRequest(BaseModel):
    session_id: str = Field(
        ..., description="Session ID from /session/new or /upload"
    )
    query: str = Field(..., min_length=1, max_length=5000)
    has_documents: bool = Field(default=False)


class AgentStep(BaseModel):
    agent: str
    status: str
    output_preview: Optional[str] = None
    error: Optional[str] = None


class QueryResponse(BaseModel):
    session_id: str
    query: str
    plan: List[str]
    plan_reasoning: str
    sources: List[str]
    final_report: str
    agent_steps: List[AgentStep]
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


# ── History ────────────────────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str
    content: str
    query: Optional[str] = None
    timestamp: Optional[str] = None


class HistoryResponse(BaseModel):
    session_id: str
    messages: List[ChatMessage]


# ── Health ─────────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    version: str
    llm_provider: str
    vector_store: str
