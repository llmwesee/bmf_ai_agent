from __future__ import annotations

from functools import lru_cache
import logging

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from bfm_agent.config import Settings, get_settings
from bfm_agent.schemas import FollowUpDraft, ProviderStatus


logger = logging.getLogger(__name__)


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


class ProviderConfigurationError(RuntimeError):
    pass


def _ascii_secret_issue(env_var: str, value: str | None) -> str | None:
    if not value:
        return f"Set {env_var} to enable."
    if value.isascii():
        return None
    return f"{env_var} contains non-ASCII characters. Retype or paste the key again using plain ASCII characters."


def _openai_configuration_issue(settings: Settings) -> str | None:
    return _ascii_secret_issue("OPENAI_API_KEY", settings.openai_api_key)


def _azure_configuration_issue(settings: Settings) -> str | None:
    missing = [
        env_var
        for env_var, value in [
            ("AZURE_OPENAI_API_KEY", settings.azure_openai_api_key),
            ("AZURE_OPENAI_ENDPOINT", settings.azure_openai_endpoint),
            ("AZURE_OPENAI_DEPLOYMENT", settings.azure_openai_deployment),
        ]
        if not value
    ]
    if missing:
        return f"Set {', '.join(missing)} to enable."
    return _ascii_secret_issue("AZURE_OPENAI_API_KEY", settings.azure_openai_api_key)


def _provider_configuration_issue(provider: str, settings: Settings) -> str | None:
    if provider == "openai":
        return _openai_configuration_issue(settings)
    if provider == "azure_openai":
        return _azure_configuration_issue(settings)
    return None


def provider_statuses(settings: Settings | None = None) -> list[ProviderStatus]:
    settings = settings or get_settings()
    openai_issue = _openai_configuration_issue(settings)
    azure_issue = _azure_configuration_issue(settings)
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
            available=openai_issue is None,
            detail="Configured with OpenAI GPT-4.1." if openai_issue is None else openai_issue,
        ),
        ProviderStatus(
            provider="azure_openai",
            model=settings.azure_openai_model,
            available=azure_issue is None,
            detail=(
                "Configured with Azure OpenAI GPT-4.1 deployment."
                if azure_issue is None
                else azure_issue
            ),
        ),
    ]


def _fallback_draft(context: dict[str, object], supporting_facts: list[str], focus_area: str) -> FollowUpDraft:
    account_name = str(context["account_name"])
    project_code = str(context.get("project_code") or "portfolio")
    recipient_name = str(context.get("recipient_name") or context.get("account_manager") or "team")
    metrics = context.get("summary_metrics", {})
    revenue_plan = float(metrics.get("revenue_plan", 0.0)) if isinstance(metrics, dict) else 0.0
    revenue_forecast = float(metrics.get("revenue_forecast", 0.0)) if isinstance(metrics, dict) else 0.0
    revenue_gap = float(metrics.get("revenue_gap", revenue_forecast - revenue_plan)) if isinstance(metrics, dict) else 0.0
    shortfall = abs(revenue_gap) / revenue_plan if revenue_plan and revenue_gap < 0 else 0.0

    nudge = f"{account_name} {focus_area.replace('_', ' ')} needs follow-up. Do you want me to contact {recipient_name} for {project_code}?"
    if focus_area == "revenue_realization" and revenue_plan:
        nudge = (
            f"{account_name} account revenue is running {shortfall:.0%} below monthly target. "
            f"Do you want me to follow up with {recipient_name}?"
        )
    if focus_area == "billing_trigger":
        nudge = (
            f"{account_name} billing trigger is pending for {project_code}. "
            f"Do you want me to follow up with {recipient_name}?"
        )
    if focus_area == "unbilled_revenue":
        nudge = (
            f"{account_name} has recognized revenue waiting to be billed on {project_code}. "
            f"Do you want me to follow up with {recipient_name}?"
        )
    if focus_area == "collection_monitoring":
        nudge = (
            f"{account_name} has an overdue collection item on {project_code}. "
            f"Do you want me to send a payment reminder to {recipient_name}?"
        )
    if focus_area == "revenue_forecasting" and revenue_plan:
        nudge = (
            f"{account_name} is forecast below target for {project_code}. "
            f"Do you want me to review pending billing milestones with {recipient_name}?"
        )

    subject = f"Action needed: {account_name} {focus_area.replace('_', ' ')} follow-up for {project_code}"
    body = (
        f"Hi {recipient_name},\n\n"
        f"I am reviewing the current finance position for {account_name}"
        f"{' / ' + project_code if project_code != 'portfolio' else ''}. "
        f"The current forecast variance is ${revenue_gap:,.0f} against plan.\n\n"
        f"Key points:\n- " + "\n- ".join(supporting_facts[:3]) + "\n\n"
        "Please confirm the current blocker, the expected closure date, and any support needed from finance so the BFM team can close the item in this cycle.\n\n"
        "Regards,\nBFM Operations"
    )
    return FollowUpDraft(
        nudge=nudge,
        subject=subject,
        body=body,
        recommended_action="Review blockers with the owner and close the finance dependency this week.",
    )


@lru_cache
def _openai_model() -> ChatOpenAI | None:
    settings = get_settings()
    issue = _openai_configuration_issue(settings)
    if issue:
        logger.warning("OpenAI provider unavailable: %s", issue)
        return None
    return ChatOpenAI(
        model=settings.openai_model,
        temperature=0,
        openai_api_key=settings.openai_api_key,
        # Structured output via the Responses API emits serializer warnings in the
        # current langchain-openai/openai stack, so keep this flow on chat
        # completions until that path stabilizes.
        use_responses_api=False,
    )


@lru_cache
def _azure_model() -> AzureChatOpenAI | None:
    settings = get_settings()
    issue = _azure_configuration_issue(settings)
    if issue:
        logger.warning("Azure OpenAI provider unavailable: %s", issue)
        return None
    return AzureChatOpenAI(
        model=settings.azure_openai_model,
        azure_deployment=settings.azure_openai_deployment,
        api_version=settings.azure_openai_api_version,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        temperature=0,
        use_responses_api=False,
    )


def _model_for_provider(provider: str):
    if provider == "openai":
        return _openai_model()
    if provider == "azure_openai":
        return _azure_model()
    return None


def generate_follow_up(provider: str, focus_area: str, context: dict[str, object], supporting_facts: list[str], question: str | None) -> FollowUpDraft:
    settings = get_settings()
    issue = _provider_configuration_issue(provider, settings)
    if issue:
        raise ProviderConfigurationError(issue)

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
