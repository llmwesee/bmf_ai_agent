from __future__ import annotations

from functools import lru_cache
from typing import Any

from langfuse import Langfuse

from bfm_agent.config import get_settings


@lru_cache
def get_langfuse_client() -> Langfuse | None:
    settings = get_settings()
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
        environment=settings.app_env,
    )


def log_agent_run(input_payload: dict[str, Any], output_payload: dict[str, Any], metadata: dict[str, Any] | None = None) -> tuple[str | None, str | None]:
    client = get_langfuse_client()
    if client is None:
        return None, None
    trace_id = client.create_trace_id()
    client.create_event(
        trace_context={"trace_id": trace_id},
        name="bfm-agent-follow-up",
        input=input_payload,
        output=output_payload,
        metadata=metadata or {},
    )
    client.flush()
    return trace_id, client.get_trace_url(trace_id=trace_id)
