"""Agent 5: Decision Engine.

Synthesizes outputs from all upstream agents into a final claim decision.
Produces: decision, approved_amount, confidence_score, summary, and recommendations.
"""

from __future__ import annotations

from typing import Any

from backend.agents.base import AgentResult, BaseAgent
from backend.models.decision import CheckResult, Decision


class DecisionEngineAgent(BaseAgent):
    name = "Decision Engine"
    critical = False

    def execute(self, context: dict[str, Any]) -> AgentResult:
        policy_data: dict = context.get("policy_result", {})
        fraud_data: dict = context.get("fraud_result", {})
        extraction_data: dict = context.get("extraction_result", {})
        component_failures: list[str] = context.get("component_failures", [])
        checks: list[CheckResult] = []
        warnings: list[str] = []

        rejection_reasons = policy_data.get("rejection_reasons", [])
        fraud_info = fraud_data.get("fraud", {})
        fraud_signals = fraud_info.get("fraud_signals", [])
        recommend_manual = fraud_info.get("recommend_manual_review", False)
        approved_amount = policy_data.get("approved_amount", 0)
        amount_breakdown = policy_data.get("amount_breakdown")
        is_partial = policy_data.get("is_partial", False)
        extraction_confidence = extraction_data.get("extracted", {}).get("extraction_confidence", 1.0)

        # ── Determine decision ────────────────────────────────────

        decision = None
        summary_parts = []

        # Priority 1: Fraud signals → MANUAL_REVIEW
        if recommend_manual:
            decision = Decision.MANUAL_REVIEW
            summary_parts.append(
                f"Claim routed to manual review due to fraud signals: "
                f"{'; '.join(fraud_signals)}"
            )
            checks.append(CheckResult(
                check_name="Fraud Review",
                passed=False,
                detail=f"Fraud score exceeded threshold — {len(fraud_signals)} signal(s) detected",
            ))
        else:
            checks.append(CheckResult(
                check_name="Fraud Review",
                passed=True,
                detail="No fraud signals requiring manual review",
            ))

        # Priority 2: Policy rejections
        if not decision and rejection_reasons:
            decision = Decision.REJECTED
            approved_amount = 0
            reason_map = {
                "WAITING_PERIOD": "Claim falls within a waiting period",
                "EXCLUDED_CONDITION": "Treatment is excluded under the policy",
                "PRE_AUTH_MISSING": "Pre-authorization was required but not obtained",
                "PER_CLAIM_EXCEEDED": "Claimed amount exceeds the per-claim limit",
                "MEMBER_NOT_FOUND": "Member not found in the policy roster",
            }
            reasons_text = [reason_map.get(r, r) for r in rejection_reasons]
            summary_parts.append(
                f"Claim rejected: {'; '.join(reasons_text)}"
            )
            checks.append(CheckResult(
                check_name="Policy Compliance",
                passed=False,
                detail=f"Rejection reasons: {', '.join(rejection_reasons)}",
            ))

        # Priority 3: Partial approval (some items excluded)
        if not decision and is_partial:
            decision = Decision.PARTIAL
            rejected_items = policy_data.get("rejected_items", [])
            approved_items = policy_data.get("approved_items", [])
            items_detail = []
            for item in approved_items:
                items_detail.append(f"✓ {item['description']}: ₹{item['amount']:,.0f} (approved)")
            for item in rejected_items:
                items_detail.append(f"✗ {item['description']}: ₹{item['amount']:,.0f} (rejected — {item.get('reason', 'excluded')})")
            summary_parts.append(
                f"Partial approval — {len(approved_items)} item(s) approved, "
                f"{len(rejected_items)} item(s) excluded:\n" + "\n".join(items_detail)
            )
            checks.append(CheckResult(
                check_name="Line-Item Coverage",
                passed=True,
                detail=f"{len(approved_items)} approved, {len(rejected_items)} rejected",
            ))

        # Priority 4: Full approval
        if not decision:
            decision = Decision.APPROVED
            summary_parts.append(
                f"Claim approved for ₹{approved_amount:,.0f}"
            )
            if amount_breakdown:
                bd = amount_breakdown
                if bd.get("network_discount"):
                    summary_parts.append(
                        f"Network discount of ₹{bd['network_discount']:,.0f} applied"
                    )
                if bd.get("copay_amount"):
                    summary_parts.append(
                        f"Co-pay of ₹{bd['copay_amount']:,.0f} deducted"
                    )
            checks.append(CheckResult(
                check_name="Policy Compliance",
                passed=True,
                detail="All policy checks passed",
            ))

        # ── Confidence score ──────────────────────────────────────
        confidence = 0.95  # Base confidence

        # Adjust for extraction quality
        confidence *= extraction_confidence

        # Adjust for component failures
        if component_failures:
            confidence *= 0.6  # Significant drop
            warnings.append(
                f"Component failure(s) during processing: {', '.join(component_failures)}. "
                f"Manual review recommended due to incomplete processing."
            )
            summary_parts.append(
                f"⚠ Processing was incomplete due to component failure(s): "
                f"{', '.join(component_failures)}. Confidence reduced. "
                f"Manual review recommended."
            )

        # High confidence for clear rejections
        if decision == Decision.REJECTED and rejection_reasons:
            confidence = max(confidence, 0.92)

        confidence = round(min(1.0, max(0.1, confidence)), 2)

        # ── Recommendations ───────────────────────────────────────
        recommendations = []
        if component_failures:
            recommendations.append("Manual review recommended due to incomplete processing")
        if decision == Decision.REJECTED:
            if "PRE_AUTH_MISSING" in rejection_reasons:
                recommendations.append(
                    "Obtain pre-authorization from the insurer and resubmit the claim"
                )
            if "PER_CLAIM_EXCEEDED" in rejection_reasons:
                recommendations.append(
                    "Split the treatment into multiple claims within the per-claim limit, or contact HR for limit increase"
                )

        checks.append(CheckResult(
            check_name="Confidence Score",
            passed=confidence >= 0.7,
            detail=f"Final confidence: {confidence} (extraction: {extraction_confidence}, failures: {len(component_failures)})",
        ))

        return AgentResult(
            success=True,
            data={
                "decision": decision.value,
                "approved_amount": approved_amount if decision != Decision.REJECTED else 0,
                "rejection_reasons": rejection_reasons,
                "confidence_score": confidence,
                "amount_breakdown": amount_breakdown,
                "fraud_signals": fraud_signals,
                "summary": " | ".join(summary_parts),
                "recommendations": recommendations,
            },
            checks=checks,
            warnings=warnings,
        )
