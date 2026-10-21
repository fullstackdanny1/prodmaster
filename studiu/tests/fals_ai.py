"""Servere AI false, locale, pentru teste: format OpenAI și format Anthropic.

Răspunsurile se pun într-o coadă; cererile primite sunt reținute pentru verificări.
Fișier identic în Studiu și Unelte.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeAIServer:
    def __init__(self, kind: str = "openai"):
        self.kind = kind
        self.queue: list[tuple[int, object, dict]] = []
        self.requests: list[dict] = []
        self.models = ["model-test", "model-mare"]
        self.default_text = "OK"
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, body, headers=None):
                raw = body if isinstance(body, (bytes, str)) else json.dumps(body)
                raw = raw.encode() if isinstance(raw, str) else raw
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                server.requests.append({"method": "GET", "path": self.path, "headers": dict(self.headers)})
                if self.path.rstrip("/").endswith("/models"):
                    self._send(200, {"data": [{"id": m} for m in server.models]})
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                server.requests.append({"method": "POST", "path": self.path,
                                        "headers": dict(self.headers), "json": body})
                if server.queue:
                    status, payload, headers = server.queue.pop(0)
                else:
                    status, payload, headers = 200, server.text_body(server.default_text), {}
                self._send(status, payload, headers)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, args=(0.05,), daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    # ---------- răspunsuri ----------

    def text_body(self, text: str, usage: bool = True) -> dict:
        if self.kind == "anthropic":
            body = {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}
            if usage:
                body["usage"] = {"input_tokens": 11, "output_tokens": 7}
            return body
        body = {"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}]}
        if usage:
            body["usage"] = {"prompt_tokens": 11, "completion_tokens": 7}
        return body

    def reply(self, text: str, usage: bool = True):
        self.queue.append((200, self.text_body(text, usage), {}))
        return self

    def reply_json(self, value, usage: bool = True):
        return self.reply(json.dumps(value, ensure_ascii=False), usage)

    def error(self, status: int, message: str = "eroare", headers: dict | None = None):
        self.queue.append((status, {"error": {"message": message}}, headers or {}))
        return self

    @property
    def chat_requests(self) -> list[dict]:
        return [r for r in self.requests if r["method"] == "POST"]


def write_config(path, url: str, kind: str = "openai", **provider) -> None:
    """Scrie un ai.toml de test cu furnizorul «fals» (și cheia lui în .env)."""
    extra = "".join(f"{k} = {json.dumps(v)}\n" for k, v in provider.items())
    path.write_text(
        'implicit = "fals:model-test"\n'
        "[aliasuri]\n"
        'rapid = "fals:model-test"\n'
        'bun = "rapid"\n'
        "[sarcini]\n"
        'carduri = "bun"\n'
        "[furnizori.fals]\n"
        f'tip = "{kind}"\n'
        f'base_url = "{url}"\n'
        'cheie = "FALS_API_KEY"\n'
        + extra,
        encoding="utf-8",
    )
    (path.parent / ".env").write_text("FALS_API_KEY=cheie-de-test\n", encoding="utf-8")
