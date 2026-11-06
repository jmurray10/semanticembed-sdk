"""The Gemini agent CLI passes --model through to the model call."""

from __future__ import annotations

import importlib
import sys
import types

import pytest


@pytest.fixture
def gemini_agent(monkeypatch):
    # Stand-in for google-genai so the test needs neither the package nor a key.
    google = types.ModuleType("google")
    genai = types.ModuleType("google.genai")
    genai.Client = lambda **kwargs: object()
    genai.types = types.ModuleType("google.genai.types")
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", genai.types)
    monkeypatch.delitem(sys.modules, "semanticembed.agent.gemini_agent", raising=False)
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
