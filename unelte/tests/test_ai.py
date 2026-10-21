"""Testele stratului AI comun (fișier identic în Studiu și Unelte).
Aceleași scenarii rulează pe adaptorul openai și pe adaptorul anthropic."""
import json

import pytest

try:
    from app import ai
    from app.ai import client, config as aicfg, schema
except ImportError:  # proiectul Unelte
    from unelte import ai
    from unelte.ai import client, config as aicfg, schema

from fals_ai import FakeAIServer, write_config

SCHEMA = {
    "type": "object",
    "required": ["carduri"],
    "properties": {
        "carduri": {
            "type": "array", "minItems": 1,
            "items": {"type": "object", "required": ["intrebare"],
                      "properties": {"intrebare": {"type": "string", "minLength": 3}}},
        }
    },
}
VALID = {"carduri": [{"intrebare": "Ce e lichiditatea?"}]}


@pytest.fixture
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(client, "_sleep", lambda s: calls.append(s))
    return calls


@pytest.fixture(params=["openai", "anthropic"])
def srv(request, tmp_path, monkeypatch, sleeps):
    s = FakeAIServer(request.param).start()
    cfg = tmp_path / "ai" / "ai.toml"
    cfg.parent.mkdir()
    write_config(cfg, s.url, request.param)
    monkeypatch.setenv("AI_CONFIG", str(cfg))
    monkeypatch.setenv("AI_STATE", str(tmp_path / "state"))
    monkeypatch.delenv("FALS_API_KEY", raising=False)
    client._schema_rejected.clear()
    client._last_call.clear()
    yield s
    s.stop()


def msgs(text="Salut"):
    return [{"role": "system", "content": "Ești de test."}, {"role": "user", "content": text}]


def test_text_simplu(srv):
    srv.reply("Bună ziua")
    r = ai.ruleaza("chat", msgs())
    assert r.text == "Bună ziua" and r.furnizor == "fals" and r.model == "model-test"
    assert (r.intrare, r.iesire, r.estimat) == (11, 7, False)
    req = srv.chat_requests[0]
    headers = {k.lower(): v for k, v in req["headers"].items()}
    if srv.kind == "anthropic":
        assert headers["x-api-key"] == "cheie-de-test"
        assert "anthropic-version" in headers
        assert req["json"]["system"] == "Ești de test."
        assert req["json"]["max_tokens"] == 8192
    else:
        assert headers["authorization"] == "Bearer cheie-de-test"


def test_json_cu_schema(srv):
    srv.reply_json(VALID)
    r = ai.ruleaza("carduri", msgs(), schema=SCHEMA)
    assert r.date == VALID
    body = srv.chat_requests[0]["json"]
    sent = json.dumps(body, ensure_ascii=False)
    assert "Răspunde DOAR cu JSON" in sent        # instrucțiunea e mereu în prompt
    if srv.kind == "openai":
        assert body["response_format"]["type"] == "json_schema"
    else:
        assert "response_format" not in body


def test_schema_respinsa_fallback(srv):
    if srv.kind == "openai":
        srv.error(400, "Invalid response_format: json_schema not supported")
    srv.reply_json(VALID).reply_json(VALID)
    assert ai.ruleaza("carduri", msgs(), schema=SCHEMA).date == VALID
    if srv.kind == "openai":
        assert "response_format" not in srv.chat_requests[1]["json"]
        # reținut până la repornire: al doilea apel nu mai încearcă schema
        ai.ruleaza("carduri", msgs(), schema=SCHEMA)
        assert "response_format" not in srv.chat_requests[2]["json"]


def test_json_in_bloc_de_cod(srv):
    srv.reply("Iată:\n```json\n" + json.dumps(VALID) + "\n```\nGata.")
    assert ai.ruleaza("carduri", msgs(), schema=SCHEMA).date == VALID


def test_json_invalid_apoi_valid(srv):
    srv.reply('{"carduri": []}').reply_json(VALID)
    r = ai.ruleaza("carduri", msgs(), schema=SCHEMA)
    assert r.date == VALID
    retry = srv.chat_requests[1]["json"]["messages"]
    assert "nu e valid" in retry[-1]["content"]
    assert r.intrare == 22


def test_json_invalid_de_doua_ori(srv):
    srv.reply("nu e json").reply("tot nu")
    with pytest.raises(ai.AIError, match="JSON valid"):
        ai.ruleaza("carduri", msgs(), schema=SCHEMA)


def test_429_cu_retry_after(srv, sleeps):
    srv.error(429, "rate", {"Retry-After": "2"}).reply("OK")
    seen = []
    assert ai.ruleaza("chat", msgs(), la_progres=seen.append).text == "OK"
    assert sleeps == [2.0]
    assert "Limită de rată la fals, reiau în 2 s" in seen[0]


def test_429_fara_retry_after(srv, sleeps):
    for _ in range(4):
        srv.error(429)
    srv.reply("OK")
    assert ai.ruleaza("chat", msgs()).text == "OK"
    assert sleeps == [5, 15, 45, 90]


def test_429_epuizat(srv, sleeps):
    for _ in range(5):
        srv.error(429)
    with pytest.raises(ai.AIError, match="Limita de rată"):
        ai.ruleaza("chat", msgs())


def test_5xx_reincercari(srv, sleeps):
    srv.error(503).error(500).reply("OK")
    assert ai.ruleaza("chat", msgs()).text == "OK"
    assert len(sleeps) == 2
    srv.error(500).error(500).error(500)
    with pytest.raises(ai.AIError, match="probleme"):
        ai.ruleaza("chat", msgs())


def test_401(srv):
    srv.error(401, "invalid api key")
    with pytest.raises(ai.AIError, match="respinsă .*FALS_API_KEY"):
        ai.ruleaza("chat", msgs())
    assert len(srv.chat_requests) == 1          # fără reîncercare


def test_model_inexistent(srv):
    srv.error(404, "model not found")
    with pytest.raises(ai.AIError, match="Modelul «model-test» nu există"):
        ai.ruleaza("chat", msgs())


def test_fara_usage(srv):
    srv.reply("Răspuns fără usage", usage=False)
    r = ai.ruleaza("chat", msgs("x" * 35))
    assert r.estimat and r.iesire == ai.estimeaza_tokeni("Răspuns fără usage")
    line = json.loads(next((client._usage_dir()).glob("*.jsonl")).read_text().splitlines()[0])
    assert line["estimat"] is True


def test_modele(srv):
    assert ai.listeaza_modele("fals") == ["model-mare", "model-test"]


def test_consum_scris(srv):
    client.set_application("test-app")
    ai.ruleaza("carduri", msgs())
    rows = ai.consum()
    assert rows[0]["aplicatie"] == "test-app" and rows[0]["sarcina"] == "carduri"
    assert set(rows[0]) == {"t", "aplicatie", "sarcina", "furnizor", "model", "intrare", "iesire",
                            "estimat", "cost_usd"}
    assert rows[0]["cost_usd"] == 0


def test_testeaza(srv):
    d = ai.testeaza()
    assert d.ok and d.furnizor == "fals"


# ---------- fără server ----------

@pytest.fixture
def cfgdir(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_CONFIG", str(tmp_path / "ai.toml"))
    monkeypatch.setenv("AI_STATE", str(tmp_path / "state"))
    return tmp_path


def test_config_lipsa_foloseste_gemini(cfgdir, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    cfg = aicfg.load()
    assert cfg.errors == []
    assert aicfg.resolve_ref(cfg, cfg.implicit) == ("gemini", "gemini-3.8-flash")
    with pytest.raises(ai.AIError, match="GEMINI_API_KEY=.*\\.env"):
        ai.ruleaza("chat", msgs())


def test_aliasuri(cfgdir):
    (cfgdir / "ai.toml").write_text(
        'implicit = "a"\n[aliasuri]\na = "b"\nb = "c"\nc = "ollama:qwen3:8b"\n'
        'x = "y"\ny = "x"\nlung = "a"\nnec = "nimic:model"\n', encoding="utf-8")
    cfg = aicfg.load()
    assert aicfg.resolve_ref(cfg, "a") == ("ollama", "qwen3:8b")     # ":" în numele modelului
    with pytest.raises(aicfg.ConfigError, match="Ciclu"):
        aicfg.resolve_ref(cfg, "x")
    with pytest.raises(aicfg.ConfigError, match="prea multe"):
        aicfg.resolve_ref(cfg, "lung")
    with pytest.raises(aicfg.ConfigError, match="nu e declarat"):
        aicfg.resolve_ref(cfg, "nec")
    joined = " ".join(cfg.errors)
    assert "Ciclu" in joined and "nimic" in joined       # erorile apar la încărcare


def test_prioritate_model_explicit(cfgdir):
    (cfgdir / "ai.toml").write_text(
        'implicit = "ollama:mic"\n[sarcini]\ncarduri = "ollama:mediu"\n', encoding="utf-8")
    assert client.resolve("carduri")[2] == "mediu"
    assert client.resolve("carduri", "ollama:mare")[2] == "mare"
    assert client.resolve("altceva")[2] == "mic"
    with pytest.raises(ai.AIError, match="Modele configurate"):
        ai.check_model_ref("necunoscut")


def test_buget(cfgdir):
    (cfgdir / "ai.toml").write_text(
        'implicit = "plata:m"\n[buget]\nlunar_usd = 1\n'
        '[furnizori.plata]\ntip = "openai"\nbase_url = "http://127.0.0.1:9"\ncheie = ""\n'
        'pret_intrare_1m = 2.0\npret_iesire_1m = 8.0\n', encoding="utf-8")
    assert ai.estimeaza_cost("chat", 1_000_000, 0) == 2.0
    assert ai.estimeaza_cost("chat", 0, 500_000) == 4.0
    d = client._usage_dir()
    d.mkdir(parents=True)
    from datetime import datetime
    (d / f"{datetime.now():%Y-%m}.jsonl").write_text(json.dumps({"cost_usd": 1.2}) + "\n")
    with pytest.raises(ai.AIError, match="Bugetul lunar de 1 USD a fost atins"):
        ai.ruleaza("chat", msgs())


def test_context_prea_mic(cfgdir):
    (cfgdir / "ai.toml").write_text(
        'implicit = "ollama:m"\n[furnizori.ollama]\ncontext_max = 10\n', encoding="utf-8")
    with pytest.raises(ai.AIError, match="prea lung"):
        ai.ruleaza("chat", msgs("x" * 500))
    assert ai.max_chunk_chars("notite", 12000) == 1000


def test_ollama_nu_ruleaza(cfgdir):
    (cfgdir / "ai.toml").write_text(
        'implicit = "ollama:m"\n[furnizori.ollama]\nbase_url = "http://127.0.0.1:11434/v1"\n', encoding="utf-8")
    import socket
    s = socket.socket()
    try:
        if s.connect_ex(("127.0.0.1", 11434)) == 0:
            pytest.skip("Ollama chiar rulează pe acest calculator")
    finally:
        s.close()
    with pytest.raises(ai.AIError, match="Ollama nu rulează"):
        ai.ruleaza("chat", msgs())


def test_limitare_ritm(cfgdir, monkeypatch):
    now = [100.0]
    slept = []
    monkeypatch.setattr(client, "_clock", lambda: now[0])

    def fake_sleep(s):
        slept.append(s)
        now[0] += s
    monkeypatch.setattr(client, "_sleep", fake_sleep)
    client._last_call.clear()
    p = aicfg.Provider(name="r", cereri_pe_minut=30)   # 2 s între apeluri
    client._wait_rate(p)
    now[0] += 0.5
    client._wait_rate(p)
    assert slept == [pytest.approx(1.5)]
    now[0] += 5
    client._wait_rate(p)
    assert len(slept) == 1


def test_cheie_din_mediu_are_prioritate(cfgdir, monkeypatch):
    (cfgdir / ".env").write_text("GEMINI_API_KEY=din-fisier\n")
    cfg = aicfg.load()
    assert aicfg.key_value(cfg.providers["gemini"], cfg) == "din-fisier"
    monkeypatch.setenv("GEMINI_API_KEY", "din-mediu")
    assert aicfg.key_value(cfg.providers["gemini"], cfg) == "din-mediu"


def test_validator_schema():
    assert schema.errors(VALID, SCHEMA) == []
    errs = schema.errors({"carduri": [{"intrebare": "x"}, {}]}, SCHEMA)
    assert any("minLength" in e or "mai puțin" in e for e in errs)
    assert any("intrebare" in e for e in errs)
    assert schema.errors(3, {"type": "integer"}) == []
    assert schema.errors(True, {"type": "integer"})
    assert schema.errors("c", {"enum": ["a", "b"]})
    assert schema.errors([1, 2, 3], {"type": "array", "maxItems": 2})
    assert schema.errors(None, {"type": ["string", "null"]}) == []


def test_extragere_json():
    assert schema.extract_json('text {"a": [1, 2]} după') == {"a": [1, 2]}
    assert schema.extract_json("```\n[1]\n```") == [1]
    with pytest.raises(schema.SchemaError):
        schema.extract_json("nimic aici")
