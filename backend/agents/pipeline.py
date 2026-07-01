"""
pipeline.py — Multi-Agent Pipeline Orchestrator

Pipeline flow:
    run_planner()
        ↓
    run_researcher()
        ↓
    run_summarizer()
        ↓
    run_report_generator()
        ↓
    PipelineResult (dataclass)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from backend.agents.planner import run_planner
from backend.agents.researcher import run_researcher
from backend.agents.summarizer import run_summarizer
from backend.agents.report_generator import run_report_generator


@dataclass
class AgentStep:
    """Audit record for one agent's execution."""
    agent: str
    status: str          # "completed" | "error"
    output_preview: str = ""
    error: Optional[str] = None


@dataclass
class PipelineResult:
    """Final output returned to the API layer."""
    session_id: str
    query: str
    plan: List[str]
    plan_reasoning: str
    retrieved_chunks: List[str]
    source_files: List[str]
    summary: str
    final_report: str
    agent_steps: List[AgentStep]
    chat_history: List[Dict]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


def run_pipeline(
    session_id: str,
    query: str,
    has_documents: bool,
    chat_history: List[Dict],
) -> PipelineResult:
    """
    Run the full 4-agent research pipeline.

    Args:
        session_id:     Unique session identifier (used to load FAISS store)
        query:          User's research question
        has_documents:  Whether documents have been uploaded for this session
        chat_history:   Prior conversation turns for this session

    Returns:
        PipelineResult with all intermediate and final outputs
    """
    steps: List[AgentStep] = []

    # ── Step 1: Planner ────────────────────────────────────────────────────────
    try:
        planner_out = run_planner(query=query, has_documents=has_documents)
        sub_tasks   = planner_out.get("sub_tasks") or [query]
        steps.append(
            AgentStep(
                agent="Planner",
                status="completed",
                output_preview=planner_out.get("reasoning", "")[:150],
                error=planner_out.get("error"),
            )
        )
    except Exception as e:
        sub_tasks   = [query]
        planner_out = {"sub_tasks": sub_tasks, "reasoning": "Error fallback."}
        steps.append(AgentStep(agent="Planner", status="error", error=str(e)))

    # ── Step 2: Researcher ─────────────────────────────────────────────────────
    try:
        researcher_out = run_researcher(
            sub_tasks=sub_tasks,
            session_id=session_id,
            has_documents=has_documents,
        )
        answers          = researcher_out.get("answers", [])
        retrieved_chunks = researcher_out.get("retrieved_chunks", [])
        source_files     = researcher_out.get("source_files", [])
        steps.append(
            AgentStep(
                agent="Researcher",
                status="completed",
                output_preview=(
                    f"Retrieved {len(retrieved_chunks)} chunks "
                    f"from {len(source_files)} source(s)."
                ),
            )
        )
    except Exception as e:
        answers          = [f"Research failed: {e}"]
        retrieved_chunks = []
        source_files     = []
        steps.append(AgentStep(agent="Researcher", status="error", error=str(e)))

    # ── Step 3: Summarizer ─────────────────────────────────────────────────────
    try:
        summarizer_out = run_summarizer(query=query, answers=answers)
        summary        = summarizer_out.get("summary", "")
        steps.append(
            AgentStep(
                agent="Summarizer",
                status="completed",
                output_preview=summary[:150],
            )
        )
    except Exception as e:
        summary = "\n\n".join(answers)   # fallback: raw answers
        steps.append(AgentStep(agent="Summarizer", status="error", error=str(e)))

    # ── Step 4: Report Generator ───────────────────────────────────────────────
    try:
        report_out   = run_report_generator(
            query=query,
            summary=summary,
            source_files=source_files,
        )
        final_report = report_out.get("report", summary)
        steps.append(
            AgentStep(
                agent="Report Generator",
                status="completed",
                output_preview=final_report[:150],
            )
        )
    except Exception as e:
        final_report = summary   # fallback: return summary as report
        steps.append(AgentStep(agent="Report Generator", status="error", error=str(e)))

    # ── Append to conversation memory ──────────────────────────────────────────
    updated_history = list(chat_history) + [
        {
            "role":      "assistant",
            "content":   final_report,
            "query":     query,
            "timestamp": datetime.now().isoformat(),
        }
    ]

    return PipelineResult(
        session_id=session_id,
        query=query,
        plan=sub_tasks,
        plan_reasoning=planner_out.get("reasoning", ""),
        retrieved_chunks=retrieved_chunks,
        source_files=source_files,
        summary=summary,
        final_report=final_report,
        agent_steps=steps,
        chat_history=updated_history,
    )
