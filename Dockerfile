FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (needed for standard tools and chroma/faiss if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose ports for both backend and frontend
EXPOSE 8000 8501
