"""
test_api.py — Integration tests for the FastAPI routes that don't require
a live LLM call (health check, session creation, and input validation).
"""


def test_health_check(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["vector_store"] == "faiss"


def test_new_session_returns_uuid(client):
    r = client.post("/api/v1/session/new")
    assert r.status_code == 200
    session_id = r.json()["session_id"]
    assert len(session_id) == 36  # UUID4 string length


def test_upload_rejects_unsupported_file_type(client):
    r = client.post(
        "/api/v1/upload",
        files={"file": ("notes.exe", b"not a real document", "application/octet-stream")},
    )
    assert r.status_code == 400
    assert "not supported" in r.json()["detail"]


def test_research_rejects_empty_query(client):
    r = client.post(
        "/api/v1/research",
        json={"session_id": "s1", "query": "", "has_documents": False},
    )
    assert r.status_code == 422


def test_chat_rejects_empty_message(client):
    r = client.post(
        "/api/v1/chat",
        json={"session_id": "s1", "message": "", "has_documents": False},
    )
    assert r.status_code == 422


def test_history_empty_session_returns_empty_list(client):
    r = client.get("/api/v1/history/nonexistent-session")
    assert r.status_code == 200
    assert r.json()["messages"] == []
