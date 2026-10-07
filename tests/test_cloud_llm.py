import os
from unittest.mock import patch

from pipeline.analysis.cloud_llm import resolve_synthesis_settings


def test_resolve_synthesis_auto_enables_with_gemini_key():
    cfg = {"enabled": False, "provider": "gemini", "model_id": None}
    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False):
        enabled, provider, model_id = resolve_synthesis_settings(cfg, {})
    assert enabled is True
    assert provider == "gemini"
    assert model_id == "gemini-2.0-flash"


def test_resolve_synthesis_prefers_groq_when_only_groq_key():
    cfg = {"enabled": False}
    with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test", "GEMINI_API_KEY": ""}, clear=False):
        enabled, provider, model_id = resolve_synthesis_settings(cfg, {})
    assert enabled is True
    assert provider == "groq"
    assert model_id == "llama-3.1-8b-instant"


def test_resolve_synthesis_explicit_huggingface_over_env():
    cfg = {"enabled": False, "provider": "huggingface", "model_id": None}
    with patch.dict(
        os.environ,
        {"GROQ_API_KEY": "gsk_test", "HF_TOKEN": "hf_test"},
        clear=False,
    ):
        enabled, provider, model_id = resolve_synthesis_settings(cfg, {})
    assert enabled is True
    assert provider == "huggingface"
    assert model_id == "Qwen/Qwen2.5-7B-Instruct"
