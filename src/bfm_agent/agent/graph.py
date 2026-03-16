from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from bfm_agent.analytics import AnalyticsService
from bfm_agent.langfuse_utils import log_agent_run
from bfm_agent.llm import generate_follow_up
from bfm_agent.models import FollowUpLog
from bfm_agent.schemas import AgentRequest, AgentResponse


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
        graph.add_node("prepare_findings", self._prepare_findings)
        graph.add_node("draft_follow_up", self._draft_follow_up)
        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "prepare_findings")
        graph.add_edge("prepare_findings", "draft_follow_up")
        graph.add_edge("draft_follow_up", END)
        return graph.compile()

    def _load_context(self, state: AgentState) -> AgentState:
        request = state["request"]
        return {"context": self.analytics.account_snapshot(account_name=request.account_name, project_code=request.project_code)}

    def _prepare_findings(self, state: AgentState) -> AgentState:
        request = state["request"]
        context = state["context"]
        primary = context["primary_row"]
        totals = context["totals"]
        gap_ratio = abs(float(totals["revenue_gap"])) / float(totals["revenue_plan"]) if float(totals["revenue_plan"]) else 0.0
        supporting_facts = [
            f"{primary['project_code']} has recognized ${float(primary['revenue_recognized']):,.0f} against a monthly plan of ${float(primary['revenue_plan']):,.0f}.",
            f"Portfolio forecast variance is ${float(totals['revenue_gap']):,.0f}, equivalent to {gap_ratio:.0%} below target.",
            f"Unbilled revenue stands at ${float(totals['total_unbilled']):,.0f} and overdue collections total ${float(totals['overdue_amount']):,.0f}.",
        ]
        if request.focus_area == "billing":
            supporting_facts.append(
                f"{primary['project_code']} is carrying ${float(primary['unbilled_amount']):,.0f} unbilled with {int(primary['billing_delay_days'])} delay days."
            )
        if request.focus_area == "collections":
            supporting_facts.append(
                f"{primary['project_code']} has ${float(primary['outstanding_collection']):,.0f} outstanding with {int(primary['overdue_days'])} overdue days."
            )
        summary = (
            f"{context['account_name']} is {context['risk_level'].lower()} risk with a "
            f"${float(totals['revenue_gap']):,.0f} forecast gap and ${float(totals['total_unbilled']):,.0f} pending billing."
        )
        return {"supporting_facts": supporting_facts, "summary": summary, "risk_level": str(context["risk_level"])}

    def _draft_follow_up(self, state: AgentState) -> AgentState:
        request = state["request"]
        draft = generate_follow_up(
            provider=request.provider,
            focus_area=request.focus_area,
            context=state["context"],
            supporting_facts=state["supporting_facts"],
            question=request.question,
        )
        return {"draft": draft.model_dump()}

    def run(self, request: AgentRequest) -> AgentResponse:
        state = self.graph.invoke({"request": request})
        context = state["context"]
        draft = state["draft"]
        self.session.add(
            FollowUpLog(
                account_id=None,
                project_id=None,
                provider=request.provider,
                focus_area=request.focus_area,
                subject=draft["subject"],
                message_body=draft["body"],
            )
        )
        self.session.commit()
        trace_id, trace_url = log_agent_run(
            input_payload=request.model_dump(),
            output_payload={"summary": state["summary"], "risk_level": state["risk_level"], "nudge": draft["nudge"]},
            metadata={"account_name": context["account_name"], "project_code": context["project_code"]},
        )
        return AgentResponse(
            provider=request.provider,
            account_name=str(context["account_name"]),
            project_code=str(context["project_code"]),
            focus_area=request.focus_area,
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
