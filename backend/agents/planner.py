"""
planner.py — Planner Agent
Breaks the user query into 2-4 focused sub-tasks using Structured Outputs.
"""

from pydantic import BaseModel, Field
from backend.core.llm import get_llm


class Plan(BaseModel):
    sub_tasks: list[str] = Field(
        description="List of 2 to 4 focused, atomic sub-tasks to research."
    )
    reasoning: str = Field(
        description="One sentence explaining the decomposition strategy."
    )


PLANNER_PROMPT = """You are a Research Planner. Break the user's query into 2 to 4 focused sub-tasks that together produce a comprehensive answer.

User Query: {query}
Documents uploaded: {has_docs}

Rules:
- If documents are uploaded, include sub-tasks that reference them explicitly.
- Each sub-task must be atomic and independently answerable."""


def run_planner(query: str, has_documents: bool) -> dict:
    """
    Agent 1 — Planner.
    Input:  user query string, bool flag for documents
    Output: {"sub_tasks": [...], "reasoning": "..."}
    """
    llm = get_llm()
    structured_llm = llm.with_structured_output(Plan)

    prompt = PLANNER_PROMPT.format(
        query=query,
        has_docs="Yes" if has_documents else "No",
    )

    try:
        plan: Plan = structured_llm.invoke(prompt)

        return {
            "sub_tasks": plan.sub_tasks if plan.sub_tasks else [query],
            "reasoning": plan.reasoning,
            "error": None,
        }

    except Exception as e:
        # Graceful fallback — treat original query as single task
        return {
            "sub_tasks": [query],
            "reasoning": "Fallback to single-task mode.",
            "error": f"Planner warning: {str(e)}",
        }
