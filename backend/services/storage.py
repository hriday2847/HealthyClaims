"""In-memory claim storage with persistence to JSON.

Uses a simple in-memory dictionary backed by a JSON file for durability.
This avoids async SQLite complexity while remaining persistent across restarts.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from backend.config import BASE_DIR
from backend.models.claim import StoredClaim

STORAGE_FILE = BASE_DIR / "claims_store.json"

_lock = threading.Lock()
_claims: dict[str, StoredClaim] = {}
_loaded = False


def _ensure_loaded():
    """Lazy-load claims from disk on first access."""
    global _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        if STORAGE_FILE.exists():
            try:
                with open(STORAGE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for cid, cdata in data.items():
                    _claims[cid] = StoredClaim(**cdata)
            except Exception:
                pass  # Start fresh if file is corrupted
        _loaded = True


def _persist():
    """Write current claims to disk."""
    try:
        with open(STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {cid: c.model_dump() for cid, c in _claims.items()},
                f,
                indent=2,
                default=str,
            )
    except Exception:
        pass  # Non-critical — data is still in memory


def save_claim(claim: StoredClaim) -> StoredClaim:
    """Save a claim to the store."""
    _ensure_loaded()
    with _lock:
        _claims[claim.id] = claim
        _persist()
    return claim


def get_claim(claim_id: str) -> Optional[StoredClaim]:
    """Retrieve a claim by ID."""
    _ensure_loaded()
    return _claims.get(claim_id)


def get_all_claims() -> list[StoredClaim]:
    """Get all stored claims, newest first."""
    _ensure_loaded()
    return sorted(_claims.values(), key=lambda c: c.created_at, reverse=True)


def clear_claims():
    """Clear all stored claims (for testing)."""
    global _loaded
    with _lock:
        _claims.clear()
        _loaded = True
        _persist()
