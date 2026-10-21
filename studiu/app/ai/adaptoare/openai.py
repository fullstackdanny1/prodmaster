"""Adaptorul pentru API-urile compatibile OpenAI: Gemini, OpenAI, Groq, OpenRouter, Mistral,
DeepSeek, Ollama, LM Studio, llama.cpp server, vLLM."""
from __future__ import annotations

from . import CerereChat, ProviderHTTPError, ProviderSettings, RaspunsChat, http_json


class OpenAIAdaptor:
    accepta_schema = True

    def __init__(self, settings: ProviderSettings):
        self.s = settings

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.s.key}"} if self.s.key else {}

    def chat(self, cerere: CerereChat) -> RaspunsChat:
        body = {
            "model": cerere.model,
            "messages": [{"role": m["role"], "content": m["content"]} for m in cerere.mesaje],
            "temperature": cerere.temperatura,
        }
        # max_tokens nu se trimite: unele modele îl refuză, iar limita implicită e suficientă.
        if cerere.schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "raspuns", "schema": cerere.schema, "strict": False},
            }
        data = http_json("POST", f"{self.s.base_url}/chat/completions", self._headers(), body, self.s.timeout_s)
        try:
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
        except (KeyError, IndexError, TypeError, AttributeError) as e:
            raise ProviderHTTPError(502, f"Răspuns neașteptat: {str(data)[:300]}") from e
        usage = data.get("usage") or {}
        tin, tout = usage.get("prompt_tokens"), usage.get("completion_tokens")
        return RaspunsChat(
            text=text,
            tokeni_intrare=int(tin or 0),
            tokeni_iesire=int(tout or 0),
            estimat=tin is None or tout is None,
            motiv_oprire=str(choice.get("finish_reason") or ""),
        )

    def modele(self) -> list[str]:
        data = http_json("GET", f"{self.s.base_url}/models", self._headers(), None, min(self.s.timeout_s, 60))
        items = data.get("data", []) if isinstance(data, dict) else []
        names = [str(m.get("id", "")) for m in items if isinstance(m, dict)]
        return sorted(n.removeprefix("models/") for n in names if n)
