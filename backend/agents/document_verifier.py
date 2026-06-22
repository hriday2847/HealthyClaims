"""Agent 1: Document Verifier.

Validates uploaded documents BEFORE any claim processing begins.
Checks:
  - Required document types are present for the claim category
  - Document quality is sufficient (not UNREADABLE)
  - Patient names are consistent across all documents
"""

from __future__ import annotations

from typing import Any

from backend.agents.base import AgentResult, BaseAgent
from backend.models.claim import ClaimSubmission
from backend.models.decision import CheckResult, DocumentError
from backend.services.policy_loader import get_document_requirements, get_member, load_policy


class DocumentVerifierAgent(BaseAgent):
    name = "Document Verifier"
    critical = True  # Pipeline must stop if verification fails

    def execute(self, context: dict[str, Any]) -> AgentResult:
        submission: ClaimSubmission = context["submission"]
        policy = context["policy"]

        errors: list[DocumentError] = []
        checks: list[CheckResult] = []
        warnings: list[str] = []

        # ── Check 1: Required document types ──────────────────────
        doc_reqs = get_document_requirements(policy, submission.claim_category.value)
        if doc_reqs:
            uploaded_types = [d.actual_type.upper() for d in submission.documents]
            missing = []
            for req in doc_reqs.required:
                if req.upper() not in uploaded_types:
                    missing.append(req)

            if missing:
                # Build a specific error message (not generic!)
                uploaded_str = ", ".join(set(uploaded_types))
                missing_str = ", ".join(missing)
                msg = (
                    f"Your {submission.claim_category.value.lower()} claim requires the following "
                    f"document(s) that were not found: {missing_str}. "
                    f"You uploaded: {uploaded_str}. "
                    f"Please upload the missing document(s) and resubmit."
                )
                errors.append(
                    DocumentError(
                        error_type="WRONG_DOCUMENT",
                        message=msg,
                        affected_documents=[d.file_id for d in submission.documents],
                        required_action=f"Upload the following document type(s): {missing_str}",
                    )
                )
                checks.append(CheckResult(
                    check_name="Required Document Types",
                    passed=False,
                    detail=f"Missing required documents: {missing_str}. Uploaded: {uploaded_str}",
                ))
            else:
                checks.append(CheckResult(
                    check_name="Required Document Types",
                    passed=True,
                    detail=f"All required documents present: {', '.join(doc_reqs.required)}",
                ))
        else:
            checks.append(CheckResult(
                check_name="Required Document Types",
                passed=True,
                detail="No specific document requirements found for this category",
            ))

        # ── Check 2: Document quality ─────────────────────────────
        for doc in submission.documents:
            quality = (doc.quality or "GOOD").upper()
            if quality == "UNREADABLE":
                doc_name = doc.file_name or doc.file_id
                doc_type = doc.actual_type.replace("_", " ").lower()
                msg = (
                    f"The {doc_type} you uploaded ('{doc_name}') is unreadable — "
                    f"it appears to be blurry or too low quality to process. "
                    f"Please re-upload a clearer photo or scan of your {doc_type}."
                )
                errors.append(
                    DocumentError(
                        error_type="UNREADABLE",
                        message=msg,
                        affected_documents=[doc.file_id],
                        required_action=f"Re-upload a clear copy of your {doc_type}",
                    )
                )
                checks.append(CheckResult(
                    check_name=f"Document Quality — {doc.file_id}",
                    passed=False,
                    detail=f"Document '{doc_name}' is UNREADABLE",
                ))
            else:
                checks.append(CheckResult(
                    check_name=f"Document Quality — {doc.file_id}",
                    passed=True,
                    detail=f"Quality is {quality}",
                ))

        # ── Check 3: Patient name consistency ─────────────────────
        patient_names: dict[str, str] = {}  # file_id -> name found

        for doc in submission.documents:
            name = None
            # Check explicit patient_name_on_doc field
            if doc.patient_name_on_doc:
                name = doc.patient_name_on_doc
            # Check content.patient_name
            elif doc.content and "patient_name" in doc.content:
                name = doc.content["patient_name"]
            if name:
                patient_names[doc.file_id] = name.strip()

        if len(set(patient_names.values())) > 1:
            names_detail = "; ".join(
                f"Document {fid}: '{name}'" for fid, name in patient_names.items()
            )
            msg = (
                f"The documents you uploaded appear to belong to different patients. "
                f"We found: {names_detail}. "
                f"All documents in a single claim must belong to the same patient. "
                f"Please verify and re-upload the correct documents."
            )
            errors.append(
                DocumentError(
                    error_type="PATIENT_MISMATCH",
                    message=msg,
                    affected_documents=list(patient_names.keys()),
                    required_action="Ensure all documents belong to the same patient",
                )
            )
            checks.append(CheckResult(
                check_name="Patient Name Consistency",
                passed=False,
                detail=f"Mismatched patient names: {names_detail}",
            ))
        elif patient_names:
            the_name = list(patient_names.values())[0]
            # Also verify the name matches the member on the policy
            member = get_member(policy, submission.member_id)
            if member:
                member_name_lower = member.name.lower()
                doc_name_lower = the_name.lower()
                # Check if names loosely match (contains)
                name_match = (
                    member_name_lower in doc_name_lower
                    or doc_name_lower in member_name_lower
                )
                if not name_match:
                    # Check dependents
                    # For now just warn — don't hard-fail on name mismatch with member
                    warnings.append(
                        f"Document patient name '{the_name}' does not exactly match "
                        f"member name '{member.name}'. This may be fine if the claim "
                        f"is for a dependent."
                    )
            checks.append(CheckResult(
                check_name="Patient Name Consistency",
                passed=True,
                detail=f"All documents reference patient: {the_name}",
            ))
        else:
            checks.append(CheckResult(
                check_name="Patient Name Consistency",
                passed=True,
                detail="No patient names found on documents to cross-check",
            ))

        # ── Result ────────────────────────────────────────────────
        if errors:
            return AgentResult(
                success=False,
                data={"document_errors": [e.model_dump() for e in errors]},
                checks=checks,
                error=errors[0].message,
                warnings=warnings,
            )

        return AgentResult(success=True, checks=checks, warnings=warnings)
