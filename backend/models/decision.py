"""Pydantic models for decisions and observability traces."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Decision(str, Enum):
    APPROVED = "APPROVED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class TraceStepStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    DEGRADED = "DEGRADED"


class CheckResult(BaseModel):
    """A single check performed by an agent."""
    check_name: str
    passed: bool
    detail: str
    data: Optional[dict[str, Any]] = None


class TraceStep(BaseModel):
    """A single step in the processing trace."""
    agent_name: str
    status: TraceStepStatus
    duration_ms: int = 0
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    checks: list[CheckResult] = Field(default_factory=list)
    error: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


class AmountBreakdown(BaseModel):
    """Breakdown of how the approved amount was calculated."""
    claimed_amount: float
    eligible_amount: Optional[float] = None
    network_discount: Optional[float] = None
    amount_after_discount: Optional[float] = None
    copay_amount: Optional[float] = None
    sub_limit_cap: Optional[float] = None
    per_claim_cap: Optional[float] = None
    approved_amount: float
    line_item_details: Optional[list[dict[str, Any]]] = None


class DocumentError(BaseModel):
    """Specific document verification error."""
    error_type: str  # WRONG_DOCUMENT, UNREADABLE, PATIENT_MISMATCH
    message: str
    affected_documents: list[str] = Field(default_factory=list)
    required_action: str


class ClaimDecision(BaseModel):
    """The full decision output for a processed claim."""
    decision: Optional[Decision] = None
    approved_amount: Optional[float] = None
    rejection_reasons: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0
    amount_breakdown: Optional[AmountBreakdown] = None
    document_errors: list[DocumentError] = Field(default_factory=list)
    fraud_signals: list[str] = Field(default_factory=list)
    trace: list[TraceStep] = Field(default_factory=list)
    summary: str = ""
    recommendations: list[str] = Field(default_factory=list)
