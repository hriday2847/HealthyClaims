"""Tests for the full pipeline — runs all 12 test cases."""

import json
import sys
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.models.claim import ClaimDocument, ClaimHistoryEntry, ClaimSubmission
from backend.pipeline.orchestrator import PipelineOrchestrator


@pytest.fixture(scope="module")
def pipeline():
    policy_path = str(Path(__file__).resolve().parent.parent.parent / "policy_terms.json")
    return PipelineOrchestrator(policy_path=policy_path)


@pytest.fixture(scope="module")
def test_cases():
    tc_path = Path(__file__).resolve().parent.parent.parent / "test_cases.json"
    with open(tc_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["test_cases"]


def _make_submission(tc_input: dict) -> ClaimSubmission:
    docs = []
    for d in tc_input.get("documents", []):
        docs.append(ClaimDocument(
            file_id=d.get("file_id", ""),
            file_name=d.get("file_name"),
            actual_type=d["actual_type"],
            content=d.get("content"),
            quality=d.get("quality", "GOOD"),
            patient_name_on_doc=d.get("patient_name_on_doc"),
        ))
    history = [ClaimHistoryEntry(**h) for h in tc_input.get("claims_history", [])]
    return ClaimSubmission(
        member_id=tc_input["member_id"],
        policy_id=tc_input.get("policy_id", "PLUM_GHI_2024"),
        claim_category=tc_input["claim_category"],
        treatment_date=tc_input["treatment_date"],
        claimed_amount=tc_input["claimed_amount"],
        hospital_name=tc_input.get("hospital_name"),
        ytd_claims_amount=tc_input.get("ytd_claims_amount", 0),
        documents=docs,
        claims_history=history,
        simulate_component_failure=tc_input.get("simulate_component_failure", False),
    )


class TestTC001WrongDocument:
    def test_stops_before_decision(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC001")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert result.decision is None
        assert len(result.document_errors) > 0

    def test_specific_error_message(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC001")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        msg = result.document_errors[0].message.lower()
        assert "hospital_bill" in msg or "hospital bill" in msg
        assert "prescription" in msg


class TestTC002UnreadableDocument:
    def test_identifies_unreadable(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC002")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert result.decision is None
        assert any(e.error_type == "UNREADABLE" for e in result.document_errors)

    def test_asks_reupload(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC002")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        msg = result.document_errors[0].message.lower()
        assert "re-upload" in msg or "reupload" in msg


class TestTC003PatientMismatch:
    def test_detects_mismatch(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC003")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert result.decision is None
        assert any(e.error_type == "PATIENT_MISMATCH" for e in result.document_errors)

    def test_surfaces_names(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC003")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        msg = result.document_errors[0].message
        assert "Rajesh Kumar" in msg
        assert "Arjun Mehta" in msg


class TestTC004CleanApproval:
    def test_approved(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC004")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert result.decision is not None
        assert result.decision.value == "APPROVED"

    def test_amount(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC004")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert result.approved_amount == 1350

    def test_confidence(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC004")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert result.confidence_score > 0.85


class TestTC005WaitingPeriod:
    def test_rejected(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC005")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert result.decision is not None
        assert result.decision.value == "REJECTED"
        assert "WAITING_PERIOD" in result.rejection_reasons


class TestTC006DentalPartial:
    def test_partial(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC006")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert result.decision is not None
        assert result.decision.value == "PARTIAL"

    def test_amount(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC006")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert result.approved_amount == 8000


class TestTC007PreAuth:
    def test_rejected(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC007")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert result.decision is not None
        assert result.decision.value == "REJECTED"
        assert "PRE_AUTH_MISSING" in result.rejection_reasons


class TestTC008PerClaimLimit:
    def test_rejected(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC008")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert result.decision is not None
        assert result.decision.value == "REJECTED"
        assert "PER_CLAIM_EXCEEDED" in result.rejection_reasons


class TestTC009Fraud:
    def test_manual_review(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC009")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert result.decision is not None
        assert result.decision.value == "MANUAL_REVIEW"

    def test_fraud_signals(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC009")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert len(result.fraud_signals) > 0


class TestTC010NetworkDiscount:
    def test_approved(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC010")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert result.decision is not None
        assert result.decision.value == "APPROVED"

    def test_amount(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC010")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert result.approved_amount == 3240


class TestTC011GracefulDegradation:
    def test_does_not_crash(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC011")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert result is not None
        assert result.decision is not None

    def test_reduced_confidence(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC011")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        # Confidence should be lower than a normal approval
        assert result.confidence_score < 0.85


class TestTC012ExcludedTreatment:
    def test_rejected(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC012")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert result.decision is not None
        assert result.decision.value == "REJECTED"
        assert "EXCLUDED_CONDITION" in result.rejection_reasons

    def test_confidence(self, pipeline, test_cases):
        tc = next(t for t in test_cases if t["case_id"] == "TC012")
        sub = _make_submission(tc["input"])
        result = pipeline.process_claim(sub)
        assert result.confidence_score > 0.90
