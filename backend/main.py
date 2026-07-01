"""
main.py — FastAPI application entry point.

Start with:
    uvicorn backend.main:app --reload

API docs: http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from backend.core.config import settings
from backend.api.routes import router

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
## Multi-Agent Research & Document Assistant

Agentic AI pipeline built from scratch with four specialised agents:

| Agent | Responsibility |
|---|---|
| **Planner** | Decomposes query into 2–4 focused sub-tasks |
| **Researcher** | RAG retrieval over uploaded documents (FAISS) |
| **Summarizer** | Condenses findings into structured summaries |
| **Report Generator** | Assembles final report with citations |

**Supported files:** PDF · DOCX · TXT
**LLM backend:** Google Gemini (set via `.env`)
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

# Mount static assets
if os.path.exists("frontend/dist/assets"):
    app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")
    
# Catch-all to serve React app
@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    index_path = "frontend/dist/index.html"
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Frontend not built yet. Run 'npm run build' in the frontend directory."}
