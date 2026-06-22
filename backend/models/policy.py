"""Pydantic models for policy terms deserialization."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class PolicyHolder(BaseModel):
    company_name: str
    employee_count: int
    policy_start_date: str
    policy_end_date: str
    renewal_status: str


class FamilyFloater(BaseModel):
    enabled: bool
    combined_limit: float
    covered_relationships: list[str]


class Coverage(BaseModel):
    sum_insured_per_employee: float
    annual_opd_limit: float
    per_claim_limit: float
    family_floater: FamilyFloater


class OPDCategory(BaseModel):
    sub_limit: float
    copay_percent: float
    network_discount_percent: Optional[float] = 0
    requires_prescription: bool = False
    requires_pre_auth: bool = False
    pre_auth_threshold: Optional[float] = None
    high_value_tests_requiring_pre_auth: Optional[list[str]] = None
    covered: bool = True
    branded_drug_copay_percent: Optional[float] = None
    generic_mandatory: Optional[bool] = None
    requires_dental_report: Optional[bool] = None
    requires_registered_practitioner: Optional[bool] = None
    max_sessions_per_year: Optional[int] = None
    covered_procedures: Optional[list[str]] = None
    excluded_procedures: Optional[list[str]] = None
    covered_items: Optional[list[str]] = None
    excluded_items: Optional[list[str]] = None
    covered_systems: Optional[list[str]] = None


class WaitingPeriods(BaseModel):
    initial_waiting_period_days: int
    pre_existing_conditions_days: int
    specific_conditions: dict[str, int]


class Exclusions(BaseModel):
    conditions: list[str]
    dental_exclusions: Optional[list[str]] = None
    vision_exclusions: Optional[list[str]] = None


class PreAuthorization(BaseModel):
    required_for: list[str]
    validity_days: int


class SubmissionRules(BaseModel):
    deadline_days_from_treatment: int
    minimum_claim_amount: float
    currency: str


class FraudThresholds(BaseModel):
    same_day_claims_limit: int
    monthly_claims_limit: int
    high_value_claim_threshold: float
    auto_manual_review_above: float
    fraud_score_manual_review_threshold: float


class Member(BaseModel):
    member_id: str
    name: str
    date_of_birth: str
    gender: str
    relationship: str
    join_date: Optional[str] = None
    dependents: Optional[list[str]] = None
    primary_member_id: Optional[str] = None


class DocumentRequirements(BaseModel):
    required: list[str]
    optional: list[str] = Field(default_factory=list)


class PolicyTerms(BaseModel):
    policy_id: str
    policy_name: str
    insurer: str
    policy_holder: PolicyHolder
    coverage: Coverage
    opd_categories: dict[str, OPDCategory]
    waiting_periods: WaitingPeriods
    exclusions: Exclusions
    pre_authorization: PreAuthorization
    network_hospitals: list[str]
    submission_rules: SubmissionRules
    document_requirements: dict[str, DocumentRequirements]
    fraud_thresholds: FraudThresholds
    members: list[Member]
