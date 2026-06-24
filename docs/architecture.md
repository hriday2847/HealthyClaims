# Architecture Document — CLAMS (Claims Processing System)

## 1. System Overview

CLAMS is an AI-powered health insurance claims processing system that automates the evaluation of OPD claims against policy terms. The system is designed as a **multi-agent pipeline** where each agent is a specialised, isolated component responsible for one phase of claim evaluation.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Next.js Frontend                                │
│  ┌──────────┐  ┌────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │Dashboard │  │Submit Claim│  │ Claim Detail │  │   Eval Report    │  │
│  │          │  │(JSON/File) │  │ + Trace View │  │ (12 Test Cases)  │  │
│  └──────────┘  └────────────┘  └──────────────┘  └──────────────────┘  │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ REST API (JSON / Multipart)
┌──────────────────────────────▼──────────────────────────────────────────┐
│                        FastAPI Backend                                   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    Pipeline Orchestrator                          │   │
│  │                                                                  │   │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │   │
│  │  │  Document     │    │  Document     │    │   Policy     │       │   │
│  │  │  Verifier     │───▶│  Extractor    │───▶│   Engine     │       │   │
│  │  │  (CRITICAL)   │    │              │    │              │       │   │
│  │  └──────────────┘    └──────────────┘    └──────┬───────┘       │   │
│  │         │                                       │               │   │
│  │         │ stops on failure              ┌───────┴───────┐       │   │
│  │         ▼                               │               │       │   │
│  │   [Document Error                  ┌────▼─────┐  ┌──────▼────┐  │   │
│  │    returned early]                 │  Fraud    │  │ Decision  │  │   │
│  │                                    │ Detector  │  │  Engine   │  │   │
│  │                                    └──────────┘  └───────────┘  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐    │
│  │ Policy Loader   │  │  Storage       │  │  Config (.env)         │    │
│  │ (policy_terms   │  │  (JSON file)   │  │  LLM, CORS, etc.     │    │
│  │  .json)         │  │               │  │                        │    │
│  └────────────────┘  └────────────────┘  └────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

## 2. Data Flow

```
Claim Submission (API)
        │
        ▼
┌───────────────────────┐
│   Document Verifier   │──── FAIL ──▶ Return DocumentError (pipeline stops)
│   • required types?   │             specific message: what's wrong & what to do
│   • quality OK?       │
│   • patient names     │
│     consistent?       │
└───────────┬───────────┘
            │ PASS
            ▼
┌───────────────────────┐
│  Document Extractor   │──── FAIL ──▶ Degraded mode (continue with partial data)
│   • structured JSON?  │             confidence score reduced
│   • LLM vision?      │
│   • field extraction  │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│    Policy Engine      │
│   • member lookup     │
│   • submission rules  │
│   • waiting periods   │
│   • exclusions        │
│   • sub-limits/caps   │
│   • network discount  │
│   • co-pay            │
│   • annual OPD limit  │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│   Fraud Detector      │──── non-critical, continues on failure
│   • same-day claims   │
│   • monthly frequency │
│   • high-value flag   │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│   Decision Engine     │
│   Priority logic:     │
│   1. Fraud → MANUAL   │
│   2. Rejection →      │
│      REJECTED         │
│   3. Partial items →  │
│      PARTIAL          │
│   4. Otherwise →      │
│      APPROVED         │
│   + confidence score  │
│   + recommendations   │
└───────────┬───────────┘
            │
            ▼
    ClaimDecision (with full trace)
```

## 3. Component Descriptions

### 3.1 Pipeline Orchestrator (`pipeline/orchestrator.py`)

The central coordinator. Runs agents in sequence, passes context between them, collects traces, and handles the `simulate_component_failure` flag for resilience testing. Does **not** contain business logic — it delegates to agents.

### 3.2 Document Verifier (Agent 1 — CRITICAL)

The only `critical=True` agent. If verification fails, the pipeline halts immediately and returns a `DocumentError` with an actionable, user-facing message. This enforces "catch problems early" — no claim processing happens if the documents are wrong.

**Why critical?** Processing a claim with wrong documents wastes compute and produces misleading results. Early termination is the correct behaviour.

### 3.3 Document Extractor (Agent 2)

Extracts structured fields from documents. Supports two modes:
- **Structured passthrough**: When documents carry structured JSON `content` (test cases, API submissions)
- **LLM vision extraction**: When `ENABLE_LLM_EXTRACTION=true` and documents carry `file_data` (base64), calls GPT-4o vision for OCR/extraction

Marked `critical=False` — if extraction fails, the pipeline continues with degraded confidence.

### 3.4 Policy Engine (Agent 3)

The most complex agent. Evaluates the claim against all policy rules:
- Member eligibility lookup
- Submission rules (minimum amount, deadline)
- Initial and condition-specific waiting periods
- General, dental, and vision exclusions
- Per-claim limits
- Pre-authorization requirements
- Line-item level coverage (for partial approvals)
- Financial calculation: sub-limit → network discount → co-pay → annual OPD cap

**Financial calculation order**: Network discount is applied *before* co-pay, not after. This is a deliberate design decision matching how Indian health insurance typically works — the insured pays co-pay on the discounted amount, not the full amount.

### 3.5 Fraud Detector (Agent 4)

Checks for suspicious patterns using the policy's fraud thresholds. Produces a fraud score (0–1) and signals. Non-critical — a crash here doesn't halt the pipeline.

### 3.6 Decision Engine (Agent 5)

Synthesizes all upstream outputs into a final decision using strict priority ordering:
1. Fraud signals above threshold → `MANUAL_REVIEW`
2. Policy rejection reasons → `REJECTED`
3. Partial line-item coverage → `PARTIAL`
4. Everything passes → `APPROVED`

Also computes the final confidence score by combining extraction confidence, component failures, and decision clarity.

## 4. Design Decisions & Trade-offs

### Chosen: Sequential Pipeline (not Parallel Agents)

**Why:** The agents have natural data dependencies (extractor needs verifier output, policy engine needs extracted data). A parallel architecture would require speculative execution and merge logic with no real latency benefit for 5 lightweight agents.

**Rejected alternative:** We considered running Policy Engine and Fraud Detector in parallel (they're independent). Decided against it because the latency savings are negligible (both run in <5ms) and sequential execution simplifies debugging.

### Chosen: JSON File Storage (not Database)

**Why:** For a demo/assignment system, a JSON file backed by an in-memory dict is simple, zero-dependency, and sufficient. The thread-safe locking prevents corruption during concurrent writes.

**Trade-off:** No query capabilities, no indexing, doesn't scale beyond a single process. Acknowledged as a demo limitation.

**At 10x scale:** Would replace with PostgreSQL or DynamoDB, add a proper ORM layer, and use connection pooling.

### Chosen: Structured Content Passthrough + Optional LLM

**Why:** Test cases provide structured JSON documents. For a working demo, we accept structured input and add LLM extraction as an opt-in feature behind a feature flag. This lets the system work reliably without an API key while supporting real document uploads when configured.

**Trade-off:** The system doesn't *require* LLM extraction, which means it can't demonstrate real OCR in the default configuration.

### Chosen: Policy Rules from JSON (not Hardcoded)

**Why:** The assignment explicitly requires this. All coverage, limits, exclusions, and thresholds are read from `policy_terms.json` at startup. Changing the policy requires only editing the JSON file.

### Chosen: Pydantic for All Data Models

**Why:** Pydantic provides runtime validation, serialisation, and clear schema definitions. Every input and output is a Pydantic model, which means type mismatches fail fast at the API boundary rather than deep in business logic.

## 5. Failure Handling Philosophy

The system follows a **"degrade, don't crash"** philosophy:

1. **Critical agents** (Document Verifier only) halt the pipeline on failure — this is intentional since proceeding with bad documents produces garbage.
2. **Non-critical agents** catch exceptions via `BaseAgent.run()`, log the error in the trace, return a degraded `AgentResult`, and let the pipeline continue.
3. **Component failures** are tracked explicitly (`component_failures` list) and propagated to the Decision Engine, which reduces the confidence score and recommends manual review.
4. **LLM failures** (timeouts, parsing errors, API limits) are caught in the extractor and treated as "no content available" — the system falls back to the claimed amount and reduces confidence.

## 6. Observability

Every agent produces:
- **CheckResults**: Named checks with pass/fail, human-readable detail, and optional structured data
- **TraceSteps**: Agent name, status (SUCCESS/FAILED/DEGRADED), duration in ms, input/output summaries, checks, errors, warnings

The full trace is attached to every `ClaimDecision` and rendered as an interactive timeline in the UI. An operations team member can reconstruct *exactly* why any claim received any decision.

## 7. Scaling to 10x Load

### Current bottlenecks:
- **JSON file storage**: Single-process, no concurrent write safety beyond threading locks
- **Synchronous request handling**: Each claim blocks a worker thread
- **In-memory policy cache**: Fine for single process, breaks with multiple workers

### Strategy for 10x (750,000 claims/year):

1. **Storage**: Replace JSON file with PostgreSQL. Add proper indexing on member_id, status, created_at.
2. **Async processing**: Move claim processing to a task queue (Celery + Redis or AWS SQS). API returns a claim ID immediately, processes asynchronously, notifies via webhook.
3. **Horizontal scaling**: Multiple API workers behind a load balancer. Stateless request handling (all state in DB).
4. **Policy caching**: Redis-backed policy cache with TTL-based invalidation.
5. **LLM extraction**: Rate-limit aware queue for OpenAI calls. Batch processing during off-peak. Consider self-hosted vision models for cost control.
6. **Monitoring**: Structured logging (JSON), Prometheus metrics for pipeline latency/throughput, alerting on error rates.

## 8. Known Limitations

1. **No real authentication/authorization** — the API is open. Production would need JWT + RBAC.
2. **Family floater logic** is modelled in the policy schema but not fully implemented in the policy engine — the combined limit across dependents is not enforced.
3. **No idempotency** — submitting the same claim twice creates two separate records.
4. **Document content is trusted** — in structured mode, the system doesn't verify that the content matches the declared document type.
5. **Date parsing** assumes YYYY-MM-DD format. Regional date formats (DD-MM-YYYY common in India) would need a parser.
6. **Storage doesn't persist across Docker restarts** unless a volume is mounted for `claims_store.json`.
