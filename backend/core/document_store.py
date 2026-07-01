"""
document_store.py — Document loading, chunking, embedding, and
                    FAISS vector store creation/retrieval.

Embeddings are computed via the Gemini API (langchain_google_genai), not a
local sentence-transformers model. A local model + torch pulls in several
hundred MB of RAM just to import, which reliably OOMs on free-tier hosts
with a 512MB limit (Render, Railway free plans, etc.). Calling out to
Gemini's embedding endpoint keeps the whole app's memory footprint small
enough to run comfortably within that limit, at the cost of one extra
network round-trip per chunk (batched, so it's still fast).
"""

from pathlib import Path
from typing import List

from langchain_core.documents import Document
from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    TextLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from backend.core.config import settings

# ── Embeddings (Gemini API — no local model, minimal RAM) ─────────────────────
# Lazy-loaded so importing this module (e.g. for /health or tests) doesn't
# require a configured API key.
_embeddings_instance = None


def _get_embeddings() -> GoogleGenerativeAIEmbeddings:
    global _embeddings_instance
    if _embeddings_instance is None:
        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is required for document embeddings "
                "(RAG/document upload), even if you're using a different "
                "provider for chat. Set it in your .env file."
            )
        _embeddings_instance = GoogleGenerativeAIEmbeddings(
            model=settings.gemini_embedding_model,
            google_api_key=settings.gemini_api_key,
        )
    return _embeddings_instance


# ── Text splitter ──────────────────────────────────────────────────────────────
_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=150,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def load_documents(file_path: Path) -> List[Document]:
    """Load a PDF, DOCX, or TXT file into LangChain Document objects."""
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        loader = PyPDFLoader(str(file_path))
    elif suffix in (".docx", ".doc"):
        loader = Docx2txtLoader(str(file_path))
    elif suffix == ".txt":
        loader = TextLoader(str(file_path), encoding="utf-8")
    else:
        raise ValueError(
            f"Unsupported file type: '{suffix}'. Allowed: .pdf, .docx, .doc, .txt"
        )
    return loader.load()


def ingest_file(file_path: Path, session_id: str) -> dict:
    """
    Load → chunk → embed → persist vector store for one file.
    Merges with existing store if session already has documents.
    Returns: {"num_chunks": int, "store_path": str}
    """
    docs = load_documents(file_path)
    chunks = _splitter.split_documents(docs)

    for chunk in chunks:
        chunk.metadata["source_file"] = file_path.name
        chunk.metadata["session_id"] = session_id

    store_path = settings.vectorstore_dir / session_id
    store_path.mkdir(parents=True, exist_ok=True)

    from langchain_community.vectorstores import FAISS

    index_file = store_path / "index.faiss"

    if index_file.exists():
        # Merge into existing store so multiple uploads share one session index
        existing = FAISS.load_local(
            str(store_path),
            _get_embeddings(),
            allow_dangerous_deserialization=True,
        )
        existing.add_documents(chunks)
        existing.save_local(str(store_path))
    else:
        vs = FAISS.from_documents(chunks, _get_embeddings())
        vs.save_local(str(store_path))

    return {"num_chunks": len(chunks), "store_path": str(store_path)}


def get_retriever(session_id: str, k: int = 5):
    """Return a retriever for an existing session's FAISS vector store."""
    store_path = settings.vectorstore_dir / session_id

    if not store_path.exists():
        raise FileNotFoundError(
            f"No vector store found for session '{session_id}'. "
            "Please upload a document first."
        )

    from langchain_community.vectorstores import FAISS

    vs = FAISS.load_local(
        str(store_path),
        _get_embeddings(),
        allow_dangerous_deserialization=True,
    )
    return vs.as_retriever(search_type="similarity", search_kwargs={"k": k})


def session_has_documents(session_id: str) -> bool:
    """Check whether a session already has an ingested vector store."""
    store_path = settings.vectorstore_dir / session_id
    return store_path.exists() and any(store_path.iterdir())
