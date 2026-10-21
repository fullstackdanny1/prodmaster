"""Adaptoarele furnizorilor AI. Un furnizor nou cu API diferit = un fișier nou aici
plus o intrare în ADAPTOARE. Doar urllib din biblioteca standard, fără SDK-uri."""
from __future__ import annotations

import email.utils
import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class CerereChat:
    model: str
    mesaje: list[dict]                # [{"role": "system"|"user"|"assistant", "content": "..."}]
    temperatura: float = 0.3
    max_iesire: int = 8192
    schema: dict | None = None        # trimisă ca response_format doar dacă adaptorul o acceptă


@dataclass
class RaspunsChat:
    text: str
    tokeni_intrare: int = 0
    tokeni_iesire: int = 0
    estimat: bool = False             # True dacă furnizorul nu a raportat tokenii
    motiv_oprire: str = ""


class ProviderHTTPError(Exception):
    def __init__(self, status: int, body: str, retry_after: float | None = None):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body
        self.retry_after = retry_after


class ProviderNetworkError(Exception):
    pass


class Adaptor(Protocol):
    accepta_schema: bool

    def chat(self, cerere: CerereChat) -> RaspunsChat: ...
    def modele(self) -> list[str]: ...


@dataclass
class ProviderSettings:
    """Ce primește un adaptor: adresa, cheia (valoarea) și timeout-ul."""
    name: str
    base_url: str
    key: str = ""
    timeout_s: float = 180
    extra: dict = field(default_factory=dict)


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(value)
        return max(0.0, dt.timestamp() - time.time())
    except (TypeError, ValueError):
        return None


def http_json(method: str, url: str, headers: dict, body: dict | None, timeout: float):
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Accept": "application/json", **headers}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    try:
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    except ValueError as e:
        raise ProviderNetworkError(f"adresă invalidă «{url}» (verifică base_url)") from e
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        raise ProviderHTTPError(e.code, text, _retry_after(e.headers.get("Retry-After"))) from e
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise ProviderNetworkError(str(reason)) from e
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ProviderHTTPError(502, f"Răspuns care nu e JSON: {raw[:200]!r}") from e


from . import anthropic, openai  # noqa: E402

ADAPTOARE = {
    "openai": openai.OpenAIAdaptor,
    "anthropic": anthropic.AnthropicAdaptor,
}
