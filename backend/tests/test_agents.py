"""Unit tests for individual pipeline agents.

Tests each agent in isolation to verify its core logic independently
of the full pipeline orchestrator.
"""

import sys
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.agents.base import AgentResult
from backend.agents.decision_engine import DecisionEngineAgent
from backend.agents.document_extractor import DocumentExtractorAgent
from backend.agents.document_verifier import DocumentVerifierAgent
from backend.agents.fraud_detector import FraudDetectorAgent
from backend.agents.policy_engine import PolicyEngineAgent
from backend.models.claim import ClaimDocument, ClaimHistoryEntry, ClaimSubmission
from backend.services.policy_loader import load_policy


@pytest.fixture(scope="module")
def policy():
    policy_path = str(Path(__file__).resolve().parent.parent.parent / "policy_terms.json")
    return load_policy(policy_path)


def _ctx(submission, policy, **extras):
    """Build a context dict for agent execution."""
    ctx = {"submission": submission, "policy": policy}
    ctx.update(extras)
    return ctx


# ─── DocumentVerifierAgent ────────────────────────────────────────


class TestDocumentVerifier:
    agent = DocumentVerifierAgent()

    def test_all_valid_documents_pass(self, policy):
        sub = ClaimSubmission(
            member_id="EMP001",
            claim_category="CONSULTATION",
            treatment_date="2024-11-01",
            claimed_amount=1500,
            documents=[
                ClaimDocument(file_id="A", actual_type="PRESCRIPTION"),
                ClaimDocument(file_id="B", actual_type="HOSPITAL_BILL"),
            ],
        )
        result, trace = self.agent.run(_ctx(sub, policy))
        assert result.success is True
        assert trace.status.value == "SUCCESS"

    def test_missing_required_document_fails(self, policy):
        sub = ClaimSubmission(
            member_id="EMP001",
            claim_category="CONSULTATION",
            treatment_date="2024-11-01",
            claimed_amount=1500,
            documents=[
                ClaimDocument(file_id="A", actual_type="PRESCRIPTION"),
                # Missing HOSPITAL_BILL
            ],
        )
        result, trace = self.agent.run(_ctx(sub, policy))
        assert result.success is False
        assert any("HOSPITAL_BILL" in e.get("message", "") for e in result.data.get("document_errors", []))

    def test_unreadable_document_fails(self, policy):
        sub = ClaimSubmission(
            member_id="EMP004",
            claim_category="PHARMACY",
            treatment_date="2024-10-25",
            claimed_amount=800,
            documents=[
                ClaimDocument(file_id="A", actual_type="PRESCRIPTION", quality="GOOD"),
                ClaimDocument(file_id="B", actual_type="PHARMACY_BILL", quality="UNREADABLE"),
            ],
        )
        result, trace = self.agent.run(_ctx(sub, policy))
        assert result.success is False
        errors = result.data.get("document_errors", [])
        assert any(e["error_type"] == "UNREADABLE" for e in errors)

    def test_patient_name_mismatch_fails(self, policy):
        sub = ClaimSubmission(
            member_id="EMP001",
            claim_category="CONSULTATION",
            treatment_date="2024-11-01",
            claimed_amount=1500,
            documents=[
                ClaimDocument(
                    file_id="A",
                    actual_type="PRESCRIPTION",
                    patient_name_on_doc="Alice Smith",
                ),
                ClaimDocument(
                    file_id="B",
                    actual_type="HOSPITAL_BILL",
                    patient_name_on_doc="Bob Jones",
                ),
            ],
        )
        result, trace = self.agent.run(_ctx(sub, policy))
        assert result.success is False
        errors = result.data.get("document_errors", [])
        assert any(e["error_type"] == "PATIENT_MISMATCH" for e in errors)

    def test_consistent_patient_names_pass(self, policy):
        sub = ClaimSubmission(
            member_id="EMP001",
            claim_category="CONSULTATION",
            treatment_date="2024-11-01",
            claimed_amount=1500,
            documents=[
                ClaimDocument(
                    file_id="A",
                    actual_type="PRESCRIPTION",
                    patient_name_on_doc="Rajesh Kumar",
                ),
                ClaimDocument(
                    file_id="B",
                    actual_type="HOSPITAL_BILL",
                    patient_name_on_doc="Rajesh Kumar",
                ),
            ],
        )
        result, trace = self.agent.run(_ctx(sub, policy))
        assert result.success is True


# ─── DocumentExtractorAgent ───────────────────────────────────────


class TestDocumentExtractor:
    agent = DocumentExtractorAgent()

    def test_extracts_structured_content(self, policy):
        sub = ClaimSubmission(
            member_id="EMP001",
            claim_category="CONSULTATION",
            treatment_date="2024-11-01",
            claimed_amount=1500,
            documents=[
                ClaimDocument(
                    file_id="D1",
                    actual_type="PRESCRIPTION",
                    content={
                        "patient_name": "Rajesh Kumar",
                        "doctor_name": "Dr. Sharma",
                        "diagnosis": "Viral Fever",
                    },
                ),
            ],
        )
        result, trace = self.agent.run(_ctx(sub, policy))
        assert result.success is True
        extracted = result.data["extracted"]
        assert extracted["patient_name"] == "Rajesh Kumar"
        assert extracted["diagnosis"] == "Viral Fever"

    def test_handles_empty_content(self, policy):
        sub = ClaimSubmission(
            member_id="EMP001",
            claim_category="CONSULTATION",
            treatment_date="2024-11-01",
            claimed_amount=1500,
            documents=[
                ClaimDocument(file_id="D1", actual_type="PRESCRIPTION"),
            ],
        )
        result, trace = self.agent.run(_ctx(sub, policy))
        assert result.success is True
        assert len(result.warnings) > 0
        # Confidence should be reduced
        assert result.data["extracted"]["extraction_confidence"] < 1.0

    def test_falls_back_to_claimed_amount(self, policy):
        sub = ClaimSubmission(
            member_id="EMP001",
            claim_category="CONSULTATION",
            treatment_date="2024-11-01",
            claimed_amount=2500,
            documents=[
                ClaimDocument(
                    file_id="D1",
                    actual_type="PRESCRIPTION",
                    content={"patient_name": "Test"},
                ),
            ],
        )
        result, trace = self.agent.run(_ctx(sub, policy))
        assert result.data["extracted"]["total_amount"] == 2500


# ─── PolicyEngineAgent ────────────────────────────────────────────


class TestPolicyEngine:
    agent = PolicyEngineAgent()

    def test_copay_calculation(self, policy):
        """10% co-pay on consultation: 1500 → 1350."""
        sub = ClaimSubmission(
            member_id="EMP001",
            claim_category="CONSULTATION",
            treatment_date="2024-11-01",
            claimed_amount=1500,
        )
        extracted = {
            "diagnosis": "Viral Fever",
            "hospital_name": "City Clinic",
            "line_items": [],
            "tests_ordered": [],
        }
        result, trace = self.agent.run(_ctx(sub, policy, extracted=extracted))
        assert result.success is True
        assert result.data["policy"]["approved_amount"] == 1350

    def test_network_discount_before_copay(self, policy):
        """Apollo Hospitals: 20% discount on 4500=3600, then 10% co-pay on 3600=360 → 3240."""
        sub = ClaimSubmission(
            member_id="EMP010",
            claim_category="CONSULTATION",
            treatment_date="2024-11-03",
            claimed_amount=4500,
            hospital_name="Apollo Hospitals",
        )
        extracted = {
            "diagnosis": "Acute Bronchitis",
            "hospital_name": "Apollo Hospitals",
            "line_items": [],
            "tests_ordered": [],
        }
        result, trace = self.agent.run(_ctx(sub, policy, extracted=extracted))
        assert result.data["policy"]["approved_amount"] == 3240

    def test_waiting_period_rejection(self, policy):
        """EMP005 joined 2024-09-01, diabetes has 90-day wait. Claim on 2024-10-15 should be rejected."""
        sub = ClaimSubmission(
            member_id="EMP005",
            claim_category="CONSULTATION",
            treatment_date="2024-10-15",
            claimed_amount=3000,
        )
        extracted = {
            "diagnosis": "Type 2 Diabetes Mellitus",
            "treatment": "",
            "line_items": [],
            "tests_ordered": [],
        }
        result, trace = self.agent.run(_ctx(sub, policy, extracted=extracted))
        reasons = result.data["policy"]["rejection_reasons"]
        assert "WAITING_PERIOD" in reasons

    def test_per_claim_limit_rejection(self, policy):
        sub = ClaimSubmission(
            member_id="EMP003",
            claim_category="CONSULTATION",
            treatment_date="2024-10-20",
            claimed_amount=7500,
        )
        extracted = {
            "diagnosis": "Gastroenteritis",
            "line_items": [],
            "tests_ordered": [],
        }
        result, trace = self.agent.run(_ctx(sub, policy, extracted=extracted))
        reasons = result.data["policy"]["rejection_reasons"]
        assert "PER_CLAIM_EXCEEDED" in reasons

    def test_minimum_claim_amount_rejection(self, policy):
        """₹200 is below ₹500 minimum."""
        sub = ClaimSubmission(
            member_id="EMP001",
            claim_category="CONSULTATION",
            treatment_date="2024-11-01",
            claimed_amount=200,
        )
        extracted = {"diagnosis": "Headache", "line_items": [], "tests_ordered": []}
        result, trace = self.agent.run(_ctx(sub, policy, extracted=extracted))
        reasons = result.data["policy"]["rejection_reasons"]
        assert "BELOW_MINIMUM" in reasons

    def test_annual_limit_caps_amount(self, policy):
        """When YTD is close to annual limit, approved amount should be capped."""
        sub = ClaimSubmission(
            member_id="EMP001",
            claim_category="CONSULTATION",
            treatment_date="2024-11-01",
            claimed_amount=2000,
            ytd_claims_amount=49500,  # Only ₹500 remaining from ₹50,000 limit
        )
        extracted = {"diagnosis": "Fever", "line_items": [], "tests_ordered": []}
        result, trace = self.agent.run(_ctx(sub, policy, extracted=extracted))
        # After 10% copay on 2000 = 1800, but capped at remaining 500
        approved = result.data["policy"]["approved_amount"]
        assert approved <= 500

    def test_annual_limit_exhausted_rejects(self, policy):
        """When YTD >= annual limit, claim should be rejected."""
        sub = ClaimSubmission(
            member_id="EMP001",
            claim_category="CONSULTATION",
            treatment_date="2024-11-01",
            claimed_amount=1000,
            ytd_claims_amount=50000,
        )
        extracted = {"diagnosis": "Cold", "line_items": [], "tests_ordered": []}
        result, trace = self.agent.run(_ctx(sub, policy, extracted=extracted))
        reasons = result.data["policy"]["rejection_reasons"]
        assert "ANNUAL_LIMIT_EXHAUSTED" in reasons

    def test_excluded_condition_rejection(self, policy):
        """Obesity treatment is excluded."""
        sub = ClaimSubmission(
            member_id="EMP009",
            claim_category="CONSULTATION",
            treatment_date="2024-10-18",
            claimed_amount=8000,
        )
        extracted = {
            "diagnosis": "Morbid Obesity — BMI 37",
            "treatment": "Bariatric Consultation and Customised Diet Plan",
            "line_items": [],
            "tests_ordered": [],
        }
        result, trace = self.agent.run(_ctx(sub, policy, extracted=extracted))
        reasons = result.data["policy"]["rejection_reasons"]
        assert "EXCLUDED_CONDITION" in reasons


# ─── FraudDetectorAgent ───────────────────────────────────────────


class TestFraudDetector:
    agent = FraudDetectorAgent()

    def test_clean_claim_no_signals(self, policy):
        sub = ClaimSubmission(
            member_id="EMP001",
            claim_category="CONSULTATION",
            treatment_date="2024-11-01",
            claimed_amount=1500,
        )
        result, trace = self.agent.run(_ctx(sub, policy))
        fraud = result.data["fraud"]
        assert fraud["fraud_score"] == 0.0
        assert fraud["recommend_manual_review"] is False

    def test_same_day_claims_trigger_signal(self, policy):
        sub = ClaimSubmission(
            member_id="EMP008",
            claim_category="CONSULTATION",
            treatment_date="2024-10-30",
            claimed_amount=4800,
            claims_history=[
                ClaimHistoryEntry(claim_id="C1", date="2024-10-30", amount=1200, provider="Clinic A"),
                ClaimHistoryEntry(claim_id="C2", date="2024-10-30", amount=1800, provider="Clinic B"),
            ],
        )
        result, trace = self.agent.run(_ctx(sub, policy))
        fraud = result.data["fraud"]
        assert fraud["fraud_score"] > 0
        assert len(fraud["fraud_signals"]) > 0
        assert any("SAME_DAY" in sig for sig in fraud["fraud_signals"])

    def test_high_value_claim_detection(self, policy):
        sub = ClaimSubmission(
            member_id="EMP001",
            claim_category="CONSULTATION",
            treatment_date="2024-11-01",
            claimed_amount=30000,  # Above 25000 threshold
        )
        result, trace = self.agent.run(_ctx(sub, policy))
        fraud = result.data["fraud"]
        assert fraud["fraud_score"] > 0
        assert any("HIGH_VALUE" in sig for sig in fraud["fraud_signals"])


# ─── DecisionEngineAgent ──────────────────────────────────────────


class TestDecisionEngine:
    agent = DecisionEngineAgent()

    def test_clean_approval(self, policy):
        ctx = _ctx(
            ClaimSubmission(
                member_id="EMP001",
                claim_category="CONSULTATION",
                treatment_date="2024-11-01",
                claimed_amount=1500,
                documents=[],
            ),
            policy,
            policy_result={
                "rejection_reasons": [],
                "approved_amount": 1350,
                "amount_breakdown": None,
                "is_partial": False,
                "approved_items": [],
                "rejected_items": [],
            },
            fraud_result={
                "fraud": {
                    "fraud_score": 0.0,
                    "fraud_signals": [],
                    "recommend_manual_review": False,
                }
            },
            extraction_result={"extracted": {"extraction_confidence": 1.0}},
            component_failures=[],
        )
        result, trace = self.agent.run(ctx)
        assert result.data["decision"] == "APPROVED"
        assert result.data["approved_amount"] == 1350
        assert result.data["confidence_score"] > 0.85

    def test_fraud_triggers_manual_review(self, policy):
        ctx = _ctx(
            ClaimSubmission(
                member_id="EMP008",
                claim_category="CONSULTATION",
                treatment_date="2024-10-30",
                claimed_amount=4800,
                documents=[],
            ),
            policy,
            policy_result={
                "rejection_reasons": [],
                "approved_amount": 4800,
                "is_partial": False,
                "approved_items": [],
                "rejected_items": [],
            },
            fraud_result={
                "fraud": {
                    "fraud_score": 0.9,
                    "fraud_signals": ["MULTIPLE_SAME_DAY_CLAIMS"],
                    "recommend_manual_review": True,
                }
            },
            extraction_result={"extracted": {"extraction_confidence": 1.0}},
            component_failures=[],
        )
        result, trace = self.agent.run(ctx)
        assert result.data["decision"] == "MANUAL_REVIEW"

    def test_rejection_overrides_partial(self, policy):
        """Rejections take priority over partial approval."""
        ctx = _ctx(
            ClaimSubmission(
                member_id="EMP001",
                claim_category="CONSULTATION",
                treatment_date="2024-11-01",
                claimed_amount=1500,
                documents=[],
            ),
            policy,
            policy_result={
                "rejection_reasons": ["WAITING_PERIOD"],
                "approved_amount": 0,
                "is_partial": True,
                "approved_items": [],
                "rejected_items": [],
            },
            fraud_result={"fraud": {"fraud_score": 0, "fraud_signals": [], "recommend_manual_review": False}},
            extraction_result={"extracted": {"extraction_confidence": 1.0}},
            component_failures=[],
        )
        result, trace = self.agent.run(ctx)
        assert result.data["decision"] == "REJECTED"
        assert result.data["approved_amount"] == 0

    def test_component_failure_reduces_confidence(self, policy):
        ctx = _ctx(
            ClaimSubmission(
                member_id="EMP001",
                claim_category="CONSULTATION",
                treatment_date="2024-11-01",
                claimed_amount=1500,
                documents=[],
            ),
            policy,
            policy_result={
                "rejection_reasons": [],
                "approved_amount": 1350,
                "is_partial": False,
                "approved_items": [],
                "rejected_items": [],
            },
            fraud_result={"fraud": {"fraud_score": 0, "fraud_signals": [], "recommend_manual_review": False}},
            extraction_result={"extracted": {"extraction_confidence": 0.4}},
            component_failures=["Document Extractor (simulated failure)"],
        )
        result, trace = self.agent.run(ctx)
        assert result.data["decision"] == "APPROVED"
        assert result.data["confidence_score"] < 0.85

    def test_partial_approval_with_line_items(self, policy):
        ctx = _ctx(
            ClaimSubmission(
                member_id="EMP002",
                claim_category="DENTAL",
                treatment_date="2024-10-15",
                claimed_amount=12000,
                documents=[],
            ),
            policy,
            policy_result={
                "rejection_reasons": [],
                "approved_amount": 8000,
                "is_partial": True,
                "approved_items": [{"description": "Root Canal", "amount": 8000}],
                "rejected_items": [{"description": "Teeth Whitening", "amount": 4000, "reason": "excluded"}],
            },
            fraud_result={"fraud": {"fraud_score": 0, "fraud_signals": [], "recommend_manual_review": False}},
            extraction_result={"extracted": {"extraction_confidence": 1.0}},
            component_failures=[],
        )
        result, trace = self.agent.run(ctx)
        assert result.data["decision"] == "PARTIAL"
        assert result.data["approved_amount"] == 8000
