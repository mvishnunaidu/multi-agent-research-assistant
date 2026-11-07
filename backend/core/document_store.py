"""
document_store.py — Document loading, chunking, embedding, and FAISS retrieval.

Embeddings are computed via the Google Gemini API (langchain_google_genai),
avoiding local PyTorch / SentenceTransformer models to keep memory footprint
well within free-tier limits (e.g. Render 512MB RAM).

Supported formats: PDF (.pdf), Word (.docx), Plain Text (.txt).
Legacy binary .doc files are explicitly rejected with an informative error.
"""

import json
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from langchain_core.documents import Document
from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    TextLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from backend.core.config import settings

logger = logging.getLogger(__name__)

# ── Embeddings (Gemini API — no local PyTorch / model weights) ────────────────
_embeddings_instance: Optional[GoogleGenerativeAIEmbeddings] = None


def _get_embeddings() -> GoogleGenerativeAIEmbeddings:
    global _embeddings_instance
    if _embeddings_instance is None:
        if not settings.gemini_api_key.strip():
            raise RuntimeError(
                "GEMINI_API_KEY is required for document embeddings "
                "(RAG / document upload). Set GEMINI_API_KEY in your .env file."
            )
        _embeddings_instance = GoogleGenerativeAIEmbeddings(
            model=settings.gemini_embedding_model,
            google_api_key=settings.gemini_api_key,
        )
    return _embeddings_instance


# ── Text splitter ─────────────────────────────────────────────────────────────
_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=150,
    separators=["\n\n", "\n", ". ", " ", ""],
)


import re

def validate_session_id(session_id: str) -> str:
    """
    Validate that session_id is safe against path traversal and conforms to a
    safe UUID / alphanumeric identifier format (e.g. UUID4 string).
    Blocks directory traversal attempts (../, ..\\, etc.) and invalid characters.
    """
    s = str(session_id).strip()
    if not s or not re.match(r"^[a-zA-Z0-9_\-]+$", s) or ".." in s or len(s) > 128:
        raise ValueError(f"Invalid session ID format: '{session_id}'. Must be a valid UUID or safe identifier.")
    return s


def load_documents(file_path: Path) -> List[Document]:
    """
    Load a PDF, DOCX, or TXT file into LangChain Document objects.
    Validates file existence, non-zero size, and text readability.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if file_path.stat().st_size == 0:
        raise ValueError(f"Uploaded file '{file_path.name}' is empty (0 bytes).")

    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        loader = PyPDFLoader(str(file_path))
        docs = loader.load()
    elif suffix == ".docx":
        loader = Docx2txtLoader(str(file_path))
        docs = loader.load()
    elif suffix == ".doc":
        raise ValueError(
            f"Legacy binary Word format (.doc) is not supported for '{file_path.name}'. "
            "Please convert the file to .docx or .pdf before uploading."
        )
    elif suffix == ".txt":
        # Handle UTF-8 with fallback to Latin-1
        try:
            loader = TextLoader(str(file_path), encoding="utf-8")
            docs = loader.load()
        except UnicodeDecodeError:
            loader = TextLoader(str(file_path), encoding="latin-1")
            docs = loader.load()
    else:
        raise ValueError(
            f"Unsupported file type: '{suffix}'. Allowed formats: .pdf, .docx, .txt"
        )

    # Validate extracted text content
    total_chars = sum(len(d.page_content.strip()) for d in docs)
    if total_chars == 0:
        raise ValueError(f"Uploaded file '{file_path.name}' contains no readable text content.")

    return docs


def _get_manifest_path(store_path: Path) -> Path:
    return store_path / "manifest.json"


def _read_manifest(store_path: Path) -> List[Dict[str, Any]]:
    manifest_file = _get_manifest_path(store_path)
    if manifest_file.exists():
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Could not read manifest at %s: %s", manifest_file, e)
    return []


def _write_manifest(store_path: Path, manifest: List[Dict[str, Any]]):
    manifest_file = _get_manifest_path(store_path)
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def ingest_file(file_path: Path, session_id: str) -> Dict[str, Any]:
    """
    Load → chunk → embed → persist FAISS vector store for one file.
    Merges with existing store if session already has documents.
    Prevents duplicate ingestion of identical files in the same session.
    """
    valid_session = validate_session_id(session_id)
    docs = load_documents(file_path)
    chunks = _splitter.split_documents(docs)

    store_path = settings.vectorstore_dir / valid_session
    store_path.mkdir(parents=True, exist_ok=True)

    manifest = _read_manifest(store_path)
    existing_files = [m["filename"] for m in manifest]

    if file_path.name in existing_files:
        logger.info("File '%s' already indexed for session %s. Skipping duplicate.", file_path.name, valid_session)
        existing_entry = next(m for m in manifest if m["filename"] == file_path.name)
        return {
            "num_chunks": existing_entry.get("num_chunks", len(chunks)),
            "store_path": str(store_path),
            "is_duplicate": True,
        }

    for idx, chunk in enumerate(chunks):
        chunk.metadata["source_file"] = file_path.name
        chunk.metadata["session_id"] = valid_session
        chunk.metadata["chunk_index"] = idx

    from langchain_community.vectorstores import FAISS

    index_file = store_path / "index.faiss"

    if index_file.exists():
        # Merge into existing store so multiple uploads share one session index
        existing_vs = FAISS.load_local(
            str(store_path),
            _get_embeddings(),
            allow_dangerous_deserialization=True,
        )
        existing_vs.add_documents(chunks)
        existing_vs.save_local(str(store_path))
        _vectorstore_cache[valid_session] = existing_vs
    else:
        vs = FAISS.from_documents(chunks, _get_embeddings())
        vs.save_local(str(store_path))
        _vectorstore_cache[valid_session] = vs

    # Update manifest
    manifest.append({
        "filename": file_path.name,
        "num_chunks": len(chunks),
        "uploaded_at": datetime.now().isoformat(),
        "file_size_bytes": file_path.stat().st_size,
    })
    _write_manifest(store_path, manifest)

    return {
        "num_chunks": len(chunks),
        "store_path": str(store_path),
        "is_duplicate": False,
    }


_vectorstore_cache: Dict[str, Any] = {}


def get_retriever(session_id: str, k: int = 5):
    """
    Return a similarity retriever for an existing session's FAISS vector store.
    Validates session isolation to ensure only authorized session directories are loaded.
    Uses in-memory cache to eliminate disk I/O deserialization latency on repeat lookups.
    """
    valid_session = validate_session_id(session_id)
    store_path = settings.vectorstore_dir / valid_session
    index_file = store_path / "index.faiss"

    if not index_file.exists():
        raise FileNotFoundError(
            f"No vector store index found for session '{valid_session}'. "
            "Please upload a document first."
        )

    if valid_session in _vectorstore_cache:
        vs = _vectorstore_cache[valid_session]
    else:
        from langchain_community.vectorstores import FAISS

        vs = FAISS.load_local(
            str(store_path),
            _get_embeddings(),
            allow_dangerous_deserialization=True,
        )
        _vectorstore_cache[valid_session] = vs

    return vs.as_retriever(search_type="similarity", search_kwargs={"k": k})


def session_has_documents(session_id: str) -> bool:
    """Check whether a session already has an ingested vector store index."""
    try:
        valid_session = validate_session_id(session_id)
        store_path = settings.vectorstore_dir / valid_session
        return (store_path / "index.faiss").exists()
    except Exception:
        return False


def get_session_documents(session_id: str) -> List[Dict[str, Any]]:
    """Return the list of ingested document manifests for a session."""
    try:
        valid_session = validate_session_id(session_id)
        store_path = settings.vectorstore_dir / valid_session
        return _read_manifest(store_path)
    except Exception:
        return []


def delete_session_document(session_id: str, filename: str) -> bool:
    """
    Remove a specific document from a session.
    Updates the manifest, cleans up the upload file, and rebuilds the vector index
    from remaining documents (or deletes the index if 0 documents remain).
    """
    valid_session = validate_session_id(session_id)
    store_path = settings.vectorstore_dir / valid_session
    upload_session_dir = settings.upload_dir / valid_session

    if not store_path.exists():
        return False

    manifest = _read_manifest(store_path)
    clean_target = Path(filename).name
    remaining_manifest = [d for d in manifest if d.get("filename") != clean_target]

    if len(remaining_manifest) == len(manifest):
        return False

    # 1. Remove physical uploaded file if present
    target_upload_file = upload_session_dir / clean_target
    if target_upload_file.exists():
        try:
            target_upload_file.unlink()
        except Exception as e:
            logger.warning("Could not delete upload file %s: %s", target_upload_file, e)

    # 2. Update manifest
    _write_manifest(store_path, remaining_manifest)

    # 3. Evict from memory cache
    _vectorstore_cache.pop(valid_session, None)

    # 4. If no documents remain, delete index files
    if not remaining_manifest:
        index_file = store_path / "index.faiss"
        pkl_file = store_path / "index.pkl"
        if index_file.exists():
            index_file.unlink()
        if pkl_file.exists():
            pkl_file.unlink()
        return True

    # 5. If documents remain, rebuild index from remaining upload files
    from langchain_community.vectorstores import FAISS

    all_chunks = []
    for item in remaining_manifest:
        f_name = item.get("filename")
        f_path = upload_session_dir / f_name
        if f_path.exists():
            try:
                docs = load_and_split_document(f_path)
                for idx, chunk in enumerate(docs):
                    chunk.metadata["source_file"] = f_name
                    chunk.metadata["session_id"] = valid_session
                    chunk.metadata["chunk_index"] = idx
                all_chunks.extend(docs)
            except Exception as e:
                logger.error("Error re-indexing file %s: %s", f_name, e)

    if all_chunks:
        new_vs = FAISS.from_documents(all_chunks, _get_embeddings())
        new_vs.save_local(str(store_path))
        _vectorstore_cache[valid_session] = new_vs
    else:
        index_file = store_path / "index.faiss"
        pkl_file = store_path / "index.pkl"
        if index_file.exists():
            index_file.unlink()
        if pkl_file.exists():
            pkl_file.unlink()

    return True


def clear_session_documents(session_id: str) -> bool:
    """Clear all documents and delete the FAISS vector index for a session."""
    valid_session = validate_session_id(session_id)
    store_path = settings.vectorstore_dir / valid_session
    upload_session_dir = settings.upload_dir / valid_session

    _vectorstore_cache.pop(valid_session, None)

    import shutil
    if store_path.exists():
        shutil.rmtree(store_path, ignore_errors=True)
    if upload_session_dir.exists():
        shutil.rmtree(upload_session_dir, ignore_errors=True)
    return True
