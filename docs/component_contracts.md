# Component Contracts

This document defines the interface contract for every significant component in the CLAMS pipeline. Each contract specifies inputs, outputs, and error conditions precisely enough that another engineer could reimplement the component without reading its source code.

---

## 1. PipelineOrchestrator

**Location:** `backend/pipeline/orchestrator.py`

### Interface

```python
class PipelineOrchestrator:
    def __init__(self, policy_path: str | None = None):
        """Initialise with an optional policy JSON path. Defaults to project-root policy_terms.json."""

    def process_claim(self, submission: ClaimSubmission) -> ClaimDecision:
        """Process a claim through the full multi-agent pipeline."""
```

### Input: `ClaimSubmission`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `member_id` | `str` | Yes | Member ID from the policy roster (e.g., `"EMP001"`) |
| `policy_id` | `str` | No | Defaults to `"PLUM_GHI_2024"` |
| `claim_category` | `ClaimCategory` enum | Yes | One of: `CONSULTATION`, `DIAGNOSTIC`, `PHARMACY`, `DENTAL`, `VISION`, `ALTERNATIVE_MEDICINE` |
| `treatment_date` | `str` | Yes | Format: `YYYY-MM-DD` |
| `claimed_amount` | `float` | Yes | Total claim amount in INR |
| `hospital_name` | `str` | No | Name of the treating hospital |
| `ytd_claims_amount` | `float` | No | Year-to-date claims total for this member. Defaults to `0` |
| `documents` | `list[ClaimDocument]` | Yes | One or more documents (see below) |
| `claims_history` | `list[ClaimHistoryEntry]` | No | Previous claims for fraud detection |
| `simulate_component_failure` | `bool` | No | If `true`, the Document Extractor simulates a crash (for resilience testing) |

### Input: `ClaimDocument`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file_id` | `str` | Yes | Unique identifier for this document |
| `file_name` | `str` | No | Original filename |
| `actual_type` | `str` | Yes | Document type: `PRESCRIPTION`, `HOSPITAL_BILL`, `LAB_REPORT`, `PHARMACY_BILL`, `DENTAL_REPORT`, `DISCHARGE_SUMMARY` |
| `content` | `dict` | No | Structured JSON content (for test cases / API submissions) |
| `file_data` | `str` | No | Base64-encoded image/PDF for LLM extraction |
| `quality` | `str` | No | `GOOD`, `FAIR`, `POOR`, or `UNREADABLE`. Defaults to `GOOD` |
| `patient_name_on_doc` | `str` | No | Patient name found on the document (for cross-referencing) |

### Output: `ClaimDecision`

| Field | Type | Description |
|-------|------|-------------|
| `decision` | `Decision \| None` | `APPROVED`, `PARTIAL`, `REJECTED`, `MANUAL_REVIEW`, or `None` (document error) |
| `approved_amount` | `float \| None` | Final approved amount in INR |
| `rejection_reasons` | `list[str]` | Reason codes: `WAITING_PERIOD`, `EXCLUDED_CONDITION`, `PRE_AUTH_MISSING`, `PER_CLAIM_EXCEEDED`, `MEMBER_NOT_FOUND`, `BELOW_MINIMUM`, `SUBMISSION_DEADLINE_EXCEEDED`, `ANNUAL_LIMIT_EXHAUSTED` |
| `confidence_score` | `float` | 0.0–1.0 confidence in the decision |
| `amount_breakdown` | `AmountBreakdown \| None` | Step-by-step financial calculation |
| `document_errors` | `list[DocumentError]` | Document problems (only when pipeline stopped early) |
| `fraud_signals` | `list[str]` | Human-readable fraud signal descriptions |
| `trace` | `list[TraceStep]` | Full execution trace with per-agent results |
| `summary` | `str` | Human-readable decision summary |
| `recommendations` | `list[str]` | Actionable next steps for the member/ops team |

### Errors

- The orchestrator **never raises exceptions** to the caller. All errors are captured in the `ClaimDecision` output (either as `document_errors` or within the `trace`).
- If a critical agent (Document Verifier) fails, the pipeline returns immediately with `decision=None` and `document_errors` populated.
- If a non-critical agent crashes, the pipeline continues with degraded data and the failure is recorded in `trace` and `component_failures`.

---

## 2. DocumentVerifierAgent

**Location:** `backend/agents/document_verifier.py`
**Classification:** CRITICAL — pipeline stops on failure.

### Contract

```
Input context:
  - submission: ClaimSubmission
  - policy: PolicyTerms

Output (AgentResult):
  - success: bool
  - data.document_errors: list[DocumentError]  (only when success=False)
  - checks: list[CheckResult]
  - warnings: list[str]
```

### Checks Performed

| Check | Pass Condition | Failure Output |
|-------|---------------|----------------|
| Required Document Types | All required document types for the `claim_category` are present in `documents[].actual_type` | `DocumentError(error_type="WRONG_DOCUMENT", message=<specific message naming missing and uploaded types>, required_action=<what to upload>)` |
| Document Quality | No document has `quality="UNREADABLE"` | `DocumentError(error_type="UNREADABLE", message=<names the specific document>, required_action="Re-upload a clear copy")` |
| Patient Name Consistency | All `patient_name_on_doc` values across documents are identical (case-insensitive) | `DocumentError(error_type="PATIENT_MISMATCH", message=<lists each document with the name found>, required_action="Ensure all documents belong to the same patient")` |

### Error Contract

When `success=False`, `data["document_errors"]` is a list of `DocumentError` objects:

| Field | Type | Description |
|-------|------|-------------|
| `error_type` | `str` | `WRONG_DOCUMENT`, `UNREADABLE`, or `PATIENT_MISMATCH` |
| `message` | `str` | Specific, actionable message (NOT generic) |
| `affected_documents` | `list[str]` | `file_id`s of the problematic documents |
| `required_action` | `str` | What the user must do to fix the issue |

---

## 3. DocumentExtractorAgent

**Location:** `backend/agents/document_extractor.py`
**Classification:** Non-critical — pipeline continues on failure with degraded confidence.

### Contract

```
Input context:
  - submission: ClaimSubmission  (accesses documents with content/file_data)
  - policy: PolicyTerms

Output (AgentResult):
  - success: bool (always True unless an unrecoverable error occurs)
  - data.extracted: dict (the extracted structured data — see fields below)
  - checks: list[CheckResult]
  - warnings: list[str]
```

### Extracted Fields

| Field | Type | Source |
|-------|------|--------|
| `patient_name` | `str \| None` | From document content or LLM extraction |
| `doctor_name` | `str \| None` | From document content |
| `doctor_registration` | `str \| None` | From document content |
| `diagnosis` | `str \| None` | From document content |
| `treatment` | `str \| None` | From document content |
| `medicines` | `list[str]` | From prescription content |
| `tests_ordered` | `list[str]` | From prescription or lab report |
| `hospital_name` | `str \| None` | From document content, falls back to `submission.hospital_name` |
| `line_items` | `list[dict]` | `[{description: str, amount: float}]` from bill content |
| `total_amount` | `float \| None` | From bill content, falls back to `submission.claimed_amount` |
| `treatment_date` | `str` | From document content, falls back to `submission.treatment_date` |
| `extraction_confidence` | `float` | 0.3–1.0 confidence in the extraction quality |

### LLM Extraction Mode

When `ENABLE_LLM_EXTRACTION=true` and a document has `file_data` but no `content`:
1. Sends the base64-encoded image to GPT-4o vision with a structured extraction prompt
2. Parses the JSON response into the standard extracted fields
3. On failure: logs a warning, reduces confidence by 0.15, continues with empty content

---

## 4. PolicyEngineAgent

**Location:** `backend/agents/policy_engine.py`
**Classification:** Non-critical.

### Contract

```
Input context:
  - submission: ClaimSubmission
  - policy: PolicyTerms
  - extracted: dict  (from DocumentExtractorAgent output)

Output (AgentResult):
  - data.policy.rejection_reasons: list[str]
  - data.policy.approved_amount: float  (only when no rejections)
  - data.policy.amount_breakdown: dict  (serialised AmountBreakdown)
  - data.policy.is_partial: bool
  - data.policy.approved_items: list[dict]
  - data.policy.rejected_items: list[dict]
  - checks: list[CheckResult]
```

### Checks Performed (in order)

| # | Check | Rejection Reason |
|---|-------|-----------------|
| 0 | Minimum claim amount (≥ ₹500) | `BELOW_MINIMUM` |
| 0 | Submission deadline (within 30 days of treatment) | `SUBMISSION_DEADLINE_EXCEEDED` |
| 1 | Member exists in policy roster | `MEMBER_NOT_FOUND` |
| 2 | Initial waiting period (30 days from join date) | `WAITING_PERIOD` |
| 3 | Condition-specific waiting period (e.g., 90 days for diabetes) | `WAITING_PERIOD` |
| 4 | General exclusions + dental/vision-specific exclusions | `EXCLUDED_CONDITION` |
| 5 | Per-claim limit (≤ ₹5,000) | `PER_CLAIM_EXCEEDED` |
| 6 | Pre-authorization for high-value tests (MRI/CT/PET above threshold) | `PRE_AUTH_MISSING` |
| 7 | Line-item level exclusions (approved vs rejected items) | — (affects partial/full) |
| 8 | Financial calculation (sub-limit → network discount → co-pay → annual OPD cap) | `ANNUAL_LIMIT_EXHAUSTED` |

### Financial Calculation Order

```
claimed_amount
  │
  ├── Line-item exclusions ──▶ eligible_amount (sum of approved items)
  │
  ├── Sub-limit cap ──▶ min(eligible_amount, category.sub_limit)
  │
  ├── Network discount ──▶ eligible × (1 - discount_pct/100)   [if network hospital]
  │
  ├── Co-pay ──▶ after_discount × (1 - copay_pct/100)
  │
  └── Annual OPD limit cap ──▶ min(after_copay, remaining_annual_budget)
                                                               ▼
                                                       approved_amount
```

---

## 5. FraudDetectorAgent

**Location:** `backend/agents/fraud_detector.py`
**Classification:** Non-critical.

### Contract

```
Input context:
  - submission: ClaimSubmission  (accesses claims_history, claimed_amount)
  - policy: PolicyTerms  (accesses fraud_thresholds)

Output (AgentResult):
  - data.fraud.fraud_score: float  (0.0–1.0)
  - data.fraud.fraud_signals: list[str]  (human-readable signal descriptions)
  - data.fraud.recommend_manual_review: bool
  - checks: list[CheckResult]
```

### Fraud Signals

| Signal | Trigger | Score Impact |
|--------|---------|-------------|
| `MULTIPLE_SAME_DAY_CLAIMS` | Same-day claims > `same_day_claims_limit` (2) | +0.5 |
| `HIGH_MONTHLY_FREQUENCY` | Monthly claims > `monthly_claims_limit` (6) | +0.3 |
| `HIGH_VALUE_CLAIM` | Amount > `high_value_claim_threshold` (₹25,000) | +0.2 |
| `AUTO_MANUAL_REVIEW` | Amount > `auto_manual_review_above` (₹25,000) | +0.1 |

**Manual review threshold:** `fraud_score ≥ fraud_score_manual_review_threshold` (0.80)

---

## 6. DecisionEngineAgent

**Location:** `backend/agents/decision_engine.py`
**Classification:** Non-critical.

### Contract

```
Input context:
  - policy_result: dict  (from PolicyEngineAgent)
  - fraud_result: dict  (from FraudDetectorAgent)
  - extraction_result: dict  (from DocumentExtractorAgent)
  - component_failures: list[str]

Output (AgentResult):
  - data.decision: str  (Decision enum value)
  - data.approved_amount: float
  - data.rejection_reasons: list[str]
  - data.confidence_score: float
  - data.amount_breakdown: dict | None
  - data.fraud_signals: list[str]
  - data.summary: str
  - data.recommendations: list[str]
```

### Decision Priority

| Priority | Condition | Decision | Amount |
|----------|-----------|----------|--------|
| 1 (highest) | `fraud.recommend_manual_review == True` | `MANUAL_REVIEW` | As calculated |
| 2 | `rejection_reasons` is non-empty | `REJECTED` | `0` |
| 3 | `is_partial == True` (some line items excluded) | `PARTIAL` | Sum of approved items after discounts |
| 4 (lowest) | All checks pass | `APPROVED` | Full calculated amount |

### Confidence Score Calculation

```
base = 0.95
base *= extraction_confidence           (from extractor)
if component_failures: base *= 0.60     (significant penalty)
if REJECTED with clear reasons: base = max(base, 0.92)   (high confidence in clear rejections)
final = clamp(base, 0.10, 1.00)
```

---

## 7. BaseAgent (Abstract Base Class)

**Location:** `backend/agents/base.py`

### Contract

All agents inherit from `BaseAgent` and must implement:

```python
@abstractmethod
def execute(self, context: dict[str, Any]) -> AgentResult:
    """Core agent logic. Must return AgentResult, never raise to caller."""
```

`BaseAgent.run()` wraps `execute()` with:
- **Automatic timing** (start/end in milliseconds)
- **Exception catching**: If `execute()` raises, the exception is captured in a `TraceStep` with status `FAILED`, and a degraded `AgentResult` is returned
- **Trace generation**: Every call produces a `TraceStep` with agent name, status, duration, input/output summaries, checks, errors, and warnings

### AgentResult

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | Whether the agent completed its core task |
| `data` | `dict` | Agent-specific output data |
| `checks` | `list[CheckResult]` | Named checks performed |
| `error` | `str \| None` | Error message if failed |
| `warnings` | `list[str]` | Non-fatal warnings |

### TraceStep

| Field | Type | Description |
|-------|------|-------------|
| `agent_name` | `str` | Name of the agent |
| `status` | `TraceStepStatus` | `SUCCESS`, `FAILED`, `SKIPPED`, or `DEGRADED` |
| `duration_ms` | `int` | Execution time in milliseconds |
| `input_summary` | `str` | Brief summary of input context |
| `output_summary` | `str` | Brief summary of output (or error) |
| `checks` | `list[CheckResult]` | All checks performed |
| `error` | `str \| None` | Error message if failed |
| `warnings` | `list[str]` | Non-fatal warnings |

---

## 8. Services

### PolicyLoader (`services/policy_loader.py`)

```python
def load_policy(path: str | None = None) -> PolicyTerms
    """Load and cache policy terms from JSON. LRU-cached (1 entry)."""

def get_member(policy: PolicyTerms, member_id: str) -> Member | None
    """Lookup member by ID. Returns None if not found."""

def get_category_config(policy: PolicyTerms, category: str) -> OPDCategory | None
    """Get OPD category config by claim category name."""

def get_document_requirements(policy: PolicyTerms, category: str) -> DocumentRequirements | None
    """Get required/optional document types for a category."""

def is_network_hospital(policy: PolicyTerms, hospital_name: str) -> bool
    """Case-insensitive partial match against the network hospitals list."""
```

### Storage (`services/storage.py`)

```python
def save_claim(claim: StoredClaim) -> StoredClaim
    """Save a claim. Thread-safe. Persists to JSON file."""

def get_claim(claim_id: str) -> StoredClaim | None
    """Retrieve by ID. Returns None if not found."""

def get_all_claims() -> list[StoredClaim]
    """All claims, newest first."""

def clear_claims() -> None
    """Delete all claims (for testing)."""
```
