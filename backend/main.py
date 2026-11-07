"""
main.py — FastAPI application entry point.

Start with:
    uvicorn backend.main:app --reload

API docs: http://localhost:8000/docs
"""

import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.core.config import settings
from backend.api.routes import router

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
## Multi-Agent Research & Document Assistant

Production-grade agentic AI pipeline featuring four specialised sequential agents:

| Agent | Responsibility | Output |
|---|---|---|
| **Planner** | Decomposes complex queries into 2–4 atomic sub-tasks | Validated Pydantic Plan |
| **Researcher** | RAG retrieval over FAISS vector store or foundational knowledge | Evidence-grounded answers |
| **Summarizer** | Synthesizes findings, preserving metrics & citations | Structured factual summary |
| **Report Generator** | Assembles formal 5-section Markdown research report | Publication-ready report |

**Document Ingestion:** PDF (.pdf), Word (.docx), Plain Text (.txt)
**Embeddings:** Google Gemini Embeddings (`models/gemini-embedding-001`)
**Vector Store:** FAISS (in-memory & persisted per session)
**LLM Fallback:** Google Gemini → OpenAI → Groq → DeepSeek
    """,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/api", tags=["Root"])
async def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/api/v1/health",
    }


# Mount static assets if build exists
frontend_dist = Path("frontend/dist")
assets_dir = frontend_dist / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


# SPA catch-all for serving frontend client routes
@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    # Don't intercept API or docs routes
    if full_path.startswith("api") or full_path.startswith("docs") or full_path.startswith("redoc") or full_path.startswith("openapi.json"):
        return {"message": "Resource not found"}

    target_file = frontend_dist / full_path
    if target_file.is_file():
        return FileResponse(str(target_file))

    index_path = frontend_dist / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))

    return {
        "message": "Frontend not built yet. Run 'npm run build' in the frontend directory.",
        "api_docs": "/docs",
        "health": "/api/v1/health",
    }
