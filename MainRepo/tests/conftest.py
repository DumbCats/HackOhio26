import pytest

from app import config


@pytest.fixture(autouse=True)
def no_live_llm(monkeypatch):
    """Tests never call Gemini unless they set a key and fake llm._generate themselves."""
    monkeypatch.setattr(config, "GEMINI_API_KEY", None)


@pytest.fixture
def mock_tools(monkeypatch):
    """Chat logic tests: the 4 chat tools return the contract mocks (mock rule, API.md section 3),
    so expected strings stay pinned to contracts/mocks/ instead of the live models."""
    import json
    from app.chat import tools
    from app.sim import feed

    mocks = config.REPO_ROOT / "contracts" / "mocks"
    load = lambda n: json.loads((mocks / n).read_text(encoding="utf-8"))

    def restoration(ctx):
        t = ctx["t"]
        return load("restoration_not_out.json" if t < 4.3 else
                    "restoration_restored.json" if t >= 18.4 else "restoration.json")

    monkeypatch.setitem(tools.TOOLS, "get_forecast", lambda ctx: load("forecast.json"))
    monkeypatch.setitem(tools.TOOLS, "get_restoration", restoration)
    monkeypatch.setitem(tools.TOOLS, "get_prep", lambda ctx: load("prep.json"))
    monkeypatch.setitem(tools.TOOLS, "get_alerts", lambda ctx: load("alerts.json"))
    monkeypatch.setattr(feed, "home_info", lambda home_id: {})


@pytest.fixture(scope="session")
def demo_homes():
    """Real demo home ids (data/demo_homes.json, or picked live if the salt differs)."""
    from app.sim.scenario import get_scenario
    return {h["role"]: h["home_id"] for h in get_scenario()["homes"]}
