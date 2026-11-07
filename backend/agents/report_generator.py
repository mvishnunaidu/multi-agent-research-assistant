"""
report_generator.py — Report Generator Agent (Agent 4)

Assembles the summarized research findings into a publication-grade Markdown report.
Enforces the strict five-part report structure:
1. # Research Report
2. ## Executive Summary
3. ## Findings
4. ## Key Takeaways
5. ## Sources
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from backend.core.llm import get_llm

logger = logging.getLogger(__name__)

REPORT_PROMPT = """You are an expert Technical Report Writer. Compose an authoritative, publication-quality research report based on the provided summary.

Research Query: {query}
Source Documents: {sources}
Date: {date}

Summary of Findings:
{summary}

Strict Report Structure Requirements:
You must format your response using EXACTLY these headings in this order:

# Research Report

## Executive Summary
(2 to 3 sentences delivering a direct, decisive answer to the user query)

## Findings
(Expand the summary into logically structured subheadings, delivering depth, technical metrics, and evidence without repetitive filler)

## Key Takeaways
(3 to 5 high-impact, actionable bullet points capturing the core insights)

## Sources
(List the exact source documents used, or write "General knowledge (no documents uploaded)" if no document sources were provided)

Formatting & Grounding Rules:
- Never invent citations, page numbers, author names, or statistics not present in the summary.
- Maintain a polished, professional engineering tone.
- Do NOT add intro or outro meta-commentary (e.g., "Here is your report")."""


def run_report_generator(
    query: str,
    summary: str,
    source_files: List[str],
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Agent 4 — Report Generator.
    Input:
        query: Original user question
        summary: Structured summary from Summarizer agent
        source_files: List of document filenames cited
        kwargs: Optional extra parameters (e.g., grounding)
    Output:
        {
            "report": str,
            "status": "completed" | "fallback" | "error",
            "error": Optional[str],
        }
    """
    grounding = kwargs.get("grounding", "document")
    cleaned_query = query.strip()
    cleaned_summary = summary.strip()

    if not cleaned_summary:
        cleaned_summary = "No summarized findings were available for report generation."

    date_str = datetime.now().strftime("%B %d, %Y")

    if source_files:
        sources_str = ", ".join(source_files)
    elif grounding == "document":
        sources_str = "Uploaded documents (no matching excerpts identified)"
    else:
        sources_str = "General knowledge (no documents uploaded)"

    try:
        llm = get_llm()
        prompt = REPORT_PROMPT.format(
            query=cleaned_query,
            sources=sources_str,
            date=date_str,
            summary=cleaned_summary,
        )

        response = llm.invoke(prompt)
        report_content = response.content.strip() if hasattr(response, "content") else str(response)

        # Enforce structure check
        if "# Research Report" not in report_content:
            report_content = f"# Research Report\n\n{report_content}"

        return {
            "report": report_content,
            "status": "completed",
            "error": None,
        }

    except Exception as e:
        logger.warning("Report Generator LLM invocation failed, using structured template fallback: %s", e)
        # Deterministic structured fallback adhering strictly to the 5-section format
        fallback_report = f"""# Research Report

## Executive Summary
This report summarizes findings regarding "{cleaned_query}". Detailed synthesis was completed via fallback formatting.

## Findings
{cleaned_summary}

## Key Takeaways
- Direct synthesis of available research findings for query: {cleaned_query}
- Primary findings preserved from intermediate agent stages.
- Generated via reliable fallback handler due to model invocation notice.

## Sources
{sources_str}
"""
        return {
            "report": fallback_report.strip(),
            "status": "fallback",
            "error": f"Report Generator notice: {str(e)}",
        }
