"""Fixture-uri comune: folder de notițe temporar, cache temporar, AI fals, fără rețea."""
import os
import sys
import tempfile
from pathlib import Path

_BOOT = Path(tempfile.mkdtemp(prefix="studiu-test-"))
(_BOOT / "config.toml").write_text("", encoding="utf-8")
os.environ["STUDIU_CONFIG"] = str(_BOOT / "config.toml")
os.environ["STUDIU_NOTITE"] = str(_BOOT / "notite")
os.environ["STUDIU_DATE"] = str(_BOOT / "data")
os.environ["AI_CONFIG"] = str(_BOOT / "ai" / "ai.toml")
os.environ["AI_STATE"] = str(_BOOT / "ai-state")
sys.path.insert(0, str(Path(__file__).parent))

import pytest  # noqa: E402

from app import config as appcfg  # noqa: E402
from app import storage  # noqa: E402
from fals_ai import FakeAIServer, write_config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def notes(tmp_path, monkeypatch):
    """Un folder de notițe gol și un cache gol, cu configurația implicită."""
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("STUDIU_NOTITE", str(tmp_path / "notite"))
    monkeypatch.setenv("STUDIU_DATE", str(tmp_path / "data"))
    monkeypatch.setenv("AI_CONFIG", str(tmp_path / "ai" / "ai.toml"))
    monkeypatch.setenv("AI_STATE", str(tmp_path / "ai-state"))
    appcfg.replace(appcfg.load(cfg_file))
    (tmp_path / "notite").mkdir()
    storage.ensure()
    yield tmp_path / "notite"
    from app import jobs
    jobs.wait_idle()


def write(base: Path, rel: str, text: str) -> Path:
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def fake_ai(tmp_path, monkeypatch):
    s = FakeAIServer("openai").start()
    cfg = tmp_path / "ai" / "ai.toml"
    cfg.parent.mkdir(exist_ok=True)
    write_config(cfg, s.url, "openai")
    monkeypatch.setenv("AI_CONFIG", str(cfg))
    from app.ai import client
    monkeypatch.setattr(client, "_sleep", lambda s: None)
    client._schema_rejected.clear()
    yield s
    s.stop()


@pytest.fixture
def client(notes):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
