from __future__ import annotations

from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from bfm_agent.config import Settings, get_settings
from bfm_agent.schemas import FollowUpDraft, ProviderStatus


LLM_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a business finance management assistant for an IT services organization. "
            "Write concise operational finance follow-ups for BFM leads. "
            "Focus on revenue closure, billing unblockers, and collection outcomes. "
            "Keep the nudge short and the email practical, direct, and professional.",
        ),
        (
            "human",
            "Focus area: {focus_area}\n"
            "User question: {question}\n"
            "Portfolio context: {context}\n"
            "Supporting facts: {supporting_facts}\n"
            "Return a direct BFM recommendation.",
        ),
    ]
)


def provider_statuses(settings: Settings | None = None) -> list[ProviderStatus]:
    settings = settings or get_settings()
    return [
        ProviderStatus(
            provider="mock",
            model="deterministic-demo",
            available=True,
            detail="Always available for offline demo runs.",
        ),
        ProviderStatus(
            provider="openai",
            model=settings.openai_model,
            available=bool(settings.openai_api_key),
            detail="Configured with OpenAI GPT-4.1." if settings.openai_api_key else "Set OPENAI_API_KEY to enable.",
        ),
        ProviderStatus(
            provider="azure_openai",
            model=settings.azure_openai_model,
            available=bool(settings.azure_openai_api_key and settings.azure_openai_endpoint and settings.azure_openai_deployment),
            detail=(
                "Configured with Azure OpenAI GPT-4.1 deployment."
                if settings.azure_openai_api_key and settings.azure_openai_endpoint and settings.azure_openai_deployment
                else "Set Azure endpoint, key, and deployment to enable."
            ),
        ),
    ]


def _fallback_draft(context: dict[str, object], supporting_facts: list[str], focus_area: str) -> FollowUpDraft:
    primary = context["primary_row"]
    account_name = str(context["account_name"])
    project_code = str(primary["project_code"])
    account_manager = str(context["account_manager"])
    totals = context["totals"]
    gap_ratio = abs(float(totals["revenue_gap"])) / float(totals["revenue_plan"]) if float(totals["revenue_plan"]) else 0.0

    nudge = (
        f"{account_name} revenue is tracking {gap_ratio:.0%} below monthly target. "
        f"Do you want me to follow up with {account_manager} on {project_code}?"
    )
    subject = f"Action needed: {account_name} {focus_area} follow-up for {project_code}"
    body = (
        f"Hi {account_manager},\n\n"
        f"I am reviewing the current finance position for {account_name} / {project_code}. "
        f"We are seeing a portfolio forecast gap of ${float(totals['revenue_gap']):,.0f}, "
        f"along with ${float(totals['total_unbilled']):,.0f} pending billing and "
        f"${float(totals['overdue_amount']):,.0f} in outstanding collections.\n\n"
        f"Key points:\n- " + "\n- ".join(supporting_facts[:3]) + "\n\n"
        f"Please confirm the blockers, the expected closure date, and any support needed from finance so we can recover revenue in this cycle.\n\n"
        "Regards,\nBFM Operations"
    )
    return FollowUpDraft(
        nudge=nudge,
        subject=subject,
        body=body,
        recommended_action="Review blockers with the account manager and close billing or collection dependencies this week.",
    )


@lru_cache
def _openai_model() -> ChatOpenAI | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    return ChatOpenAI(
        model=settings.openai_model,
        temperature=0,
        openai_api_key=settings.openai_api_key,
        use_responses_api=True,
    )


@lru_cache
def _azure_model() -> AzureChatOpenAI | None:
    settings = get_settings()
    if not (settings.azure_openai_api_key and settings.azure_openai_endpoint and settings.azure_openai_deployment):
        return None
    return AzureChatOpenAI(
        model=settings.azure_openai_model,
        azure_deployment=settings.azure_openai_deployment,
        api_version=settings.azure_openai_api_version,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        temperature=0,
        use_responses_api=True,
    )


def _model_for_provider(provider: str):
    if provider == "openai":
        return _openai_model()
    if provider == "azure_openai":
        return _azure_model()
    return None


def generate_follow_up(provider: str, focus_area: str, context: dict[str, object], supporting_facts: list[str], question: str | None) -> FollowUpDraft:
    model = _model_for_provider(provider)
    if model is None:
        return _fallback_draft(context, supporting_facts, focus_area)

    runnable = LLM_PROMPT | model.with_structured_output(FollowUpDraft)
    return runnable.invoke(
        {
            "focus_area": focus_area,
            "question": question or "Prepare a follow-up for the account manager.",
            "context": context,
            "supporting_facts": supporting_facts,
        }
    )
