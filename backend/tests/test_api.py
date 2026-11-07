"""
test_api.py — Integration tests for FastAPI endpoints.

Tests input validation, session creation, upload constraints, security against
path traversal, health reporting, and mock-based chat & research endpoints.
"""

import uuid
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage


def test_health_check(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["vector_store"] == "faiss"
    assert "configured_providers" in body
    assert "embeddings_ready" in body


def test_new_session_returns_uuid(client):
    r = client.post("/api/v1/session/new")
    assert r.status_code == 200
    session_id = r.json()["session_id"]
    assert len(session_id) == 36  # UUID4 string length
    # Verify valid UUID structure
    val = uuid.UUID(session_id)
    assert str(val) == session_id


def test_upload_rejects_unsupported_file_type(client):
    r = client.post(
        "/api/v1/upload",
        files={"file": ("notes.exe", b"not a real document", "application/octet-stream")},
    )
    assert r.status_code == 400
    assert "not supported" in r.json()["detail"].lower()


def test_upload_rejects_legacy_doc_file(client):
    r = client.post(
        "/api/v1/upload",
        files={"file": ("old_doc.doc", b"legacy binary doc content", "application/msword")},
    )
    assert r.status_code == 400
    assert "legacy binary word format" in r.json()["detail"].lower()


def test_upload_rejects_empty_file(client):
    r = client.post(
        "/api/v1/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


def test_upload_rejects_path_traversal_session_id(client):
    r = client.post(
        "/api/v1/upload?session_id=../../etc/passwd",
        files={"file": ("test.txt", b"safe content", "text/plain")},
    )
    assert r.status_code == 400
    assert "invalid session id" in r.json()["detail"].lower()


def test_research_rejects_empty_query(client):
    sid = str(uuid.uuid4())
    r = client.post(
        "/api/v1/research",
        json={"session_id": sid, "query": "", "has_documents": False},
    )
    assert r.status_code == 422


def test_research_rejects_invalid_session_id(client):
    r = client.post(
        "/api/v1/research",
        json={"session_id": "../../bad_session", "query": "Valid query", "has_documents": False},
    )
    assert r.status_code == 400
    assert "invalid session id" in r.json()["detail"].lower()


def test_chat_rejects_empty_message(client):
    sid = str(uuid.uuid4())
    r = client.post(
        "/api/v1/chat",
        json={"session_id": sid, "message": "", "has_documents": False},
    )
    assert r.status_code == 422


def test_history_empty_session_returns_empty_list(client):
    r = client.get("/api/v1/history/nonexistent-session")
    assert r.status_code == 200
    assert r.json()["messages"] == []


def test_history_clear_session(client):
    sid = str(uuid.uuid4())
    r = client.delete(f"/api/v1/history/{sid}")
    assert r.status_code == 200
    assert f"History cleared for session '{sid}'" in r.json()["message"]


def test_documents_listing_empty(client):
    sid = str(uuid.uuid4())
    r = client.get(f"/api/v1/documents/{sid}")
    assert r.status_code == 200
    assert r.json()["session_id"] == sid
    assert r.json()["documents"] == []


def test_chat_happy_path_mocked(client, monkeypatch):
    """Verifies that /api/v1/chat handles conversation with mocked LLM."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(content="Hello! This is a mocked AI response.")
    monkeypatch.setattr("backend.api.routes.get_llm", lambda: mock_llm)

    sid = str(uuid.uuid4())
    r = client.post(
        "/api/v1/chat",
        json={"session_id": sid, "message": "Hello world", "has_documents": False},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"] == sid
    assert data["reply"] == "Hello! This is a mocked AI response."
    assert "sources" in data


def test_research_happy_path_mocked(client, monkeypatch):
    """Verifies that /api/v1/research returns expected schema with mocked run_pipeline."""
    from backend.agents.pipeline import PipelineResult, AgentStep

    sid = str(uuid.uuid4())
    fake_result = PipelineResult(
        session_id=sid,
        query="Explain transformers",
        plan=["Self-attention", "Feed-forward"],
        plan_reasoning="Component analysis",
        retrieved_chunks=[],
        source_files=[],
        summary="Summary of transformers",
        final_report="# Research Report\n\n## Findings\nTransformers are neural networks.",
        agent_steps=[
            AgentStep(agent="Planner", status="completed", output_preview="Plan ok", duration_seconds=0.1),
            AgentStep(agent="Researcher", status="completed", output_preview="Findings ok", duration_seconds=0.2),
            AgentStep(agent="Summarizer", status="completed", output_preview="Summary ok", duration_seconds=0.1),
            AgentStep(agent="Report Generator", status="completed", output_preview="Report ok", duration_seconds=0.1),
        ],
        chat_history=[],
        overall_status="completed",
    )

    monkeypatch.setattr("backend.api.routes.run_pipeline", lambda **kwargs: fake_result)

    r = client.post(
        "/api/v1/research",
        json={"session_id": sid, "query": "Explain transformers", "has_documents": False},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"] == sid
    assert len(data["plan"]) == 2
    assert data["final_report"].startswith("# Research Report")
    assert len(data["agent_steps"]) == 4
    assert data["overall_status"] == "completed"


def test_delete_document_not_found(client):
    sid = client.post("/api/v1/session/new").json()["session_id"]
    r = client.delete(f"/api/v1/documents/{sid}/nonexistent.pdf")
    assert r.status_code == 404


def test_clear_all_documents(client):
    sid = client.post("/api/v1/session/new").json()["session_id"]
    r = client.delete(f"/api/v1/documents/{sid}")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
