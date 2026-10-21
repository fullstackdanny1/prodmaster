"""Adaptorul pentru API-ul Messages al Anthropic. JSON-ul se cere doar prin prompt."""
from __future__ import annotations

from . import CerereChat, ProviderHTTPError, ProviderSettings, RaspunsChat, http_json

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAdaptor:
    accepta_schema = False

    def __init__(self, settings: ProviderSettings):
        self.s = settings

    def _headers(self) -> dict:
        h = {"anthropic-version": ANTHROPIC_VERSION}
        if self.s.key:
            h["x-api-key"] = self.s.key
        return h

    def chat(self, cerere: CerereChat) -> RaspunsChat:
        system = "\n\n".join(m["content"] for m in cerere.mesaje if m["role"] == "system")
        messages = [{"role": m["role"], "content": m["content"]} for m in cerere.mesaje if m["role"] != "system"]
        body = {
            "model": cerere.model,
            "max_tokens": cerere.max_iesire,
            "messages": messages,
            "temperature": cerere.temperatura,
        }
        if system:
            body["system"] = system
        data = http_json("POST", f"{self.s.base_url}/messages", self._headers(), body, self.s.timeout_s)
        try:
            blocks = data["content"]
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        except (KeyError, TypeError, AttributeError) as e:
            raise ProviderHTTPError(502, f"Răspuns neașteptat: {str(data)[:300]}") from e
        usage = data.get("usage") or {}
        tin, tout = usage.get("input_tokens"), usage.get("output_tokens")
        return RaspunsChat(
            text=text,
            tokeni_intrare=int(tin or 0),
            tokeni_iesire=int(tout or 0),
            estimat=tin is None or tout is None,
            motiv_oprire=str(data.get("stop_reason") or ""),
        )

    def modele(self) -> list[str]:
        data = http_json("GET", f"{self.s.base_url}/models", self._headers(), None, min(self.s.timeout_s, 60))
        items = data.get("data", []) if isinstance(data, dict) else []
        return sorted(str(m.get("id")) for m in items if isinstance(m, dict) and m.get("id"))
