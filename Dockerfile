# ── Build the React frontend ────────────────────────────────────────────────
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ── Backend runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim
WORKDIR /app

# System deps for building some Python packages (e.g. faiss-cpu wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

ENV UPLOAD_DIR=/app/uploads \
    VECTORSTORE_DIR=/app/vectorstores
RUN mkdir -p /app/uploads /app/vectorstores

EXPOSE 8000
CMD sh -c "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"
