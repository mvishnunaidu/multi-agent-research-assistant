"""
planner.py — Planner Agent
Breaks the user query into 2-4 focused sub-tasks.
Returns a plain Python dict — no framework magic.
"""
import json
from backend.core.llm import get_llm

PLANNER_PROMPT = """You are a Research Planner. Break the user's query into 2 to 4 focused sub-tasks that together produce a comprehensive answer.

User Query: {query}
Documents uploaded: {has_docs}

Rules:
- If documents are uploaded, include sub-tasks that reference them explicitly.
- Each sub-task must be atomic and independently answerable.
- Output ONLY valid JSON. No markdown fences, no explanation outside JSON.

Required output format:
{{
  "sub_tasks": ["sub-task 1", "sub-task 2", "sub-task 3"],
  "reasoning": "One sentence explaining your decomposition strategy."
}}"""


def run_planner(query: str, has_documents: bool) -> dict:
    """
    Agent 1 — Planner.
    Input:  user query string, bool flag for documents
    Output: {"sub_tasks": [...], "reasoning": "..."}
    """
    llm = get_llm()
    prompt = PLANNER_PROMPT.format(
        query=query,
        has_docs="Yes" if has_documents else "No",
    )

    try:
        response = llm.invoke(prompt)
        raw = response.content.strip()

        # Strip markdown fences if LLM wraps response anyway
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)
        return {
            "sub_tasks": parsed.get("sub_tasks", [query]),
            "reasoning": parsed.get("reasoning", ""),
            "error": None,
        }

    except Exception as e:
        # Graceful fallback — treat original query as single task
        return {
            "sub_tasks": [query],
            "reasoning": "Fallback to single-task mode.",
            "error": f"Planner warning: {str(e)}",
        }
