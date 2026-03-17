from __future__ import annotations

import importlib
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


def _make_client(monkeypatch, env_overrides: dict[str, str] | None = None):
    sandbox = Path.cwd() / ".test-artifacts" / uuid4().hex
    sandbox.mkdir(parents=True, exist_ok=True)
    (sandbox / "uploads").mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("SQLITE_PATH", str(sandbox / "bfm_demo.db"))
    monkeypatch.setenv("WORKBOOK_PATH", str(sandbox / "bfm_demo_data.xlsx"))
    monkeypatch.setenv("UPLOAD_DIR", str(sandbox / "uploads"))
    monkeypatch.setenv("DEFAULT_PROVIDER", "mock")
    for key, value in (env_overrides or {}).items():
        monkeypatch.setenv(key, value)

    for module_name in [
        "bfm_agent.config",
        "bfm_agent.db",
        "bfm_agent.models",
        "bfm_agent.seed_data",
        "bfm_agent.analytics",
        "bfm_agent.gmail",
        "bfm_agent.llm",
        "bfm_agent.langfuse_utils",
        "bfm_agent.app",
    ]:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])

    app_module = importlib.import_module("bfm_agent.app")
    return TestClient(app_module.app)


@pytest.fixture
def client(monkeypatch):
    with _make_client(monkeypatch) as test_client:
        yield test_client


@pytest.fixture
def invalid_openai_client(monkeypatch):
    with _make_client(
        monkeypatch,
        {
            "OPENAI_API_KEY": "sk-prоj-invalid",
        },
    ) as test_client:
        yield test_client
