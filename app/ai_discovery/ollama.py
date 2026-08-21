from __future__ import annotations

import httpx

from ..provider_contracts import CAPABILITY_AI_DISCOVERY

DEFAULT_DISCOVERY_PROMPT_TEMPLATE = (
    "List up to 10 NSE-listed equity symbols from the {universe_version} universe that show "
    "a genuine short-term positive trading opportunity. Respond with exactly one line per "
    "symbol, formatted as 'SYMBOL: one-sentence rationale', and nothing else."
)


class OllamaDiscoveryError(RuntimeError):
    """Raised when the local Ollama server cannot provide a usable
    discovery response."""


class OllamaDiscoveryClient:
    """The one real, fully-functional AI/discovery provider in this
    codebase (EPIC-M1.91) -- a free, local, no-authentication model
    server. Real and callable in production against a running Ollama
    instance; unit tests never hit the network, they monkeypatch the
    underlying HTTP call with local fixtures. Response parsing is
    deliberately simple and explicit (`SYMBOL: rationale` per line) --
    an unparseable line is skipped rather than guessed at, honest about
    what a free-text model response can reliably yield without a
    structured-output contract from the model itself.
    """

    source = "ollama"
    capability = CAPABILITY_AI_DISCOVERY
    version = "1"

    def __init__(self, model: str, base_url: str = "http://localhost:11434", timeout: float = 60.0) -> None:
        if not model:
            raise ValueError("model is required")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def discover_candidates(self, universe_version: str) -> tuple[dict, ...]:
        if not universe_version:
            raise ValueError("universe_version is required")
        prompt = DEFAULT_DISCOVERY_PROMPT_TEMPLATE.format(universe_version=universe_version)

        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise OllamaDiscoveryError(f"Ollama generate request failed for model {self.model}: {exc}") from exc

        raw_text = payload.get("response") if isinstance(payload, dict) else None
        if not raw_text:
            return ()

        return self._parse(raw_text)

    @staticmethod
    def _parse(raw_text: str) -> tuple[dict, ...]:
        candidates = []
        seen_symbols = set()
        for line in raw_text.splitlines():
            line = line.strip().lstrip("-*").strip()
            if ":" not in line:
                continue
            symbol, _, rationale = line.partition(":")
            symbol = symbol.strip().upper()
            rationale = rationale.strip()
            if not symbol or not rationale or not symbol.replace("&", "").isalnum():
                continue
            if symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)
            candidates.append({"symbol": symbol, "rationale": rationale})
        return tuple(candidates)
