"""
pipeline.py — Multi-Agent Pipeline Orchestrator

Sequential 4-agent execution flow:
    run_planner()          (Agent 1: Query decomposition into 2–4 sub-tasks)
         ↓
    run_researcher()       (Agent 2: RAG retrieval over FAISS or general knowledge)
         ↓
    run_summarizer()       (Agent 3: Factual evidence synthesis)
         ↓
    run_report_generator() (Agent 4: Publication-ready Markdown report assembly)
         ↓
    PipelineResult         (Complete execution audit trace & results)

Each step records genuine status ("completed" | "fallback" | "error" | "skipped"),
precise timing durations, and isolates failures so downstream agents operate safely.
"""

import time
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

from backend.agents.planner import run_planner
from backend.agents.researcher import run_researcher
from backend.agents.summarizer import run_summarizer
from backend.agents.report_generator import run_report_generator

logger = logging.getLogger(__name__)


@dataclass
class AgentStep:
    """Audit record for a single agent's execution."""
    agent: str
    status: str              # "pending" | "running" | "completed" | "fallback" | "error" | "skipped"
    output_preview: str = ""
    duration_seconds: float = 0.0
    error: Optional[str] = None


@dataclass
class PipelineResult:
    """Final output returned to the API layer with full audit metadata."""
    session_id: str
    query: str
    plan: List[str]
    plan_reasoning: str
    retrieved_chunks: List[str]
    source_files: List[str]
    summary: str
    final_report: str
    agent_steps: List[AgentStep]
    chat_history: List[Dict[str, Any]]
    overall_status: str       # "completed" | "fallback" | "error"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


def run_pipeline(
    session_id: str,
    query: str,
    has_documents: bool,
    chat_history: List[Dict[str, Any]],
) -> PipelineResult:
    """
    Run the full 4-agent research pipeline sequentially.

    Args:
        session_id:     Session identifier (used for FAISS vector store lookup)
        query:          User's research question
        has_documents:  Whether documents have been ingested for this session
        chat_history:   Prior conversation turns for conversation memory

    Returns:
        PipelineResult with all intermediate artifacts and execution metrics
    """
    steps: List[AgentStep] = []
    clean_query = query.strip()
    has_any_error = False
    has_any_fallback = False

    # ── Step 1: Planner ────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    try:
        planner_out = run_planner(query=clean_query, has_documents=has_documents)
        planner_dur = round(time.perf_counter() - t0, 3)

        raw_tasks = planner_out.get("sub_tasks") or []
        sub_tasks = [t for t in raw_tasks if isinstance(t, str) and t.strip()]
        if not sub_tasks:
            sub_tasks = [clean_query]

        planner_status = planner_out.get("status", "completed")
        planner_error = planner_out.get("error")

        if planner_error or planner_status == "fallback":
            planner_status = "fallback"
            has_any_fallback = True

        reasoning = planner_out.get("reasoning", "")
        preview = f"{len(sub_tasks)} sub-tasks: " + (reasoning or ", ".join(sub_tasks[:2]))

        steps.append(
            AgentStep(
                agent="Planner",
                status=planner_status,
                output_preview=preview[:200],
                duration_seconds=planner_dur,
                error=planner_error,
            )
        )
    except Exception as e:
        planner_dur = round(time.perf_counter() - t0, 3)
        sub_tasks = [clean_query]
        planner_out = {"sub_tasks": sub_tasks, "reasoning": "Planner failure fallback."}
        has_any_error = True
        logger.exception("Planner step crashed: %s", e)
        steps.append(
            AgentStep(
                agent="Planner",
                status="error",
                output_preview="Error during planning. Falling back to original query.",
                duration_seconds=planner_dur,
                error=str(e),
            )
        )

    # ── Step 2: Researcher ─────────────────────────────────────────────────────
    t0 = time.perf_counter()
    try:
        researcher_out = run_researcher(
            sub_tasks=sub_tasks,
            session_id=session_id,
            has_documents=has_documents,
        )
        researcher_dur = round(time.perf_counter() - t0, 3)

        answers = researcher_out.get("answers", [])
        retrieved_chunks = researcher_out.get("retrieved_chunks", [])
        source_files = researcher_out.get("source_files", [])
        grounding = researcher_out.get("grounding", "general_knowledge")
        res_status = researcher_out.get("status", "completed")
        res_error = researcher_out.get("error")

        if res_status == "error":
            has_any_error = True
        elif res_status == "fallback" or res_error:
            has_any_fallback = True

        if grounding == "document" and retrieved_chunks:
            preview = f"Retrieved {len(retrieved_chunks)} chunks from {len(source_files)} source(s)."
        elif has_documents and not retrieved_chunks:
            preview = "No matching document excerpts found; research used general knowledge."
        else:
            preview = f"Generated research findings for {len(answers)} sub-task(s) via general knowledge."

        steps.append(
            AgentStep(
                agent="Researcher",
                status=res_status,
                output_preview=preview[:200],
                duration_seconds=researcher_dur,
                error=res_error,
            )
        )
    except Exception as e:
        researcher_dur = round(time.perf_counter() - t0, 3)
        answers = [f"Research could not be completed: {e}"]
        retrieved_chunks = []
        source_files = []
        grounding = "general_knowledge"
        has_any_error = True
        logger.exception("Researcher step crashed: %s", e)
        steps.append(
            AgentStep(
                agent="Researcher",
                status="error",
                output_preview="Researcher failed with exception.",
                duration_seconds=researcher_dur,
                error=str(e),
            )
        )

    # ── Step 3: Summarizer ─────────────────────────────────────────────────────
    t0 = time.perf_counter()
    try:
        summarizer_out = run_summarizer(query=clean_query, answers=answers)
        summarizer_dur = round(time.perf_counter() - t0, 3)

        summary = summarizer_out.get("summary", "")
        sum_status = summarizer_out.get("status", "completed")
        sum_error = summarizer_out.get("error")

        if sum_status == "error":
            has_any_error = True
        elif sum_status == "fallback" or sum_error:
            has_any_fallback = True

        steps.append(
            AgentStep(
                agent="Summarizer",
                status=sum_status,
                output_preview=summary[:180],
                duration_seconds=summarizer_dur,
                error=sum_error,
            )
        )
    except Exception as e:
        summarizer_dur = round(time.perf_counter() - t0, 3)
        summary = "\n\n".join(answers)
        has_any_error = True
        logger.exception("Summarizer step crashed: %s", e)
        steps.append(
            AgentStep(
                agent="Summarizer",
                status="error",
                output_preview="Summarizer failed; passing raw findings to report generator.",
                duration_seconds=summarizer_dur,
                error=str(e),
            )
        )

    # ── Step 4: Report Generator ───────────────────────────────────────────────
    t0 = time.perf_counter()
    try:
        try:
            report_out = run_report_generator(
                query=clean_query,
                summary=summary,
                source_files=source_files,
                grounding=grounding,
            )
        except TypeError as te:
            if "grounding" in str(te):
                report_out = run_report_generator(
                    query=clean_query,
                    summary=summary,
                    source_files=source_files,
                )
            else:
                raise
        report_dur = round(time.perf_counter() - t0, 3)

        final_report = report_out.get("report", summary)
        rep_status = report_out.get("status", "completed")
        rep_error = report_out.get("error")

        if rep_status == "error":
            has_any_error = True
        elif rep_status == "fallback" or rep_error:
            has_any_fallback = True

        steps.append(
            AgentStep(
                agent="Report Generator",
                status=rep_status,
                output_preview=final_report[:180],
                duration_seconds=report_dur,
                error=rep_error,
            )
        )
    except Exception as e:
        report_dur = round(time.perf_counter() - t0, 3)
        final_report = summary
        has_any_error = True
        logger.exception("Report Generator step crashed: %s", e)
        steps.append(
            AgentStep(
                agent="Report Generator",
                status="error",
                output_preview="Report generation failed; returning summary.",
                duration_seconds=report_dur,
                error=str(e),
            )
        )

    # ── Determine overall pipeline health ──────────────────────────────────────
    if has_any_error:
        overall_status = "completed" if final_report else "error"
    else:
        overall_status = "completed"

    # ── Append to conversation history ─────────────────────────────────────────
    updated_history = list(chat_history) + [
        {
            "role": "user",
            "content": clean_query,
            "timestamp": datetime.now().isoformat(),
        },
        {
            "role": "assistant",
            "content": final_report,
            "query": clean_query,
            "overall_status": overall_status,
            "sources": source_files,
            "timestamp": datetime.now().isoformat(),
        },
    ]

    return PipelineResult(
        session_id=session_id,
        query=clean_query,
        plan=sub_tasks,
        plan_reasoning=planner_out.get("reasoning", ""),
        retrieved_chunks=retrieved_chunks,
        source_files=source_files,
        summary=summary,
        final_report=final_report,
        agent_steps=steps,
        chat_history=updated_history,
        overall_status=overall_status,
    )
