FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY policy_terms.json .
COPY test_cases.json .

# Run FastAPI with uvicorn on Railway's PORT (default 8000)
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}
