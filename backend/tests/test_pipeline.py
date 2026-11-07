"""
test_pipeline.py — Unit tests for the multi-agent orchestrator.

Each agent function is mocked so the pipeline can be exercised without any
API keys, network access, or the local embedding model. This verifies the
*orchestration logic* — ordering, data hand-off between agents, and
graceful degradation when a step fails — rather than the LLM output itself.
"""
from backend.agents import pipeline as pipeline_mod


def test_pipeline_happy_path(monkeypatch):
    monkeypatch.setattr(
        pipeline_mod, "run_planner",
        lambda query, has_documents: {
            "sub_tasks": ["sub-task 1", "sub-task 2"],
            "reasoning": "split by theme",
            "status": "completed",
            "error": None,
        },
    )
    monkeypatch.setattr(
        pipeline_mod, "run_researcher",
        lambda sub_tasks, session_id, has_documents: {
            "answers": ["answer 1", "answer 2"],
            "retrieved_chunks": ["chunk a", "chunk b"],
            "source_files": ["doc.pdf"],
            "grounding": "document",
            "status": "completed",
            "error": None,
        },
    )
    monkeypatch.setattr(
        pipeline_mod, "run_summarizer",
        lambda query, answers: {
            "summary": "a tidy summary",
            "status": "completed",
            "error": None,
        },
    )
    monkeypatch.setattr(
        pipeline_mod, "run_report_generator",
        lambda query, summary, source_files, **kwargs: {
            "report": "# Research Report\n\n## Findings\nReport content",
            "status": "completed",
            "error": None,
        },
    )

    result = pipeline_mod.run_pipeline(
        session_id="s1", query="What is X?", has_documents=True, chat_history=[]
    )

    assert result.plan == ["sub-task 1", "sub-task 2"]
    assert result.source_files == ["doc.pdf"]
    assert result.summary == "a tidy summary"
    assert result.final_report.startswith("# Research Report")
    assert result.overall_status == "completed"
    assert [s.agent for s in result.agent_steps] == [
        "Planner", "Researcher", "Summarizer", "Report Generator",
    ]
    assert all(s.status == "completed" for s in result.agent_steps)
    assert all(isinstance(s.duration_seconds, float) and s.duration_seconds >= 0.0 for s in result.agent_steps)
    # Pipeline appends the final report to chat history for the next turn
    assert result.chat_history[-1]["content"] == result.final_report


def test_pipeline_survives_researcher_failure(monkeypatch):
    """If one agent throws, the pipeline should still return a usable result
    instead of crashing the whole request."""
    monkeypatch.setattr(
        pipeline_mod, "run_planner",
        lambda query, has_documents: {
            "sub_tasks": [query],
            "reasoning": "",
            "status": "completed",
            "error": None,
        },
    )

    def boom(*args, **kwargs):
        raise RuntimeError("vector store unavailable")

    monkeypatch.setattr(pipeline_mod, "run_researcher", boom)
    monkeypatch.setattr(
        pipeline_mod, "run_summarizer",
        lambda query, answers: {
            "summary": "fallback summary",
            "status": "completed",
            "error": None,
        },
    )
    monkeypatch.setattr(
        pipeline_mod, "run_report_generator",
        lambda query, summary, source_files, **kwargs: {
            "report": summary,
            "status": "completed",
            "error": None,
        },
    )

    result = pipeline_mod.run_pipeline(
        session_id="s1", query="test query", has_documents=False, chat_history=[]
    )

    researcher_step = next(s for s in result.agent_steps if s.agent == "Researcher")
    assert researcher_step.status == "error"
    assert "vector store unavailable" in researcher_step.error
    assert result.overall_status == "fallback"
    assert result.final_report == "fallback summary"


def test_pipeline_empty_sub_tasks_falls_back_to_query(monkeypatch):
    monkeypatch.setattr(
        pipeline_mod, "run_planner",
        lambda query, has_documents: {
            "sub_tasks": [],
            "reasoning": "",
            "status": "fallback",
            "error": "Model gave 0 subtasks",
        },
    )
    monkeypatch.setattr(
        pipeline_mod, "run_researcher",
        lambda sub_tasks, session_id, has_documents: {
            "answers": [],
            "retrieved_chunks": [],
            "source_files": [],
            "grounding": "general_knowledge",
            "status": "fallback",
            "error": None,
        },
    )
    monkeypatch.setattr(
        pipeline_mod, "run_summarizer",
        lambda query, answers: {
            "summary": "",
            "status": "error",
            "error": "No research findings to summarize.",
        },
    )
    monkeypatch.setattr(
        pipeline_mod, "run_report_generator",
        lambda query, summary, source_files, **kwargs: {
            "report": "No information found.",
            "status": "fallback",
            "error": None,
        },
    )

    result = pipeline_mod.run_pipeline(
        session_id="s1", query="orphan query", has_documents=False, chat_history=[]
    )

    # planner.run_pipeline falls back to [query] when sub_tasks is empty
    assert result.plan == ["orphan query"]
    planner_step = next(s for s in result.agent_steps if s.agent == "Planner")
    assert planner_step.status == "fallback"


def test_pipeline_correctly_reports_planner_warning(monkeypatch):
    """Verifies that if Planner returns an error/warning dict, status is fallback, not falsely completed."""
    monkeypatch.setattr(
        pipeline_mod, "run_planner",
        lambda query, has_documents: {
            "sub_tasks": [query],
            "reasoning": "Fallback mode.",
            "status": "fallback",
            "error": "Rate limit on structured outputs.",
        },
    )
    monkeypatch.setattr(
        pipeline_mod, "run_researcher",
        lambda sub_tasks, session_id, has_documents: {
            "answers": ["Answer to primary query"],
            "retrieved_chunks": [],
            "source_files": [],
            "status": "completed",
            "error": None,
        },
    )
    monkeypatch.setattr(
        pipeline_mod, "run_summarizer",
        lambda query, answers: {"summary": "Direct summary", "status": "completed", "error": None},
    )
    monkeypatch.setattr(
        pipeline_mod, "run_report_generator",
        lambda query, summary, source_files, **kwargs: {
            "report": "# Research Report\n\nDirect report",
            "status": "completed",
            "error": None,
        },
    )

    result = pipeline_mod.run_pipeline(
        session_id="s1", query="Direct question", has_documents=False, chat_history=[]
    )

    planner_step = next(s for s in result.agent_steps if s.agent == "Planner")
    assert planner_step.status == "fallback"
    assert "Rate limit" in planner_step.error
    assert result.overall_status == "fallback"


def test_pipeline_step_durations_measured(monkeypatch):
    """Ensures each agent step records a valid non-negative float duration in seconds."""
    monkeypatch.setattr(
        pipeline_mod, "run_planner",
        lambda query, has_documents: {"sub_tasks": ["t1", "t2"], "reasoning": "ok", "status": "completed", "error": None},
    )
    monkeypatch.setattr(
        pipeline_mod, "run_researcher",
        lambda sub_tasks, session_id, has_documents: {"answers": ["a1"], "retrieved_chunks": [], "source_files": [], "status": "completed", "error": None},
    )
    monkeypatch.setattr(
        pipeline_mod, "run_summarizer",
        lambda query, answers: {"summary": "summary text", "status": "completed", "error": None},
    )
    monkeypatch.setattr(
        pipeline_mod, "run_report_generator",
        lambda query, summary, source_files, **kwargs: {"report": "# Research Report", "status": "completed", "error": None},
    )

    result = pipeline_mod.run_pipeline(
        session_id="s1", query="Measure timing", has_documents=False, chat_history=[]
    )

    for step in result.agent_steps:
        assert isinstance(step.duration_seconds, float)
        assert step.duration_seconds >= 0.0
