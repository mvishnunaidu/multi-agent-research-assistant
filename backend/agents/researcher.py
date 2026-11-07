"""
researcher.py — Researcher Agent (Agent 2)

Executes research for each Planner sub-task.
- If documents exist in the session FAISS vector store, performs RAG retrieval (top-5 similarity)
  and grounds answers strictly on retrieved document excerpts.
- If no documents are uploaded, uses general LLM knowledge while explicitly noting general knowledge mode.
- Preserves source file metadata and prevents leaking internal tracebacks into final output.
"""

import logging
from typing import List, Dict, Any, Set
from backend.core.llm import get_llm
from backend.core.document_store import get_retriever, session_has_documents

logger = logging.getLogger(__name__)

RAG_PROMPT = """You are an objective Research Agent. Answer the sub-task below using ONLY the provided document context excerpts.

Sub-task: {task}

Document Context Excerpts:
{context}

Strict Grounding Rules:
1. Base your answer solely on facts, metrics, and statements present in the context excerpts above.
2. If the context does not contain enough information to address the sub-task, explicitly state: "The provided document excerpts do not contain sufficient information to answer this sub-task."
3. Cite the source document filename (and page number if specified in the excerpt header) for each major fact.
4. Do NOT speculate, hallucinate external references, or invent page numbers or statistics."""

GENERAL_PROMPT = """You are an objective Research Agent. Answer the following question using your foundational knowledge.

Question: {task}

Rules:
1. Provide a factual, balanced, and structured answer.
2. Clearly distinguish established facts from general consensus or ongoing debates.
3. Keep the response concise, informative, and free of filler phrases."""


def run_researcher(
    sub_tasks: List[str], session_id: str, has_documents: bool
) -> Dict[str, Any]:
    """
    Agent 2 — Researcher.
    Input:
        sub_tasks: List of atomic sub-tasks from Planner
        session_id: Session identifier to locate FAISS vector store
        has_documents: Flag indicating document presence
    Output:
        {
            "answers": List[str],
            "retrieved_chunks": List[str],
            "source_files": List[str],
            "grounding": "document" | "general_knowledge" | "mixed",
            "status": "completed" | "fallback" | "error",
            "error": Optional[str],
        }
    """
    if not sub_tasks:
        return {
            "answers": [],
            "retrieved_chunks": [],
            "source_files": [],
            "grounding": "general_knowledge",
            "status": "fallback",
            "error": "No sub-tasks provided to Researcher.",
        }

    try:
        llm = get_llm()
    except Exception as e:
        logger.error("Researcher failed to acquire LLM instance: %s", e)
        return {
            "answers": [f"Research unavailable: {e}"],
            "retrieved_chunks": [],
            "source_files": [],
            "grounding": "general_knowledge",
            "status": "error",
            "error": str(e),
        }

    has_docs = bool(has_documents and session_has_documents(session_id))
    answers: List[str] = []
    retrieved_chunks: List[str] = []
    source_files: Set[str] = set()
    total_chunks_found = 0
    errors: List[str] = []

    retriever = None
    if has_docs:
        try:
            retriever = get_retriever(session_id, k=5)
        except Exception as e:
            logger.warning("Failed to initialize retriever for session %s: %s", session_id, e)
            errors.append(f"Retriever initialization warning: {e}")
            has_docs = False  # Fall back to general knowledge if retriever fails

    for task in sub_tasks:
        clean_task = task.strip()
        if not clean_task:
            continue

        try:
            if has_docs and retriever is not None:
                # ── Document-grounded RAG path ────────────────────────────────
                docs = retriever.invoke(clean_task)
                context_parts = []

                for idx, doc in enumerate(docs):
                    src = doc.metadata.get("source_file", "Uploaded Document")
                    page = doc.metadata.get("page")
                    page_str = f" (Page {page + 1})" if page is not None else ""
                    source_files.add(src)

                    header = f"[Excerpt {idx + 1} | Source: {src}{page_str}]"
                    chunk_text = f"{header}\n{doc.page_content.strip()}"
                    context_parts.append(chunk_text)
                    retrieved_chunks.append(doc.page_content.strip())

                if context_parts:
                    total_chunks_found += len(context_parts)
                    context_block = "\n\n---\n\n".join(context_parts)
                    prompt = RAG_PROMPT.format(task=clean_task, context=context_block)
                else:
                    context_block = "No matching excerpts found in the uploaded documents."
                    prompt = (
                        f"Sub-task: {clean_task}\n\n"
                        "Note: No relevant excerpts were found in the uploaded documents for this sub-task. "
                        "State clearly that the uploaded documents do not contain information on this topic."
                    )

                response = llm.invoke(prompt)
                content = response.content.strip() if hasattr(response, "content") else str(response)
                answers.append(f"### Sub-task: {clean_task}\n\n{content}")

            else:
                # ── General knowledge LLM path ────────────────────────────────
                prompt = GENERAL_PROMPT.format(task=clean_task)
                response = llm.invoke(prompt)
                content = response.content.strip() if hasattr(response, "content") else str(response)
                answers.append(f"### Sub-task: {clean_task}\n\n{content}")

        except Exception as task_err:
            logger.error("Error executing researcher sub-task '%s': %s", clean_task, task_err)
            errors.append(str(task_err))
            answers.append(
                f"### Sub-task: {clean_task}\n\n"
                f"*Notice: Could not retrieve or generate findings for this sub-task due to an execution issue.*"
            )

    # Determine grounding and status
    if has_docs:
        grounding = "document" if total_chunks_found > 0 else "general_knowledge"
    else:
        grounding = "general_knowledge"

    if not answers:
        status = "error"
        error_msg = "; ".join(errors) if errors else "Researcher generated 0 answers."
    elif errors and len(errors) == len(sub_tasks):
        status = "error"
        error_msg = "; ".join(errors)
    elif errors or (has_docs and total_chunks_found == 0):
        status = "fallback"
        error_msg = "; ".join(errors) if errors else "No relevant document chunks found in index."
    else:
        status = "completed"
        error_msg = None

    return {
        "answers": answers,
        "retrieved_chunks": retrieved_chunks,
        "source_files": sorted(list(source_files)),
        "grounding": grounding,
        "status": status,
        "error": error_msg,
    }
