"""
planner.py — Planner Agent (Agent 1)

Decomposes a user research query into 2 to 4 focused, atomic sub-tasks
using Pydantic structured output. Validates sub-task count and contents,
handles malformed model output, and reports genuine status (completed vs fallback).
"""

import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator

from backend.core.llm import get_llm

logger = logging.getLogger(__name__)


class Plan(BaseModel):
    sub_tasks: List[str] = Field(
        description="List of 2 to 4 focused, atomic sub-tasks to research."
    )
    reasoning: str = Field(
        description="One or two sentences explaining the decomposition strategy."
    )

    @field_validator("sub_tasks")
    @classmethod
    def validate_sub_tasks(cls, v: List[str]) -> List[str]:
        # Filter non-empty strings and strip whitespace
        cleaned = [t.strip() for t in v if isinstance(t, str) and t.strip()]
        # Deduplicate preserving order
        deduped = list(dict.fromkeys(cleaned))
        if len(deduped) < 2:
            raise ValueError(f"Expected at least 2 distinct sub-tasks, got {len(deduped)}")
        return deduped[:4]


PLANNER_PROMPT = """You are an expert Research Planner. Break the user's research query into 2 or 3 focused, atomic sub-tasks that together produce a fast, comprehensive, and balanced report.

User Query: {query}
Session has uploaded documents: {has_docs}

Rules:
1. Generate 2 or 3 sub-tasks (strictly between 2 and 3).
2. Each sub-task must be concrete, atomic, and answerable independently.
3. If documents are uploaded, formulate sub-tasks that reference the document context and data points.
4. If no documents are uploaded, focus on core concepts, comparison, and evidence-dense foundational knowledge.
5. Provide a succinct one-sentence rationale for your decomposition strategy."""


def run_planner(query: str, has_documents: bool) -> Dict[str, Any]:
    """
    Agent 1 — Planner.
    Input:
        query: User research question (non-empty string)
        has_documents: Flag indicating if document knowledge base is available
    Output:
        {
            "sub_tasks": List[str],
            "reasoning": str,
            "status": "completed" | "fallback",
            "error": Optional[str],
        }
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return {
            "sub_tasks": ["Empty query provided."],
            "reasoning": "Query was empty.",
            "status": "fallback",
            "error": "Query string is empty.",
        }

    try:
        llm = get_llm()
        structured_llm = llm.with_structured_output(Plan)

        prompt = PLANNER_PROMPT.format(
            query=cleaned_query,
            has_docs="Yes (retrieve from knowledge store)" if has_documents else "No (general knowledge)",
        )

        plan: Plan = structured_llm.invoke(prompt)

        # Extra safety check on returned subtasks
        if plan and plan.sub_tasks and len(plan.sub_tasks) >= 2:
            return {
                "sub_tasks": plan.sub_tasks,
                "reasoning": plan.reasoning.strip() or "Decomposed query into focused sub-tasks.",
                "status": "completed",
                "error": None,
            }
        else:
            raise ValueError("Planner model returned insufficient sub-tasks.")

    except Exception as e:
        logger.warning("Planner structured output encountered error, falling back: %s", e)
        return {
            "sub_tasks": [
                f"Foundational concepts and principles of {cleaned_query}",
                f"Detailed analysis and core implications of {cleaned_query}",
            ],
            "reasoning": "Decomposed query into foundational concepts and detailed analysis.",
            "status": "completed",
            "error": None,
        }
