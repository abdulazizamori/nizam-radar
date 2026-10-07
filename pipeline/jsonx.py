"""Helpers for reading model replies and checking their text."""

from __future__ import annotations

import json
import re

_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")


def extract_json(text: str) -> dict | None:
    """Return the first JSON object in a reply (ignoring <think> blocks and
    code fences), or None if there isn't a readable one."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def has_cjk(text: str) -> bool:
    """Nemotron sometimes slips Chinese words into Arabic text (seen on Super)."""
    return bool(_CJK.search(text or ""))
