from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


RiskLevel = Literal["Low", "Medium", "High"]
ProviderName = Literal["mock", "openai", "azure_openai"]
FocusArea = Literal["portfolio", "revenue", "billing", "collections"]


class SummaryMetrics(BaseModel):
    revenue_plan: float
    revenue_recognized: float
    revenue_remaining: float
    revenue_forecast: float
    revenue_gap: float
    revenue_completion_pct: float
    total_unbilled: float
    overdue_amount: float
    high_risk_projects: int
    medium_risk_projects: int


class RevenueRow(BaseModel):
    account_name: str
    project_code: str
    project_name: str
    delivery_unit: str
    account_manager: str
    contract_value: float
    revenue_plan: float
    revenue_recognized: float
    revenue_remaining: float
    revenue_forecast: float
    revenue_gap: float
    revenue_completion_pct: float
    revenue_burn_rate: float
    risk_level: RiskLevel
    last_revenue_update: str
    unbilled_amount: float
    billing_delay_days: int
    overdue_days: int
    outstanding_collection: float


class AlertItem(BaseModel):
    severity: RiskLevel
    focus_area: FocusArea
    account_name: str
    project_code: str
    title: str
    message: str
    suggested_action: str
    score: float


class CollectionRow(BaseModel):
    account_name: str
    project_code: str
    invoice_number: str
    invoice_amount: float
    collected_amount: float
    outstanding_amount: float
    due_date: str
    overdue_days: int
    status: str


class ProviderStatus(BaseModel):
    provider: ProviderName
    model: str
    available: bool
    detail: str


class FollowUpDraft(BaseModel):
    nudge: str
    subject: str
    body: str
    recommended_action: str


class AgentRequest(BaseModel):
    account_name: str | None = None
    project_code: str | None = None
    focus_area: FocusArea = "revenue"
    provider: ProviderName = "mock"
    question: str | None = None


class AgentResponse(BaseModel):
    provider: ProviderName
    account_name: str
    project_code: str | None = None
    focus_area: FocusArea
    summary: str
    risk_level: RiskLevel
    supporting_facts: list[str]
    nudge: str
    email_subject: str
    email_body: str
    recommended_action: str
    trace_id: str | None = None
    trace_url: str | None = None


class ReportResponse(BaseModel):
    summary: SummaryMetrics
    top_accounts: list[dict[str, str | float]]
    top_delivery_units: list[dict[str, str | float]]
    narrative: str


class DataResetResponse(BaseModel):
    workbook_path: str
    database_path: str
    records_loaded: int
