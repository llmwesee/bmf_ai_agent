from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from bfm_agent.gmail import gmail_status
from bfm_agent.models import (
    AgentAction,
    AppConfig,
    BillingMilestone,
    InvoiceRecord,
    NotificationEvent,
    Project,
    RiskThreshold,
)
from bfm_agent.schemas import (
    AgentAnalysis,
    AgentKey,
    AgentNudge,
    BillingKpiSummary,
    BillingMonitoringRow,
    BillingSection,
    CollectionKpiSummary,
    CollectionMonitoringRow,
    CollectionsSection,
    DashboardResponse,
    ForecastKpiSummary,
    ForecastSection,
    FormulaInput,
    IntegrationStatus,
    NotificationRecord,
    OverviewSummary,
    PortfolioNarrative,
    RevenueForecastRow,
    RevenueKpiSummary,
    RevenueRealizationRow,
    RevenueSection,
    RiskLevel,
    RiskThresholdItem,
    ThresholdCheck,
    UnbilledRevenueKpiSummary,
    UnbilledRevenueRow,
    UnbilledSection,
)


RISK_ORDER: dict[str, int] = {"High": 0, "Medium": 1, "Low": 2}


@dataclass
class ProjectSnapshot:
    entity_id: int
    account_name: str
    account_manager: str
    account_manager_email: str
    client_contact_name: str
    client_contact_email: str
    delivery_unit: str
    project_code: str
    project_name: str
    billing_type: str
    billing_owner: str
    billing_owner_email: str
    contract_value: float
    revenue_plan: float
    revenue_recognized: float
    revenue_remaining: float
    revenue_forecast: float
    revenue_gap: float
    revenue_completion_pct: float
    revenue_burn_rate: float
    recognized_last_30_days: float
    pending_pipeline: float
    trend_projection: float
    milestone_projection: float
    pipeline_projection: float
    revenue_delay_days: int
    last_revenue_update: str
    pending_billable_amount: float
    revenue_billed: float
    unbilled_revenue: float
    days_unbilled: int
    outstanding_receivables: float
    overdue_amount: float
    forecast_confidence: float
    forecast_explanation: str
    invoice_count: int


class AnalyticsService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.today = date.today()

    def _projects(self) -> list[Project]:
        result = self.session.scalars(
            select(Project).options(
                joinedload(Project.account),
                joinedload(Project.milestones),
                joinedload(Project.invoices),
            )
        )
        return list(result.unique().all())

    def _threshold_lookup(self) -> dict[tuple[str, str], RiskThreshold]:
        return {(item.agent_key, item.metric_key): item for item in self.session.scalars(select(RiskThreshold)).all()}

    def thresholds(self) -> list[RiskThresholdItem]:
        thresholds = self.session.scalars(select(RiskThreshold).order_by(RiskThreshold.agent_key, RiskThreshold.metric_key)).all()
        return [self._threshold_item(item) for item in thresholds]

    def update_threshold(self, threshold_id: int, medium_value: float, high_value: float) -> RiskThresholdItem:
        threshold = self.session.get(RiskThreshold, threshold_id)
        if threshold is None:
            raise ValueError("Threshold not found.")
        threshold.medium_value = medium_value
        threshold.high_value = high_value
        self.session.flush()
        return self._threshold_item(threshold)

    def _format_value(self, value: float | str, unit: str) -> str:
        if isinstance(value, str):
            return value
        if unit == "currency":
            return f"${value:,.0f}"
        if unit == "percent":
            return f"{value:.0%}"
        if unit == "days":
            return f"{int(round(value))} days"
        if unit == "count":
            return f"{int(round(value))}"
        return f"{value:,.2f}"

    def _threshold_checks(
        self,
        agent_key: AgentKey,
        metrics: dict[str, float],
        thresholds: dict[tuple[str, str], RiskThreshold],
    ) -> tuple[RiskLevel, list[ThresholdCheck], list[str]]:
        severity: RiskLevel = "Low"
        checks: list[ThresholdCheck] = []
        breaches: list[str] = []

        for metric_key, value in metrics.items():
            threshold = thresholds.get((agent_key, metric_key))
            if threshold is None:
                continue
            breached_level: RiskLevel | None = None
            if value >= threshold.high_value:
                severity = "High"
                breached_level = "High"
            elif value >= threshold.medium_value and severity != "High":
                severity = "Medium"
                breached_level = "Medium"

            current_display = self._format_value(value, threshold.unit)
            medium_display = self._format_value(threshold.medium_value, threshold.unit)
            high_display = self._format_value(threshold.high_value, threshold.unit)
            checks.append(
                ThresholdCheck(
                    metric_key=metric_key,
                    label=threshold.label,
                    current_value=value,
                    current_display=current_display,
                    medium_value=threshold.medium_value,
                    medium_display=medium_display,
                    high_value=threshold.high_value,
                    high_display=high_display,
                    breached_level=breached_level,
                    description=threshold.description,
                )
            )
            if breached_level is not None:
                breaches.append(
                    f"{threshold.label} is at {current_display}, breaching the {breached_level.lower()} threshold "
                    f"({high_display if breached_level == 'High' else medium_display})."
                )

        return severity, checks, breaches

    @staticmethod
    def _why_triggered(breaches: list[str], fallback: str) -> str:
        return " ".join(breaches) if breaches else fallback

    def _metric_input(self, key: str, label: str, value: float | str, unit: str, description: str) -> FormulaInput:
        return FormulaInput(
            key=key,
            label=label,
            value=value,
            display_value=self._format_value(value, unit),
            description=description,
        )

    def overview(self) -> OverviewSummary:
        snapshots = self._project_snapshots()
        revenue_plan = sum(item.revenue_plan for item in snapshots)
        revenue_forecast = sum(item.revenue_forecast for item in snapshots)
        return OverviewSummary(
            revenue_plan=revenue_plan,
            revenue_recognized=sum(item.revenue_recognized for item in snapshots),
            revenue_forecast=revenue_forecast,
            invoices_generated=sum(item.invoice_count for item in snapshots),
            unbilled_revenue=sum(item.unbilled_revenue for item in snapshots),
            outstanding_receivables=sum(item.outstanding_receivables for item in snapshots),
            overdue_amount=sum(item.overdue_amount for item in snapshots),
            revenue_at_risk=sum(max(item.revenue_plan - item.revenue_forecast, 0.0) for item in snapshots),
        )

    def dashboard(self) -> DashboardResponse:
        overview = self.overview()
        revenue = self.revenue_section()
        billing = self.billing_section()
        unbilled = self.unbilled_section()
        collections = self.collection_section()
        forecast = self.forecast_section()
        queue = sorted(
            revenue.nudges + billing.nudges + unbilled.nudges + collections.nudges + forecast.nudges,
            key=lambda item: (RISK_ORDER[item.severity], -item.score),
        )[:15]
        return DashboardResponse(
            generated_at=datetime.utcnow().isoformat(),
            overview=overview,
            narrative=self.narrative(),
            queue=queue,
            revenue_realization=revenue,
            billing_trigger=billing,
            unbilled_revenue=unbilled,
            collection_monitoring=collections,
            revenue_forecasting=forecast,
            thresholds=self.thresholds(),
            notifications=self.notifications(),
            integrations=self.integrations(),
        )

    def revenue_section(self) -> RevenueSection:
        thresholds = self._threshold_lookup()
        rows: list[RevenueRealizationRow] = []
        nudges: list[AgentNudge] = []
        for snapshot in self._project_snapshots():
            shortfall_ratio = max(snapshot.revenue_plan - snapshot.revenue_forecast, 0.0) / snapshot.revenue_plan if snapshot.revenue_plan else 0.0
            risk, threshold_checks, breaches = self._threshold_checks(
                "revenue_realization",
                {
                    "forecast_shortfall_ratio": shortfall_ratio,
                    "revenue_delay_days": float(snapshot.revenue_delay_days),
                },
                thresholds,
            )
            current_status = self._entity_status("revenue_realization", "project", snapshot.entity_id, default="Monitoring")
            recommended_action = "Review revenue closure blockers and confirm pending revenue recognition dates."
            analysis = AgentAnalysis(
                headline=f"{snapshot.account_name} / {snapshot.project_code} revenue realization",
                why_triggered=self._why_triggered(
                    breaches,
                    "Revenue recognition is being monitored against plan, forecast trend, and stale-update thresholds.",
                ),
                current_status=current_status,
                recommended_action=recommended_action,
                formula_inputs=[
                    self._metric_input("revenue_plan", "Revenue plan", snapshot.revenue_plan, "currency", "Monthly target for the selected project."),
                    self._metric_input("revenue_recognized", "Revenue recognized", snapshot.revenue_recognized, "currency", "Revenue already recognized in the current month."),
                    self._metric_input("revenue_remaining", "Revenue remaining", snapshot.revenue_remaining, "currency", "Revenue plan minus recognized revenue."),
                    self._metric_input("revenue_forecast", "Revenue forecast", snapshot.revenue_forecast, "currency", "Recognized revenue plus trend, milestone, and pipeline projection."),
                    self._metric_input("revenue_gap", "Revenue gap", snapshot.revenue_gap, "currency", "Revenue forecast minus revenue plan."),
                    self._metric_input("revenue_completion_pct", "Revenue completion", snapshot.revenue_completion_pct, "percent", "Revenue recognized divided by revenue plan."),
                    self._metric_input("revenue_burn_rate", "Revenue burn rate", snapshot.revenue_burn_rate, "currency", "Recognized revenue in the last 7 days, treated as weekly burn."),
                    self._metric_input("forecast_shortfall_ratio", "Forecast shortfall ratio", shortfall_ratio, "percent", "max(revenue plan - revenue forecast, 0) divided by revenue plan."),
                    self._metric_input("revenue_delay_days", "Revenue update delay", float(snapshot.revenue_delay_days), "days", "Days since the last revenue recognition update."),
                ],
                threshold_checks=threshold_checks,
                calculation_notes=[
                    f"Revenue remaining = {self._format_value(snapshot.revenue_plan, 'currency')} - {self._format_value(snapshot.revenue_recognized, 'currency')} = {self._format_value(snapshot.revenue_remaining, 'currency')}.",
                    f"Revenue completion = {self._format_value(snapshot.revenue_recognized, 'currency')} / {self._format_value(snapshot.revenue_plan, 'currency')} = {self._format_value(snapshot.revenue_completion_pct, 'percent')}.",
                    f"Forecast uses {self._format_value(snapshot.revenue_burn_rate, 'currency')} weekly burn, {self._format_value(snapshot.pending_billable_amount, 'currency')} pending billable milestones, and {self._format_value(snapshot.pending_pipeline, 'currency')} near-term pipeline.",
                    f"Workflow status is {current_status}; the operational revenue signal also considers {self._format_value(float(snapshot.revenue_delay_days), 'days')} since the last update.",
                ],
            )
            rows.append(
                RevenueRealizationRow(
                    entity_id=snapshot.entity_id,
                    account_name=snapshot.account_name,
                    project_code=snapshot.project_code,
                    project_name=snapshot.project_name,
                    delivery_unit=snapshot.delivery_unit,
                    account_manager=snapshot.account_manager,
                    contract_value=snapshot.contract_value,
                    revenue_plan=snapshot.revenue_plan,
                    revenue_recognized=snapshot.revenue_recognized,
                    revenue_remaining=snapshot.revenue_remaining,
                    revenue_forecast=snapshot.revenue_forecast,
                    revenue_gap=snapshot.revenue_gap,
                    revenue_completion_pct=snapshot.revenue_completion_pct,
                    revenue_burn_rate=snapshot.revenue_burn_rate,
                    risk_level=risk,
                    last_revenue_update=snapshot.last_revenue_update,
                    revenue_delay_days=snapshot.revenue_delay_days,
                    unbilled_amount=snapshot.unbilled_revenue,
                    outstanding_collection=snapshot.overdue_amount,
                    analysis=analysis,
                )
            )
            if risk != "Low":
                nudges.append(
                    AgentNudge(
                        id=f"revenue-{snapshot.entity_id}",
                        agent_key="revenue_realization",
                        entity_type="project",
                        entity_id=snapshot.entity_id,
                        severity=risk,
                        account_name=snapshot.account_name,
                        project_code=snapshot.project_code,
                        title=f"{snapshot.account_name} revenue gap",
                        message=(
                            f"{snapshot.account_name} account revenue is running {shortfall_ratio:.0%} below monthly target. "
                            "Do you want me to follow up with the account manager?"
                        ),
                        suggested_action=recommended_action,
                        current_status=current_status,
                        score=max(shortfall_ratio * 100, float(snapshot.revenue_delay_days)),
                    )
                )
        rows.sort(key=lambda row: (RISK_ORDER[row.risk_level], row.account_name, row.project_code))
        total_plan = sum(row.revenue_plan for row in rows)
        total_recognized = sum(row.revenue_recognized for row in rows)
        summary = RevenueKpiSummary(
            revenue_plan=total_plan,
            revenue_recognized=total_recognized,
            revenue_remaining=sum(row.revenue_remaining for row in rows),
            revenue_forecast=sum(row.revenue_forecast for row in rows),
            revenue_gap=sum(row.revenue_gap for row in rows),
            revenue_completion_pct=(total_recognized / total_plan) if total_plan else 0.0,
        )
        nudges.sort(key=lambda item: (RISK_ORDER[item.severity], -item.score))
        return RevenueSection(summary=summary, rows=rows, nudges=nudges[:12])

    def billing_section(self) -> BillingSection:
        thresholds = self._threshold_lookup()
        rows: list[BillingMonitoringRow] = []
        nudges: list[AgentNudge] = []
        milestones = self.session.scalars(select(BillingMilestone).options(joinedload(BillingMilestone.project).joinedload(Project.account))).all()
        for milestone in milestones:
            project = milestone.project
            unbilled_amount = max(milestone.billable_amount - milestone.billed_amount, 0.0)
            billing_delay_days = self._billing_delay_days(milestone)
            risk, threshold_checks, breaches = self._threshold_checks(
                "billing_trigger",
                {
                    "billing_delay_days": float(billing_delay_days),
                    "unbilled_amount": unbilled_amount,
                },
                thresholds,
            )
            status = self._billing_status(milestone, billing_delay_days)
            current_status = self._entity_status("billing_trigger", "milestone", milestone.id, default=status)
            recommended_action = "Trigger billing release with the account manager or billing owner."
            analysis = AgentAnalysis(
                headline=f"{project.account.name} / {project.code} billing trigger",
                why_triggered=self._why_triggered(
                    breaches,
                    "The milestone is being checked for billing delay and pending billable amount thresholds.",
                ),
                current_status=current_status,
                recommended_action=recommended_action,
                formula_inputs=[
                    self._metric_input("billable_amount", "Billable amount", milestone.billable_amount, "currency", "Value eligible for invoicing once the milestone is completed."),
                    self._metric_input("billed_amount", "Billed amount", milestone.billed_amount, "currency", "Amount already invoiced for the milestone."),
                    self._metric_input("unbilled_amount", "Unbilled amount", unbilled_amount, "currency", "Billable amount minus billed amount."),
                    self._metric_input("billing_delay_days", "Billing delay", float(billing_delay_days), "days", "Invoice date or today minus milestone completion date."),
                ],
                threshold_checks=threshold_checks,
                calculation_notes=[
                    f"Unbilled amount = {self._format_value(milestone.billable_amount, 'currency')} - {self._format_value(milestone.billed_amount, 'currency')} = {self._format_value(unbilled_amount, 'currency')}.",
                    f"Billing delay is measured from {milestone.completion_date.isoformat()} to {milestone.invoice_date.isoformat() if milestone.invoice_date else self.today.isoformat()} = {self._format_value(float(billing_delay_days), 'days')}.",
                    "Billing status becomes Completed once the account manager approves the milestone or the billed amount reaches the full billable amount.",
                    f"Operational status is {status}; workflow status is {current_status}.",
                ],
            )
            rows.append(
                BillingMonitoringRow(
                    entity_id=milestone.id,
                    account_name=project.account.name,
                    project_code=project.code,
                    delivery_unit=project.account.delivery_unit,
                    account_manager=project.account.account_manager,
                    billing_type=project.billing_type,
                    billing_milestone=milestone.milestone_name,
                    milestone_completion_date=milestone.completion_date.isoformat(),
                    billable_amount=milestone.billable_amount,
                    billed_amount=milestone.billed_amount,
                    unbilled_amount=unbilled_amount,
                    invoice_generated=milestone.invoice_generated,
                    invoice_number=milestone.invoice_number,
                    invoice_date=milestone.invoice_date.isoformat() if milestone.invoice_date else None,
                    billing_delay_days=billing_delay_days,
                    billing_status=status,
                    risk_level=risk,
                    account_manager_response=milestone.account_manager_response,
                    analysis=analysis,
                )
            )
            if risk != "Low":
                nudges.append(
                    AgentNudge(
                        id=f"billing-{milestone.id}",
                        agent_key="billing_trigger",
                        entity_type="milestone",
                        entity_id=milestone.id,
                        severity=risk,
                        account_name=project.account.name,
                        project_code=project.code,
                        title=f"{project.code} billing trigger pending",
                        message=(
                            f"Billing milestone for {project.account.name} Project {project.code} was completed {billing_delay_days} "
                            "days ago, but the invoice has not been generated. Do you want me to follow up with the account manager?"
                        ),
                        suggested_action=recommended_action,
                        current_status=current_status,
                        score=max(float(billing_delay_days), unbilled_amount / 10_000),
                    )
                )
        rows.sort(key=lambda row: (RISK_ORDER[row.risk_level], -row.unbilled_amount, -row.billing_delay_days))
        delayed = [row for row in rows if row.billing_delay_days > 0]
        summary = BillingKpiSummary(
            billable_amount=sum(row.billable_amount for row in rows),
            invoices_generated=sum(1 for row in rows if row.invoice_generated),
            invoices_pending=sum(1 for row in rows if not row.invoice_generated or row.unbilled_amount > 0),
            unbilled_revenue=sum(row.unbilled_amount for row in rows),
            average_billing_delay=(sum(row.billing_delay_days for row in delayed) / len(delayed)) if delayed else 0.0,
            billing_risk_amount=sum(row.unbilled_amount for row in rows if row.risk_level == "High"),
        )
        nudges.sort(key=lambda item: (RISK_ORDER[item.severity], -item.score))
        return BillingSection(summary=summary, rows=rows, nudges=nudges[:12])

    def unbilled_section(self) -> UnbilledSection:
        thresholds = self._threshold_lookup()
        rows: list[UnbilledRevenueRow] = []
        nudges: list[AgentNudge] = []
        for snapshot in self._project_snapshots():
            risk, threshold_checks, breaches = self._threshold_checks(
                "unbilled_revenue",
                {
                    "days_unbilled": float(snapshot.days_unbilled),
                    "unbilled_amount": snapshot.unbilled_revenue,
                },
                thresholds,
            )
            current_status = self._entity_status("unbilled_revenue", "project", snapshot.entity_id, default="Monitoring")
            recommended_action = "Escalate pending billing approvals and trigger invoice creation."
            analysis = AgentAnalysis(
                headline=f"{snapshot.account_name} / {snapshot.project_code} unbilled revenue",
                why_triggered=self._why_triggered(
                    breaches,
                    "Recognized revenue is being monitored against unbilled amount and aging thresholds.",
                ),
                current_status=current_status,
                recommended_action=recommended_action,
                formula_inputs=[
                    self._metric_input("revenue_recognized", "Revenue recognized", snapshot.revenue_recognized, "currency", "Revenue recognized for the current month."),
                    self._metric_input("revenue_billed", "Revenue billed", snapshot.revenue_billed, "currency", "Invoices already generated for the project."),
                    self._metric_input("unbilled_revenue", "Unbilled revenue", snapshot.unbilled_revenue, "currency", "Revenue recognized minus revenue billed."),
                    self._metric_input("days_unbilled", "Days unbilled", float(snapshot.days_unbilled), "days", "Days since the oldest pending billable milestone was completed."),
                    self._metric_input("revenue_forecast", "Revenue forecast", snapshot.revenue_forecast, "currency", "Projected revenue close while billing is still pending."),
                ],
                threshold_checks=threshold_checks,
                calculation_notes=[
                    f"Unbilled revenue = {self._format_value(snapshot.revenue_recognized, 'currency')} - {self._format_value(snapshot.revenue_billed, 'currency')} = {self._format_value(snapshot.unbilled_revenue, 'currency')}.",
                    f"Aging is measured from the oldest open billing milestone and currently stands at {self._format_value(float(snapshot.days_unbilled), 'days')}.",
                    f"Pending billable milestone value feeding this exposure is {self._format_value(snapshot.pending_billable_amount, 'currency')}.",
                    f"Workflow status is {current_status}; finance follow-up remains open until billing is triggered.",
                ],
            )
            rows.append(
                UnbilledRevenueRow(
                    entity_id=snapshot.entity_id,
                    account_name=snapshot.account_name,
                    project_code=snapshot.project_code,
                    delivery_unit=snapshot.delivery_unit,
                    account_manager=snapshot.account_manager,
                    contract_value=snapshot.contract_value,
                    revenue_recognized=snapshot.revenue_recognized,
                    revenue_billed=snapshot.revenue_billed,
                    unbilled_revenue=snapshot.unbilled_revenue,
                    days_unbilled=snapshot.days_unbilled,
                    billing_owner=snapshot.billing_owner,
                    risk_level=risk,
                    analysis=analysis,
                )
            )
            if risk != "Low":
                nudges.append(
                    AgentNudge(
                        id=f"unbilled-{snapshot.entity_id}",
                        agent_key="unbilled_revenue",
                        entity_type="project",
                        entity_id=snapshot.entity_id,
                        severity=risk,
                        account_name=snapshot.account_name,
                        project_code=snapshot.project_code,
                        title=f"{snapshot.project_code} unbilled exposure",
                        message=(
                            f"{snapshot.account_name} Project {snapshot.project_code} has ${snapshot.unbilled_revenue:,.0f} "
                            f"of revenue recognized but not invoiced for the past {snapshot.days_unbilled} days. "
                            "Do you want me to follow up with the account manager to trigger billing?"
                        ),
                        suggested_action=recommended_action,
                        current_status=current_status,
                        score=max(float(snapshot.days_unbilled), snapshot.unbilled_revenue / 10_000),
                    )
                )
        rows.sort(key=lambda row: (RISK_ORDER[row.risk_level], -row.unbilled_revenue, -row.days_unbilled))
        filtered = [row for row in rows if row.days_unbilled > 0]
        summary = UnbilledRevenueKpiSummary(
            total_revenue_recognized=sum(row.revenue_recognized for row in rows),
            total_revenue_billed=sum(row.revenue_billed for row in rows),
            total_unbilled_revenue=sum(row.unbilled_revenue for row in rows),
            average_days_unbilled=(sum(row.days_unbilled for row in filtered) / len(filtered)) if filtered else 0.0,
            high_risk_unbilled_revenue=sum(row.unbilled_revenue for row in rows if row.risk_level == "High"),
        )
        nudges.sort(key=lambda item: (RISK_ORDER[item.severity], -item.score))
        return UnbilledSection(summary=summary, rows=rows, nudges=nudges[:12])

    def collection_section(self) -> CollectionsSection:
        thresholds = self._threshold_lookup()
        rows: list[CollectionMonitoringRow] = []
        nudges: list[AgentNudge] = []
        invoices = self.session.scalars(select(InvoiceRecord).options(joinedload(InvoiceRecord.project).joinedload(Project.account))).all()
        for invoice in invoices:
            project = invoice.project
            outstanding = max(invoice.invoice_amount - invoice.amount_received, 0.0)
            overdue_days = self._overdue_days(invoice)
            days_outstanding = (self.today - invoice.invoice_date).days
            risk, threshold_checks, breaches = self._threshold_checks(
                "collection_monitoring",
                {
                    "overdue_days": float(overdue_days),
                    "outstanding_balance": outstanding,
                },
                thresholds,
            )
            status = self._collection_status(invoice, overdue_days)
            current_status = self._entity_status("collection_monitoring", "invoice", invoice.id, default=status)
            recommended_action = "Send a payment reminder and notify the account manager of overdue exposure."
            analysis = AgentAnalysis(
                headline=f"{project.account.name} / {invoice.invoice_number} collection monitoring",
                why_triggered=self._why_triggered(
                    breaches,
                    "Collections are being monitored against overdue days and outstanding balance thresholds.",
                ),
                current_status=current_status,
                recommended_action=recommended_action,
                formula_inputs=[
                    self._metric_input("invoice_amount", "Invoice amount", invoice.invoice_amount, "currency", "Gross value of the invoice."),
                    self._metric_input("amount_received", "Amount received", invoice.amount_received, "currency", "Cash collected against the invoice."),
                    self._metric_input("outstanding_balance", "Outstanding balance", outstanding, "currency", "Invoice amount minus amount received."),
                    self._metric_input("days_outstanding", "Days outstanding", float(days_outstanding), "days", "Days since invoice issuance."),
                    self._metric_input("overdue_days", "Overdue days", float(overdue_days), "days", "Days past contractual payment due date while balance remains open."),
                ],
                threshold_checks=threshold_checks,
                calculation_notes=[
                    f"Outstanding balance = {self._format_value(invoice.invoice_amount, 'currency')} - {self._format_value(invoice.amount_received, 'currency')} = {self._format_value(outstanding, 'currency')}.",
                    f"Overdue days are counted from {invoice.due_date.isoformat()} to {self.today.isoformat()} while the invoice remains open, currently {self._format_value(float(overdue_days), 'days')}.",
                    "Collection status becomes Completed once the amount received reaches the invoice amount or a completed client response is synced back.",
                    f"Operational status is {status}; workflow status is {current_status}.",
                ],
            )
            rows.append(
                CollectionMonitoringRow(
                    entity_id=invoice.id,
                    account_name=project.account.name,
                    invoice_number=invoice.invoice_number,
                    project_code=project.code,
                    invoice_amount=invoice.invoice_amount,
                    invoice_date=invoice.invoice_date.isoformat(),
                    payment_due_date=invoice.due_date.isoformat(),
                    amount_received=invoice.amount_received,
                    outstanding_balance=outstanding,
                    days_outstanding=days_outstanding,
                    overdue_days=overdue_days,
                    collection_risk=risk,
                    account_manager=project.account.account_manager,
                    collection_status=status,
                    client_response_status=invoice.client_response_status,
                    analysis=analysis,
                )
            )
            if risk != "Low":
                nudges.append(
                    AgentNudge(
                        id=f"collection-{invoice.id}",
                        agent_key="collection_monitoring",
                        entity_type="invoice",
                        entity_id=invoice.id,
                        severity=risk,
                        account_name=project.account.name,
                        project_code=project.code,
                        title=f"{invoice.invoice_number} overdue collection",
                        message=(
                            f"Invoice {invoice.invoice_number} for {project.account.name} worth ${invoice.invoice_amount:,.0f} "
                            f"is overdue by {overdue_days} days. Do you want me to send a payment reminder to the client?"
                        ),
                        suggested_action=recommended_action,
                        current_status=current_status,
                        score=max(float(overdue_days), outstanding / 10_000),
                    )
                )
        rows.sort(key=lambda row: (RISK_ORDER[row.collection_risk], -row.outstanding_balance, -row.overdue_days))
        dso_source = [((invoice.collected_date or self.today) - invoice.invoice_date).days for invoice in invoices]
        summary = CollectionKpiSummary(
            total_invoiced=sum(row.invoice_amount for row in rows),
            total_collected=sum(row.amount_received for row in rows),
            outstanding_receivables=sum(row.outstanding_balance for row in rows),
            dso=(sum(dso_source) / len(dso_source)) if dso_source else 0.0,
            overdue_amount=sum(row.outstanding_balance for row in rows if row.overdue_days > 0),
            high_risk_receivables=sum(row.outstanding_balance for row in rows if row.collection_risk == "High"),
        )
        nudges.sort(key=lambda item: (RISK_ORDER[item.severity], -item.score))
        return CollectionsSection(summary=summary, rows=rows, nudges=nudges[:12])

    def forecast_section(self) -> ForecastSection:
        thresholds = self._threshold_lookup()
        rows: list[RevenueForecastRow] = []
        nudges: list[AgentNudge] = []
        for snapshot in self._project_snapshots():
            gap_ratio = max(snapshot.revenue_plan - snapshot.revenue_forecast, 0.0) / snapshot.revenue_plan if snapshot.revenue_plan else 0.0
            risk, threshold_checks, breaches = self._threshold_checks(
                "revenue_forecasting",
                {"forecast_gap_ratio": gap_ratio},
                thresholds,
            )
            current_status = self._entity_status("revenue_forecasting", "project", snapshot.entity_id, default="Monitoring")
            recommended_action = "Investigate forecast drivers and recover pending revenue or billing milestones."
            analysis = AgentAnalysis(
                headline=f"{snapshot.account_name} / {snapshot.project_code} revenue forecast",
                why_triggered=self._why_triggered(
                    breaches,
                    "Forecast variance is being monitored against the configured forecast gap ratio threshold.",
                ),
                current_status=current_status,
                recommended_action=recommended_action,
                formula_inputs=[
                    self._metric_input("revenue_plan", "Revenue plan", snapshot.revenue_plan, "currency", "Monthly target for the project."),
                    self._metric_input("revenue_recognized", "Revenue recognized", snapshot.revenue_recognized, "currency", "Revenue recognized so far."),
                    self._metric_input("trend_projection", "Trend projection", snapshot.trend_projection, "currency", "Weekly burn rate extended across the remaining weeks in the month."),
                    self._metric_input("milestone_projection", "Milestone projection", snapshot.milestone_projection, "currency", "Near-term revenue expected from pending billable milestones."),
                    self._metric_input("pipeline_projection", "Pipeline projection", snapshot.pipeline_projection, "currency", "Weighted contribution from pending pipeline opportunities."),
                    self._metric_input("revenue_forecast", "Revenue forecast", snapshot.revenue_forecast, "currency", "Recognized revenue plus trend, milestone, and pipeline projection."),
                    self._metric_input("revenue_gap", "Revenue gap", snapshot.revenue_gap, "currency", "Revenue forecast minus revenue plan."),
                    self._metric_input("forecast_gap_ratio", "Forecast gap ratio", gap_ratio, "percent", "max(revenue plan - revenue forecast, 0) divided by revenue plan."),
                ],
                threshold_checks=threshold_checks,
                calculation_notes=[
                    f"Revenue forecast = {self._format_value(snapshot.revenue_recognized, 'currency')} + {self._format_value(snapshot.trend_projection, 'currency')} + {self._format_value(snapshot.milestone_projection, 'currency')} + {self._format_value(snapshot.pipeline_projection, 'currency')} = {self._format_value(snapshot.revenue_forecast, 'currency')}.",
                    f"Trend projection uses {self._format_value(snapshot.revenue_burn_rate, 'currency')} weekly burn across the remaining month and is capped by contract value.",
                    f"Confidence starts from 92% and is adjusted for {self._format_value(float(snapshot.revenue_delay_days), 'days')} stale updates, {self._format_value(snapshot.pending_billable_amount, 'currency')} pending billable value, forecast gap ratio, and 30-day recognition pace.",
                    f"Workflow status is {current_status}; current forecast confidence is {self._format_value(snapshot.forecast_confidence, 'percent')}.",
                ],
                confidence_score=snapshot.forecast_confidence,
                confidence_display=self._format_value(snapshot.forecast_confidence, "percent"),
            )
            rows.append(
                RevenueForecastRow(
                    entity_id=snapshot.entity_id,
                    account_name=snapshot.account_name,
                    project_code=snapshot.project_code,
                    delivery_unit=snapshot.delivery_unit,
                    account_manager=snapshot.account_manager,
                    revenue_plan=snapshot.revenue_plan,
                    revenue_recognized=snapshot.revenue_recognized,
                    revenue_forecast=snapshot.revenue_forecast,
                    revenue_gap=snapshot.revenue_gap,
                    forecast_confidence=snapshot.forecast_confidence,
                    risk_level=risk,
                    forecast_explanation=snapshot.forecast_explanation,
                    analysis=analysis,
                )
            )
            if risk != "Low":
                nudges.append(
                    AgentNudge(
                        id=f"forecast-{snapshot.entity_id}",
                        agent_key="revenue_forecasting",
                        entity_type="project",
                        entity_id=snapshot.entity_id,
                        severity=risk,
                        account_name=snapshot.account_name,
                        project_code=snapshot.project_code,
                        title=f"{snapshot.account_name} forecast shortfall",
                        message=(
                            f"{snapshot.account_name} account revenue is forecasted to close at ${snapshot.revenue_forecast:,.0f} "
                            f"this month against the ${snapshot.revenue_plan:,.0f} target. "
                            "Do you want me to follow up with the account manager to review pending billing milestones?"
                        ),
                        suggested_action=recommended_action,
                        current_status=current_status,
                        score=max(gap_ratio * 100, (1 - snapshot.forecast_confidence) * 100),
                    )
                )
        rows.sort(key=lambda row: (RISK_ORDER[row.risk_level], row.revenue_gap, row.account_name))
        summary = ForecastKpiSummary(
            revenue_plan=sum(row.revenue_plan for row in rows),
            revenue_recognized=sum(row.revenue_recognized for row in rows),
            revenue_forecast=sum(row.revenue_forecast for row in rows),
            revenue_gap=sum(row.revenue_gap for row in rows),
            forecast_confidence_score=(sum(row.forecast_confidence for row in rows) / len(rows)) if rows else 0.0,
        )
        nudges.sort(key=lambda item: (RISK_ORDER[item.severity], -item.score))
        return ForecastSection(summary=summary, rows=rows, nudges=nudges[:12])

    def narrative(self) -> PortfolioNarrative:
        snapshots = self._project_snapshots()
        account_rollup: dict[str, dict[str, float | str]] = defaultdict(
            lambda: {"account_name": "", "forecast_gap": 0.0, "unbilled_revenue": 0.0, "overdue_amount": 0.0}
        )
        delivery_rollup: dict[str, dict[str, float | str]] = defaultdict(
            lambda: {"delivery_unit": "", "forecast_gap": 0.0, "revenue_forecast": 0.0}
        )
        for snapshot in snapshots:
            account = account_rollup[snapshot.account_name]
            account["account_name"] = snapshot.account_name
            account["forecast_gap"] += snapshot.revenue_gap
            account["unbilled_revenue"] += snapshot.unbilled_revenue
            account["overdue_amount"] += snapshot.overdue_amount

            delivery = delivery_rollup[snapshot.delivery_unit]
            delivery["delivery_unit"] = snapshot.delivery_unit
            delivery["forecast_gap"] += snapshot.revenue_gap
            delivery["revenue_forecast"] += snapshot.revenue_forecast

        total_high_risk = sum(1 for item in self.dashboard_queue() if item.severity == "High")
        overview = self.overview()
        headline = f"{total_high_risk} high-priority finance exceptions need BFM action."
        narrative = (
            f"Portfolio forecast is ${overview.revenue_forecast:,.0f} against a ${overview.revenue_plan:,.0f} plan. "
            f"Unbilled revenue is ${overview.unbilled_revenue:,.0f}, overdue receivables are ${overview.overdue_amount:,.0f}, "
            "and the agent is tracking revenue realization, billing triggers, collections, and forecast risk across project milestones."
        )
        top_accounts = sorted(account_rollup.values(), key=lambda item: float(item["forecast_gap"]))[:5]
        top_delivery_units = sorted(delivery_rollup.values(), key=lambda item: float(item["forecast_gap"]))[:4]
        return PortfolioNarrative(
            headline=headline,
            narrative=narrative,
            top_accounts=top_accounts,
            top_delivery_units=top_delivery_units,
        )

    def dashboard_queue(self) -> list[AgentNudge]:
        sections = [
            self.revenue_section().nudges,
            self.billing_section().nudges,
            self.unbilled_section().nudges,
            self.collection_section().nudges,
            self.forecast_section().nudges,
        ]
        return sorted([item for items in sections for item in items], key=lambda item: (RISK_ORDER[item.severity], -item.score))

    def notifications(self, limit: int = 20) -> list[NotificationRecord]:
        query: Select[tuple[NotificationEvent]] = select(NotificationEvent).order_by(NotificationEvent.created_at.desc()).limit(limit)
        rows = self.session.scalars(query).all()
        return [self._notification_item(row) for row in rows]

    def integrations(self) -> list[IntegrationStatus]:
        gmail = gmail_status()
        last_sync = self.session.scalar(select(AppConfig.value).where(AppConfig.key == "gmail_last_sync_at"))
        return [
            IntegrationStatus(
                channel="gmail",
                configured=gmail.configured,
                detail=gmail.detail,
                last_sync_at=last_sync,
            )
        ]

    def entity_context(self, agent_key: AgentKey, entity_type: str, entity_id: int) -> dict[str, Any]:
        if entity_type == "project":
            snapshot = next((item for item in self._project_snapshots() if item.entity_id == entity_id), None)
            if snapshot is None:
                raise ValueError("Project not found.")
            return {
                "agent_key": agent_key,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "account_name": snapshot.account_name,
                "project_code": snapshot.project_code,
                "recipient_name": self._recipient_name(agent_key, snapshot),
                "recipient_email": self._recipient_email(agent_key, snapshot),
                "account_manager": snapshot.account_manager,
                "billing_owner": snapshot.billing_owner,
                "client_contact_name": snapshot.client_contact_name,
                "summary_metrics": {
                    "revenue_plan": snapshot.revenue_plan,
                    "revenue_recognized": snapshot.revenue_recognized,
                    "revenue_remaining": snapshot.revenue_remaining,
                    "revenue_forecast": snapshot.revenue_forecast,
                    "revenue_gap": snapshot.revenue_gap,
                    "revenue_completion_pct": snapshot.revenue_completion_pct,
                    "revenue_burn_rate": snapshot.revenue_burn_rate,
                    "revenue_delay_days": snapshot.revenue_delay_days,
                    "pending_billable_amount": snapshot.pending_billable_amount,
                    "revenue_billed": snapshot.revenue_billed,
                    "unbilled_revenue": snapshot.unbilled_revenue,
                    "days_unbilled": snapshot.days_unbilled,
                    "outstanding_receivables": snapshot.outstanding_receivables,
                    "forecast_confidence": snapshot.forecast_confidence,
                    "trend_projection": snapshot.trend_projection,
                    "milestone_projection": snapshot.milestone_projection,
                    "pipeline_projection": snapshot.pipeline_projection,
                    "pending_pipeline": snapshot.pending_pipeline,
                    "recognized_last_30_days": snapshot.recognized_last_30_days,
                },
                "primary_record": {
                    "project_name": snapshot.project_name,
                    "delivery_unit": snapshot.delivery_unit,
                    "billing_type": snapshot.billing_type,
                    "last_revenue_update": snapshot.last_revenue_update,
                    "forecast_explanation": snapshot.forecast_explanation,
                },
            }
        if entity_type == "milestone":
            milestone = self.session.get(BillingMilestone, entity_id)
            if milestone is None:
                raise ValueError("Milestone not found.")
            return {
                "agent_key": agent_key,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "account_name": milestone.project.account.name,
                "project_code": milestone.project.code,
                "recipient_name": milestone.project.account.account_manager,
                "recipient_email": milestone.project.account.account_manager_email,
                "account_manager": milestone.project.account.account_manager,
                "billing_owner": milestone.billing_owner,
                "summary_metrics": {
                    "billable_amount": milestone.billable_amount,
                    "billed_amount": milestone.billed_amount,
                    "unbilled_amount": max(milestone.billable_amount - milestone.billed_amount, 0.0),
                    "billing_delay_days": self._billing_delay_days(milestone),
                    "invoice_generated": 1.0 if milestone.invoice_generated else 0.0,
                },
                "primary_record": {
                    "milestone_name": milestone.milestone_name,
                    "completion_date": milestone.completion_date.isoformat(),
                    "account_manager_response": milestone.account_manager_response,
                    "status_note": milestone.status_note or "",
                },
            }
        if entity_type == "invoice":
            invoice = self.session.get(InvoiceRecord, entity_id)
            if invoice is None:
                raise ValueError("Invoice not found.")
            return {
                "agent_key": agent_key,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "account_name": invoice.project.account.name,
                "project_code": invoice.project.code,
                "recipient_name": invoice.project.account.client_contact_name,
                "recipient_email": invoice.project.account.client_contact_email,
                "account_manager": invoice.project.account.account_manager,
                "billing_owner": invoice.project.billing_owner,
                "summary_metrics": {
                    "invoice_amount": invoice.invoice_amount,
                    "amount_received": invoice.amount_received,
                    "outstanding_balance": max(invoice.invoice_amount - invoice.amount_received, 0.0),
                    "days_outstanding": max((self.today - invoice.invoice_date).days, 0),
                    "overdue_days": self._overdue_days(invoice),
                },
                "primary_record": {
                    "invoice_number": invoice.invoice_number,
                    "due_date": invoice.due_date.isoformat(),
                    "client_response_status": invoice.client_response_status,
                    "status_note": invoice.status_note or "",
                },
            }
        raise ValueError("Unsupported entity type.")

    def create_action(
        self,
        agent_key: AgentKey,
        entity_type: str,
        entity_id: int,
        provider: str,
        channel: str,
        subject: str,
        body: str,
        recommended_action: str,
        trace_id: str | None,
        trace_url: str | None,
        approved_by: str,
    ) -> AgentAction:
        context = self.entity_context(agent_key, entity_type, entity_id)
        action = AgentAction(
            agent_key=agent_key,
            entity_type=entity_type,
            entity_id=entity_id,
            account_name=context["account_name"],
            project_code=context.get("project_code"),
            recipient_name=context["recipient_name"],
            recipient_email=context["recipient_email"],
            provider=provider,
            channel=channel,
            subject=subject,
            body=body,
            recommended_action=recommended_action,
            status="Approved",
            approved_by=approved_by,
            latest_trace_id=trace_id,
            latest_trace_url=trace_url,
        )
        self.session.add(action)
        self.session.flush()
        return action

    def record_notification(
        self,
        action_id: int,
        agent_key: AgentKey,
        entity_type: str,
        entity_id: int,
        channel: str,
        subject: str,
        message_excerpt: str,
        recipient_email: str,
        status: str,
        direction: str = "outbound",
        thread_id: str | None = None,
        external_message_id: str | None = None,
        sender_email: str | None = None,
        sent_at: datetime | None = None,
        received_at: datetime | None = None,
    ) -> NotificationEvent:
        event = NotificationEvent(
            action_id=action_id,
            agent_key=agent_key,
            entity_type=entity_type,
            entity_id=entity_id,
            direction=direction,
            channel=channel,
            subject=subject,
            message_excerpt=message_excerpt[:1_200],
            recipient_email=recipient_email,
            sender_email=sender_email,
            thread_id=thread_id,
            external_message_id=external_message_id,
            status=status,
            sent_at=sent_at,
            received_at=received_at,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def pending_gmail_threads(self) -> list[NotificationEvent]:
        events = self.session.scalars(
            select(NotificationEvent)
            .where(NotificationEvent.channel == "gmail")
            .where(NotificationEvent.direction == "outbound")
            .where(NotificationEvent.thread_id.is_not(None))
            .order_by(NotificationEvent.created_at.desc())
        ).all()
        latest: dict[str, NotificationEvent] = {}
        for event in events:
            if event.thread_id and event.thread_id not in latest:
                latest[event.thread_id] = event
        return list(latest.values())

    def set_gmail_last_sync(self, value: str) -> None:
        self.session.merge(AppConfig(key="gmail_last_sync_at", value=value))
        self.session.flush()

    def apply_reply(
        self,
        event: NotificationEvent,
        body: str,
        sender_email: str | None,
        received_at: datetime | None,
        message_id: str | None,
        subject: str,
    ) -> bool:
        action = self.session.get(AgentAction, event.action_id) if event.action_id else None
        if action is None or self._reply_signal(body) == "none":
            return False

        updated = self._complete_entity(action.agent_key, action.entity_type, action.entity_id, body)
        if updated:
            action.status = "Completed"
            action.completed_at = received_at or datetime.utcnow()
            self.record_notification(
                action_id=action.id,
                agent_key=action.agent_key,  # type: ignore[arg-type]
                entity_type=action.entity_type,
                entity_id=action.entity_id,
                channel=event.channel,
                subject=subject,
                message_excerpt=body,
                recipient_email=event.recipient_email,
                sender_email=sender_email,
                direction="inbound",
                status="Reply Received",
                thread_id=event.thread_id,
                external_message_id=message_id,
                received_at=received_at or datetime.utcnow(),
            )
        return updated

    def _project_snapshots(self) -> list[ProjectSnapshot]:
        days_in_month = calendar.monthrange(self.today.year, self.today.month)[1]
        remaining_days = max(days_in_month - self.today.day, 0)
        remaining_weeks = remaining_days / 7 if remaining_days else 0.0
        snapshots: list[ProjectSnapshot] = []
        for project in self._projects():
            pending_billable = sum(max(item.billable_amount - item.billed_amount, 0.0) for item in project.milestones)
            revenue_billed = sum(item.invoice_amount for item in project.invoices)
            outstanding_receivables = sum(max(item.invoice_amount - item.amount_received, 0.0) for item in project.invoices)
            overdue_amount = sum(
                max(item.invoice_amount - item.amount_received, 0.0)
                for item in project.invoices
                if self._overdue_days(item) > 0
            )
            revenue_remaining = max(project.revenue_plan_month - project.revenue_recognized, 0.0)
            trend_projection = project.recognized_last_7_days * remaining_weeks * project.forecast_bias
            milestone_projection = min(pending_billable * 0.10, revenue_remaining)
            pipeline_projection = min(project.pending_pipeline * 0.20, max(revenue_remaining - milestone_projection, 0.0))
            revenue_forecast = min(
                project.contract_value,
                round(project.revenue_recognized + trend_projection + milestone_projection + pipeline_projection, 2),
            )
            revenue_gap = round(revenue_forecast - project.revenue_plan_month, 2)
            pending_dates = [item.completion_date for item in project.milestones if max(item.billable_amount - item.billed_amount, 0.0) > 0]
            days_unbilled = max((self.today - min(pending_dates)).days, 0) if pending_dates else 0
            forecast_gap_ratio = max(project.revenue_plan_month - revenue_forecast, 0.0) / project.revenue_plan_month if project.revenue_plan_month else 0.0
            delay_days = max((self.today - project.last_revenue_update).days, 0)
            confidence = 0.92
            confidence -= min(delay_days / 30, 0.25)
            confidence -= min(pending_billable / max(project.revenue_plan_month, 1), 1.0) * 0.18
            confidence -= forecast_gap_ratio * 0.22
            confidence += min(project.recognized_last_30_days / max(project.revenue_plan_month, 1), 0.12)
            confidence = max(0.55, min(0.96, confidence))
            forecast_explanation = (
                f"Forecast blends the last 7-day revenue burn (${project.recognized_last_7_days:,.0f}/week), "
                f"${pending_billable:,.0f} pending billable milestones, and ${project.pending_pipeline:,.0f} near-term pipeline."
            )
            snapshots.append(
                ProjectSnapshot(
                    entity_id=project.id,
                    account_name=project.account.name,
                    account_manager=project.account.account_manager,
                    account_manager_email=project.account.account_manager_email,
                    client_contact_name=project.account.client_contact_name,
                    client_contact_email=project.account.client_contact_email,
                    delivery_unit=project.account.delivery_unit,
                    project_code=project.code,
                    project_name=project.name,
                    billing_type=project.billing_type,
                    billing_owner=project.billing_owner,
                    billing_owner_email=project.billing_owner_email,
                    contract_value=project.contract_value,
                    revenue_plan=project.revenue_plan_month,
                    revenue_recognized=project.revenue_recognized,
                    revenue_remaining=revenue_remaining,
                    revenue_forecast=revenue_forecast,
                    revenue_gap=revenue_gap,
                    revenue_completion_pct=(project.revenue_recognized / project.revenue_plan_month) if project.revenue_plan_month else 0.0,
                    revenue_burn_rate=project.recognized_last_7_days,
                    recognized_last_30_days=project.recognized_last_30_days,
                    pending_pipeline=project.pending_pipeline,
                    trend_projection=round(trend_projection, 2),
                    milestone_projection=round(milestone_projection, 2),
                    pipeline_projection=round(pipeline_projection, 2),
                    revenue_delay_days=delay_days,
                    last_revenue_update=project.last_revenue_update.isoformat(),
                    pending_billable_amount=pending_billable,
                    revenue_billed=revenue_billed,
                    unbilled_revenue=max(project.revenue_recognized - revenue_billed, 0.0),
                    days_unbilled=days_unbilled,
                    outstanding_receivables=outstanding_receivables,
                    overdue_amount=overdue_amount,
                    forecast_confidence=round(confidence, 2),
                    forecast_explanation=forecast_explanation,
                    invoice_count=len(project.invoices),
                )
            )
        return snapshots

    def _complete_entity(self, agent_key: str, entity_type: str, entity_id: int, body: str) -> bool:
        note = body.strip()[:500]
        if entity_type == "milestone":
            milestone = self.session.get(BillingMilestone, entity_id)
            if milestone is None:
                return False
            project = milestone.project
            milestone.account_manager_response = "Approved"
            milestone.invoice_generated = True
            milestone.billed_amount = milestone.billable_amount
            milestone.invoice_date = self.today
            milestone.status_note = note
            if not milestone.invoice_number:
                milestone.invoice_number = f"AUTO-{project.code}-{milestone.id}"
            invoice = self.session.scalar(select(InvoiceRecord).where(InvoiceRecord.invoice_number == milestone.invoice_number))
            if invoice is None:
                self.session.add(
                    InvoiceRecord(
                        project_id=project.id,
                        invoice_number=milestone.invoice_number,
                        invoice_amount=milestone.billable_amount,
                        amount_received=0.0,
                        invoice_date=self.today,
                        due_date=self.today + timedelta(days=30),
                        collected_date=None,
                        client_contact_name=project.account.client_contact_name,
                        client_contact_email=project.account.client_contact_email,
                        collection_owner=project.billing_owner,
                        collection_owner_email=project.billing_owner_email,
                        client_response_status="Pending",
                        status_note="Auto-created after account manager approval via Gmail.",
                    )
                )
            self.session.flush()
            return True
        if entity_type == "invoice":
            invoice = self.session.get(InvoiceRecord, entity_id)
            if invoice is None:
                return False
            invoice.amount_received = invoice.invoice_amount
            invoice.collected_date = self.today
            invoice.client_response_status = "Completed"
            invoice.status_note = note
            self.session.flush()
            return True
        if entity_type == "project":
            project = self.session.get(Project, entity_id)
            if project is None:
                return False
            if agent_key == "unbilled_revenue":
                for milestone in project.milestones:
                    if max(milestone.billable_amount - milestone.billed_amount, 0.0) > 0:
                        milestone.account_manager_response = "Approved"
                        milestone.invoice_generated = True
                        milestone.billed_amount = milestone.billable_amount
                        milestone.invoice_date = self.today
                        if not milestone.invoice_number:
                            milestone.invoice_number = f"AUTO-{project.code}-{milestone.id}"
            project.last_revenue_update = self.today
            self.session.flush()
            return True
        return False

    def _risk_level(self, agent_key: str, metrics: dict[str, float], thresholds: dict[tuple[str, str], RiskThreshold]) -> RiskLevel:
        return self._threshold_checks(agent_key, metrics, thresholds)[0]

    def _billing_delay_days(self, milestone: BillingMilestone) -> int:
        end_date = milestone.invoice_date or self.today
        return max((end_date - milestone.completion_date).days, 0)

    def _billing_status(self, milestone: BillingMilestone, billing_delay_days: int) -> str:
        if milestone.account_manager_response in {"Approved", "Completed"} or milestone.billed_amount >= milestone.billable_amount:
            return "Completed"
        if billing_delay_days > 0 and not milestone.invoice_generated:
            return "Delayed"
        if milestone.invoice_generated and milestone.billed_amount < milestone.billable_amount:
            return "Partially Billed"
        return "On Time"

    def _overdue_days(self, invoice: InvoiceRecord) -> int:
        if invoice.amount_received >= invoice.invoice_amount:
            return 0
        return max((self.today - invoice.due_date).days, 0)

    def _collection_status(self, invoice: InvoiceRecord, overdue_days: int) -> str:
        if invoice.client_response_status == "Completed" or invoice.amount_received >= invoice.invoice_amount:
            return "Completed"
        if overdue_days > 0:
            return "Overdue"
        if invoice.amount_received > 0:
            return "Partially Collected"
        return "Open"

    def _entity_status(self, agent_key: str, entity_type: str, entity_id: int, default: str) -> str:
        action = self.session.scalar(
            select(AgentAction)
            .where(AgentAction.agent_key == agent_key)
            .where(AgentAction.entity_type == entity_type)
            .where(AgentAction.entity_id == entity_id)
            .order_by(AgentAction.updated_at.desc())
            .limit(1)
        )
        return action.status if action else default

    def _recipient_name(self, agent_key: AgentKey, snapshot: ProjectSnapshot) -> str:
        if agent_key == "collection_monitoring":
            return snapshot.client_contact_name
        if agent_key == "unbilled_revenue":
            return snapshot.billing_owner
        return snapshot.account_manager

    def _recipient_email(self, agent_key: AgentKey, snapshot: ProjectSnapshot) -> str:
        if agent_key == "collection_monitoring":
            return snapshot.client_contact_email
        if agent_key == "unbilled_revenue":
            return snapshot.billing_owner_email
        return snapshot.account_manager_email

    def _notification_item(self, row: NotificationEvent) -> NotificationRecord:
        return NotificationRecord(
            id=row.id,
            action_id=row.action_id,
            agent_key=row.agent_key,  # type: ignore[arg-type]
            entity_type=row.entity_type,  # type: ignore[arg-type]
            entity_id=row.entity_id,
            direction=row.direction,
            channel=row.channel,
            subject=row.subject,
            message_excerpt=row.message_excerpt,
            recipient_email=row.recipient_email,
            sender_email=row.sender_email,
            thread_id=row.thread_id,
            status=row.status,
            sent_at=row.sent_at.isoformat() if row.sent_at else None,
            received_at=row.received_at.isoformat() if row.received_at else None,
            created_at=row.created_at.isoformat(),
        )

    def _threshold_item(self, item: RiskThreshold) -> RiskThresholdItem:
        return RiskThresholdItem(
            id=item.id,
            agent_key=item.agent_key,  # type: ignore[arg-type]
            metric_key=item.metric_key,
            label=item.label,
            unit=item.unit,
            medium_value=item.medium_value,
            high_value=item.high_value,
            description=item.description,
        )

    @staticmethod
    def _reply_signal(body: str) -> str:
        normalized = body.lower()
        if any(keyword in normalized for keyword in ["approved", "complete", "completed", "invoice raised", "payment done", "paid", "cleared"]):
            return "complete"
        if any(keyword in normalized for keyword in ["will do", "working", "by tomorrow", "next week", "in progress"]):
            return "progress"
        return "none"
