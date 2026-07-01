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
            "error": None,
        },
    )
    monkeypatch.setattr(
        pipeline_mod, "run_researcher",
        lambda sub_tasks, session_id, has_documents: {
            "answers": ["answer 1", "answer 2"],
            "retrieved_chunks": ["chunk a", "chunk b"],
            "source_files": ["doc.pdf"],
        },
    )
    monkeypatch.setattr(
        pipeline_mod, "run_summarizer",
        lambda query, answers: {"summary": "a tidy summary", "error": None},
    )
    monkeypatch.setattr(
        pipeline_mod, "run_report_generator",
        lambda query, summary, source_files: {"report": "# Research Report\n..."},
    )

    result = pipeline_mod.run_pipeline(
        session_id="s1", query="What is X?", has_documents=True, chat_history=[]
    )

    assert result.plan == ["sub-task 1", "sub-task 2"]
    assert result.source_files == ["doc.pdf"]
    assert result.summary == "a tidy summary"
    assert result.final_report.startswith("# Research Report")
    assert [s.agent for s in result.agent_steps] == [
        "Planner", "Researcher", "Summarizer", "Report Generator",
    ]
    assert all(s.status == "completed" for s in result.agent_steps)
    # Pipeline appends the final report to chat history for the next turn
    assert result.chat_history[-1]["content"] == result.final_report


def test_pipeline_survives_researcher_failure(monkeypatch):
    """If one agent throws, the pipeline should still return a usable result
    instead of crashing the whole request."""
    monkeypatch.setattr(
        pipeline_mod, "run_planner",
        lambda query, has_documents: {"sub_tasks": [query], "reasoning": "", "error": None},
    )

    def boom(*args, **kwargs):
        raise RuntimeError("vector store unavailable")

    monkeypatch.setattr(pipeline_mod, "run_researcher", boom)
    monkeypatch.setattr(
        pipeline_mod, "run_summarizer",
        lambda query, answers: {"summary": "fallback summary", "error": None},
    )
    monkeypatch.setattr(
        pipeline_mod, "run_report_generator",
        lambda query, summary, source_files: {"report": summary},
    )

    result = pipeline_mod.run_pipeline(
        session_id="s1", query="test query", has_documents=False, chat_history=[]
    )

    researcher_step = next(s for s in result.agent_steps if s.agent == "Researcher")
    assert researcher_step.status == "error"
    assert "vector store unavailable" in researcher_step.error
    # Downstream agents still ran with whatever partial data was available
    assert result.final_report == "fallback summary"


def test_pipeline_empty_sub_tasks_falls_back_to_query(monkeypatch):
    monkeypatch.setattr(
        pipeline_mod, "run_planner",
        lambda query, has_documents: {"sub_tasks": [], "reasoning": "", "error": None},
    )
    monkeypatch.setattr(
        pipeline_mod, "run_researcher",
        lambda sub_tasks, session_id, has_documents: {
            "answers": [], "retrieved_chunks": [], "source_files": [],
        },
    )
    monkeypatch.setattr(
        pipeline_mod, "run_summarizer",
        lambda query, answers: {"summary": "", "error": "No research findings to summarize."},
    )
    monkeypatch.setattr(
        pipeline_mod, "run_report_generator",
        lambda query, summary, source_files: {"report": "No information found."},
    )

    result = pipeline_mod.run_pipeline(
        session_id="s1", query="orphan query", has_documents=False, chat_history=[]
    )

    # planner.run_pipeline falls back to [query] when sub_tasks is empty
    assert result.plan == ["orphan query"]
