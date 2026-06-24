"""Agent 2: Document Extractor.

Extracts structured information from uploaded medical documents.

For test cases that provide structured content directly, this agent simply
normalises and passes through. For real document uploads (images/PDFs),
this agent calls an LLM vision model for extraction when ENABLE_LLM_EXTRACTION
is enabled.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.agents.base import AgentResult, BaseAgent
from backend.config import ENABLE_LLM_EXTRACTION, LLM_MODEL, LLM_TIMEOUT_SECONDS, OPENAI_API_KEY
from backend.models.claim import ClaimSubmission
from backend.models.decision import CheckResult

logger = logging.getLogger(__name__)

# LLM extraction prompt for medical document parsing
_EXTRACTION_PROMPT = """You are a medical document parser for an Indian health insurance claims system.
Extract the following fields from this medical document image. Return ONLY valid JSON, no markdown.

Fields to extract:
- patient_name: string or null
- doctor_name: string or null
- doctor_registration: string or null (format: STATE/XXXXX/YYYY)
- diagnosis: string or null
- treatment: string or null
- medicines: list of strings or []
- tests_ordered: list of strings or []
- hospital_name: string or null
- line_items: list of {description: string, amount: number} or []
- total: number or null
- date: string (YYYY-MM-DD format) or null

Handle:
- Handwritten prescriptions (best effort)
- Indian medical abbreviations (HTN=Hypertension, T2DM=Type 2 Diabetes, etc.)
- Partial/blurry text (extract what's readable, leave unreadable fields as null)

Return JSON only:"""


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

            # If no structured content but file_data exists, try LLM extraction
            if not content and doc.file_data and ENABLE_LLM_EXTRACTION:
                llm_result = self._extract_via_llm(doc.file_data, doc.actual_type)
                if llm_result:
                    content = llm_result
                    checks.append(CheckResult(
                        check_name=f"LLM Extract — {doc.file_id} ({doc.actual_type})",
                        passed=True,
                        detail=f"Extracted structured content via {LLM_MODEL} vision",
                    ))
                else:
                    warnings.append(
                        f"LLM extraction failed for document {doc.file_id} ({doc.actual_type})"
                    )
                    confidence_adjustments.append(-0.15)
                    checks.append(CheckResult(
                        check_name=f"LLM Extract — {doc.file_id}",
                        passed=False,
                        detail="LLM extraction returned no usable result",
                    ))

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

    @staticmethod
    def _extract_via_llm(file_data: str, doc_type: str) -> dict | None:
        """Call OpenAI GPT-4o vision to extract structured data from a document image.

        Args:
            file_data: Base64-encoded image data.
            doc_type: The document type hint (e.g., PRESCRIPTION, HOSPITAL_BILL).

        Returns:
            Parsed dict of extracted fields, or None on failure.
        """
        if not OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY not set — skipping LLM extraction")
            return None

        try:
            from openai import OpenAI

            client = OpenAI(api_key=OPENAI_API_KEY, timeout=LLM_TIMEOUT_SECONDS)

            # Determine media type (assume JPEG if not clear)
            media_type = "image/jpeg"
            if file_data.startswith("/9j/"):
                media_type = "image/jpeg"
            elif file_data.startswith("iVBOR"):
                media_type = "image/png"
            elif file_data.startswith("JVBER"):
                media_type = "application/pdf"

            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"{_EXTRACTION_PROMPT}\n\nDocument type hint: {doc_type}"},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{media_type};base64,{file_data}",
                                    "detail": "high",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=2000,
                temperature=0,
            )

            raw_text = response.choices[0].message.content.strip()
            # Strip markdown code fences if present
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]

            parsed = json.loads(raw_text)
            return parsed if isinstance(parsed, dict) else None

        except Exception as exc:
            logger.warning(f"LLM extraction failed: {exc}")
            return None
