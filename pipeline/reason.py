"""Step 2 of the pipeline: Nemotron Ultra applicability reasoning.

Input: profile + the full regulation text. Output: applicability,
confidence, reasoning and obligations, each with a citation.

Trust rule (spec section 7), enforced here in code: every quote must appear
in the regulation's full_text. An obligation whose quote can't be found is
dropped, and the result becomes needs_review.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from contracts.models import (
    Applicability, Bilingual, BusinessProfile, Citation, Confidence, DeadlineType, Obligation,
    RegulationRecord,
)
from pipeline.filter import PROFILE_FIELDS
from pipeline.jsonx import extract_json, has_cjk
from pipeline.llm import LLMResponse, chat

PROMPT_VERSION = "reason_v1"
PROMPT = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")
QUOTE_MAX = 300
MAX_OBLIGATIONS = 5


@dataclass
class ReasonResult:
    applicability: str
    confidence: str
    reasoning_summary: Bilingual
    obligations: list[Obligation] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)   # why it was downgraded, for logs/eval
    calls: list[LLMResponse] = field(default_factory=list)


def build_prompt(profile: BusinessProfile, reg: RegulationRecord) -> str:
    facts = {k: getattr(profile, k) for k in PROFILE_FIELDS}
    meta = {
        "title": reg.title_en or reg.title_original,
        "issuing_authority": reg.issuing_authority,
        "doc_type": reg.doc_type,
        "status": reg.status,
        "published_date": str(reg.published_date) if reg.published_date else None,
        "effective_date": str(reg.effective_date) if reg.effective_date else None,
        "language": reg.language_original,
    }
    return PROMPT.format(profile=json.dumps(facts, ensure_ascii=False),
                         meta=json.dumps(meta, ensure_ascii=False), text=reg.full_text)


# --- citation check ----------------------------------------------------------

def _strip_quotes(q: str) -> str:
    return q.strip().strip('"“”«»\'').strip().rstrip("…").strip()


def find_quote(quote: str, full_text: str) -> str | None:
    """Return the exact span of full_text that the quote points to, or None.

    Exact match first. Otherwise allow differences in whitespace only (models
    often join lines), and return the original text so the stored quote is
    always verbatim.
    """
    q = _strip_quotes(quote or "")
    if len(q) < 15:          # too short to prove anything
        return None
    if q in full_text:
        return q
    tokens = q.split()
    pattern = r"\s+".join(re.escape(t) for t in tokens)
    m = re.search(pattern, full_text)
    return m.group(0) if m else None


def _trim(quote: str) -> str:
    """Keep a verified quote under 300 chars by cutting at a word boundary
    (still a substring of full_text)."""
    if len(quote) <= QUOTE_MAX:
        return quote
    cut = quote[:QUOTE_MAX]
    return cut[:cut.rfind(" ")] if " " in cut else cut


def _parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _enum(value, enum, default):
    values = {e.value for e in enum}
    return value if value in values else default


def check(data: dict, reg: RegulationRecord) -> ReasonResult:
    """Turn Ultra's JSON into checked contract objects."""
    problems = []
    applicability = _enum(data.get("applicability"), Applicability, Applicability.needs_review.value)
    if data.get("applicability") != applicability:
        problems.append(f"unknown applicability {data.get('applicability')!r}")
    confidence = _enum(data.get("confidence"), Confidence, Confidence.low.value)

    rs = data.get("reasoning_summary") or {}
    reasoning = Bilingual(ar=str(rs.get("ar") or "").strip(), en=str(rs.get("en") or "").strip())
    if not reasoning.en:
        problems.append("missing reasoning")
    if has_cjk(reasoning.ar) or has_cjk(reasoning.en):
        problems.append("non-Arabic script in reasoning")

    obligations = []
    raw = data.get("obligations") or []
    if applicability in ("applies", "likely_applies"):
        for i, ob in enumerate(raw[:MAX_OBLIGATIONS], 1):
            if not isinstance(ob, dict):
                continue
            quote = find_quote(str(ob.get("quote") or ""), reg.full_text)
            if quote is None:
                problems.append(f"obligation {i}: quote not found in full_text")
                continue
            desc = ob.get("description") or {}
            deadline = _parse_date(ob.get("deadline"))
            dtype = _enum(ob.get("deadline_type"), DeadlineType, DeadlineType.none.value)
            if deadline and dtype == "none":
                dtype = "fixed_date"
            if not deadline and dtype == "fixed_date":
                dtype = "none"
            penalty = ob.get("penalty") or None
            obligations.append(Obligation(
                obligation_id=f"obl_{len(obligations) + 1}",
                description=Bilingual(ar=str(desc.get("ar") or "").strip(),
                                      en=str(desc.get("en") or "").strip()),
                deadline=deadline,
                deadline_type=dtype,
                deadline_text=(str(ob["deadline_text"]).strip() or None) if ob.get("deadline_text") else None,
                penalty=str(penalty).strip() if penalty else None,
                citation=Citation(article_ref=ob.get("article_ref") or None,
                                  quote=_trim(quote), source_url=reg.source_url),
            ))
        if not obligations:
            problems.append("applies but no verifiable obligation")

    if problems:
        applicability, confidence = "needs_review", "low"
    return ReasonResult(applicability, confidence, reasoning, obligations, problems)


def reason(profile: BusinessProfile, reg: RegulationRecord, client=None) -> ReasonResult:
    model = os.environ.get("MODEL_ULTRA", "nvidia/Nemotron-3-Ultra-550b-a55b")
    messages = [{"role": "user", "content": build_prompt(profile, reg)}]
    calls = []
    for attempt in range(2):
        if attempt:
            messages = messages + [
                {"role": "assistant", "content": calls[-1].text},
                {"role": "user", "content": "That was not valid JSON. Reply with the JSON object only."},
            ]
        resp = chat("reason", model, messages, max_tokens=8000, client=client)
        calls.append(resp)
        data = extract_json(resp.text)
        if data is not None:
            result = check(data, reg)
            result.calls = calls
            return result
    return ReasonResult(
        "needs_review", "low",
        Bilingual(ar="تعذر تحليل هذا النظام تلقائيًا، ويحتاج إلى مراجعة.",
                  en="This regulation could not be analysed automatically and needs review."),
        problems=["Ultra reply unreadable"], calls=calls)
