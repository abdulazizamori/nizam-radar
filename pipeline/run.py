"""The pipeline entry point (spec section 10):
analyze(profile, reg) -> AnalysisResult.

Nano filter -> Ultra reasoning (+ citation check) -> Super writer.
"""

from __future__ import annotations

import os
import secrets
import string
from datetime import date, datetime, timedelta, timezone

from contracts.models import (
    AnalysisResult, Bilingual, BusinessProfile, ModelsUsed, Obligation, RegulationRecord, Usage,
)
from pipeline.filter import filter_regulation
from pipeline.reason import reason
from pipeline.write import write

URGENT_DAYS = 30


def new_analysis_id() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "ana_" + "".join(secrets.choice(alphabet) for _ in range(8))


def compute_priority(applicability: str, obligations: list[Obligation], today: date) -> str:
    """urgent = applies + a deadline within 30 days (or already passed) or a
    penalty stated; important = applies otherwise; info = everything else."""
    if applicability not in ("applies", "likely_applies"):
        return "info"
    if any(o.penalty for o in obligations):
        return "urgent"
    if any(o.deadline and o.deadline <= today + timedelta(days=URGENT_DAYS) for o in obligations):
        return "urgent"
    return "important"


def next_deadline(obligations: list[Obligation]) -> date | None:
    return min((o.deadline for o in obligations if o.deadline), default=None)


def _models() -> ModelsUsed:
    return ModelsUsed(
        filter=os.environ.get("MODEL_NANO", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
        reasoning=os.environ.get("MODEL_ULTRA", "nvidia/Nemotron-3-Ultra-550b-a55b"),
        writer=os.environ.get("MODEL_SUPER", "nvidia/nemotron-3-super-120b-a12b"),
    )


def _usage(calls) -> Usage:
    return Usage(tokens_in=sum(c.tokens_in for c in calls),
                 tokens_out=sum(c.tokens_out for c in calls),
                 cost_usd=round(sum(c.cost_usd for c in calls), 6))


def analyze(profile: BusinessProfile, reg: RegulationRecord, today: date | None = None,
            client=None, trace: list[str] | None = None) -> AnalysisResult:
    """trace, if given, collects the checks that failed (for scripts and eval)."""
    trace = trace if trace is not None else []
    today = today or date.today()
    base = dict(
        analysis_id=new_analysis_id(),
        regulation_id=reg.regulation_id,
        profile_id=profile.profile_id,
        created_at=datetime.now(timezone.utc),
        models_used=_models(),
    )

    flt, calls = filter_regulation(profile, reg, client=client)
    if not flt.relevant:
        text = Bilingual(ar="هذا النظام لا يخص نشاطك على الأرجح.", en=flt.reason)
        return AnalysisResult(**base, filter=flt, applicability="does_not_apply", confidence="low",
                              reasoning_summary=text, priority="info", summary=text,
                              usage=_usage(calls))

    r = reason(profile, reg, client=client)
    calls += r.calls
    w = write(profile, reg, r, today=today, client=client)
    calls += w.calls
    trace += [f"reason: {p}" for p in r.problems] + [f"write: {p}" for p in w.problems]

    return AnalysisResult(
        **base,
        filter=flt,
        applicability=r.applicability,
        confidence=r.confidence,
        reasoning_summary=r.reasoning_summary,
        obligations=r.obligations,
        next_deadline=next_deadline(r.obligations),
        priority=compute_priority(r.applicability, r.obligations, today),
        summary=w.summary,
        checklist=w.checklist,
        usage=_usage(calls),
    )
