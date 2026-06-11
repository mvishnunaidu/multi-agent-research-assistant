"""
main.py — FastAPI application entry point.

Start with:
    uvicorn backend.main:app --reload

API docs: http://localhost:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.api.routes import router

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
## Multi-Agent Research & Document Assistant

Agentic AI pipeline with four specialised LangGraph agents:

| Agent | Responsibility |
|---|---|
| **Planner** | Decomposes query into 2–4 focused sub-tasks |
| **Researcher** | RAG retrieval over uploaded documents (FAISS) |
| **Summarizer** | Condenses findings into structured summaries |
| **Report Generator** | Assembles final report with citations |

**Supported files:** PDF · DOCX · TXT  
**LLM backends:** Gemini · OpenAI · Groq (set via `.env`)
    """,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/api/v1/health",
    }
