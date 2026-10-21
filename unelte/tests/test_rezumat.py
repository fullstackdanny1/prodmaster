import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from conftest import set_config

from unelte import rezumat

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>
<item><title>Audit crypto nou</title><link>https://ex.ro/1</link><guid>g1</guid>
<description>&lt;p&gt;Un audit &lt;b&gt;important&lt;/b&gt; al unui protocol.&lt;/p&gt;</description>
<pubDate>Mon, 19 Oct 2026 08:00:00 +0000</pubDate></item>
<item><title>Reclamă</title><link>https://ex.ro/2</link><guid>g2</guid><description>Cumpără</description>
<pubDate>Tue, 20 Oct 2026 08:00:00 +0000</pubDate></item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>A</title>
<entry><id>tag:a,1</id><title>Joburi pentru juniori</title><link href="https://a.ro/j"/>
<updated>2026-10-20T10:00:00Z</updated><summary>Piața muncii IT pentru juniori.</summary></entry></feed>"""


class Feeds:
    def __init__(self):
        self.hits = []
        self.feeds = {"/rss": RSS, "/atom": ATOM}
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                srv.hits.append((self.path, self.headers.get("If-None-Match"), self.headers.get("User-Agent")))
                if self.path not in srv.feeds:
                    self.send_response(404)
                    self.end_headers()
                    return
                etag = f'"{hash(srv.feeds[self.path])}"'
                if self.headers.get("If-None-Match") == etag:
                    self.send_response(304)
                    self.end_headers()
                    return
                body = srv.feeds[self.path].encode()
                self.send_response(200)
                self.send_header("ETag", etag)
                self.send_header("Content-Type", "application/xml")
                self.end_headers()
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.httpd.serve_forever, args=(0.05,), daemon=True).start()
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"


def setup(env, tmp_path, feeds):
    out = tmp_path / "Rezumate"
    set_config(env, f"""
[rezumat]
iesire = "{out}"
interese = "audit crypto, carieră"
max_pe_subiect = 1
[[rezumat.subiect]]
nume = "Securitate crypto"
surse = ["{feeds.url}/rss", "{feeds.url}/lipsa"]
[[rezumat.subiect]]
nume = "Carieră"
surse = ["{feeds.url}/atom"]
""")
    return out


def test_rss_si_atom():
    items = rezumat.parse_feed(RSS.encode(), "ex.ro")
    assert [i.id for i in items] == ["g1", "g2"] and items[0].text == "Un audit important al unui protocol."
    atom = rezumat.parse_feed(ATOM.encode(), "a.ro")
    assert atom[0].link == "https://a.ro/j" and atom[0].published.year == 2026


def test_fara_ai_sursa_defecta_si_fara_duplicate(env, tmp_path, monkeypatch):
    feeds = Feeds()
    out = setup(env, tmp_path, feeds)
    monkeypatch.setattr(rezumat.sistem, "notifica", lambda *a, **k: None)
    d1 = rezumat.run(rezumat.config.load(), no_ai=True, today=date(2026, 10, 21))
    text = d1.read_text()
    assert text.startswith("---\ntip: rezumat\n")
    assert "## Securitate crypto" in text and "[Reclamă](https://ex.ro/2)" in text
    assert text.index("Reclamă") < text.index("Audit crypto")              # cele mai noi primele
    assert "Surse care nu au răspuns" in text and "/lipsa" in text           # sursa defectă nu oprește restul
    assert "Unelte-rezumat" in feeds.hits[0][2]
    # a doua zi: cerere condiționată (304), fără duplicate
    d2 = rezumat.run(rezumat.config.load(), no_ai=True, today=date(2026, 10, 22))
    assert any(h[1] for h in feeds.hits if h[0] == "/rss")
    assert "Niciun articol nou" in d2.read_text()
    # în aceeași zi sursele nu se mai descarcă
    n = len(feeds.hits)
    rezumat.run(rezumat.config.load(), no_ai=True, today=date(2026, 10, 22))
    assert len(feeds.hits) == n
    assert sorted(p.name for p in out.iterdir()) == ["2026-10-21.md", "2026-10-22 (2).md", "2026-10-22.md"]
    state = json.loads(rezumat.state_path().read_text())
    assert set(state["vazute"]) == {"g1", "g2", "tag:a,1"}


def test_cu_ai(env, tmp_path, fake_ai, monkeypatch):
    feeds = Feeds()
    setup(env, tmp_path, feeds)
    monkeypatch.setattr(rezumat.sistem, "notifica", lambda *a, **k: None)
    # elementele sunt numerotate de la cel mai nou: [0] Reclamă, [1] Audit
    fake_ai.reply_json({"elemente": [{"id": 0, "relevanta": 0.1, "rezumat": "Reclamă fără interes."},
                                     {"id": 1, "relevanta": 0.9, "rezumat": "Un audit important."}]})
    fake_ai.reply_json({"elemente": [{"id": 0, "relevanta": 0.8, "rezumat": "Locuri de muncă pentru juniori."}]})
    d = rezumat.run(rezumat.config.load(), today=date(2026, 10, 21))
    text = d.read_text()
    assert "sursa: ai" in text and "Un audit important." in text and "Reclamă" not in text   # max_pe_subiect = 1
    prompt = fake_ai.chat_requests[0]["json"]["messages"]
    assert "audit crypto" in prompt[0]["content"] and "[1] Audit crypto nou" in prompt[-1]["content"]


def test_vazute_curatate_dupa_60_zile(env):
    st = {"surse": {}, "vazute": {"vechi": "2026-07-01", "nou": "2026-10-01"}}
    rezumat.save_state(st, date(2026, 10, 21))
    assert set(rezumat.load_state()["vazute"]) == {"nou"}
