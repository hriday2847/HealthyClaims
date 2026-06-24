"""Pydantic models for claims."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ClaimCategory(str, Enum):
    CONSULTATION = "CONSULTATION"
    DIAGNOSTIC = "DIAGNOSTIC"
    PHARMACY = "PHARMACY"
    DENTAL = "DENTAL"
    VISION = "VISION"
    ALTERNATIVE_MEDICINE = "ALTERNATIVE_MEDICINE"


class ClaimStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DECIDED = "DECIDED"
    DOCUMENT_ERROR = "DOCUMENT_ERROR"
    ERROR = "ERROR"


class DocumentType(str, Enum):
    PRESCRIPTION = "PRESCRIPTION"
    HOSPITAL_BILL = "HOSPITAL_BILL"
    LAB_REPORT = "LAB_REPORT"
    PHARMACY_BILL = "PHARMACY_BILL"
    DIAGNOSTIC_REPORT = "DIAGNOSTIC_REPORT"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    DENTAL_REPORT = "DENTAL_REPORT"


class DocumentQuality(str, Enum):
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"
    UNREADABLE = "UNREADABLE"


class ClaimDocument(BaseModel):
    """A document attached to a claim submission."""
    file_id: str
    file_name: Optional[str] = None
    actual_type: str
    content: Optional[dict[str, Any]] = None
    file_data: Optional[str] = None  # Base64-encoded image/PDF for LLM extraction
    quality: Optional[str] = "GOOD"
    patient_name_on_doc: Optional[str] = None


class ClaimHistoryEntry(BaseModel):
    """A past claim from the member."""
    claim_id: str
    date: str
    amount: float
    provider: Optional[str] = None


class ClaimSubmission(BaseModel):
    """Input model for submitting a new claim."""
    member_id: str
    policy_id: str = "PLUM_GHI_2024"
    claim_category: ClaimCategory
    treatment_date: str
    claimed_amount: float
    hospital_name: Optional[str] = None
    ytd_claims_amount: Optional[float] = 0
    documents: list[ClaimDocument]
    claims_history: Optional[list[ClaimHistoryEntry]] = Field(default_factory=list)
    simulate_component_failure: Optional[bool] = False


class StoredClaim(BaseModel):
    """A claim as stored in the database."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8].upper())
    submission: ClaimSubmission
    status: ClaimStatus = ClaimStatus.PENDING
    result: Optional[dict[str, Any]] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    processing_time_ms: Optional[int] = None
