"""One place for every model call: client, cache and call log.

- Cache: when USE_LLM_CACHE=true, a response is saved under .cache/llm/ keyed
  by sha256 of (model, messages, max_tokens). Re-running the same prompt costs
  nothing. This protects the $40 dev budget (spec section 11).
- Log: every call (cached or not) is appended to logs/llm_calls.jsonl with
  model, tokens, cost and latency. This becomes the "routing vs Ultra-only"
  chart. It moves to a database table once the database exists.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache" / "llm"
LOG_PATH = ROOT / "logs" / "llm_calls.jsonl"

# USD per 1M tokens (input, output), from the Token Factory catalog on 2026-10-07.
PRICES = {
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B": (0.06, 0.24),
    "nvidia/nemotron-3-super-120b-a12b": (0.30, 0.90),
    "nvidia/Nemotron-3-Ultra-550b-a55b": (1.00, 3.00),
}


@dataclass
class LLMResponse:
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    cached: bool
    finish_reason: str | None = None


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    p_in, p_out = PRICES.get(model, (0.0, 0.0))
    return round((tokens_in * p_in + tokens_out * p_out) / 1_000_000, 6)


def _client():
    from openai import OpenAI

    return OpenAI(
        base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"),
        api_key=os.environ["NEBIUS_API_KEY"],
    )


def _cache_key(model: str, messages: list[dict], max_tokens: int) -> str:
    raw = json.dumps({"model": model, "messages": messages, "max_tokens": max_tokens},
                     ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _use_cache() -> bool:
    return os.environ.get("USE_LLM_CACHE", "true").lower() == "true"


def _log(step: str, resp: LLMResponse) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "step": step,
        "model": resp.model,
        "tokens_in": resp.tokens_in,
        "tokens_out": resp.tokens_out,
        "cost_usd": resp.cost_usd,
        "latency_ms": resp.latency_ms,
        "cached": resp.cached,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def chat(step: str, model: str, messages: list[dict], max_tokens: int = 2000,
         client=None) -> LLMResponse:
    """Call a chat model, using the cache when allowed, and log the call.

    max_tokens is generous by default: Nemotron models may think first, and
    thinking counts against max_tokens (see scripts/test_models.py).
    """
    key = _cache_key(model, messages, max_tokens)
    cache_file = CACHE_DIR / f"{key}.json"

    if _use_cache() and cache_file.exists():
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        resp = LLMResponse(**{**data, "cached": True, "cost_usd": 0.0, "latency_ms": 0})
        _log(step, resp)
        return resp

    client = client or _client()
    start = time.time()
    r = client.chat.completions.create(model=model, messages=messages, max_tokens=max_tokens,
                                       temperature=0)
    latency = int((time.time() - start) * 1000)
    tin = r.usage.prompt_tokens if r.usage else 0
    tout = r.usage.completion_tokens if r.usage else 0
    resp = LLMResponse(
        text=(r.choices[0].message.content or "").strip(),
        model=model,
        tokens_in=tin,
        tokens_out=tout,
        cost_usd=cost_usd(model, tin, tout),
        latency_ms=latency,
        cached=False,
        finish_reason=r.choices[0].finish_reason,
    )
    if _use_cache() and resp.text:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(resp.__dict__, ensure_ascii=False), encoding="utf-8")
    _log(step, resp)
    return resp
