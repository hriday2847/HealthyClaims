"""Policy terms loader — reads and parses the policy_terms.json file."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from backend.config import POLICY_FILE
from backend.models.policy import PolicyTerms, Member


@lru_cache(maxsize=1)
def load_policy(path: Optional[str] = None) -> PolicyTerms:
    """Load and parse the policy terms JSON file.

    Uses an LRU cache so the file is only read once per process lifetime.
    """
    file_path = Path(path) if path else POLICY_FILE
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return PolicyTerms(**data)


def get_member(policy: PolicyTerms, member_id: str) -> Optional[Member]:
    """Look up a member by ID from the policy roster."""
    for m in policy.members:
        if m.member_id == member_id:
            return m
    return None


def get_category_config(policy: PolicyTerms, category: str):
    """Get the OPD category configuration by claim category name."""
    # Map claim categories to policy config keys
    category_map = {
        "CONSULTATION": "consultation",
        "DIAGNOSTIC": "diagnostic",
        "PHARMACY": "pharmacy",
        "DENTAL": "dental",
        "VISION": "vision",
        "ALTERNATIVE_MEDICINE": "alternative_medicine",
    }
    key = category_map.get(category.upper())
    if key and key in policy.opd_categories:
        return policy.opd_categories[key]
    return None


def get_document_requirements(policy: PolicyTerms, category: str):
    """Get required and optional document types for a claim category."""
    return policy.document_requirements.get(category.upper())


def is_network_hospital(policy: PolicyTerms, hospital_name: str) -> bool:
    """Check if a hospital is in the network list (case-insensitive partial match)."""
    if not hospital_name:
        return False
    hospital_lower = hospital_name.lower()
    for nh in policy.network_hospitals:
        if nh.lower() in hospital_lower or hospital_lower in nh.lower():
            return True
    return False
