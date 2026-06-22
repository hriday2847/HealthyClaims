FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY policy_terms.json .
COPY test_cases.json .
COPY .env .

# Expose port
EXPOSE 8000

# Run FastAPI with uvicorn
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
