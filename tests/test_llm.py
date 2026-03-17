from __future__ import annotations

import importlib
import sys


def test_structured_output_models_use_chat_completions(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-test")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-test-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1")

    for module_name in ["bfm_agent.config", "bfm_agent.llm"]:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])

    llm = importlib.import_module("bfm_agent.llm")

    openai_model = llm._openai_model()
    azure_model = llm._azure_model()

    assert openai_model is not None
    assert openai_model.use_responses_api is False
    assert azure_model is not None
    assert azure_model.use_responses_api is False
