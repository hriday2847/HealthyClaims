"""Agent 2: Document Extractor.

Extracts structured information from uploaded medical documents.

For test cases that provide structured content directly, this agent simply
normalises and passes through. For real document uploads (images/PDFs),
this agent would call an LLM vision model for extraction.
"""

from __future__ import annotations

from typing import Any

from backend.agents.base import AgentResult, BaseAgent
from backend.models.claim import ClaimSubmission
from backend.models.decision import CheckResult


class DocumentExtractorAgent(BaseAgent):
    name = "Document Extractor"
    critical = False  # Pipeline can continue with partial extraction

    def execute(self, context: dict[str, Any]) -> AgentResult:
        submission: ClaimSubmission = context["submission"]
        checks: list[CheckResult] = []
        warnings: list[str] = []

        extracted = {
            "patient_name": None,
            "doctor_name": None,
            "doctor_registration": None,
            "diagnosis": None,
            "treatment": None,
            "medicines": [],
            "tests_ordered": [],
            "hospital_name": None,
            "line_items": [],
            "total_amount": None,
            "treatment_date": submission.treatment_date,
        }

        confidence_adjustments: list[float] = []

        for doc in submission.documents:
            content = doc.content
            if not content:
                warnings.append(
                    f"Document {doc.file_id} ({doc.actual_type}) has no extractable content"
                )
                confidence_adjustments.append(-0.1)
                checks.append(CheckResult(
                    check_name=f"Extract — {doc.file_id}",
                    passed=False,
                    detail="No content available for extraction",
                ))
                continue

            # Extract fields from the structured content
            fields_extracted = 0

            if "patient_name" in content and content["patient_name"]:
                extracted["patient_name"] = content["patient_name"]
                fields_extracted += 1

            if "doctor_name" in content and content["doctor_name"]:
                extracted["doctor_name"] = content["doctor_name"]
                fields_extracted += 1

            if "doctor_registration" in content and content["doctor_registration"]:
                extracted["doctor_registration"] = content["doctor_registration"]
                fields_extracted += 1

            if "diagnosis" in content and content["diagnosis"]:
                extracted["diagnosis"] = content["diagnosis"]
                fields_extracted += 1

            if "treatment" in content and content["treatment"]:
                extracted["treatment"] = content["treatment"]
                fields_extracted += 1

            if "medicines" in content and content["medicines"]:
                extracted["medicines"] = content["medicines"]
                fields_extracted += 1

            if "tests_ordered" in content and content["tests_ordered"]:
                extracted["tests_ordered"] = content["tests_ordered"]
                fields_extracted += 1

            if "hospital_name" in content and content["hospital_name"]:
                extracted["hospital_name"] = content["hospital_name"]
                fields_extracted += 1

            if "line_items" in content and content["line_items"]:
                extracted["line_items"] = content["line_items"]
                fields_extracted += 1

            if "total" in content and content["total"] is not None:
                extracted["total_amount"] = content["total"]
                fields_extracted += 1

            if "date" in content and content["date"]:
                extracted["treatment_date"] = content["date"]
                fields_extracted += 1

            if "test_name" in content:
                extracted["tests_ordered"].append(content["test_name"])
                fields_extracted += 1

            checks.append(CheckResult(
                check_name=f"Extract — {doc.file_id} ({doc.actual_type})",
                passed=fields_extracted > 0,
                detail=f"Extracted {fields_extracted} field(s) from {doc.actual_type}",
                data={"fields_extracted": fields_extracted},
            ))

            if fields_extracted == 0:
                confidence_adjustments.append(-0.05)

        # Use hospital name from submission if not found in documents
        if not extracted["hospital_name"] and submission.hospital_name:
            extracted["hospital_name"] = submission.hospital_name

        # If no total found in documents, use claimed amount
        if extracted["total_amount"] is None:
            extracted["total_amount"] = submission.claimed_amount

        # Calculate extraction confidence
        base_confidence = 1.0
        for adj in confidence_adjustments:
            base_confidence += adj
        base_confidence = max(0.3, min(1.0, base_confidence))
        extracted["extraction_confidence"] = base_confidence

        if base_confidence < 0.8:
            warnings.append(
                f"Extraction confidence is low ({base_confidence:.2f}) — "
                f"some document fields could not be extracted"
            )

        return AgentResult(
            success=True,
            data={"extracted": extracted},
            checks=checks,
            warnings=warnings,
        )
