"""Several LLM providers behind one failover chain.

Google AI Studio (Gemini), Groq, OpenRouter, NVIDIA and Hugging Face all serve
an OpenAI-compatible `/chat/completions` endpoint, so one code path reaches
all of them. Gemini is opt-in (see DEFAULT_ORDER); the others serve open-weight models
(gpt-oss-120b on Groq and Hugging Face, Nemotron 3 Super on OpenRouter's free
tier, gpt-oss-20b on NVIDIA). Free tiers are small (Groq's is 200k tokens a day per model),
so one provider alone runs out; with a chain, the app keeps answering.

A provider is used only when its API key is set. `LLM_PROVIDERS` sets the
order (default: groq, openrouter, nvidia, huggingface), `<NAME>_MODEL` and
`<NAME>_BASE_URL` override the defaults, and `LLM_FALLBACK_MODEL` adds a
second Groq model at the end of the chain (each Groq model has its own
quota). The older single-provider settings (`LLM_API_KEY`, `LLM_BASE_URL`,
`LLM_MODEL`) still configure the first slot, so existing .env files keep
working.

A provider that fails is put on a short cooldown, so the next questions go
straight to one that works instead of waiting on it again:
rate limits for as long as the provider asks (capped), a bad key, used-up
credits or an unknown model for 15 minutes, timeouts and server errors for 30 seconds.
"""

import os
import threading
import time
from dataclasses import dataclass, field, replace
from urllib.parse import urlsplit

# Google AI Studio is supported but opt-in (add "google" to LLM_PROVIDERS):
# in testing on 2026-09-29 its free tier was overloaded (503) or rate
# limited on most calls, so it could not be verified against the
# prompt-injection tests the other providers pass.
DEFAULT_ORDER = "groq,openrouter,nvidia,huggingface"

KNOWN = {
    # Google AI Studio (Gemini API) through its OpenAI-compatible endpoint.
    "google": {
        "label": "Google AI Studio",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-3.6-flash",
        "keys": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    },
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-120b",
        "keys": ("GROQ_API_KEY", "LLM_API_KEY"),
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        # gpt-oss-120b is paid-only on OpenRouter now; this free 120B model
        # answered as well in testing (2026-09-29).
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
        "keys": ("OPENROUTER_API_KEY",),
        # Optional attribution headers OpenRouter asks apps to send.
        "headers": (
            ("HTTP-Referer", "https://ai-doc-assistant.duckdns.org"),
            ("X-Title", "AI Document Assistant"),
        ),
    },
    "nvidia": {
        "label": "NVIDIA",
        "base_url": "https://integrate.api.nvidia.com/v1",
        # gpt-oss-120b reached end of life on NVIDIA's API on 2026-09-03.
        "model": "openai/gpt-oss-20b",
        "keys": ("NVIDIA_API_KEY",),
    },
    "huggingface": {
        "label": "Hugging Face",
        "base_url": "https://router.huggingface.co/v1",
        "model": "openai/gpt-oss-120b",
        "keys": ("HF_TOKEN", "HUGGINGFACE_API_KEY"),
    },
}

RATE_LIMIT_COOLDOWN_DEFAULT = 60.0
RATE_LIMIT_COOLDOWN_MAX = 900.0
BROKEN_COOLDOWN = 900.0  # bad key, no credits, unknown or retired model
FLAKY_COOLDOWN = 30.0  # timeout, connection error, 5xx


@dataclass(frozen=True)
class Route:
    """One provider + model the app can send a chat completion to."""

    provider: str
    label: str
    base_url: str
    model: str
    api_key: str = field(repr=False)
    headers: tuple = ()

    @property
    def id(self) -> str:
        return f"{self.provider}:{self.model}"

    def describe(self) -> dict:
        """What the UI shows about who answered (never the key)."""
        return {"provider": self.label, "model": self.model}


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def routes() -> list[Route]:
    """The configured chain, in order. Read from the environment on every
    call, so tests (and a restarted container) see changes immediately."""
    order = [p.strip().lower() for p in (_env("LLM_PROVIDERS") or DEFAULT_ORDER).split(",") if p.strip()]
    chain = []
    for name in dict.fromkeys(order):
        spec = KNOWN.get(name)
        if spec is None:
            continue
        key = next((_env(k) for k in spec["keys"] if _env(k)), "")
        if not key:
            continue
        prefix = name.upper()
        legacy = name == "groq"
        base_url = (_env(f"{prefix}_BASE_URL") or (legacy and _env("LLM_BASE_URL")) or spec["base_url"]).rstrip("/")
        model = _env(f"{prefix}_MODEL") or (legacy and _env("LLM_MODEL")) or spec["model"]
        label = spec["label"]
        if legacy and "groq.com" not in base_url:
            # LLM_BASE_URL pointed at some other OpenAI-compatible server.
            label = urlsplit(base_url).hostname or "Custom"
        chain.append(Route(name, label, base_url, model, key, spec.get("headers", ())))

    fallback = _env("LLM_FALLBACK_MODEL")
    first = next((r for r in chain if r.provider == "groq"), None)
    if fallback and first is not None and fallback != first.model:
        chain.append(replace(first, model=fallback))
    return chain


# --- Cooldowns -----------------------------------------------------------------

_lock = threading.Lock()
_cooldown_until: dict[str, float] = {}
_last_error: dict[str, str] = {}


def reset() -> None:
    with _lock:
        _cooldown_until.clear()
        _last_error.clear()


def cooling(route: Route) -> bool:
    with _lock:
        return _cooldown_until.get(route.id, 0.0) > time.monotonic()


def candidates() -> list[Route]:
    """Routes to try, in order: those not cooling down first. When every
    route is cooling down they are all tried anyway -- a provider may have
    recovered early, and trying beats refusing outright."""
    chain = routes()
    ready = [r for r in chain if not cooling(r)]
    return ready + [r for r in chain if r not in ready]


def cool_down(route: Route, seconds: float, reason: str) -> None:
    with _lock:
        _cooldown_until[route.id] = time.monotonic() + seconds
        _last_error[route.id] = reason
    print(f"LLM provider {route.label} ({route.model}) unavailable: {reason}; skipping it for {seconds:.0f}s")


def mark_ok(route: Route) -> None:
    with _lock:
        _cooldown_until.pop(route.id, None)
        _last_error.pop(route.id, None)


def status() -> list[dict]:
    """Per configured route: who it is and whether it's usable right now.
    No keys, URLs or error details -- this is shown on the public page."""
    now = time.monotonic()
    out = []
    for route in routes():
        with _lock:
            until = _cooldown_until.get(route.id, 0.0)
        out.append({**route.describe(), "state": "cooling" if until > now else "ready"})
    return out
