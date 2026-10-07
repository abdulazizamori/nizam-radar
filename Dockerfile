# API container for Nebius Serverless Endpoint (or Render as fallback).
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY contracts/ contracts/
COPY api/ api/
COPY pipeline/ pipeline/

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
