from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["Low", "Medium", "High"]
ProviderName = Literal["mock", "openai", "azure_openai"]
AgentKey = Literal[
    "revenue_realization",
    "billing_trigger",
    "unbilled_revenue",
    "collection_monitoring",
    "revenue_forecasting",
]
EntityType = Literal["project", "milestone", "invoice", "account"]
ChannelName = Literal["mock_email", "gmail"]


class OverviewSummary(BaseModel):
    revenue_plan: float
    revenue_recognized: float
    revenue_forecast: float
    invoices_generated: int
    unbilled_revenue: float
    outstanding_receivables: float
    overdue_amount: float
    revenue_at_risk: float


class FormulaInput(BaseModel):
    key: str
    label: str
    value: float | str
    display_value: str
    description: str


class ThresholdCheck(BaseModel):
    metric_key: str
    label: str
    current_value: float
    current_display: str
    medium_value: float
    medium_display: str
    high_value: float
    high_display: str
    breached_level: RiskLevel | None = None
    description: str


class AgentAnalysis(BaseModel):
    headline: str
    why_triggered: str
    current_status: str
    recommended_action: str
    formula_inputs: list[FormulaInput]
    threshold_checks: list[ThresholdCheck]
    calculation_notes: list[str]
    confidence_score: float | None = None
    confidence_display: str | None = None


class RevenueKpiSummary(BaseModel):
    revenue_plan: float
    revenue_recognized: float
    revenue_remaining: float
    revenue_forecast: float
    revenue_gap: float
    revenue_completion_pct: float


class RevenueRealizationRow(BaseModel):
    entity_type: EntityType = "project"
    entity_id: int
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
    revenue_delay_days: int
    unbilled_amount: float = 0.0
    outstanding_collection: float = 0.0
    analysis: AgentAnalysis


class BillingKpiSummary(BaseModel):
    billable_amount: float
    invoices_generated: int
    invoices_pending: int
    unbilled_revenue: float
    average_billing_delay: float
    billing_risk_amount: float


class BillingMonitoringRow(BaseModel):
    entity_type: EntityType = "milestone"
    entity_id: int
    account_name: str
    project_code: str
    delivery_unit: str
    account_manager: str
    billing_type: str
    billing_milestone: str
    milestone_completion_date: str
    billable_amount: float
    billed_amount: float
    unbilled_amount: float
    invoice_generated: bool
    invoice_number: str | None
    invoice_date: str | None
    billing_delay_days: int
    billing_status: str
    risk_level: RiskLevel
    account_manager_response: str
    analysis: AgentAnalysis


class UnbilledRevenueKpiSummary(BaseModel):
    total_revenue_recognized: float
    total_revenue_billed: float
    total_unbilled_revenue: float
    average_days_unbilled: float
    high_risk_unbilled_revenue: float


class UnbilledRevenueRow(BaseModel):
    entity_type: EntityType = "project"
    entity_id: int
    account_name: str
    project_code: str
    delivery_unit: str
    account_manager: str
    contract_value: float
    revenue_recognized: float
    revenue_billed: float
    unbilled_revenue: float
    days_unbilled: int
    billing_owner: str
    risk_level: RiskLevel
    analysis: AgentAnalysis


class CollectionKpiSummary(BaseModel):
    total_invoiced: float
    total_collected: float
    outstanding_receivables: float
    dso: float
    overdue_amount: float
    high_risk_receivables: float


class CollectionMonitoringRow(BaseModel):
    entity_type: EntityType = "invoice"
    entity_id: int
    account_name: str
    invoice_number: str
    project_code: str
    invoice_amount: float
    invoice_date: str
    payment_due_date: str
    amount_received: float
    outstanding_balance: float
    days_outstanding: int
    overdue_days: int
    collection_risk: RiskLevel
    account_manager: str
    collection_status: str
    client_response_status: str
    analysis: AgentAnalysis


class ForecastKpiSummary(BaseModel):
    revenue_plan: float
    revenue_recognized: float
    revenue_forecast: float
    revenue_gap: float
    forecast_confidence_score: float


class RevenueForecastRow(BaseModel):
    entity_type: EntityType = "project"
    entity_id: int
    account_name: str
    project_code: str
    delivery_unit: str
    account_manager: str
    revenue_plan: float
    revenue_recognized: float
    revenue_forecast: float
    revenue_gap: float
    forecast_confidence: float
    risk_level: RiskLevel
    forecast_explanation: str
    analysis: AgentAnalysis


class AgentNudge(BaseModel):
    id: str
    agent_key: AgentKey
    entity_type: EntityType
    entity_id: int
    severity: RiskLevel
    account_name: str
    project_code: str | None = None
    title: str
    message: str
    suggested_action: str
    current_status: str
    score: float


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
    agent_key: AgentKey
    entity_type: EntityType
    entity_id: int
    provider: ProviderName = "mock"
    question: str | None = None


class AgentResponse(BaseModel):
    provider: ProviderName
    agent_key: AgentKey
    entity_type: EntityType
    entity_id: int
    account_name: str
    project_code: str | None = None
    summary: str
    risk_level: RiskLevel
    supporting_facts: list[str]
    nudge: str
    email_subject: str
    email_body: str
    recommended_action: str
    trace_id: str | None = None
    trace_url: str | None = None


class ActionApproveRequest(AgentRequest):
    channel: ChannelName = "mock_email"
    approved_by: str = "BFM Lead"


class ActionApproveResponse(BaseModel):
    action_id: int
    status: str
    channel: ChannelName
    notification_status: str
    recipient_email: str
    thread_id: str | None = None


class RiskThresholdItem(BaseModel):
    id: int
    agent_key: AgentKey
    metric_key: str
    label: str
    unit: str
    medium_value: float
    high_value: float
    description: str


class ThresholdUpdateRequest(BaseModel):
    medium_value: float = Field(ge=0)
    high_value: float = Field(ge=0)


class NotificationRecord(BaseModel):
    id: int
    action_id: int | None
    agent_key: AgentKey
    entity_type: EntityType
    entity_id: int
    direction: str
    channel: str
    subject: str
    message_excerpt: str
    recipient_email: str
    sender_email: str | None
    thread_id: str | None
    status: str
    sent_at: str | None
    received_at: str | None
    created_at: str


class IntegrationStatus(BaseModel):
    channel: str
    configured: bool
    detail: str
    last_sync_at: str | None = None


class GmailSyncResponse(BaseModel):
    synced_threads: int
    updated_actions: int
    updated_entities: int
    detail: str


class PortfolioNarrative(BaseModel):
    headline: str
    narrative: str
    top_accounts: list[dict[str, str | float]]
    top_delivery_units: list[dict[str, str | float]]


class RevenueSection(BaseModel):
    summary: RevenueKpiSummary
    rows: list[RevenueRealizationRow]
    nudges: list[AgentNudge]


class BillingSection(BaseModel):
    summary: BillingKpiSummary
    rows: list[BillingMonitoringRow]
    nudges: list[AgentNudge]


class UnbilledSection(BaseModel):
    summary: UnbilledRevenueKpiSummary
    rows: list[UnbilledRevenueRow]
    nudges: list[AgentNudge]


class CollectionsSection(BaseModel):
    summary: CollectionKpiSummary
    rows: list[CollectionMonitoringRow]
    nudges: list[AgentNudge]


class ForecastSection(BaseModel):
    summary: ForecastKpiSummary
    rows: list[RevenueForecastRow]
    nudges: list[AgentNudge]


class DashboardResponse(BaseModel):
    generated_at: str
    overview: OverviewSummary
    narrative: PortfolioNarrative
    queue: list[AgentNudge]
    revenue_realization: RevenueSection
    billing_trigger: BillingSection
    unbilled_revenue: UnbilledSection
    collection_monitoring: CollectionsSection
    revenue_forecasting: ForecastSection
    thresholds: list[RiskThresholdItem]
    notifications: list[NotificationRecord]
    integrations: list[IntegrationStatus]


class DataResetResponse(BaseModel):
    workbook_path: str
    database_path: str
    records_loaded: int
