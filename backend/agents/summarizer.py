"""
summarizer.py — Summarizer Agent
Condenses raw research answers into a clean, structured summary.
"""
from backend.core.llm import get_llm

SUMMARIZER_PROMPT = """You are a Summarizer Agent. Condense the research findings below into a clear, structured summary.

Original Query: {query}

Research Findings:
{findings}

Instructions:
- Write in clear, professional prose.
- Use bullet points only for lists of facts or comparisons.
- Keep each sub-task answer under 200 words.
- Preserve specific numbers, names, and technical terms from the findings.
- Do NOT add information not present in the findings."""


def run_summarizer(query: str, answers: list[str]) -> dict:
    """
    Agent 3 — Summarizer.
    Input:  original query, list of raw answers from researcher
    Output: {"summary": "..."}
    """
    llm = get_llm()

    if not answers:
        return {"summary": "", "error": "No research findings to summarize."}

    findings_text = "\n\n".join(answers)
    prompt = SUMMARIZER_PROMPT.format(query=query, findings=findings_text)

    response = llm.invoke(prompt)
    return {"summary": response.content.strip(), "error": None}
