"""
report_generator.py — Report Generator Agent
Assembles the summary into a polished final report with citations.
"""
from datetime import datetime
from backend.core.llm import get_llm

REPORT_PROMPT = """You are a Report Generator. Compose a well-structured research report from the summary below.

Original Query: {query}
Sources: {sources}
Date: {date}

Summary:
{summary}

Write the report in this exact format:

# Research Report

## Executive Summary
(2–3 sentences capturing the core answer)

## Findings
(Expand the summary into coherent sections with subheadings if needed)

## Key Takeaways
(3–5 bullet points)

## Sources
(List the document sources, or "General knowledge" if no documents were used)

Write in professional, report-style English. Be specific. Avoid filler phrases."""


def run_report_generator(query: str, summary: str, source_files: list[str]) -> dict:
    """
    Agent 4 — Report Generator.
    Input:  original query, summary from summarizer, list of source filenames
    Output: {"report": "..."}
    """
    llm = get_llm()

    sources_str = ", ".join(source_files) if source_files else "General knowledge (no documents uploaded)"

    prompt = REPORT_PROMPT.format(
        query=query,
        sources=sources_str,
        date=datetime.now().strftime("%B %d, %Y"),
        summary=summary,
    )

    response = llm.invoke(prompt)
    return {"report": response.content.strip()}
