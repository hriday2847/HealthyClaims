"""Agent 4: Fraud Detector.

Checks for suspicious patterns in claim submissions:
- Multiple same-day claims (TC009)
- High monthly claim frequency
- High-value claims above threshold
"""

from __future__ import annotations

from typing import Any

from backend.agents.base import AgentResult, BaseAgent
from backend.models.claim import ClaimSubmission
from backend.models.decision import CheckResult


class FraudDetectorAgent(BaseAgent):
    name = "Fraud Detector"
    critical = False  # Fraud check failure should not crash the pipeline

    def execute(self, context: dict[str, Any]) -> AgentResult:
        submission: ClaimSubmission = context["submission"]
        policy = context["policy"]
        checks: list[CheckResult] = []
        warnings: list[str] = []
        fraud_signals: list[str] = []

        thresholds = policy.fraud_thresholds
        fraud_score = 0.0

        # ── 1. Same-day claims check ──────────────────────────────
        same_day_claims = []
        if submission.claims_history:
            treatment_date = submission.treatment_date
            same_day_claims = [
                c for c in submission.claims_history
                if c.date == treatment_date
            ]

        same_day_count = len(same_day_claims) + 1  # +1 for current claim
        if same_day_count > thresholds.same_day_claims_limit:
            fraud_score += 0.5
            providers = [c.provider or "Unknown" for c in same_day_claims]
            total_same_day = sum(c.amount for c in same_day_claims) + submission.claimed_amount
            signal = (
                f"MULTIPLE_SAME_DAY_CLAIMS: {same_day_count} claims on {submission.treatment_date} "
                f"(limit: {thresholds.same_day_claims_limit}). "
                f"Previous providers: {', '.join(providers)}. "
                f"Total same-day amount: ₹{total_same_day:,.0f}"
            )
            fraud_signals.append(signal)
            checks.append(CheckResult(
                check_name="Same-Day Claims",
                passed=False,
                detail=signal,
                data={
                    "same_day_count": same_day_count,
                    "limit": thresholds.same_day_claims_limit,
                    "previous_claims": [c.model_dump() for c in same_day_claims],
                },
            ))
        else:
            checks.append(CheckResult(
                check_name="Same-Day Claims",
                passed=True,
                detail=f"{same_day_count} claim(s) today (limit: {thresholds.same_day_claims_limit})",
            ))

        # ── 2. Monthly claims frequency ───────────────────────────
        if submission.claims_history:
            monthly_count = len(submission.claims_history) + 1
            if monthly_count > thresholds.monthly_claims_limit:
                fraud_score += 0.3
                signal = (
                    f"HIGH_MONTHLY_FREQUENCY: {monthly_count} claims this period "
                    f"(limit: {thresholds.monthly_claims_limit})"
                )
                fraud_signals.append(signal)
                checks.append(CheckResult(
                    check_name="Monthly Claim Frequency",
                    passed=False,
                    detail=signal,
                ))
            else:
                checks.append(CheckResult(
                    check_name="Monthly Claim Frequency",
                    passed=True,
                    detail=f"{monthly_count} claim(s) in period (limit: {thresholds.monthly_claims_limit})",
                ))
        else:
            checks.append(CheckResult(
                check_name="Monthly Claim Frequency",
                passed=True,
                detail="No claims history provided — frequency check passed",
            ))

        # ── 3. High-value claim check ─────────────────────────────
        if submission.claimed_amount > thresholds.high_value_claim_threshold:
            fraud_score += 0.2
            signal = (
                f"HIGH_VALUE_CLAIM: ₹{submission.claimed_amount:,.0f} exceeds "
                f"high-value threshold of ₹{thresholds.high_value_claim_threshold:,.0f}"
            )
            fraud_signals.append(signal)
            checks.append(CheckResult(
                check_name="High-Value Claim",
                passed=False,
                detail=signal,
            ))
        else:
            checks.append(CheckResult(
                check_name="High-Value Claim",
                passed=True,
                detail=f"₹{submission.claimed_amount:,.0f} below threshold of ₹{thresholds.high_value_claim_threshold:,.0f}",
            ))

        # ── 4. Auto-manual-review threshold ───────────────────────
        if submission.claimed_amount > thresholds.auto_manual_review_above:
            fraud_score += 0.1
            signal = (
                f"AUTO_MANUAL_REVIEW: Amount ₹{submission.claimed_amount:,.0f} exceeds "
                f"auto-review threshold of ₹{thresholds.auto_manual_review_above:,.0f}"
            )
            fraud_signals.append(signal)

        # Cap fraud score at 1.0
        fraud_score = min(1.0, fraud_score)

        # Should this go to manual review?
        recommend_manual = fraud_score >= thresholds.fraud_score_manual_review_threshold

        checks.append(CheckResult(
            check_name="Overall Fraud Score",
            passed=not recommend_manual,
            detail=(
                f"Fraud score: {fraud_score:.2f} "
                f"(threshold for manual review: {thresholds.fraud_score_manual_review_threshold}). "
                f"{'MANUAL REVIEW RECOMMENDED' if recommend_manual else 'No manual review needed'}"
            ),
            data={"fraud_score": fraud_score, "recommend_manual": recommend_manual},
        ))

        return AgentResult(
            success=True,
            data={
                "fraud": {
                    "fraud_score": fraud_score,
                    "fraud_signals": fraud_signals,
                    "recommend_manual_review": recommend_manual,
                }
            },
            checks=checks,
            warnings=warnings,
        )
