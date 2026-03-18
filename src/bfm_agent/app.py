from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from bfm_agent.agent.graph import BFMAgentRunner
from bfm_agent.analytics import AnalyticsService
from bfm_agent.config import get_settings
from bfm_agent.db import get_session
from bfm_agent.gmail import GmailService
from bfm_agent.llm import ProviderConfigurationError, provider_statuses
from bfm_agent.models import NotificationEvent
from bfm_agent.schemas import (
    ActionApproveRequest,
    ActionApproveResponse,
    AgentRequest,
    AgentResponse,
    DashboardResponse,
    DataResetResponse,
    GmailSyncResponse,
    ThresholdUpdateRequest,
)
from bfm_agent.seed_data import bootstrap_demo_assets, generate_demo_workbook, import_workbook_into_db


settings = get_settings()
templates = Jinja2Templates(directory=str(settings.templates_dir))


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap_demo_assets(force_regenerate=not settings.workbook_file.exists())
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")


def _analytics(session: Session) -> AnalyticsService:
    return AnalyticsService(session)


def _focus_area_for_agent(agent_key: str) -> str:
    if agent_key in {"billing_trigger", "unbilled_revenue"}:
        return "billing"
    if agent_key == "collection_monitoring":
        return "collections"
    return "revenue"


def _legacy_summary(payload) -> dict[str, Any]:
    overview = payload.overview
    revenue_rows = payload.revenue_realization.rows
    return {
        "revenue_plan": overview.revenue_plan,
        "revenue_recognized": overview.revenue_recognized,
        "revenue_remaining": max(overview.revenue_plan - overview.revenue_recognized, 0.0),
        "revenue_forecast": overview.revenue_forecast,
        "revenue_gap": overview.revenue_forecast - overview.revenue_plan,
        "revenue_completion_pct": (overview.revenue_recognized / overview.revenue_plan) if overview.revenue_plan else 0.0,
        "total_unbilled": overview.unbilled_revenue,
        "overdue_amount": overview.overdue_amount,
        "high_risk_projects": sum(1 for row in revenue_rows if row.risk_level == "High"),
        "medium_risk_projects": sum(1 for row in revenue_rows if row.risk_level == "Medium"),
    }


def _legacy_alerts(payload) -> list[dict[str, Any]]:
    return [
        {
            **item.model_dump(),
            "focus_area": _focus_area_for_agent(item.agent_key),
        }
        for item in payload.queue
    ]


def _legacy_revenue_rows(payload) -> list[dict[str, Any]]:
    unbilled_by_project = {row.project_code: row for row in payload.unbilled_revenue.rows}
    billing_by_project: dict[str, list[Any]] = {}
    for row in payload.billing_trigger.rows:
        billing_by_project.setdefault(row.project_code, []).append(row)
    collections_by_project: dict[str, list[Any]] = {}
    for row in payload.collection_monitoring.rows:
        collections_by_project.setdefault(row.project_code, []).append(row)

    rows: list[dict[str, Any]] = []
    for row in payload.revenue_realization.rows:
        billing_rows = billing_by_project.get(row.project_code, [])
        collection_rows = collections_by_project.get(row.project_code, [])
        unbilled_row = unbilled_by_project.get(row.project_code)
        rows.append(
            {
                **row.model_dump(),
                "unbilled_amount": unbilled_row.unbilled_revenue if unbilled_row else 0.0,
                "billing_delay_days": max((item.billing_delay_days for item in billing_rows), default=0),
                "overdue_days": max((item.overdue_days for item in collection_rows), default=0),
                "outstanding_collection": sum(item.outstanding_balance for item in collection_rows),
            }
        )
    return rows


def _legacy_collections(payload) -> list[dict[str, Any]]:
    return [
        {
            "account_name": row.account_name,
            "project_code": row.project_code,
            "invoice_number": row.invoice_number,
            "invoice_amount": row.invoice_amount,
            "collected_amount": row.amount_received,
            "outstanding_amount": row.outstanding_balance,
            "due_date": row.payment_due_date,
            "overdue_days": row.overdue_days,
            "status": row.collection_status,
        }
        for row in payload.collection_monitoring.rows
    ]


def _resolve_legacy_request(raw_payload: dict[str, Any], analytics: AnalyticsService) -> AgentRequest:
    if {"agent_key", "entity_type", "entity_id"}.issubset(raw_payload):
        return AgentRequest.model_validate(raw_payload)

    project_code = raw_payload.get("project_code")
    account_name = raw_payload.get("account_name")
    focus_area = str(raw_payload.get("focus_area") or "revenue")
    provider = raw_payload.get("provider", "mock")
    question = raw_payload.get("question")
    dashboard_payload = analytics.dashboard()

    if focus_area == "collections":
        candidates = dashboard_payload.collection_monitoring.rows
        if project_code:
            candidates = [row for row in candidates if row.project_code == project_code]
        if account_name:
            candidates = [row for row in candidates if row.account_name == account_name]
        if candidates:
            target = sorted(candidates, key=lambda row: (-row.overdue_days, -row.outstanding_balance))[0]
            return AgentRequest(
                agent_key="collection_monitoring",
                entity_type="invoice",
                entity_id=target.entity_id,
                provider=provider,
                question=question,
            )

    if focus_area == "billing":
        project_candidates = dashboard_payload.unbilled_revenue.rows
        if project_code:
            project_candidates = [row for row in project_candidates if row.project_code == project_code]
        if account_name:
            project_candidates = [row for row in project_candidates if row.account_name == account_name]
        if project_candidates:
            target = sorted(project_candidates, key=lambda row: (-row.unbilled_revenue, -row.days_unbilled))[0]
            return AgentRequest(
                agent_key="unbilled_revenue",
                entity_type="project",
                entity_id=target.entity_id,
                provider=provider,
                question=question,
            )

        milestone_candidates = dashboard_payload.billing_trigger.rows
        if project_code:
            milestone_candidates = [row for row in milestone_candidates if row.project_code == project_code]
        if account_name:
            milestone_candidates = [row for row in milestone_candidates if row.account_name == account_name]
        if milestone_candidates:
            target = sorted(milestone_candidates, key=lambda row: (-row.unbilled_amount, -row.billing_delay_days))[0]
            return AgentRequest(
                agent_key="billing_trigger",
                entity_type="milestone",
                entity_id=target.entity_id,
                provider=provider,
                question=question,
            )

    revenue_candidates = dashboard_payload.revenue_realization.rows
    if project_code:
        revenue_candidates = [row for row in revenue_candidates if row.project_code == project_code]
    if account_name:
        revenue_candidates = [row for row in revenue_candidates if row.account_name == account_name]
    if not revenue_candidates:
        raise ValueError("No matching account or project found in the portfolio.")
    target = sorted(revenue_candidates, key=lambda row: (row.risk_level != "High", row.account_name, row.project_code))[0]
    agent_key = "revenue_forecasting" if focus_area == "forecast" else "revenue_realization"
    return AgentRequest(
        agent_key=agent_key,
        entity_type="project",
        entity_id=target.entity_id,
        provider=provider,
        question=question,
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    css_path = settings.static_dir / "app.css"
    js_path = settings.static_dir / "app.js"
    asset_version = str(max(css_path.stat().st_mtime_ns, js_path.stat().st_mtime_ns))
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_name": settings.app_name,
            "default_provider": settings.default_provider,
            "asset_version": asset_version,
        },
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/api/providers")
def providers():
    return provider_statuses()


@app.get("/api/dashboard", response_model=DashboardResponse)
def dashboard(session: Session = Depends(get_session)):
    return _analytics(session).dashboard()


@app.get("/api/summary")
def summary(session: Session = Depends(get_session)):
    return _legacy_summary(_analytics(session).dashboard())


@app.get("/api/alerts")
def alerts(session: Session = Depends(get_session)):
    return _legacy_alerts(_analytics(session).dashboard())


@app.get("/api/revenue-table")
def revenue_table(session: Session = Depends(get_session)):
    return _legacy_revenue_rows(_analytics(session).dashboard())


@app.get("/api/collections")
def collections(session: Session = Depends(get_session)):
    return _legacy_collections(_analytics(session).dashboard())


@app.get("/api/report")
def report(session: Session = Depends(get_session)):
    dashboard_payload = _analytics(session).dashboard()
    return {
        "summary": dashboard_payload.overview,
        "top_accounts": dashboard_payload.narrative.top_accounts,
        "top_delivery_units": dashboard_payload.narrative.top_delivery_units,
        "narrative": dashboard_payload.narrative.narrative,
    }


@app.get("/api/thresholds")
def thresholds(session: Session = Depends(get_session)):
    return _analytics(session).thresholds()


@app.put("/api/thresholds/{threshold_id}")
def update_threshold(threshold_id: int, payload: ThresholdUpdateRequest, session: Session = Depends(get_session)):
    if payload.high_value < payload.medium_value:
        raise HTTPException(status_code=400, detail="high_value must be greater than or equal to medium_value.")
    try:
        threshold = _analytics(session).update_threshold(threshold_id, payload.medium_value, payload.high_value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session.commit()
    return threshold


@app.post("/api/agent/draft-followup", response_model=AgentResponse)
def draft_follow_up(payload: dict[str, Any], session: Session = Depends(get_session)):
    analytics = _analytics(session)
    try:
        request = _resolve_legacy_request(payload, analytics)
        return BFMAgentRunner(session).run(request)
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/actions/approve", response_model=ActionApproveResponse)
def approve_action(payload: ActionApproveRequest, session: Session = Depends(get_session)):
    analytics = _analytics(session)
    try:
        draft = BFMAgentRunner(session).run(
            AgentRequest(
                agent_key=payload.agent_key,
                entity_type=payload.entity_type,
                entity_id=payload.entity_id,
                provider=payload.provider,
                question=payload.question,
            )
        )
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    action = analytics.create_action(
        agent_key=payload.agent_key,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        provider=payload.provider,
        channel=payload.channel,
        subject=draft.email_subject,
        body=draft.email_body,
        recommended_action=draft.recommended_action,
        trace_id=draft.trace_id,
        trace_url=draft.trace_url,
        approved_by=payload.approved_by,
    )

    notification_status = "Mock Sent"
    thread_id = None
    if payload.channel == "gmail":
        send_result = GmailService().send_message(
            recipient_email=action.recipient_email,
            subject=action.subject,
            body=action.body,
        )
        notification_status = send_result.status
        thread_id = send_result.thread_id
        action.status = "Sent" if send_result.status == "Sent" else "Failed"
        analytics.record_notification(
            action_id=action.id,
            agent_key=payload.agent_key,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            channel=payload.channel,
            subject=action.subject,
            message_excerpt=action.body,
            recipient_email=action.recipient_email,
            status=send_result.status,
            thread_id=send_result.thread_id,
            external_message_id=send_result.message_id,
            sent_at=datetime.utcnow() if send_result.status == "Sent" else None,
        )
    else:
        action.status = "Sent"
        analytics.record_notification(
            action_id=action.id,
            agent_key=payload.agent_key,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            channel=payload.channel,
            subject=action.subject,
            message_excerpt=action.body,
            recipient_email=action.recipient_email,
            status=notification_status,
            thread_id=f"mock-{action.id}",
            sent_at=datetime.utcnow(),
        )
        thread_id = f"mock-{action.id}"

    session.commit()
    return ActionApproveResponse(
        action_id=action.id,
        status=action.status,
        channel=payload.channel,
        notification_status=notification_status,
        recipient_email=action.recipient_email,
        thread_id=thread_id,
    )


@app.post("/api/actions/{notification_id}/resolve")
def resolve_notification(notification_id: int, payload: dict[str, Any], session: Session = Depends(get_session)):
    event = session.get(NotificationEvent, notification_id)
    if not event:
        raise HTTPException(status_code=404, detail="Notification not found")
    signal = payload.get("signal", "complete")
    body_map = {"complete": "Approved", "progress": "Will do, working on it", "none": "No response yet"}
    body = body_map.get(signal, "Approved")
    analytics = _analytics(session)
    updated = analytics.apply_reply(
        event=event,
        body=body,
        sender_email=event.recipient_email,
        received_at=datetime.utcnow(),
        message_id=f"manual-resolve-{notification_id}",
        subject=f"Re: {event.subject}",
    )
    session.commit()
    return {"status": "resolved", "signal": signal, "entity_updated": updated}


@app.post("/api/integrations/gmail/sync", response_model=GmailSyncResponse)
def sync_gmail(session: Session = Depends(get_session)):
    service = GmailService()
    status = service.status()
    if not status.configured:
        raise HTTPException(status_code=503, detail=status.detail)

    analytics = _analytics(session)
    thread_events = analytics.pending_gmail_threads()
    replies = service.sync_threads([event.thread_id or "" for event in thread_events])
    event_by_thread = {event.thread_id: event for event in thread_events if event.thread_id}
    updated_actions = 0
    updated_entities = 0

    for reply in replies:
        event = event_by_thread.get(reply.thread_id)
        if event is None:
            continue
        duplicate = session.scalar(
            select(NotificationEvent.id).where(NotificationEvent.external_message_id == reply.message_id).limit(1)
        )
        if duplicate:
            continue
        if analytics.apply_reply(
            event=event,
            body=reply.body,
            sender_email=reply.sender_email,
            received_at=reply.received_at,
            message_id=reply.message_id,
            subject=reply.subject,
        ):
            updated_actions += 1
            updated_entities += 1

    analytics.set_gmail_last_sync(datetime.utcnow().isoformat())
    session.commit()
    return GmailSyncResponse(
        synced_threads=len(replies),
        updated_actions=updated_actions,
        updated_entities=updated_entities,
        detail="Gmail threads checked and matching replies applied to BFM actions.",
    )


@app.post("/api/data/reseed", response_model=DataResetResponse)
def reseed_data(regenerate_workbook: bool = False, session: Session = Depends(get_session)):
    if regenerate_workbook:
        generate_demo_workbook(settings.workbook_file)
    records_loaded = import_workbook_into_db(settings.workbook_file, session)
    session.commit()
    return DataResetResponse(
        workbook_path=str(settings.workbook_file),
        database_path=str(settings.sqlite_file),
        records_loaded=records_loaded,
    )


@app.get("/api/data/workbook")
def download_workbook():
    if not settings.workbook_file.exists():
        generate_demo_workbook(settings.workbook_file)
    return FileResponse(
        path=settings.workbook_file,
        filename=settings.workbook_file.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/api/data/upload", response_model=DataResetResponse)
async def upload_workbook(file: UploadFile = File(...), session: Session = Depends(get_session)):
    suffix = Path(file.filename or "uploaded.xlsx").suffix.lower()
    if suffix != ".xlsx":
        raise HTTPException(status_code=400, detail="Upload an .xlsx workbook.")

    destination = settings.upload_path / (file.filename or "uploaded.xlsx")
    content = await file.read()
    destination.write_bytes(content)
    records_loaded = import_workbook_into_db(destination, session)
    session.commit()
    return DataResetResponse(
        workbook_path=str(destination),
        database_path=str(settings.sqlite_file),
        records_loaded=records_loaded,
    )
