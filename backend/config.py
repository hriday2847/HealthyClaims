"""Application configuration loaded from environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
POLICY_FILE = BASE_DIR / "policy_terms.json"
TEST_CASES_FILE = BASE_DIR / "test_cases.json"
DB_PATH = BASE_DIR / "claims.db"

# LLM Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# Feature flags
ENABLE_LLM_EXTRACTION = os.getenv("ENABLE_LLM_EXTRACTION", "false").lower() == "true"
