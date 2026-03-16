from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from bfm_agent.models import Project
from bfm_agent.schemas import AlertItem, CollectionRow, ReportResponse, RevenueRow, SummaryMetrics


@dataclass
class ProjectHealth:
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
    risk_level: str
    last_revenue_update: str
    unbilled_amount: float
    billing_delay_days: int
    overdue_days: int
    outstanding_collection: float
    billing_status: str
    primary_issue: str


class AnalyticsService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _projects(self) -> list[Project]:
        result = self.session.scalars(
            select(Project).options(
                joinedload(Project.account),
                joinedload(Project.revenues),
                joinedload(Project.billings),
                joinedload(Project.invoices),
            )
        )
        return list(result.unique().all())

    @staticmethod
    def _risk_level(gap_ratio: float, billing_delay_days: int, overdue_days: int, unbilled_amount: float) -> str:
        if gap_ratio <= -0.12 or overdue_days >= 20 or billing_delay_days >= 14 or unbilled_amount >= 50_000:
            return "High"
        if gap_ratio <= -0.05 or overdue_days >= 8 or billing_delay_days >= 5 or unbilled_amount >= 20_000:
            return "Medium"
        return "Low"

    def _project_health(self, project: Project) -> ProjectHealth:
        revenue = max(project.revenues, key=lambda row: row.snapshot_date)
        billings = project.billings
        invoices = project.invoices
        unbilled_amount = sum(item.unbilled_amount for item in billings)
        billing_delay_days = max((item.delay_days for item in billings), default=0)
        overdue_days = max((item.overdue_days for item in invoices), default=0)
        outstanding_collection = sum(max(item.invoice_amount - item.collected_amount, 0.0) for item in invoices)
        revenue_gap = revenue.forecast_revenue - revenue.planned_revenue
        gap_ratio = revenue_gap / revenue.planned_revenue if revenue.planned_revenue else 0.0

        primary_issue = "Revenue lag"
        if overdue_days >= billing_delay_days and overdue_days > 0:
            primary_issue = "Collection risk"
        elif billing_delay_days > 0 and unbilled_amount > 0:
            primary_issue = "Billing delay"

        return ProjectHealth(
            account_name=project.account.name,
            project_code=project.code,
            project_name=project.name,
            delivery_unit=project.account.delivery_unit,
            account_manager=project.account.account_manager,
            contract_value=project.contract_value,
            revenue_plan=revenue.planned_revenue,
            revenue_recognized=revenue.recognized_revenue,
            revenue_remaining=max(revenue.planned_revenue - revenue.recognized_revenue, 0.0),
            revenue_forecast=revenue.forecast_revenue,
            revenue_gap=revenue_gap,
            revenue_completion_pct=(revenue.recognized_revenue / revenue.planned_revenue) if revenue.planned_revenue else 0.0,
            revenue_burn_rate=revenue.burn_rate_weekly,
            risk_level=self._risk_level(gap_ratio, billing_delay_days, overdue_days, unbilled_amount),
            last_revenue_update=project.last_revenue_update.isoformat(),
            unbilled_amount=unbilled_amount,
            billing_delay_days=billing_delay_days,
            overdue_days=overdue_days,
            outstanding_collection=outstanding_collection,
            billing_status=max((item.status for item in billings), default=""),
            primary_issue=primary_issue,
        )

    def revenue_rows(self) -> list[RevenueRow]:
        rows = [RevenueRow(**asdict(self._project_health(project))) for project in self._projects()]
        order = {"High": 0, "Medium": 1, "Low": 2}
        return sorted(rows, key=lambda row: (order[row.risk_level], row.account_name, row.project_code))

    def collection_rows(self) -> list[CollectionRow]:
        rows: list[CollectionRow] = []
        for project in self._projects():
            for invoice in project.invoices:
                rows.append(
                    CollectionRow(
                        account_name=project.account.name,
                        project_code=project.code,
                        invoice_number=invoice.invoice_number,
                        invoice_amount=invoice.invoice_amount,
                        collected_amount=invoice.collected_amount,
                        outstanding_amount=max(invoice.invoice_amount - invoice.collected_amount, 0.0),
                        due_date=invoice.due_date.isoformat(),
                        overdue_days=invoice.overdue_days,
                        status=invoice.status,
                    )
                )
        return sorted(rows, key=lambda row: (-row.overdue_days, -row.outstanding_amount))

    def summary(self) -> SummaryMetrics:
        rows = self.revenue_rows()
        revenue_plan = sum(row.revenue_plan for row in rows)
        revenue_recognized = sum(row.revenue_recognized for row in rows)
        revenue_forecast = sum(row.revenue_forecast for row in rows)
        total_unbilled = sum(row.unbilled_amount for row in rows)
        overdue_amount = sum(row.outstanding_collection for row in rows if row.overdue_days > 0)
        return SummaryMetrics(
            revenue_plan=revenue_plan,
            revenue_recognized=revenue_recognized,
            revenue_remaining=max(revenue_plan - revenue_recognized, 0.0),
            revenue_forecast=revenue_forecast,
            revenue_gap=revenue_forecast - revenue_plan,
            revenue_completion_pct=(revenue_recognized / revenue_plan) if revenue_plan else 0.0,
            total_unbilled=total_unbilled,
            overdue_amount=overdue_amount,
            high_risk_projects=sum(1 for row in rows if row.risk_level == "High"),
            medium_risk_projects=sum(1 for row in rows if row.risk_level == "Medium"),
        )

    def alerts(self, limit: int = 8) -> list[AlertItem]:
        alerts: list[AlertItem] = []
        for row in self.revenue_rows():
            gap_ratio = row.revenue_gap / row.revenue_plan if row.revenue_plan else 0.0
            if gap_ratio <= -0.05:
                alerts.append(
                    AlertItem(
                        severity="High" if gap_ratio <= -0.12 else "Medium",
                        focus_area="revenue",
                        account_name=row.account_name,
                        project_code=row.project_code,
                        title=f"{row.account_name} revenue shortfall",
                        message=f"{row.project_code} is forecast {abs(gap_ratio):.0%} below target for the month.",
                        suggested_action="Review revenue closure blockers with the account manager.",
                        score=abs(gap_ratio) * 100,
                    )
                )
            if row.unbilled_amount >= 20_000:
                alerts.append(
                    AlertItem(
                        severity="High" if row.unbilled_amount >= 50_000 else "Medium",
                        focus_area="billing",
                        account_name=row.account_name,
                        project_code=row.project_code,
                        title=f"{row.project_code} billing delay",
                        message=f"Unbilled revenue of ${row.unbilled_amount:,.0f} is waiting {row.billing_delay_days} days past billing due date.",
                        suggested_action="Push milestone approval and release billing immediately.",
                        score=row.unbilled_amount / 1_000,
                    )
                )
            if row.overdue_days > 0:
                alerts.append(
                    AlertItem(
                        severity="High" if row.overdue_days >= 20 else "Medium",
                        focus_area="collections",
                        account_name=row.account_name,
                        project_code=row.project_code,
                        title=f"{row.project_code} overdue collection",
                        message=f"${row.outstanding_collection:,.0f} remains outstanding with {row.overdue_days} overdue days.",
                        suggested_action="Follow up with the account manager and collections SPOC.",
                        score=row.overdue_days + (row.outstanding_collection / 10_000),
                    )
                )
        order = {"High": 0, "Medium": 1, "Low": 2}
        alerts.sort(key=lambda item: (order[item.severity], -item.score))
        return alerts[:limit]

    def account_snapshot(self, account_name: str | None = None, project_code: str | None = None) -> dict[str, object]:
        rows = self.revenue_rows()
        if project_code:
            rows = [row for row in rows if row.project_code == project_code]
        elif account_name:
            rows = [row for row in rows if row.account_name == account_name]
        if not rows:
            raise ValueError("No matching account or project found in the portfolio.")

        primary = next((row for row in rows if row.project_code == project_code), rows[0])
        totals = {
            "revenue_plan": sum(row.revenue_plan for row in rows),
            "revenue_recognized": sum(row.revenue_recognized for row in rows),
            "revenue_forecast": sum(row.revenue_forecast for row in rows),
            "total_unbilled": sum(row.unbilled_amount for row in rows),
            "overdue_amount": sum(row.outstanding_collection for row in rows if row.overdue_days > 0),
        }
        totals["revenue_gap"] = totals["revenue_forecast"] - totals["revenue_plan"]
        totals["completion_pct"] = (totals["revenue_recognized"] / totals["revenue_plan"]) if totals["revenue_plan"] else 0.0
        return {
            "account_name": primary.account_name,
            "project_code": primary.project_code,
            "project_name": primary.project_name,
            "account_manager": primary.account_manager,
            "delivery_unit": primary.delivery_unit,
            "risk_level": primary.risk_level,
            "totals": totals,
            "rows": [row.model_dump() for row in rows],
            "primary_row": primary.model_dump(),
        }

    def report(self) -> ReportResponse:
        rows = self.revenue_rows()
        summary = self.summary()
        account_rollup: dict[str, dict[str, float | str]] = defaultdict(
            lambda: {"account_name": "", "revenue_gap": 0.0, "unbilled_amount": 0.0, "overdue_amount": 0.0}
        )
        delivery_rollup: dict[str, dict[str, float | str]] = defaultdict(
            lambda: {"delivery_unit": "", "revenue_gap": 0.0, "revenue_forecast": 0.0}
        )
        for row in rows:
            account = account_rollup[row.account_name]
            account["account_name"] = row.account_name
            account["revenue_gap"] += row.revenue_gap
            account["unbilled_amount"] += row.unbilled_amount
            account["overdue_amount"] += row.outstanding_collection

            delivery = delivery_rollup[row.delivery_unit]
            delivery["delivery_unit"] = row.delivery_unit
            delivery["revenue_gap"] += row.revenue_gap
            delivery["revenue_forecast"] += row.revenue_forecast

        top_accounts = sorted(account_rollup.values(), key=lambda item: float(item["revenue_gap"]))[:5]
        top_delivery_units = sorted(delivery_rollup.values(), key=lambda item: float(item["revenue_gap"]))[:4]
        high_risk = [row for row in rows if row.risk_level == "High"]
        narrative = (
            f"{len(high_risk)} projects are currently high risk. "
            f"Portfolio forecast is ${summary.revenue_gap:,.0f} versus target, "
            f"with ${summary.total_unbilled:,.0f} unbilled and ${summary.overdue_amount:,.0f} overdue."
        )
        return ReportResponse(
            summary=summary,
            top_accounts=top_accounts,
            top_delivery_units=top_delivery_units,
            narrative=narrative,
        )
