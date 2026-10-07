"""Step 2 of the pipeline: Nemotron Ultra applicability reasoning.

Input: profile + the full regulation text. Output: applicability,
confidence, reasoning and obligations, each with a citation.

Trust rule (spec section 7), enforced here in code: every quote must appear
in the regulation's full_text. An obligation whose quote can't be found
(even after one repair round) is dropped, so no unverified quote is ever
shown. If that leaves no verified obligation, the result is needs_review.
"""

from __future__ import annotations

import difflib
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

PROMPT_VERSION = "reason_v2"
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
    failed_quotes: list[str] = field(default_factory=list)
    calls: list[LLMResponse] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)    # obligations removed for an unverifiable quote


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
    return q.strip().strip('"“”«»\'').strip()


# Characters dropped before matching (Arabic diacritics, tatweel, bidi and
# zero-width marks) and characters treated as equal (quote marks, dashes,
# Arabic letter variants). Models often normalise these when copying.
_DROP = set("\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652\u0670\u0640"
            "\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\ufeff")
_SAME = str.maketrans({
    "’": "'", "‘": "'", "`": "'", "´": "'", "“": '"', "”": '"', "«": '"', "»": '"',
    "–": "-", "—": "-", "‐": "-", "‑": "-", "−": "-",
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
    "٫": ",", "،": ",", "؛": ";",
})


_NOISE = re.compile(r"^[\d\W_]+$")      # tokens with no letters: "1-1", "(6000)", "•"
_DIGITS = re.compile(r"\d+")


def _normalise(text: str, skip_noise: bool = False) -> tuple[str, list[int]]:
    """Normalised text plus, for each of its characters, the index of the
    original character it came from (so a match maps back to the original).

    With skip_noise, tokens that contain no letters are left out. PDF tables
    put row numbers like "1-1" or amounts in the middle of a sentence, and
    models quote the sentence without them.
    """
    out, idx = [], []
    for m in re.finditer(r"\S+", text):
        token = [(m.start() + j, ch) for j, ch in enumerate(m.group(0)) if ch not in _DROP]
        if not token:
            continue
        if skip_noise and _NOISE.match("".join(ch for _, ch in token)):
            continue
        if out:
            out.append(" ")
            idx.append(m.start())
        for i, ch in token:
            out.append(ch.translate(_SAME).lower())
            idx.append(i)
    return "".join(out), idx


def _locate(fragment: str, full_text: str, norm_text: str, idx: list[int],
            skip_noise: bool = False) -> str | None:
    nq, _ = _normalise(fragment, skip_noise)
    if len(nq) < 15:
        return None
    pos = norm_text.find(nq)
    if pos == -1:
        return None
    span = full_text[idx[pos]: idx[pos + len(nq) - 1] + 1]
    # Skipping number-only tokens must never let a wrong number through:
    # every number in the quote has to appear in the matched text.
    if skip_noise and not set(_DIGITS.findall(fragment)) <= set(_DIGITS.findall(span)):
        return None
    return span


def find_quote(quote: str, full_text: str) -> str | None:
    """Return the exact span of full_text that the quote points to, or None.

    Matching ignores differences in whitespace, case, quote marks, dashes,
    Arabic diacritics and Arabic letter variants (alef forms, ya/alef maqsura,
    ta marbuta), which models often change when copying. The returned text is
    always the original span from full_text, so the stored quote is verbatim.
    If the model joined two passages with an ellipsis, the longest matching
    piece is used. As a last resort, tokens without letters (table row
    numbers, amounts) are skipped on both sides, as long as every number in
    the quote is still present in the matched text.
    """
    q = _strip_quotes(quote or "")
    if len(q) < 15:          # too short to prove anything
        return None
    if q in full_text:
        return q
    pieces = [q] + sorted((p.strip() for p in re.split(r"\.\.\.|…|\[\.\.\.\]", q)),
                          key=len, reverse=True)
    for skip_noise in (False, True):
        norm_text, idx = _normalise(full_text, skip_noise)
        for piece in pieces:
            found = _locate(piece, full_text, norm_text, idx, skip_noise)
            if found:
                return found
    return None


def closest_passage(quote: str, full_text: str, min_ratio: float = 0.8) -> str | None:
    """The passage of full_text that looks most like a failed quote (same
    number of words), to show Ultra in the repair round. None if nothing is
    close."""
    q_tokens = _normalise(_strip_quotes(quote))[0].split()
    if len(q_tokens) < 3:
        return None
    spans = [(m.start(), m.end()) for m in re.finditer(r"\S+", full_text)]
    words = [_normalise(full_text[a:b])[0] for a, b in spans]
    target = " ".join(q_tokens)
    best, best_ratio = None, min_ratio
    n = len(q_tokens)
    for i in range(0, max(1, len(words) - n + 1)):
        cand = " ".join(words[i:i + n])
        sm = difflib.SequenceMatcher(None, target, cand, autojunk=False)
        if sm.real_quick_ratio() < best_ratio or sm.quick_ratio() < best_ratio:
            continue
        r = sm.ratio()
        if r > best_ratio:
            best, best_ratio = (spans[i][0], spans[min(i + n, len(spans)) - 1][1]), r
    return full_text[best[0]:best[1]] if best else None


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
    problems, failed, dropped = [], [], []
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
                bad = str(ob.get("quote") or "")
                failed.append(bad)
                dropped.append(f"obligation {i}: quote not found in full_text: {bad[:300]!r}")
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
    elif dropped and confidence == "high":
        confidence = "medium"
    return ReasonResult(applicability, confidence, reasoning, obligations, problems, failed, dropped=dropped)


REPAIR = (
    "A program checked your quotes against the regulation text. These quotes do not appear "
    "in the text:\n{quotes}\n\nFor each obligation with one of these quotes, replace the quote "
    "with a passage copied exactly, character for character, from the regulation text (in its "
    "original language, at most 300 characters), or remove that obligation if no passage "
    "supports it. Keep everything else the same. Reply with the full JSON object only."
)


def _repair(first: ReasonResult, data: dict, messages, resp, reg, model, calls, client) -> ReasonResult:
    """Give Ultra one chance to fix quotes that failed the check. The trust
    rule still holds: whatever comes back is checked again in code."""
    lines = []
    for q in first.failed_quotes:
        lines.append(f"- {q[:300]}")
        near = closest_passage(q, reg.full_text)
        if near:
            lines.append(f"  The closest passage in the text is: {near[:400]}")
    quotes = "\n".join(lines)
    retry = messages + [{"role": "assistant", "content": resp.text},
                        {"role": "user", "content": REPAIR.format(quotes=quotes)}]
    fixed = chat("reason_repair", model, retry, max_tokens=8000, client=client)
    calls.append(fixed)
    data2 = extract_json(fixed.text)
    if data2 is None:
        return first
    second = check(data2, reg)
    second.problems = ["after repair: " + p for p in second.problems]
    second.dropped = ["after repair: " + p for p in second.dropped]
    return second


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
            if result.failed_quotes:
                result = _repair(result, data, messages, resp, reg, model, calls, client)
            result.calls = calls
            return result
    return ReasonResult(
        "needs_review", "low",
        Bilingual(ar="تعذر تحليل هذا النظام تلقائيًا، ويحتاج إلى مراجعة.",
                  en="This regulation could not be analysed automatically and needs review."),
        problems=["Ultra reply unreadable"], calls=calls)
