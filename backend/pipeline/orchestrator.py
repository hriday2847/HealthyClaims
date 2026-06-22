"""Pipeline orchestrator — runs the multi-agent pipeline in sequence.

Flow:
  1. Document Verifier (critical — stops on failure)
  2. Document Extractor
  3. Policy Engine + Fraud Detector (can run in parallel conceptually)
  4. Decision Engine (synthesises all outputs)

Handles:
  - Graceful degradation when non-critical agents fail
  - simulate_component_failure flag for TC011
  - Full trace collection
"""

from __future__ import annotations

from typing import Any

from backend.agents.base import AgentResult
from backend.agents.decision_engine import DecisionEngineAgent
from backend.agents.document_extractor import DocumentExtractorAgent
from backend.agents.document_verifier import DocumentVerifierAgent
from backend.agents.fraud_detector import FraudDetectorAgent
from backend.agents.policy_engine import PolicyEngineAgent
from backend.models.claim import ClaimSubmission, ClaimStatus
from backend.models.decision import (
    ClaimDecision,
    Decision,
    DocumentError,
    TraceStep,
    TraceStepStatus,
)
from backend.services.policy_loader import load_policy


class PipelineOrchestrator:
    """Orchestrates the multi-agent claims processing pipeline."""

    def __init__(self, policy_path: str | None = None):
        self.policy = load_policy(policy_path)
        self.verifier = DocumentVerifierAgent()
        self.extractor = DocumentExtractorAgent()
        self.policy_engine = PolicyEngineAgent()
        self.fraud_detector = FraudDetectorAgent()
        self.decision_engine = DecisionEngineAgent()

    def process_claim(self, submission: ClaimSubmission) -> ClaimDecision:
        """Process a claim through the full pipeline and return a decision."""
        trace: list[TraceStep] = []
        component_failures: list[str] = []
        context: dict[str, Any] = {
            "submission": submission,
            "policy": self.policy,
        }

        # ────────────────────────────────────────────────────────
        # Stage 1: Document Verification (CRITICAL)
        # ────────────────────────────────────────────────────────
        verifier_result, verifier_trace = self.verifier.run(context)
        trace.append(verifier_trace)

        if not verifier_result.success:
            # Stop pipeline — return document error
            doc_errors = []
            for err_data in verifier_result.data.get("document_errors", []):
                doc_errors.append(DocumentError(**err_data))

            return ClaimDecision(
                decision=None,
                document_errors=doc_errors,
                confidence_score=1.0,  # High confidence in the error detection
                trace=trace,
                summary=verifier_result.error or "Document verification failed",
            )

        # ────────────────────────────────────────────────────────
        # Stage 2: Document Extraction
        # ────────────────────────────────────────────────────────
        if submission.simulate_component_failure:
            # TC011: Simulate extraction failure
            component_failures.append("Document Extractor (simulated failure)")
            trace.append(TraceStep(
                agent_name="Document Extractor",
                status=TraceStepStatus.FAILED,
                duration_ms=0,
                input_summary=f"member={submission.member_id}, docs={len(submission.documents)}",
                output_summary="SIMULATED FAILURE — component crashed",
                error="Simulated component failure for resilience testing",
                warnings=["This failure was intentionally simulated via the simulate_component_failure flag"],
            ))
            # Provide minimal extracted data so pipeline can continue
            context["extraction_result"] = {
                "extracted": {
                    "patient_name": None,
                    "diagnosis": None,
                    "treatment": None,
                    "hospital_name": submission.hospital_name,
                    "line_items": [],
                    "total_amount": submission.claimed_amount,
                    "extraction_confidence": 0.4,
                }
            }
            context["extracted"] = context["extraction_result"]["extracted"]
        else:
            extractor_result, extractor_trace = self.extractor.run(context)
            trace.append(extractor_trace)
            if extractor_result.success:
                context["extraction_result"] = extractor_result.data
                context["extracted"] = extractor_result.data.get("extracted", {})
            else:
                component_failures.append("Document Extractor")
                context["extraction_result"] = {"extracted": {"extraction_confidence": 0.5}}
                context["extracted"] = context["extraction_result"]["extracted"]

        # ────────────────────────────────────────────────────────
        # Stage 3a: Policy Engine
        # ────────────────────────────────────────────────────────
        policy_result, policy_trace = self.policy_engine.run(context)
        trace.append(policy_trace)
        if policy_result.success:
            context["policy_result"] = policy_result.data.get("policy", {})
        else:
            component_failures.append("Policy Engine")
            context["policy_result"] = {"rejection_reasons": [], "approved_amount": 0}

        # ────────────────────────────────────────────────────────
        # Stage 3b: Fraud Detector
        # ────────────────────────────────────────────────────────
        fraud_result, fraud_trace = self.fraud_detector.run(context)
        trace.append(fraud_trace)
        if fraud_result.success:
            context["fraud_result"] = fraud_result.data
        else:
            component_failures.append("Fraud Detector")
            context["fraud_result"] = {"fraud": {"fraud_score": 0, "fraud_signals": [], "recommend_manual_review": False}}

        # ────────────────────────────────────────────────────────
        # Stage 4: Decision Engine
        # ────────────────────────────────────────────────────────
        context["component_failures"] = component_failures
        decision_result, decision_trace = self.decision_engine.run(context)
        trace.append(decision_trace)

        # ── Build final response ──────────────────────────────────
        d = decision_result.data
        decision_enum = None
        if d.get("decision"):
            decision_enum = Decision(d["decision"])

        return ClaimDecision(
            decision=decision_enum,
            approved_amount=d.get("approved_amount"),
            rejection_reasons=d.get("rejection_reasons", []),
            confidence_score=d.get("confidence_score", 0.5),
            amount_breakdown=(
                _parse_breakdown(d["amount_breakdown"])
                if d.get("amount_breakdown")
                else None
            ),
            fraud_signals=d.get("fraud_signals", []),
            trace=trace,
            summary=d.get("summary", ""),
            recommendations=d.get("recommendations", []),
        )


def _parse_breakdown(data: dict) -> Any:
    """Parse amount breakdown dict into model (handles nested serialization)."""
    from backend.models.decision import AmountBreakdown
    try:
        return AmountBreakdown(**data)
    except Exception:
        return None
