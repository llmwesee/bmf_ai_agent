from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from bfm_agent.analytics import AnalyticsService
from bfm_agent.langfuse_utils import log_agent_run
from bfm_agent.llm import generate_follow_up
from bfm_agent.schemas import AgentKey, AgentRequest, AgentResponse


class AgentState(TypedDict, total=False):
    request: AgentRequest
    context: dict[str, object]
    supporting_facts: list[str]
    summary: str
    risk_level: str
    draft: dict[str, str]


class BFMAgentRunner:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.analytics = AnalyticsService(session)
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("load_context", self._load_context)
        graph.add_node("analyze_revenue", self._analyze_revenue)
        graph.add_node("analyze_billing", self._analyze_billing)
        graph.add_node("analyze_unbilled", self._analyze_unbilled)
        graph.add_node("analyze_collections", self._analyze_collections)
        graph.add_node("analyze_forecast", self._analyze_forecast)
        graph.add_node("draft_follow_up", self._draft_follow_up)
        graph.add_edge(START, "load_context")
        graph.add_conditional_edges(
            "load_context",
            self._route_agent,
            {
                "revenue_realization": "analyze_revenue",
                "billing_trigger": "analyze_billing",
                "unbilled_revenue": "analyze_unbilled",
                "collection_monitoring": "analyze_collections",
                "revenue_forecasting": "analyze_forecast",
            },
        )
        graph.add_edge("analyze_revenue", "draft_follow_up")
        graph.add_edge("analyze_billing", "draft_follow_up")
        graph.add_edge("analyze_unbilled", "draft_follow_up")
        graph.add_edge("analyze_collections", "draft_follow_up")
        graph.add_edge("analyze_forecast", "draft_follow_up")
        graph.add_edge("draft_follow_up", END)
        return graph.compile()

    def _load_context(self, state: AgentState) -> AgentState:
        request = state["request"]
        return {
            "context": self.analytics.entity_context(
                agent_key=request.agent_key,
                entity_type=request.entity_type,
                entity_id=request.entity_id,
            )
        }

    def _route_agent(self, state: AgentState) -> AgentKey:
        return state["request"].agent_key

    def _analyze_revenue(self, state: AgentState) -> AgentState:
        context = state["context"]
        metrics = context["summary_metrics"]
        plan = float(metrics["revenue_plan"])
        forecast = float(metrics["revenue_forecast"])
        recognized = float(metrics["revenue_recognized"])
        gap = float(metrics["revenue_gap"])
        shortfall = abs(gap) / plan if plan and gap < 0 else 0.0
        facts = [
            f"{context['project_code']} has recognized ${recognized:,.0f} against a monthly target of ${plan:,.0f}.",
            f"Forecast is ${forecast:,.0f}, creating a ${gap:,.0f} variance to plan.",
            f"Current unbilled revenue is ${float(metrics['unbilled_revenue']):,.0f} and the last update is aging.",
        ]
        summary = f"{context['account_name']} revenue realization is under target and needs account manager follow-up."
        return {
            "supporting_facts": facts,
            "summary": summary,
            "risk_level": self._risk_from_queue("revenue_realization", state["request"].entity_type, state["request"].entity_id),
        }

    def _analyze_billing(self, state: AgentState) -> AgentState:
        context = state["context"]
        metrics = context["summary_metrics"]
        facts = [
            f"{context['primary_record']['milestone_name']} completed on {context['primary_record']['completion_date']}.",
            f"${float(metrics['billable_amount']):,.0f} is billable and ${float(metrics['unbilled_amount']):,.0f} remains pending invoicing.",
            f"Billing trigger delay is {int(metrics['billing_delay_days'])} days with response status {context['primary_record']['account_manager_response']}.",
        ]
        summary = f"{context['account_name']} has a billing trigger exception that can delay revenue realization."
        return {
            "supporting_facts": facts,
            "summary": summary,
            "risk_level": self._risk_from_queue("billing_trigger", state["request"].entity_type, state["request"].entity_id),
        }

    def _analyze_unbilled(self, state: AgentState) -> AgentState:
        context = state["context"]
        metrics = context["summary_metrics"]
        facts = [
            f"{context['project_code']} has ${float(metrics['unbilled_revenue']):,.0f} recognized but not billed.",
            f"The unbilled aging is {int(metrics['days_unbilled'])} days.",
            f"Revenue forecast remains ${float(metrics['revenue_forecast']):,.0f} while billing is pending.",
        ]
        summary = f"{context['account_name']} has unbilled revenue exposure that needs billing release."
        return {
            "supporting_facts": facts,
            "summary": summary,
            "risk_level": self._risk_from_queue("unbilled_revenue", state["request"].entity_type, state["request"].entity_id),
        }

    def _analyze_collections(self, state: AgentState) -> AgentState:
        context = state["context"]
        metrics = context["summary_metrics"]
        facts = [
            f"Invoice {context['primary_record']['invoice_number']} has an outstanding balance of ${float(metrics['outstanding_balance']):,.0f}.",
            f"The invoice is overdue by {int(metrics['overdue_days'])} days against due date {context['primary_record']['due_date']}.",
            f"The client response status is {context['primary_record']['client_response_status']}.",
        ]
        summary = f"{context['account_name']} collections risk is increasing and payment follow-up is required."
        return {
            "supporting_facts": facts,
            "summary": summary,
            "risk_level": self._risk_from_queue("collection_monitoring", state["request"].entity_type, state["request"].entity_id),
        }

    def _analyze_forecast(self, state: AgentState) -> AgentState:
        context = state["context"]
        metrics = context["summary_metrics"]
        plan = float(metrics["revenue_plan"])
        forecast = float(metrics["revenue_forecast"])
        facts = [
            f"{context['project_code']} is forecast to close at ${forecast:,.0f} against a ${plan:,.0f} target.",
            f"Forecast confidence is {float(metrics['forecast_confidence']):.0%}.",
            f"Unbilled revenue and outstanding receivables are contributing to the shortfall risk.",
        ]
        summary = f"{context['account_name']} forecast is at risk of missing the monthly revenue target."
        return {
            "supporting_facts": facts,
            "summary": summary,
            "risk_level": self._risk_from_queue("revenue_forecasting", state["request"].entity_type, state["request"].entity_id),
        }

    def _draft_follow_up(self, state: AgentState) -> AgentState:
        request = state["request"]
        draft = generate_follow_up(
            provider=request.provider,
            focus_area=request.agent_key,
            context=state["context"],
            supporting_facts=state["supporting_facts"],
            question=request.question,
        )
        return {"draft": draft.model_dump()}

    def _risk_from_queue(self, agent_key: AgentKey, entity_type: str, entity_id: int) -> str:
        for item in self.analytics.dashboard_queue():
            if item.agent_key == agent_key and item.entity_type == entity_type and item.entity_id == entity_id:
                return item.severity
        return "Low"

    def run(self, request: AgentRequest) -> AgentResponse:
        state = self.graph.invoke({"request": request})
        context = state["context"]
        draft = state["draft"]
        trace_id, trace_url = log_agent_run(
            input_payload=request.model_dump(),
            output_payload={"summary": state["summary"], "risk_level": state["risk_level"], "nudge": draft["nudge"]},
            metadata={
                "account_name": context["account_name"],
                "project_code": context.get("project_code"),
                "agent_key": request.agent_key,
            },
        )
        return AgentResponse(
            provider=request.provider,
            agent_key=request.agent_key,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            account_name=str(context["account_name"]),
            project_code=str(context.get("project_code")) if context.get("project_code") else None,
            summary=state["summary"],
            risk_level=state["risk_level"],
            supporting_facts=state["supporting_facts"],
            nudge=draft["nudge"],
            email_subject=draft["subject"],
            email_body=draft["body"],
            recommended_action=draft["recommended_action"],
            trace_id=trace_id,
            trace_url=trace_url,
        )
