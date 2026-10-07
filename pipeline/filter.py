"""Step 1 of the pipeline: Nemotron Nano relevance filter (spec section 11).

Input: profile + regulation title + first 2,000 characters of full_text.
Output: FilterResult {relevant, reason}. If relevant is false the regulation
stops here; otherwise Ultra reasons over it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from contracts.models import BusinessProfile, FilterResult, RegulationRecord
from pipeline.jsonx import extract_json
from pipeline.llm import LLMResponse, chat

PROMPT_VERSION = "filter_v1"
PROMPT = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")
N_CHARS = 2000

# Only the profile fields that help decide relevance (no name or email).
PROFILE_FIELDS = [
    "sector", "sub_activity", "city", "region", "employees_saudi", "employees_non_saudi",
    "has_physical_premises", "serves_food_onsite", "sells_online", "uses_delivery_apps",
    "revenue_band", "vat_registered",
]


def build_prompt(profile: BusinessProfile, reg: RegulationRecord) -> str:
    facts = {k: getattr(profile, k) for k in PROFILE_FIELDS}
    title = reg.title_original if not reg.title_en else f"{reg.title_original} / {reg.title_en}"
    return PROMPT.format(
        profile=json.dumps(facts, ensure_ascii=False),
        title=title,
        n_chars=N_CHARS,
        text=reg.full_text[:N_CHARS],
    )


def parse(text: str) -> FilterResult | None:
    """Pull the JSON object out of the reply. Returns None if it can't."""
    data = extract_json(text)
    if data is None:
        return None
    relevant = data.get("relevant")
    if isinstance(relevant, str):
        relevant = {"true": True, "false": False}.get(relevant.strip().lower())
    if not isinstance(relevant, bool):
        return None
    reason = str(data.get("reason") or "").strip() or "No reason given."
    return FilterResult(relevant=relevant, reason=reason[:300])


def filter_regulation(profile: BusinessProfile, reg: RegulationRecord,
                      client=None) -> tuple[FilterResult, list[LLMResponse]]:
    """Run the filter. Returns the result and the model calls it made.

    If Nano's answer can't be read after one retry, the regulation is kept
    (relevant=True): Ultra checks it anyway, so failing open is the safe side.
    """
    model = os.environ.get("MODEL_NANO", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B")
    messages = [{"role": "user", "content": build_prompt(profile, reg)}]
    calls = []
    for attempt in range(2):
        if attempt:
            messages = messages + [
                {"role": "assistant", "content": calls[-1].text},
                {"role": "user", "content": 'Reply with JSON only: {"relevant": true or false, "reason": "..."}'},
            ]
        resp = chat("filter", model, messages, max_tokens=1000, client=client)
        calls.append(resp)
        result = parse(resp.text)
        if result:
            return result, calls
    return FilterResult(relevant=True, reason="Filter answer unreadable; kept for review."), calls
