import pytest

from app import config


@pytest.fixture(autouse=True)
def no_live_llm(monkeypatch):
    """Tests never call Gemini unless they set a key and fake llm._generate themselves."""
    monkeypatch.setattr(config, "GEMINI_API_KEY", None)
