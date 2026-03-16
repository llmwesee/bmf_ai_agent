from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    industry: Mapped[str] = mapped_column(String(120))
    delivery_unit: Mapped[str] = mapped_column(String(120))
    account_manager: Mapped[str] = mapped_column(String(120))
    account_manager_email: Mapped[str] = mapped_column(String(200))
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
    contract_value: Mapped[float] = mapped_column(Float)
    revenue_plan_month: Mapped[float] = mapped_column(Float)
    revenue_plan_quarter: Mapped[float] = mapped_column(Float)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    last_revenue_update: Mapped[date] = mapped_column(Date)
    billing_cycle_days: Mapped[int] = mapped_column(Integer)

    account: Mapped["Account"] = relationship(back_populates="projects")
    revenues: Mapped[list["RevenueSnapshot"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    billings: Mapped[list["BillingRecord"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    invoices: Mapped[list["InvoiceRecord"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class RevenueSnapshot(Base):
    __tablename__ = "revenue_snapshots"
    __table_args__ = (UniqueConstraint("project_id", "period_label", name="uq_project_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    period_label: Mapped[str] = mapped_column(String(20))
    snapshot_date: Mapped[date] = mapped_column(Date)
    planned_revenue: Mapped[float] = mapped_column(Float)
    recognized_revenue: Mapped[float] = mapped_column(Float)
    forecast_revenue: Mapped[float] = mapped_column(Float)
    burn_rate_weekly: Mapped[float] = mapped_column(Float)

    project: Mapped["Project"] = relationship(back_populates="revenues")


class BillingRecord(Base):
    __tablename__ = "billing_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    milestone_name: Mapped[str] = mapped_column(String(160))
    billable_amount: Mapped[float] = mapped_column(Float)
    billed_amount: Mapped[float] = mapped_column(Float)
    unbilled_amount: Mapped[float] = mapped_column(Float)
    billing_due_date: Mapped[date] = mapped_column(Date)
    billed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delay_days: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40))

    project: Mapped["Project"] = relationship(back_populates="billings")


class InvoiceRecord(Base):
    __tablename__ = "invoice_records"
    __table_args__ = (UniqueConstraint("invoice_number", name="uq_invoice_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    invoice_number: Mapped[str] = mapped_column(String(60))
    invoice_amount: Mapped[float] = mapped_column(Float)
    collected_amount: Mapped[float] = mapped_column(Float)
    invoice_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    collected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    overdue_days: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40))

    project: Mapped["Project"] = relationship(back_populates="invoices")


class FollowUpLog(Base):
    __tablename__ = "follow_up_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(40))
    focus_area: Mapped[str] = mapped_column(String(40))
    subject: Mapped[str] = mapped_column(String(200))
    message_body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
