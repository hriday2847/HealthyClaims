# Plum Claims (CLAMS)

AI-powered health insurance claims processing system.

## Architecture

This project is built using a multi-agent pipeline orchestrated in Python (FastAPI), with a Next.js frontend dashboard.

- **Backend (`/backend`)**: FastAPI, Pydantic, pytest. The processing pipeline is composed of isolated, specialized agents (Document Verifier, Document Extractor, Policy Engine, Fraud Detector, Decision Engine) orchestrated by a central `PipelineOrchestrator`. Data persistence uses a thread-safe JSON-based storage service, avoiding heavy database dependencies.
- **Frontend (`/frontend`)**: Next.js 14, React, custom CSS Design System. Provides a rich UI for claim submission, a dashboard for review, an execution trace viewer, and an evaluation report runner.

## Core Features

- **Multi-Agent Pipeline**: Evaluates policies, standardizes financial calculations (discounts before co-pay), and handles complex document combinations.
- **Resilience (Graceful Degradation)**: The pipeline catches component failures (e.g., in the Fraud Detector) and degrades to a MANUAL_REVIEW state without crashing the system (tested via TC011).
- **Execution Tracing**: Every agent's inputs, outputs, checks, and processing time are captured and presented in a detailed timeline in the UI.
- **Eval Suite**: Included 12-test-case evaluation runner built into the app to continuously verify system correctness.

## Running Locally

### Backend
1. From the `CLAMS` root directory, install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
2. Edit `.env` in the root directory to add `OPENAI_API_KEY` (if using LLM extraction)
3. Run the FastAPI server from the `CLAMS` root directory:
   ```bash
   uvicorn backend.main:app --reload
   ```
   The API will be available at `http://localhost:8000`.

### Frontend
1. `cd frontend`
2. `npm install`
3. `npm run dev`
   The UI will be available at `http://localhost:3000`.

## Testing

Run `pytest backend/tests/test_pipeline.py` from the root directory to execute the assignment evaluation test cases.

## Deployment

The application is configured to deploy via Render using the included `render.yaml` blueprint. The backend is deployed as a Docker service using `Dockerfile`, while the frontend is deployed as a Node service.

**Note**: Ensure `OPENAI_API_KEY` is added to the environment variables in the Render dashboard for the backend service.
