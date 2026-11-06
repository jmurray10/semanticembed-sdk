"""The Gemini agent CLI loads without claude-agent-sdk and passes --model through."""

from __future__ import annotations

import importlib
import sys
import types

import pytest


class _Anything:
    """Accepts any constructor call; stands in for google.genai.types classes."""

    def __init__(self, *args, **kwargs):
        pass


class _TypesModule(types.ModuleType):
    def __getattr__(self, name):
        return _Anything


@pytest.fixture
def gemini_agent(monkeypatch):
    # Stand-in for google-genai so the test needs neither the package nor a key.
    google = types.ModuleType("google")
    genai = types.ModuleType("google.genai")
    genai.Client = _Anything
    genai.types = _TypesModule("google.genai.types")
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", genai.types)
    # The Gemini agent must load without claude-agent-sdk installed.
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", None)
    for mod in ("semanticembed.agent", "semanticembed.agent.agent", "semanticembed.agent.gemini_agent"):
        monkeypatch.delitem(sys.modules, mod, raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    return importlib.import_module("semanticembed.agent.gemini_agent")


@pytest.mark.parametrize("argv, expected", [
    (["--ask", "hi"], "gemini-2.5-flash"),
    (["--ask", "hi", "--model", "gemini-2.5-pro"], "gemini-2.5-pro"),
])
def test_model_flag_reaches_the_model_call(gemini_agent, monkeypatch, argv, expected):
    seen = {}

    def fake_loop(client, model, messages, path):
        seen["model"] = model
        return "ok"

    monkeypatch.setattr(gemini_agent, "run_agent_loop", fake_loop)
    monkeypatch.setattr(sys, "argv", ["semanticembed-gemini-agent", *argv])
    gemini_agent.main()
    assert seen["model"] == expected
