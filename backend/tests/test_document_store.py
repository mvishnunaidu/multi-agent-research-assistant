"""
test_document_store.py — Unit tests for document loading, session validation, and FAISS indexing.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock
from langchain_core.documents import Document

from backend.core.document_store import (
    validate_session_id,
    load_documents,
    ingest_file,
    session_has_documents,
)


def test_validate_session_id_security():
    # Valid UUIDs
    assert validate_session_id("12345678-1234-5678-1234-567812345678") == "12345678-1234-5678-1234-567812345678"
    assert validate_session_id("session_123-abc") == "session_123-abc"

    # Traversal attacks must be rejected
    with pytest.raises(ValueError, match="Invalid session ID"):
        validate_session_id("../secret")

    with pytest.raises(ValueError, match="Invalid session ID"):
        validate_session_id("..\\etc\\passwd")

    with pytest.raises(ValueError, match="Invalid session ID"):
        validate_session_id("")

    with pytest.raises(ValueError, match="Invalid session ID"):
        validate_session_id("session/child")


def test_load_documents_rejects_empty_file(tmp_path):
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        load_documents(empty_file)


def test_load_documents_rejects_legacy_doc(tmp_path):
    doc_file = tmp_path / "sample.doc"
    doc_file.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")

    with pytest.raises(ValueError, match="Legacy binary Word format"):
        load_documents(doc_file)


def test_load_documents_rejects_unsupported_extension(tmp_path):
    bad_file = tmp_path / "script.py"
    bad_file.write_text("print('hello')", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file type"):
        load_documents(bad_file)


def test_load_documents_txt_valid(tmp_path):
    txt_file = tmp_path / "sample.txt"
    txt_file.write_text("Antigravity Multi-Agent Research Assistant test file.", encoding="utf-8")

    docs = load_documents(txt_file)
    assert len(docs) >= 1
    assert "Multi-Agent Research Assistant" in docs[0].page_content


import uuid
from backend.core.config import settings

def test_ingest_file_duplicate_handling(tmp_path, monkeypatch):
    """Verifies that re-uploading an already indexed file returns is_duplicate=True without error."""
    session_id = f"test-session-{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(settings, "vectorstore_dir", tmp_path / "vectorstores")
    txt_file = tmp_path / "data.txt"
    txt_file.write_text("Important research knowledge chunk for FAISS indexing.", encoding="utf-8")

    # Mock embeddings and FAISS
    mock_embeddings = MagicMock()
    monkeypatch.setattr("backend.core.document_store._get_embeddings", lambda: mock_embeddings)

    mock_faiss_instance = MagicMock()
    mock_faiss_class = MagicMock()
    mock_faiss_class.from_documents.return_value = mock_faiss_instance
    monkeypatch.setattr("langchain_community.vectorstores.FAISS", mock_faiss_class)

    # First ingestion
    res1 = ingest_file(txt_file, session_id)
    assert res1["num_chunks"] >= 1
    assert res1["is_duplicate"] is False

    # Second ingestion of same file should recognize duplicate
    res2 = ingest_file(txt_file, session_id)
    assert res2["is_duplicate"] is True
