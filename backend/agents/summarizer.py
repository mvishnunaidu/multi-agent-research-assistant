"""
summarizer.py — Summarizer Agent (Agent 3)

Synthesizes raw research answers into a coherent, factually consistent summary.
Strictly preserves technical metrics, proper nouns, and document references
without introducing outside claims or unsupported information.
"""

import logging
from typing import List, Dict, Any, Optional
from backend.core.llm import get_llm

logger = logging.getLogger(__name__)

SUMMARIZER_PROMPT = """You are an expert Summarizer Agent. Synthesize the research findings below into a cohesive, structured summary addressing the original user research query.

Original Query: {query}

Research Findings:
{findings}

Strict Synthesis Guidelines:
1. Grounding: Rely strictly on the findings provided above. Do NOT introduce external data, statistics, or unsupported claims.
2. Structure: Group related insights logically with concise subheadings or bullet points where comparisons are helpful.
3. Specificity: Preserve exact numbers, dates, proper nouns, and citations from the findings.
4. Completeness: Address each sub-task's key finding concisely without repetitive boilerplate.
5. Tone: Objective, technical, and executive-ready prose."""


def run_summarizer(query: str, answers: List[str]) -> Dict[str, Any]:
    """
    Agent 3 — Summarizer.
    Input:
        query: Original research query
        answers: List of raw answer blocks from the Researcher agent
    Output:
        {
            "summary": str,
            "status": "completed" | "fallback" | "error",
            "error": Optional[str],
        }
    """
    if not answers:
        return {
            "summary": "No research findings were produced to summarize.",
            "status": "error",
            "error": "No research findings to summarize.",
        }

    findings_text = "\n\n".join(answers).strip()
    if not findings_text:
        return {
            "summary": "Research findings were empty.",
            "status": "error",
            "error": "Research findings contained only empty strings.",
        }

    try:
        llm = get_llm()
        prompt = SUMMARIZER_PROMPT.format(query=query.strip(), findings=findings_text)
        response = llm.invoke(prompt)
        content = response.content.strip() if hasattr(response, "content") else str(response)

        return {
            "summary": content,
            "status": "completed",
            "error": None,
        }

    except Exception as e:
        logger.warning("Summarizer LLM invocation failed, using raw findings fallback: %s", e)
        # Graceful fallback: concatenate raw findings cleanly
        fallback_summary = (
            f"**Synthesis Note:** Structured summary generation encountered an issue ({e}). "
            f"Raw research findings are presented below:\n\n{findings_text}"
        )
        return {
            "summary": fallback_summary,
            "status": "fallback",
            "error": f"Summarizer notice: {str(e)}",
        }
