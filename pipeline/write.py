"""Step 3 of the pipeline: Nemotron Super writes the summary and checklist
from Ultra's checked analysis (spec section 11)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from contracts.models import Bilingual, BusinessProfile, ChecklistItem, RegulationRecord
from pipeline.jsonx import extract_json, has_cjk
from pipeline.llm import LLMResponse, chat
from pipeline.reason import ReasonResult

PROMPT_VERSION = "write_v1"
PROMPT = (Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")
MAX_ITEMS = 5


@dataclass
class WriteResult:
    summary: Bilingual
    checklist: list[ChecklistItem] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    calls: list[LLMResponse] = field(default_factory=list)


def build_prompt(profile: BusinessProfile, reg: RegulationRecord, r: ReasonResult, today: date) -> str:
    analysis = {
        "applicability": r.applicability,
        "confidence": r.confidence,
        "reasoning": r.reasoning_summary.model_dump(),
        "obligations": [
            {"description": o.description.en, "deadline": str(o.deadline) if o.deadline else None,
             "deadline_text": o.deadline_text, "penalty": o.penalty}
            for o in r.obligations
        ],
    }
    return PROMPT.format(today=today.isoformat(), business=profile.sub_activity,
                         title=reg.title_en or reg.title_original,
                         analysis=json.dumps(analysis, ensure_ascii=False, indent=1))


def _date(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def check(data: dict, r: ReasonResult) -> tuple[Bilingual | None, list[ChecklistItem], list[str]]:
    problems = []
    s = data.get("summary") or {}
    ar, en = str(s.get("ar") or "").strip(), str(s.get("en") or "").strip()
    if not ar or not en:
        problems.append("missing summary")
    if has_cjk(ar) or has_cjk(en):
        problems.append("non-Arabic script in summary")
    latest = max((o.deadline for o in r.obligations if o.deadline), default=None)
    items = []
    for raw in (data.get("checklist") or [])[:MAX_ITEMS]:
        if not isinstance(raw, dict):
            continue
        t_ar, t_en = str(raw.get("text_ar") or "").strip(), str(raw.get("text_en") or "").strip()
        if not t_ar or not t_en:
            continue
        if has_cjk(t_ar) or has_cjk(t_en):
            problems.append("non-Arabic script in checklist")
            continue
        due = _date(raw.get("due_date"))
        if due and latest and due > latest:
            due = latest
        items.append(ChecklistItem(item_id=f"chk_{len(items) + 1}", text_ar=t_ar, text_en=t_en,
                                   due_date=due))
    summary = Bilingual(ar=ar, en=en) if not problems else None
    return summary, items, problems


def fallback_summary(r: ReasonResult) -> Bilingual:
    """Used when Super's text fails the checks: Ultra's reasoning is still
    accurate, just less polished."""
    return r.reasoning_summary


def write(profile: BusinessProfile, reg: RegulationRecord, r: ReasonResult,
          today: date | None = None, client=None) -> WriteResult:
    model = os.environ.get("MODEL_SUPER", "nvidia/nemotron-3-super-120b-a12b")
    today = today or date.today()
    messages = [{"role": "user", "content": build_prompt(profile, reg, r, today)}]
    calls, problems = [], []
    for attempt in range(2):
        if attempt:
            messages = messages + [
                {"role": "assistant", "content": calls[-1].text},
                {"role": "user", "content": "Fix this: " + "; ".join(problems)
                 + ". Reply with the JSON object only, Arabic in Arabic script only."},
            ]
        resp = chat("write", model, messages, max_tokens=4000, client=client)
        calls.append(resp)
        data = extract_json(resp.text)
        if data is None:
            problems = ["reply was not valid JSON"]
            continue
        summary, items, problems = check(data, r)
        if summary:
            return WriteResult(summary, items, [], calls)
    return WriteResult(fallback_summary(r), [], problems, calls)
