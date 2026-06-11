"""
document_store.py — Document loading, chunking, embedding, and
                    vector store creation/retrieval (FAISS or Chroma).

FIX APPLIED: Uses langchain_huggingface.HuggingFaceEmbeddings
             (not langchain_community.embeddings which is deprecated in 0.3.x)
"""
from pathlib import Path
from typing import List

from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings   # ← fixed import

from backend.core.config import settings

# ── Embeddings (runs locally — no API key, no cost) ───────────────────────────
# Model downloads ~90 MB on first run, then caches in ~/.cache/huggingface/
_embeddings = HuggingFaceEmbeddings(
    model_name="all-MiniLM-L6-v2",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

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
        raise ValueError(f"Unsupported file type: '{suffix}'. Allowed: .pdf, .docx, .doc, .txt")
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

    if settings.vector_store == "faiss":
        from langchain_community.vectorstores import FAISS
        index_file = store_path / "index.faiss"

        if index_file.exists():
            # Merge into existing store
            existing = FAISS.load_local(
                str(store_path),
                _embeddings,
                allow_dangerous_deserialization=True,
            )
            existing.add_documents(chunks)
            existing.save_local(str(store_path))
        else:
            vs = FAISS.from_documents(chunks, _embeddings)
            vs.save_local(str(store_path))

    else:  # chroma
        from langchain_community.vectorstores import Chroma
        Chroma.from_documents(
            chunks,
            _embeddings,
            collection_name=session_id,
            persist_directory=str(store_path),
        )

    return {"num_chunks": len(chunks), "store_path": str(store_path)}


def get_retriever(session_id: str, k: int = 5):
    """Return a retriever for an existing session's vector store."""
    store_path = settings.vectorstore_dir / session_id

    if not store_path.exists():
        raise FileNotFoundError(
            f"No vector store found for session '{session_id}'. "
            "Please upload a document first."
        )

    if settings.vector_store == "faiss":
        from langchain_community.vectorstores import FAISS
        vs = FAISS.load_local(
            str(store_path),
            _embeddings,
            allow_dangerous_deserialization=True,
        )
    else:
        from langchain_community.vectorstores import Chroma
        vs = Chroma(
            collection_name=session_id,
            embedding_function=_embeddings,
            persist_directory=str(store_path),
        )

    return vs.as_retriever(search_type="similarity", search_kwargs={"k": k})


def session_has_documents(session_id: str) -> bool:
    """Check whether a session already has an ingested vector store."""
    store_path = settings.vectorstore_dir / session_id
    return store_path.exists() and any(store_path.iterdir())
