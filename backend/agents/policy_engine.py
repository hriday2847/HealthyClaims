"""Agent 3: Policy Engine.

Evaluates the extracted claim data against the policy terms to determine
coverage, limits, exclusions, waiting periods, and financial calculations.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from backend.agents.base import AgentResult, BaseAgent
from backend.models.claim import ClaimSubmission
from backend.models.decision import AmountBreakdown, CheckResult
from backend.services.policy_loader import (
    get_category_config,
    get_member,
    is_network_hospital,
)


class PolicyEngineAgent(BaseAgent):
    name = "Policy Engine"
    critical = False

    def execute(self, context: dict[str, Any]) -> AgentResult:
        submission: ClaimSubmission = context["submission"]
        policy = context["policy"]
        extracted: dict = context.get("extracted", {})
        checks: list[CheckResult] = []
        warnings: list[str] = []
        rejection_reasons: list[str] = []
        policy_data: dict[str, Any] = {}

        # ── 1. Member eligibility ─────────────────────────────────
        member = get_member(policy, submission.member_id)
        if not member:
            checks.append(CheckResult(
                check_name="Member Eligibility",
                passed=False,
                detail=f"Member {submission.member_id} not found in policy roster",
            ))
            rejection_reasons.append("MEMBER_NOT_FOUND")
        else:
            checks.append(CheckResult(
                check_name="Member Eligibility",
                passed=True,
                detail=f"Member {member.name} ({member.member_id}) found — relationship: {member.relationship}",
            ))

        # ── 2. Initial waiting period ─────────────────────────────
        if member and member.join_date:
            join_date = datetime.strptime(member.join_date, "%Y-%m-%d")
            treatment_date = datetime.strptime(submission.treatment_date, "%Y-%m-%d")
            days_since_join = (treatment_date - join_date).days
            initial_wait = policy.waiting_periods.initial_waiting_period_days

            if days_since_join < initial_wait:
                eligible_date = join_date + timedelta(days=initial_wait)
                checks.append(CheckResult(
                    check_name="Initial Waiting Period",
                    passed=False,
                    detail=(
                        f"Member joined on {member.join_date}, treatment on {submission.treatment_date} "
                        f"({days_since_join} days). Initial waiting period is {initial_wait} days. "
                        f"Eligible from {eligible_date.strftime('%Y-%m-%d')}."
                    ),
                ))
                rejection_reasons.append("WAITING_PERIOD")
            else:
                checks.append(CheckResult(
                    check_name="Initial Waiting Period",
                    passed=True,
                    detail=f"Joined {member.join_date}, {days_since_join} days ago (>{initial_wait} day wait satisfied)",
                ))

        # ── 3. Condition-specific waiting period ──────────────────
        diagnosis = (extracted.get("diagnosis") or "").lower()
        treatment = (extracted.get("treatment") or "").lower()
        combined_text = f"{diagnosis} {treatment}"

        condition_wait_found = False
        for condition, wait_days in policy.waiting_periods.specific_conditions.items():
            condition_lower = condition.lower().replace("_", " ")
            # Check if the diagnosis/treatment mentions this condition
            keywords = self._get_condition_keywords(condition)
            if any(kw in combined_text for kw in keywords):
                condition_wait_found = True
                if member and member.join_date:
                    join_date = datetime.strptime(member.join_date, "%Y-%m-%d")
                    treatment_date = datetime.strptime(submission.treatment_date, "%Y-%m-%d")
                    days_since_join = (treatment_date - join_date).days
                    if days_since_join < wait_days:
                        eligible_date = join_date + timedelta(days=wait_days)
                        checks.append(CheckResult(
                            check_name=f"Condition Waiting Period — {condition}",
                            passed=False,
                            detail=(
                                f"Diagnosis '{extracted.get('diagnosis')}' matches condition '{condition}' "
                                f"which has a {wait_days}-day waiting period. "
                                f"Member joined {member.join_date} ({days_since_join} days ago). "
                                f"Eligible for {condition}-related claims from {eligible_date.strftime('%Y-%m-%d')}."
                            ),
                        ))
                        rejection_reasons.append("WAITING_PERIOD")
                    else:
                        checks.append(CheckResult(
                            check_name=f"Condition Waiting Period — {condition}",
                            passed=True,
                            detail=f"Waiting period of {wait_days} days satisfied ({days_since_join} days since join)",
                        ))

        if not condition_wait_found:
            checks.append(CheckResult(
                check_name="Condition-Specific Waiting Period",
                passed=True,
                detail="No condition-specific waiting period applies",
            ))

        # ── 4. Exclusions check ───────────────────────────────────
        exclusion_hit = False
        for exclusion in policy.exclusions.conditions:
            exclusion_keywords = exclusion.lower().split()
            # Check if enough keywords match
            match_count = sum(1 for kw in exclusion_keywords if kw in combined_text)
            if match_count >= len(exclusion_keywords) * 0.5 and match_count >= 2:
                checks.append(CheckResult(
                    check_name=f"Exclusion — {exclusion}",
                    passed=False,
                    detail=f"Treatment/diagnosis matches excluded condition: '{exclusion}'",
                ))
                rejection_reasons.append("EXCLUDED_CONDITION")
                exclusion_hit = True

        # Check category-specific exclusions (dental, vision)
        category_config = get_category_config(policy, submission.claim_category.value)
        if not exclusion_hit:
            checks.append(CheckResult(
                check_name="General Exclusions",
                passed=True,
                detail="No general exclusions matched",
            ))

        # ── 5. Per-claim limit ────────────────────────────────────
        per_claim_limit = policy.coverage.per_claim_limit
        if submission.claimed_amount > per_claim_limit:
            checks.append(CheckResult(
                check_name="Per-Claim Limit",
                passed=False,
                detail=(
                    f"Claimed amount ₹{submission.claimed_amount:,.0f} exceeds "
                    f"the per-claim limit of ₹{per_claim_limit:,.0f}"
                ),
            ))
            rejection_reasons.append("PER_CLAIM_EXCEEDED")
        else:
            checks.append(CheckResult(
                check_name="Per-Claim Limit",
                passed=True,
                detail=f"Claimed ₹{submission.claimed_amount:,.0f} within per-claim limit of ₹{per_claim_limit:,.0f}",
            ))

        # ── 6. Pre-authorization check ────────────────────────────
        pre_auth_required = False
        tests_ordered = extracted.get("tests_ordered", [])
        line_items = extracted.get("line_items", [])

        if category_config and category_config.high_value_tests_requiring_pre_auth:
            for test in category_config.high_value_tests_requiring_pre_auth:
                test_lower = test.lower()
                # Check in tests_ordered
                if any(test_lower in t.lower() for t in tests_ordered):
                    pre_auth_threshold = category_config.pre_auth_threshold or 0
                    if submission.claimed_amount > pre_auth_threshold:
                        pre_auth_required = True
                        checks.append(CheckResult(
                            check_name=f"Pre-Authorization — {test}",
                            passed=False,
                            detail=(
                                f"{test} costing ₹{submission.claimed_amount:,.0f} requires "
                                f"pre-authorization (threshold: ₹{pre_auth_threshold:,.0f}). "
                                f"No pre-authorization was provided. "
                                f"Please obtain pre-authorization from the insurer before "
                                f"resubmitting this claim."
                            ),
                        ))
                        rejection_reasons.append("PRE_AUTH_MISSING")

                # Also check in line_items
                if any(test_lower in (item.get("description", "")).lower() for item in line_items):
                    pre_auth_threshold = category_config.pre_auth_threshold or 0
                    if submission.claimed_amount > pre_auth_threshold and not pre_auth_required:
                        pre_auth_required = True
                        checks.append(CheckResult(
                            check_name=f"Pre-Authorization — {test}",
                            passed=False,
                            detail=(
                                f"{test} found in bill line items, costing ₹{submission.claimed_amount:,.0f}. "
                                f"Pre-authorization required for {test} above ₹{pre_auth_threshold:,.0f}. "
                                f"Please obtain pre-authorization before resubmitting."
                            ),
                        ))
                        rejection_reasons.append("PRE_AUTH_MISSING")

        if not pre_auth_required:
            checks.append(CheckResult(
                check_name="Pre-Authorization",
                passed=True,
                detail="No pre-authorization required for this claim",
            ))

        # ── 7. Line-item level coverage (dental/vision exclusions)
        approved_items: list[dict] = []
        rejected_items: list[dict] = []

        if line_items and category_config:
            excluded_procedures = category_config.excluded_procedures or []
            excluded_items_list = category_config.excluded_items or []
            all_excluded = [e.lower() for e in excluded_procedures + excluded_items_list]

            for item in line_items:
                desc = item.get("description", "").lower()
                amount = item.get("amount", 0)
                is_excluded = any(
                    exc in desc or desc in exc for exc in all_excluded
                )
                # Also check against general exclusions
                for exclusion in policy.exclusions.conditions:
                    exc_words = exclusion.lower().split()
                    if sum(1 for w in exc_words if w in desc) >= max(1, len(exc_words) * 0.5):
                        is_excluded = True
                        break

                if is_excluded:
                    rejected_items.append({
                        "description": item.get("description", ""),
                        "amount": amount,
                        "reason": "Excluded procedure/treatment under policy terms",
                    })
                else:
                    approved_items.append({
                        "description": item.get("description", ""),
                        "amount": amount,
                    })

        # ── 8. Financial calculation ──────────────────────────────
        if not rejection_reasons:
            claimed = submission.claimed_amount
            eligible = claimed

            # If we have line-item level splits
            if rejected_items:
                eligible = sum(item["amount"] for item in approved_items)

            # Sub-limit cap
            sub_limit = category_config.sub_limit if category_config else None
            sub_limit_applied = None
            if sub_limit and eligible > sub_limit:
                sub_limit_applied = sub_limit
                eligible = sub_limit

            # Network hospital discount
            hospital = extracted.get("hospital_name") or submission.hospital_name or ""
            is_network = is_network_hospital(policy, hospital)
            network_discount = 0.0
            amount_after_discount = eligible

            if is_network and category_config:
                discount_pct = category_config.network_discount_percent or 0
                if discount_pct > 0:
                    network_discount = eligible * (discount_pct / 100)
                    amount_after_discount = eligible - network_discount
                    checks.append(CheckResult(
                        check_name="Network Hospital Discount",
                        passed=True,
                        detail=(
                            f"'{hospital}' is a network hospital. "
                            f"{discount_pct}% discount applied: "
                            f"₹{eligible:,.0f} → ₹{amount_after_discount:,.0f} "
                            f"(discount: ₹{network_discount:,.0f})"
                        ),
                    ))
            else:
                checks.append(CheckResult(
                    check_name="Network Hospital Discount",
                    passed=True,
                    detail=f"Hospital '{hospital}' is not in network — no discount applied" if hospital else "No hospital specified",
                ))

            # Co-pay (applied AFTER network discount)
            copay_amount = 0.0
            if category_config and category_config.copay_percent > 0:
                copay_pct = category_config.copay_percent
                copay_amount = amount_after_discount * (copay_pct / 100)
                final_amount = amount_after_discount - copay_amount
                checks.append(CheckResult(
                    check_name="Co-pay",
                    passed=True,
                    detail=(
                        f"{copay_pct}% co-pay on ₹{amount_after_discount:,.0f} = "
                        f"₹{copay_amount:,.0f} deducted. Approved: ₹{final_amount:,.0f}"
                    ),
                ))
            else:
                final_amount = amount_after_discount
                checks.append(CheckResult(
                    check_name="Co-pay",
                    passed=True,
                    detail="No co-pay applicable for this category",
                ))

            breakdown = AmountBreakdown(
                claimed_amount=claimed,
                eligible_amount=eligible,
                network_discount=network_discount if network_discount > 0 else None,
                amount_after_discount=amount_after_discount if network_discount > 0 else None,
                copay_amount=copay_amount if copay_amount > 0 else None,
                sub_limit_cap=sub_limit_applied,
                approved_amount=round(final_amount, 2),
                line_item_details=(
                    {"approved": approved_items, "rejected": rejected_items}
                    if (approved_items or rejected_items)
                    else None
                ),
            )

            policy_data["amount_breakdown"] = breakdown.model_dump()
            policy_data["approved_amount"] = round(final_amount, 2)
            policy_data["is_partial"] = len(rejected_items) > 0

        policy_data["rejection_reasons"] = list(set(rejection_reasons))
        policy_data["approved_items"] = approved_items
        policy_data["rejected_items"] = rejected_items

        return AgentResult(
            success=True,
            data={"policy": policy_data},
            checks=checks,
            warnings=warnings,
        )

    @staticmethod
    def _get_condition_keywords(condition: str) -> list[str]:
        """Map policy condition names to diagnosis keywords."""
        mapping = {
            "diabetes": ["diabetes", "diabetic", "t2dm", "type 2 diabetes", "metformin", "glimepiride"],
            "hypertension": ["hypertension", "htn", "high blood pressure"],
            "thyroid_disorders": ["thyroid", "hypothyroid", "hyperthyroid"],
            "joint_replacement": ["joint replacement", "knee replacement", "hip replacement"],
            "maternity": ["maternity", "pregnancy", "prenatal", "antenatal"],
            "mental_health": ["mental health", "depression", "anxiety", "psychiatric"],
            "obesity_treatment": ["obesity", "bariatric", "weight loss", "bmi", "diet plan", "diet program"],
            "hernia": ["hernia"],
            "cataract": ["cataract"],
        }
        return mapping.get(condition.lower(), [condition.lower().replace("_", " ")])
