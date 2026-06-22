"""FastAPI application — Claims Processing System API.

Endpoints:
  POST /api/claims          — Submit a new claim
  GET  /api/claims          — List all processed claims
  GET  /api/claims/{id}     — Get claim detail with full trace
  POST /api/claims/test/{n} — Run a specific test case (TC001–TC012)
  POST /api/eval            — Run all 12 test cases
  GET  /api/policy          — Return policy summary
  GET  /api/members         — Return member roster
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.config import CORS_ORIGINS, TEST_CASES_FILE
from backend.models.claim import ClaimDocument, ClaimHistoryEntry, ClaimSubmission, ClaimStatus, StoredClaim
from backend.pipeline.orchestrator import PipelineOrchestrator
from backend.services.policy_loader import load_policy
from backend.services.storage import get_all_claims, get_claim, save_claim

app = FastAPI(
    title="Plum Claims Processing System",
    description="Multi-agent health insurance claims processing pipeline",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize pipeline
pipeline = PipelineOrchestrator()


# ── Endpoints ─────────────────────────────────────────────────────


@app.get("/")
def root():
    return {"status": "ok", "service": "Plum Claims Processing System", "version": "1.0.0"}


@app.post("/api/claims")
def submit_claim(submission: ClaimSubmission):
    """Submit a new claim for processing."""
    claim = StoredClaim(submission=submission, status=ClaimStatus.PROCESSING)

    start = time.perf_counter()
    try:
        decision = pipeline.process_claim(submission)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        claim.status = (
            ClaimStatus.DOCUMENT_ERROR
            if decision.document_errors
            else ClaimStatus.DECIDED
        )
        claim.result = decision.model_dump()
        claim.processing_time_ms = elapsed_ms

    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        claim.status = ClaimStatus.ERROR
        claim.result = {"error": str(exc)}
        claim.processing_time_ms = elapsed_ms

    save_claim(claim)
    return claim.model_dump()


@app.get("/api/claims")
def list_claims():
    """List all processed claims."""
    claims = get_all_claims()
    return {"claims": [c.model_dump() for c in claims], "total": len(claims)}


@app.get("/api/claims/{claim_id}")
def get_claim_detail(claim_id: str):
    """Get a specific claim with full decision trace."""
    claim = get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")
    return claim.model_dump()


@app.post("/api/claims/test/{case_id}")
def run_test_case(case_id: str):
    """Run a specific test case (e.g., TC001)."""
    test_cases = _load_test_cases()
    tc = next((tc for tc in test_cases if tc["case_id"] == case_id.upper()), None)
    if not tc:
        raise HTTPException(status_code=404, detail=f"Test case {case_id} not found")

    submission = _test_case_to_submission(tc)
    claim = StoredClaim(submission=submission, status=ClaimStatus.PROCESSING)

    start = time.perf_counter()
    decision = pipeline.process_claim(submission)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    claim.status = (
        ClaimStatus.DOCUMENT_ERROR if decision.document_errors else ClaimStatus.DECIDED
    )
    claim.result = decision.model_dump()
    claim.processing_time_ms = elapsed_ms
    save_claim(claim)

    return {
        "test_case": {
            "case_id": tc["case_id"],
            "case_name": tc["case_name"],
            "description": tc["description"],
            "expected": tc["expected"],
        },
        "actual": claim.model_dump(),
        "match": _check_match(tc["expected"], decision.model_dump()),
    }


@app.post("/api/eval")
def run_eval():
    """Run all 12 test cases and produce an eval report."""
    test_cases = _load_test_cases()
    results = []
    passed = 0

    for tc in test_cases:
        submission = _test_case_to_submission(tc)
        start = time.perf_counter()
        decision = pipeline.process_claim(submission)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        claim = StoredClaim(submission=submission, status=ClaimStatus.DECIDED)
        claim.result = decision.model_dump()
        claim.processing_time_ms = elapsed_ms
        if decision.document_errors:
            claim.status = ClaimStatus.DOCUMENT_ERROR
        save_claim(claim)

        match = _check_match(tc["expected"], decision.model_dump())
        if match["passed"]:
            passed += 1

        results.append({
            "case_id": tc["case_id"],
            "case_name": tc["case_name"],
            "description": tc["description"],
            "expected": tc["expected"],
            "actual_decision": decision.model_dump(),
            "claim_id": claim.id,
            "processing_time_ms": elapsed_ms,
            "match": match,
        })

    return {
        "summary": {
            "total": len(test_cases),
            "passed": passed,
            "failed": len(test_cases) - passed,
            "pass_rate": f"{(passed / len(test_cases)) * 100:.0f}%",
        },
        "results": results,
    }


@app.get("/api/policy")
def get_policy():
    """Return the policy configuration summary."""
    policy = load_policy()
    return {
        "policy_id": policy.policy_id,
        "policy_name": policy.policy_name,
        "insurer": policy.insurer,
        "company": policy.policy_holder.company_name,
        "coverage": policy.coverage.model_dump(),
        "categories": {k: v.model_dump() for k, v in policy.opd_categories.items()},
        "network_hospitals": policy.network_hospitals,
        "waiting_periods": policy.waiting_periods.model_dump(),
        "exclusions": policy.exclusions.model_dump(),
    }


@app.get("/api/members")
def get_members():
    """Return the member roster."""
    policy = load_policy()
    return {"members": [m.model_dump() for m in policy.members]}


# ── Helpers ───────────────────────────────────────────────────────


def _load_test_cases() -> list[dict]:
    """Load test cases from the JSON file."""
    with open(TEST_CASES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["test_cases"]


def _test_case_to_submission(tc: dict) -> ClaimSubmission:
    """Convert a test case input dict to a ClaimSubmission model."""
    inp = tc["input"]
    docs = []
    for d in inp.get("documents", []):
        docs.append(ClaimDocument(
            file_id=d.get("file_id", ""),
            file_name=d.get("file_name"),
            actual_type=d["actual_type"],
            content=d.get("content"),
            quality=d.get("quality", "GOOD"),
            patient_name_on_doc=d.get("patient_name_on_doc"),
        ))

    history = []
    for h in inp.get("claims_history", []):
        history.append(ClaimHistoryEntry(**h))

    return ClaimSubmission(
        member_id=inp["member_id"],
        policy_id=inp.get("policy_id", "PLUM_GHI_2024"),
        claim_category=inp["claim_category"],
        treatment_date=inp["treatment_date"],
        claimed_amount=inp["claimed_amount"],
        hospital_name=inp.get("hospital_name"),
        ytd_claims_amount=inp.get("ytd_claims_amount", 0),
        documents=docs,
        claims_history=history,
        simulate_component_failure=inp.get("simulate_component_failure", False),
    )


def _check_match(expected: dict, actual: dict) -> dict:
    """Check if the actual result matches the expected outcome."""
    checks = []
    all_passed = True

    # Check decision match
    expected_decision = expected.get("decision")
    actual_decision = actual.get("decision")

    if expected_decision is None:
        # Expect no decision (document error cases)
        if actual.get("document_errors") and len(actual["document_errors"]) > 0:
            checks.append({"check": "No decision (document error)", "passed": True})
        elif actual_decision is None:
            checks.append({"check": "No decision", "passed": True})
        else:
            checks.append({"check": "Expected no decision", "passed": False, "detail": f"Got {actual_decision}"})
            all_passed = False
    else:
        if actual_decision == expected_decision:
            checks.append({"check": f"Decision = {expected_decision}", "passed": True})
        else:
            checks.append({"check": f"Decision = {expected_decision}", "passed": False, "detail": f"Got {actual_decision}"})
            all_passed = False

    # Check approved amount
    if "approved_amount" in expected and expected["approved_amount"] is not None:
        expected_amt = expected["approved_amount"]
        actual_amt = actual.get("approved_amount", 0)
        # Allow small rounding differences
        if abs(expected_amt - (actual_amt or 0)) <= 1:
            checks.append({"check": f"Amount = ₹{expected_amt}", "passed": True})
        else:
            checks.append({"check": f"Amount = ₹{expected_amt}", "passed": False, "detail": f"Got ₹{actual_amt}"})
            all_passed = False

    # Check rejection reasons
    if "rejection_reasons" in expected:
        for reason in expected["rejection_reasons"]:
            if reason in actual.get("rejection_reasons", []):
                checks.append({"check": f"Rejection reason: {reason}", "passed": True})
            else:
                checks.append({"check": f"Rejection reason: {reason}", "passed": False, "detail": f"Not found in {actual.get('rejection_reasons', [])}"})
                all_passed = False

    # Check confidence score bounds
    if "confidence_score" in expected:
        conf_str = expected["confidence_score"]
        actual_conf = actual.get("confidence_score", 0)
        if isinstance(conf_str, str) and conf_str.startswith("above"):
            threshold = float(conf_str.split()[-1])
            if actual_conf > threshold:
                checks.append({"check": f"Confidence {conf_str}", "passed": True, "detail": f"Got {actual_conf}"})
            else:
                checks.append({"check": f"Confidence {conf_str}", "passed": False, "detail": f"Got {actual_conf}"})
                all_passed = False

    return {"passed": all_passed, "checks": checks}


if __name__ == "__main__":
    import uvicorn
    from backend.config import HOST, PORT
    uvicorn.run(app, host=HOST, port=int(PORT))
