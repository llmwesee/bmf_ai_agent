from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AppConfig(Base):
    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    industry: Mapped[str] = mapped_column(String(120))
    delivery_unit: Mapped[str] = mapped_column(String(120))
    account_manager: Mapped[str] = mapped_column(String(120))
    account_manager_email: Mapped[str] = mapped_column(String(200))
    client_contact_name: Mapped[str] = mapped_column(String(120))
    client_contact_email: Mapped[str] = mapped_column(String(200))
    contract_value: Mapped[float] = mapped_column(Float)
    monthly_target: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    projects: Mapped[list["Project"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    service_line: Mapped[str] = mapped_column(String(120))
    billing_type: Mapped[str] = mapped_column(String(40))
    billing_owner: Mapped[str] = mapped_column(String(120))
    billing_owner_email: Mapped[str] = mapped_column(String(200))
    contract_value: Mapped[float] = mapped_column(Float)
    revenue_plan_month: Mapped[float] = mapped_column(Float)
    revenue_plan_quarter: Mapped[float] = mapped_column(Float)
    revenue_recognized: Mapped[float] = mapped_column(Float)
    recognized_last_7_days: Mapped[float] = mapped_column(Float)
    recognized_last_30_days: Mapped[float] = mapped_column(Float)
    pending_pipeline: Mapped[float] = mapped_column(Float)
    forecast_bias: Mapped[float] = mapped_column(Float, default=1.0)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    last_revenue_update: Mapped[date] = mapped_column(Date)
    billing_cycle_days: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account: Mapped["Account"] = relationship(back_populates="projects")
    milestones: Mapped[list["BillingMilestone"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    invoices: Mapped[list["InvoiceRecord"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class BillingMilestone(Base):
    __tablename__ = "billing_milestones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    milestone_name: Mapped[str] = mapped_column(String(160))
    completion_date: Mapped[date] = mapped_column(Date)
    billable_amount: Mapped[float] = mapped_column(Float)
    billed_amount: Mapped[float] = mapped_column(Float, default=0.0)
    invoice_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    invoice_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    billing_owner: Mapped[str] = mapped_column(String(120))
    billing_owner_email: Mapped[str] = mapped_column(String(200))
    account_manager_response: Mapped[str] = mapped_column(String(40), default="Pending")
    status_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="milestones")


class InvoiceRecord(Base):
    __tablename__ = "invoice_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    invoice_number: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    invoice_amount: Mapped[float] = mapped_column(Float)
    amount_received: Mapped[float] = mapped_column(Float, default=0.0)
    invoice_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    collected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    client_contact_name: Mapped[str] = mapped_column(String(120))
    client_contact_email: Mapped[str] = mapped_column(String(200))
    collection_owner: Mapped[str] = mapped_column(String(120))
    collection_owner_email: Mapped[str] = mapped_column(String(200))
    client_response_status: Mapped[str] = mapped_column(String(40), default="Pending")
    status_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="invoices")


class RiskThreshold(Base):
    __tablename__ = "risk_thresholds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_key: Mapped[str] = mapped_column(String(60), index=True)
    metric_key: Mapped[str] = mapped_column(String(60), index=True)
    label: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(20))
    medium_value: Mapped[float] = mapped_column(Float)
    high_value: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_key: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column(Integer)
    account_name: Mapped[str] = mapped_column(String(120))
    project_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    recipient_name: Mapped[str] = mapped_column(String(120))
    recipient_email: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(40))
    channel: Mapped[str] = mapped_column(String(40))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="Approved")
    approved_by: Mapped[str] = mapped_column(String(120), default="BFM Lead")
    approved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    latest_trace_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    latest_trace_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NotificationEvent(Base):
    __tablename__ = "notification_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_id: Mapped[int | None] = mapped_column(ForeignKey("agent_actions.id"), nullable=True, index=True)
    agent_key: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int] = mapped_column(Integer)
    direction: Mapped[str] = mapped_column(String(20))
    channel: Mapped[str] = mapped_column(String(40))
    subject: Mapped[str] = mapped_column(String(200))
    message_excerpt: Mapped[str] = mapped_column(Text)
    recipient_email: Mapped[str] = mapped_column(String(200))
    sender_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    external_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="Drafted")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    action: Mapped["AgentAction | None"] = relationship()
