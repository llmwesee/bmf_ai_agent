from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from sqlalchemy import delete
from sqlalchemy.orm import Session

from bfm_agent.config import get_settings
from bfm_agent.models import Account, BillingRecord, FollowUpLog, InvoiceRecord, Project, RevenueSnapshot


@dataclass(frozen=True)
class PortfolioSeed:
    account_name: str
    industry: str
    delivery_unit: str
    account_manager: str
    account_manager_email: str
    project_code: str
    project_name: str
    service_line: str
    contract_value: float
    revenue_plan_month: float
    revenue_recognized: float
    revenue_forecast: float
    revenue_burn_rate: float
    last_revenue_update_days_ago: int
    billing_cycle_days: int
    project_start_days_ago: int
    project_end_days_ahead: int
    milestone_name: str
    billable_amount: float
    billed_amount: float
    unbilled_amount: float
    billing_delay_days: int
    billing_status: str
    invoice_number: str
    invoice_amount: float
    collected_amount: float
    invoice_age_days: int
    overdue_days: int
    invoice_status: str


PORTFOLIO_SEEDS: tuple[PortfolioSeed, ...] = (
    PortfolioSeed(
        "PepsiCo",
        "Consumer Goods",
        "Data & AI",
        "Priya Sharma",
        "priya.sharma@bfmdemo.local",
        "PEP-AI-101",
        "Demand Forecasting Modernization",
        "AI Platforms",
        2_700_000,
        220_000,
        173_000,
        189_000,
        43_250,
        4,
        30,
        210,
        360,
        "March data science milestone",
        90_000,
        68_000,
        22_000,
        8,
        "Pending Approval",
        "INV-PEP-1042",
        90_000,
        25_000,
        43,
        21,
        "Partially Collected",
    ),
    PortfolioSeed(
        "PepsiCo",
        "Consumer Goods",
        "Data & AI",
        "Priya Sharma",
        "priya.sharma@bfmdemo.local",
        "PEP-DA-204",
        "Retail Data Hub Rollout",
        "Data Engineering",
        2_400_000,
        200_000,
        153_000,
        172_000,
        38_250,
        6,
        45,
        260,
        480,
        "Wave 2 platform billing",
        78_000,
        14_000,
        64_000,
        16,
        "Blocked",
        "INV-PEP-1079",
        78_000,
        0,
        49,
        27,
        "Overdue",
    ),
    PortfolioSeed(
        "Johnson Controls",
        "Industrial Technology",
        "Cloud Ops",
        "Arjun Mehta",
        "arjun.mehta@bfmdemo.local",
        "JCI-OPS-310",
        "Facilities Cloud Operations",
        "Managed Services",
        1_900_000,
        150_000,
        149_000,
        154_000,
        37_250,
        2,
        30,
        340,
        420,
        "Monthly cloud operations billing",
        62_000,
        56_000,
        6_000,
        2,
        "Ready To Bill",
        "INV-JCI-2218",
        62_000,
        62_000,
        28,
        0,
        "Collected",
    ),
    PortfolioSeed(
        "Johnson Controls",
        "Industrial Technology",
        "Cloud Ops",
        "Arjun Mehta",
        "arjun.mehta@bfmdemo.local",
        "JCI-CLO-115",
        "Workplace IoT Integration",
        "Cloud Transformation",
        1_600_000,
        110_000,
        106_000,
        114_000,
        26_500,
        3,
        30,
        190,
        300,
        "Phase gate billing",
        55_000,
        43_000,
        12_000,
        4,
        "Pending Approval",
        "INV-JCI-2244",
        55_000,
        55_000,
        16,
        0,
        "Collected",
    ),
    PortfolioSeed(
        "Comcast",
        "Telecom",
        "Digital Engineering",
        "Neha Iyer",
        "neha.iyer@bfmdemo.local",
        "COM-DIG-501",
        "Customer App Modernization",
        "Digital Product Engineering",
        2_300_000,
        170_000,
        136_000,
        152_000,
        34_000,
        5,
        21,
        280,
        400,
        "Sprint 18 billing pack",
        68_000,
        31_000,
        37_000,
        12,
        "Pending Client Confirmation",
        "INV-COM-3381",
        68_000,
        18_000,
        57,
        34,
        "Overdue",
    ),
    PortfolioSeed(
        "Comcast",
        "Telecom",
        "Digital Engineering",
        "Neha Iyer",
        "neha.iyer@bfmdemo.local",
        "COM-AIO-118",
        "Network AIOps Pilot",
        "Platform Engineering",
        1_800_000,
        140_000,
        108_000,
        127_000,
        27_000,
        7,
        30,
        160,
        330,
        "Observability billing batch",
        54_000,
        39_000,
        15_000,
        6,
        "Delayed",
        "INV-COM-3420",
        54_000,
        22_000,
        35,
        12,
        "Partially Collected",
    ),
    PortfolioSeed(
        "HSBC",
        "Banking",
        "Managed Services",
        "Rohit Desai",
        "rohit.desai@bfmdemo.local",
        "HSB-DAT-220",
        "Regulatory Data Platform",
        "Data Modernization",
        2_600_000,
        180_000,
        168_000,
        185_000,
        42_000,
        2,
        30,
        310,
        500,
        "March reporting milestone",
        72_000,
        63_000,
        9_000,
        3,
        "Ready To Bill",
        "INV-HSB-5188",
        72_000,
        52_000,
        12,
        0,
        "Partially Collected",
    ),
    PortfolioSeed(
        "HSBC",
        "Banking",
        "Managed Services",
        "Rohit Desai",
        "rohit.desai@bfmdemo.local",
        "HSB-FIN-804",
        "Treasury Operations Support",
        "Finance Ops",
        2_100_000,
        160_000,
        138_000,
        151_000,
        34_500,
        4,
        21,
        250,
        420,
        "Treasury support billing",
        69_000,
        41_000,
        28_000,
        9,
        "Pending Approval",
        "INV-HSB-5210",
        69_000,
        30_000,
        33,
        11,
        "Partially Collected",
    ),
    PortfolioSeed(
        "Cisco",
        "Networking",
        "Cyber Defense",
        "Sanjay Patel",
        "sanjay.patel@bfmdemo.local",
        "CSC-CYB-410",
        "SOC Automation Program",
        "Cybersecurity",
        2_000_000,
        145_000,
        151_000,
        156_000,
        37_750,
        1,
        30,
        300,
        390,
        "Security operations billing",
        63_000,
        59_000,
        4_000,
        0,
        "Billed",
        "INV-CSC-4106",
        63_000,
        63_000,
        19,
        0,
        "Collected",
    ),
    PortfolioSeed(
        "Cisco",
        "Networking",
        "Cyber Defense",
        "Sanjay Patel",
        "sanjay.patel@bfmdemo.local",
        "CSC-NET-870",
        "Secure Network Reliability",
        "Network Engineering",
        1_950_000,
        145_000,
        144_000,
        146_000,
        36_000,
        2,
        30,
        210,
        360,
        "Reliability squad billing",
        61_000,
        54_000,
        7_000,
        1,
        "Ready To Bill",
        "INV-CSC-4138",
        61_000,
        48_000,
        18,
        0,
        "Partially Collected",
    ),
    PortfolioSeed(
        "AstraZeneca",
        "Life Sciences",
        "Enterprise Platforms",
        "Kavya Nair",
        "kavya.nair@bfmdemo.local",
        "AZE-ERP-330",
        "SAP Finance Transformation",
        "ERP Modernization",
        2_450_000,
        150_000,
        112_000,
        129_000,
        28_000,
        8,
        30,
        320,
        520,
        "ERP wave billing",
        59_000,
        8_000,
        51_000,
        19,
        "Blocked",
        "INV-AZE-6124",
        59_000,
        15_000,
        44,
        22,
        "Overdue",
    ),
    PortfolioSeed(
        "AstraZeneca",
        "Life Sciences",
        "Enterprise Platforms",
        "Kavya Nair",
        "kavya.nair@bfmdemo.local",
        "AZE-DAT-731",
        "Clinical Data Lake",
        "Data Platforms",
        2_050_000,
        130_000,
        106_000,
        123_000,
        26_500,
        5,
        21,
        210,
        400,
        "Data ingestion milestone",
        49_000,
        31_000,
        18_000,
        5,
        "Delayed",
        "INV-AZE-6167",
        49_000,
        21_000,
        30,
        9,
        "Partially Collected",
    ),
    PortfolioSeed(
        "Target",
        "Retail",
        "Commerce Platforms",
        "Ananya Rao",
        "ananya.rao@bfmdemo.local",
        "TGT-COM-610",
        "Store Commerce Engine",
        "Commerce Engineering",
        2_100_000,
        160_000,
        157_000,
        162_000,
        39_250,
        1,
        30,
        240,
        410,
        "Commerce release billing",
        65_000,
        62_000,
        3_000,
        0,
        "Billed",
        "INV-TGT-7020",
        65_000,
        65_000,
        17,
        0,
        "Collected",
    ),
    PortfolioSeed(
        "Target",
        "Retail",
        "Commerce Platforms",
        "Ananya Rao",
        "ananya.rao@bfmdemo.local",
        "TGT-ANA-205",
        "Retail Analytics Factory",
        "Analytics",
        1_700_000,
        120_000,
        113_000,
        119_000,
        28_250,
        2,
        30,
        180,
        340,
        "Analytics sprint billing",
        50_000,
        39_000,
        11_000,
        4,
        "Pending Approval",
        "INV-TGT-7051",
        50_000,
        30_000,
        11,
        0,
        "Partially Collected",
    ),
)


def _group_account_targets() -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "industry": "",
            "delivery_unit": "",
            "account_manager": "",
            "account_manager_email": "",
            "monthly_target": 0.0,
            "contract_value": 0.0,
        }
    )
    for seed in PORTFOLIO_SEEDS:
        record = grouped[seed.account_name]
        record["industry"] = seed.industry
        record["delivery_unit"] = seed.delivery_unit
        record["account_manager"] = seed.account_manager
        record["account_manager_email"] = seed.account_manager_email
        record["monthly_target"] += seed.revenue_plan_month
        record["contract_value"] += seed.contract_value
    return grouped


def build_demo_rows(reference_date: date | None = None) -> list[dict[str, Any]]:
    today = reference_date or date.today()
    rows: list[dict[str, Any]] = []
    for seed in PORTFOLIO_SEEDS:
        billing_due_date = today - timedelta(days=seed.billing_delay_days) if seed.billing_delay_days else today + timedelta(days=2)
        billed_date = None
        if seed.billed_amount > 0 and seed.billing_status in {"Billed", "Ready To Bill"}:
            billed_date = billing_due_date - timedelta(days=1) if seed.billing_delay_days else today - timedelta(days=2)
        invoice_date = today - timedelta(days=seed.invoice_age_days)
        due_date = today - timedelta(days=seed.overdue_days) if seed.overdue_days else invoice_date + timedelta(days=30)
        collected_date = None
        if seed.collected_amount >= seed.invoice_amount:
            collected_date = invoice_date + timedelta(days=18)
        elif seed.collected_amount > 0:
            collected_date = today - timedelta(days=5)

        rows.append(
            {
                "account_name": seed.account_name,
                "industry": seed.industry,
                "delivery_unit": seed.delivery_unit,
                "account_manager": seed.account_manager,
                "account_manager_email": seed.account_manager_email,
                "project_code": seed.project_code,
                "project_name": seed.project_name,
                "service_line": seed.service_line,
                "contract_value": seed.contract_value,
                "revenue_plan_month": seed.revenue_plan_month,
                "revenue_plan_quarter": seed.revenue_plan_month * 3,
                "revenue_recognized": seed.revenue_recognized,
                "revenue_remaining": max(seed.revenue_plan_month - seed.revenue_recognized, 0.0),
                "revenue_forecast": seed.revenue_forecast,
                "revenue_gap": seed.revenue_forecast - seed.revenue_plan_month,
                "revenue_completion_pct": round(seed.revenue_recognized / seed.revenue_plan_month, 4),
                "revenue_burn_rate": seed.revenue_burn_rate,
                "last_revenue_update": today - timedelta(days=seed.last_revenue_update_days_ago),
                "billing_cycle_days": seed.billing_cycle_days,
                "start_date": today - timedelta(days=seed.project_start_days_ago),
                "end_date": today + timedelta(days=seed.project_end_days_ahead),
                "milestone_name": seed.milestone_name,
                "billable_amount": seed.billable_amount,
                "billed_amount": seed.billed_amount,
                "unbilled_amount": seed.unbilled_amount,
                "billing_due_date": billing_due_date,
                "billed_date": billed_date,
                "billing_delay_days": seed.billing_delay_days,
                "billing_status": seed.billing_status,
                "invoice_number": seed.invoice_number,
                "invoice_amount": seed.invoice_amount,
                "collected_amount": seed.collected_amount,
                "invoice_date": invoice_date,
                "due_date": due_date,
                "collected_date": collected_date,
                "overdue_days": seed.overdue_days,
                "invoice_status": seed.invoice_status,
            }
        )
    return rows


def generate_demo_workbook(path: Path, reference_date: date | None = None) -> int:
    rows = build_demo_rows(reference_date=reference_date)
    account_totals = _group_account_targets()
    workbook = Workbook()
    workbook.remove(workbook.active)

    instructions = workbook.create_sheet("Instructions")
    instructions.append(["Sheet", "Purpose"])
    instructions.append(["Accounts", "Master account directory with targets and ownership"])
    instructions.append(["Revenue Realization", "Project-level revenue monitoring inputs"])
    instructions.append(["Billing Tracker", "Milestone billing and unbilled revenue tracking"])
    instructions.append(["Collection Tracker", "Invoice collections and overdue monitoring"])

    accounts_sheet = workbook.create_sheet("Accounts")
    accounts_sheet.append(
        [
            "Account Name",
            "Industry",
            "Delivery Unit",
            "Account Manager",
            "Account Manager Email",
            "Account Monthly Target",
            "Contract Value",
        ]
    )
    for account_name, data in sorted(account_totals.items()):
        accounts_sheet.append(
            [
                account_name,
                data["industry"],
                data["delivery_unit"],
                data["account_manager"],
                data["account_manager_email"],
                data["monthly_target"],
                data["contract_value"],
            ]
        )

    revenue_sheet = workbook.create_sheet("Revenue Realization")
    revenue_sheet.append(
        [
            "Account Name",
            "Project Code",
            "Project Name",
            "Service Line",
            "Contract Value",
            "Revenue Plan (Month)",
            "Revenue Plan (Quarter)",
            "Revenue Recognized",
            "Revenue Remaining",
            "Revenue Forecast",
            "Revenue Gap",
            "Revenue Completion %",
            "Revenue Burn Rate",
            "Last Revenue Update",
            "Billing Cycle Days",
            "Start Date",
            "End Date",
        ]
    )
    for row in rows:
        revenue_sheet.append(
            [
                row["account_name"],
                row["project_code"],
                row["project_name"],
                row["service_line"],
                row["contract_value"],
                row["revenue_plan_month"],
                row["revenue_plan_quarter"],
                row["revenue_recognized"],
                row["revenue_remaining"],
                row["revenue_forecast"],
                row["revenue_gap"],
                row["revenue_completion_pct"],
                row["revenue_burn_rate"],
                row["last_revenue_update"].isoformat(),
                row["billing_cycle_days"],
                row["start_date"].isoformat(),
                row["end_date"].isoformat(),
            ]
        )

    billing_sheet = workbook.create_sheet("Billing Tracker")
    billing_sheet.append(
        [
            "Project Code",
            "Milestone Name",
            "Billable Amount",
            "Billed Amount",
            "Unbilled Amount",
            "Billing Due Date",
            "Billed Date",
            "Delay Days",
            "Status",
        ]
    )
    for row in rows:
        billing_sheet.append(
            [
                row["project_code"],
                row["milestone_name"],
                row["billable_amount"],
                row["billed_amount"],
                row["unbilled_amount"],
                row["billing_due_date"].isoformat(),
                row["billed_date"].isoformat() if row["billed_date"] else "",
                row["billing_delay_days"],
                row["billing_status"],
            ]
        )

    collection_sheet = workbook.create_sheet("Collection Tracker")
    collection_sheet.append(
        [
            "Project Code",
            "Invoice Number",
            "Invoice Amount",
            "Collected Amount",
            "Invoice Date",
            "Due Date",
            "Collected Date",
            "Overdue Days",
            "Status",
        ]
    )
    for row in rows:
        collection_sheet.append(
            [
                row["project_code"],
                row["invoice_number"],
                row["invoice_amount"],
                row["collected_amount"],
                row["invoice_date"].isoformat(),
                row["due_date"].isoformat(),
                row["collected_date"].isoformat() if row["collected_date"] else "",
                row["overdue_days"],
                row["invoice_status"],
            ]
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return len(rows)


def _sheet_records(worksheet) -> list[dict[str, Any]]:
    rows = list(worksheet.iter_rows(values_only=True))
    headers = [str(value).strip() for value in rows[0]]
    return [dict(zip(headers, row, strict=False)) for row in rows[1:] if any(value not in (None, "") for value in row)]


def _to_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def import_workbook_into_db(workbook_path: Path, session: Session) -> int:
    workbook = load_workbook(workbook_path, data_only=True)
    accounts = _sheet_records(workbook["Accounts"])
    revenues = _sheet_records(workbook["Revenue Realization"])
    billings = _sheet_records(workbook["Billing Tracker"])
    collections = _sheet_records(workbook["Collection Tracker"])

    session.execute(delete(FollowUpLog))
    session.execute(delete(InvoiceRecord))
    session.execute(delete(BillingRecord))
    session.execute(delete(RevenueSnapshot))
    session.execute(delete(Project))
    session.execute(delete(Account))
    session.flush()

    account_lookup: dict[str, Account] = {}
    for row in accounts:
        account = Account(
            name=str(row["Account Name"]),
            industry=str(row["Industry"]),
            delivery_unit=str(row["Delivery Unit"]),
            account_manager=str(row["Account Manager"]),
            account_manager_email=str(row["Account Manager Email"]),
            monthly_target=float(row["Account Monthly Target"]),
            contract_value=float(row["Contract Value"]),
        )
        session.add(account)
        session.flush()
        account_lookup[account.name] = account

    project_lookup: dict[str, Project] = {}
    for row in revenues:
        project = Project(
            account_id=account_lookup[str(row["Account Name"])].id,
            code=str(row["Project Code"]),
            name=str(row["Project Name"]),
            service_line=str(row["Service Line"]),
            contract_value=float(row["Contract Value"]),
            revenue_plan_month=float(row["Revenue Plan (Month)"]),
            revenue_plan_quarter=float(row["Revenue Plan (Quarter)"]),
            start_date=_to_date(row["Start Date"]),
            end_date=_to_date(row["End Date"]),
            last_revenue_update=_to_date(row["Last Revenue Update"]),
            billing_cycle_days=int(row["Billing Cycle Days"]),
        )
        session.add(project)
        session.flush()
        project_lookup[project.code] = project

        session.add(
            RevenueSnapshot(
                project_id=project.id,
                period_label="current_month",
                snapshot_date=_to_date(row["Last Revenue Update"]),
                planned_revenue=float(row["Revenue Plan (Month)"]),
                recognized_revenue=float(row["Revenue Recognized"]),
                forecast_revenue=float(row["Revenue Forecast"]),
                burn_rate_weekly=float(row["Revenue Burn Rate"]),
            )
        )

    for row in billings:
        billed_date = row["Billed Date"]
        session.add(
            BillingRecord(
                project_id=project_lookup[str(row["Project Code"])].id,
                milestone_name=str(row["Milestone Name"]),
                billable_amount=float(row["Billable Amount"]),
                billed_amount=float(row["Billed Amount"]),
                unbilled_amount=float(row["Unbilled Amount"]),
                billing_due_date=_to_date(row["Billing Due Date"]),
                billed_date=_to_date(billed_date) if billed_date not in (None, "") else None,
                delay_days=int(row["Delay Days"]),
                status=str(row["Status"]),
            )
        )

    for row in collections:
        collected_date = row["Collected Date"]
        session.add(
            InvoiceRecord(
                project_id=project_lookup[str(row["Project Code"])].id,
                invoice_number=str(row["Invoice Number"]),
                invoice_amount=float(row["Invoice Amount"]),
                collected_amount=float(row["Collected Amount"]),
                invoice_date=_to_date(row["Invoice Date"]),
                due_date=_to_date(row["Due Date"]),
                collected_date=_to_date(collected_date) if collected_date not in (None, "") else None,
                overdue_days=int(row["Overdue Days"]),
                status=str(row["Status"]),
            )
        )

    session.flush()
    return len(revenues)


def bootstrap_demo_assets(force_regenerate: bool = False) -> int:
    settings = get_settings()
    if force_regenerate or not settings.workbook_file.exists():
        generate_demo_workbook(settings.workbook_file)

    from bfm_agent.db import init_db, session_scope

    init_db()
    with session_scope() as session:
        return import_workbook_into_db(settings.workbook_file, session)
