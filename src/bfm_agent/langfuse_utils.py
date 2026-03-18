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
    tracer = TraceLogger(name="bfm-agent-follow-up", input_payload=input_payload, metadata=metadata)
    tracer.log(
        name="bfm-agent-output",
        input_payload={"type": "output"},
        output_payload=output_payload,
        metadata={"phase": "output"},
    )
    return tracer.finalize()


class TraceLogger:
    def __init__(self, name: str, input_payload: dict[str, Any], metadata: dict[str, Any] | None = None) -> None:
        self.client = get_langfuse_client()
        self.trace_id: str | None = None
        self._trace_url: str | None = None
        if self.client is None:
            return
        try:
            self.trace_id = self.client.create_trace_id()
            self.client.create_event(
                trace_context={"trace_id": self.trace_id},
                name=name,
                input=input_payload,
                metadata=metadata or {},
            )
        except Exception:
            self.trace_id = None

    def log(
        self,
        name: str,
        input_payload: dict[str, Any] | None = None,
        output_payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        status_message: str | None = None,
    ) -> None:
        if self.client is None or self.trace_id is None:
            return
        try:
            self.client.create_event(
                trace_context={"trace_id": self.trace_id},
                name=name,
                input=input_payload,
                output=output_payload,
                metadata=metadata or {},
                status_message=status_message,
            )
        except Exception:
            return

    def finalize(self) -> tuple[str | None, str | None]:
        if self.client is None or self.trace_id is None:
            return None, None
        try:
            self.client.flush()
            try:
                self._trace_url = self.client.get_trace_url(trace_id=self.trace_id)
            except Exception:
                self._trace_url = None
        except Exception:
            return None, None
        return self.trace_id, self._trace_url
