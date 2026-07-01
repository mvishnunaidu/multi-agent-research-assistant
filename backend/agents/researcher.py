"""
researcher.py — Researcher Agent
Performs RAG retrieval per sub-task using the session's FAISS vector store.
Falls back to LLM general knowledge when no documents are uploaded.
"""

from backend.core.llm import get_llm
from backend.core.document_store import get_retriever, session_has_documents

RAG_PROMPT = """You are a Research Agent. Answer the sub-task below using ONLY the provided document context.
If the context does not contain enough information, state that clearly.

Sub-task: {task}

Document context:
{context}

Give a factual, concise answer and reference the source where possible."""

GENERAL_PROMPT = """You are a Research Agent. Answer the following question using your knowledge.
Be factual, concise, and note any important caveats.

Question: {task}"""


def run_researcher(
    sub_tasks: list[str], session_id: str, has_documents: bool
) -> dict:
    """
    Agent 2 — Researcher.
    Input:  list of sub-tasks from planner, session_id, has_documents flag
    Output: {"answers": [...], "retrieved_chunks": [...], "source_files": [...]}
    """
    llm = get_llm()
    has_docs = has_documents and session_has_documents(session_id)

    answers: list[str] = []
    retrieved_chunks: list[str] = []
    source_files: set[str] = set()

    if has_docs:
        retriever = get_retriever(session_id, k=5)
        for task in sub_tasks:
            docs = retriever.invoke(task)
            context_parts = [doc.page_content for doc in docs]
            for doc in docs:
                src = doc.metadata.get("source_file", "unknown")
                source_files.add(src)

            context = (
                "\n\n---\n\n".join(context_parts)
                if context_parts
                else "No relevant context found."
            )
            retrieved_chunks.extend(context_parts)

            response = llm.invoke(
                RAG_PROMPT.format(task=task, context=context)
            )
            answers.append(
                f"**Sub-task:** {task}\n\n{response.content.strip()}"
            )

    else:
        for task in sub_tasks:
            response = llm.invoke(GENERAL_PROMPT.format(task=task))
            answers.append(
                f"**Sub-task:** {task}\n\n{response.content.strip()}"
            )

    return {
        "answers": answers,
        "retrieved_chunks": retrieved_chunks,
        "source_files": list(source_files),
    }
