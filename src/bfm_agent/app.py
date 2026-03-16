from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from bfm_agent.agent.graph import BFMAgentRunner
from bfm_agent.analytics import AnalyticsService
from bfm_agent.config import get_settings
from bfm_agent.db import get_session
from bfm_agent.llm import provider_statuses
from bfm_agent.schemas import AgentRequest, AgentResponse, DataResetResponse
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


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "default_provider": settings.default_provider,
        },
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/api/providers")
def providers():
    return provider_statuses()


@app.get("/api/summary")
def summary(session: Session = Depends(get_session)):
    return _analytics(session).summary()


@app.get("/api/revenue-table")
def revenue_table(session: Session = Depends(get_session)):
    return _analytics(session).revenue_rows()


@app.get("/api/alerts")
def alerts(limit: int = 8, session: Session = Depends(get_session)):
    return _analytics(session).alerts(limit=limit)


@app.get("/api/collections")
def collections(session: Session = Depends(get_session)):
    return _analytics(session).collection_rows()


@app.get("/api/report")
def report(session: Session = Depends(get_session)):
    return _analytics(session).report()


@app.post("/api/agent/draft-followup", response_model=AgentResponse)
def draft_follow_up(payload: AgentRequest, session: Session = Depends(get_session)):
    if not payload.account_name and not payload.project_code:
        raise HTTPException(status_code=400, detail="Provide at least an account_name or project_code.")
    return BFMAgentRunner(session).run(payload)


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
