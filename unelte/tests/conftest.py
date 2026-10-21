"""Fixture-uri comune: HOME, config și stare temporare; AI fals; fără rețea."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

_BOOT = Path(tempfile.mkdtemp(prefix="unelte-test-"))
os.environ["UNELTE_CONFIG_DIR"] = str(_BOOT / "config")
os.environ["UNELTE_STATE"] = str(_BOOT / "state")
os.environ["AI_CONFIG"] = str(_BOOT / "ai" / "ai.toml")
os.environ["AI_STATE"] = str(_BOOT / "ai-state")
sys.path.insert(0, str(Path(__file__).parent))

import pytest  # noqa: E402

from fals_ai import FakeAIServer, write_config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def needs(program):
    return pytest.mark.skipif(shutil.which(program) is None, reason=f"lipsește {program}")


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Foldere de config și stare goale; întoarce folderul de config."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    monkeypatch.setenv("UNELTE_CONFIG_DIR", str(cfg))
    monkeypatch.setenv("UNELTE_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("AI_CONFIG", str(tmp_path / "ai" / "ai.toml"))
    monkeypatch.setenv("AI_STATE", str(tmp_path / "ai-state"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    (tmp_path / "gitconfig").write_text("[user]\n\tname = Test\n\temail = test@example.com\n"
                                       "[init]\n\tdefaultBranch = main\n")
    return cfg


def set_config(cfg_dir: Path, text: str) -> None:
    (cfg_dir / "config.toml").write_text(text, encoding="utf-8")


@pytest.fixture
def fake_ai(tmp_path, monkeypatch):
    s = FakeAIServer("openai").start()
    cfg = tmp_path / "ai" / "ai.toml"
    cfg.parent.mkdir(exist_ok=True)
    write_config(cfg, s.url, "openai")
    monkeypatch.setenv("AI_CONFIG", str(cfg))
    from unelte.ai import client
    monkeypatch.setattr(client, "_sleep", lambda s: None)
    client._schema_rejected.clear()
    yield s
    s.stop()
