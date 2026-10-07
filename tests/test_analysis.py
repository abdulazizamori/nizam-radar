"""Offline tests for Ultra reasoning, the citation check, Super writing and
analyze(). A fake client answers per model; no API key needed."""

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from contracts.models import AnalysisResult, BusinessProfile, RegulationRecord
from pipeline import llm, reason as rsn, run, write as wr

FIX = Path(__file__).resolve().parent.parent / "contracts" / "fixtures"
W25 = "reg_9a5e4ff6ba_v1"
TODAY = date(2026, 10, 7)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(llm, "LOG_PATH", tmp_path / "calls.jsonl")
    monkeypatch.setenv("USE_LLM_CACHE", "false")


def profile(pid="prof_demo_cafe"):
    return BusinessProfile.model_validate(
        json.loads((FIX / "profiles" / f"{pid}.json").read_text(encoding="utf-8")))


def reg(rid=W25):
    return RegulationRecord.model_validate(
        json.loads((FIX / "regulations" / f"{rid}.json").read_text(encoding="utf-8")))


QUOTE = "integrate their E-invoicing solutions with the Fatoora Platform by no later than February 1, 2027."


def ultra_reply(quote=QUOTE, applicability="applies", penalty=None, deadline="2027-02-01"):
    return json.dumps({
        "applicability": applicability, "confidence": "high",
        "reasoning_summary": {"ar": "المقهى مسجل في الضريبة.", "en": "The cafe is VAT-registered."},
        "obligations": [{
            "description": {"ar": "اربط النظام بمنصة فاتورة.", "en": "Integrate with Fatoora."},
            "quote": quote, "article_ref": None, "deadline": deadline,
            "deadline_type": "fixed_date", "deadline_text": "by no later than February 1, 2027",
            "penalty": penalty,
        }],
    }, ensure_ascii=False)


SUPER_OK = json.dumps({
    "summary": {"ar": "يجب ربط نظامك بمنصة فاتورة.", "en": "You must connect to Fatoora."},
    "checklist": [
        {"text_ar": "اسأل مزود النظام", "text_en": "Ask your POS provider", "due_date": "2026-11-15"},
        {"text_ar": "أكمل الربط", "text_en": "Finish the integration", "due_date": "2027-03-01"},
    ],
}, ensure_ascii=False)


class FakeClient:
    """Returns queued replies per model role (nano/ultra/super)."""

    def __init__(self, **queues):
        self.queues = {k: list(v) for k, v in queues.items()}
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model, **kw):
        role = "nano" if "Nano" in model else "ultra" if "Ultra" in model else "super"
        text = self.queues[role].pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=2000, completion_tokens=300))


NANO_YES = '{"relevant": true, "reason": "VAT rule."}'


# --- citation check ----------------------------------------------------------

def test_find_quote_exact_and_whitespace_variant():
    text = reg().full_text
    assert rsn.find_quote(QUOTE, text) == QUOTE
    squashed = QUOTE.replace(" with the", "\n  with   the")
    assert rsn.find_quote(f'"{squashed}"', text) in text


@pytest.mark.parametrize("quote", ["The cafe must integrate by 2027 with Fatoora.", "short", ""])
def test_find_quote_rejects_invented_or_tiny(quote):
    assert rsn.find_quote(quote, reg().full_text) is None


def test_invented_quote_makes_needs_review():
    r = rsn.check(json.loads(ultra_reply(quote="Every cafe must integrate with Fatoora tomorrow.")), reg())
    assert r.applicability == "needs_review" and r.confidence == "low" and not r.obligations


def test_long_quote_is_trimmed_but_still_verbatim():
    text = reg("reg_2ab88e2596_v1").full_text
    long_quote = text[1000:1500]
    r = rsn.check(json.loads(ultra_reply(quote=long_quote)), reg("reg_2ab88e2596_v1"))
    q = r.obligations[0].citation.quote
    assert len(q) <= 300 and q in text


def test_does_not_apply_keeps_no_obligations():
    r = rsn.check(json.loads(ultra_reply(applicability="does_not_apply")), reg())
    assert r.applicability == "does_not_apply" and r.obligations == []


def test_chinese_in_reasoning_makes_needs_review():
    data = json.loads(ultra_reply())
    data["reasoning_summary"]["ar"] = "المقهى最终 مسجل"
    assert rsn.check(data, reg()).applicability == "needs_review"


# --- priority ----------------------------------------------------------------

def _obl(**kw):
    return rsn.check(json.loads(ultra_reply(**kw)), reg()).obligations


@pytest.mark.parametrize("kw,applic,expected", [
    ({}, "applies", "important"),                                  # deadline far away
    ({"deadline": "2026-10-20"}, "applies", "urgent"),             # within 30 days
    ({"deadline": "2025-07-01"}, "applies", "urgent"),             # already in force
    ({"penalty": "SAR 10,000 fine"}, "likely_applies", "urgent"),  # penalty stated
    ({}, "needs_review", "info"),
    ({}, "does_not_apply", "info"),
])
def test_priority(kw, applic, expected):
    assert run.compute_priority(applic, _obl(**kw), TODAY) == expected


# --- writer ------------------------------------------------------------------

def test_writer_caps_due_dates_at_deadline():
    r = rsn.check(json.loads(ultra_reply()), reg())
    w = wr.write(profile(), reg(), r, today=TODAY, client=FakeClient(super=[SUPER_OK]))
    assert w.checklist[1].due_date == date(2027, 2, 1)


def test_writer_retries_on_chinese_then_falls_back():
    r = rsn.check(json.loads(ultra_reply()), reg())
    bad = SUPER_OK.replace("يجب", "最终")
    w = wr.write(profile(), reg(), r, today=TODAY, client=FakeClient(super=[bad, bad]))
    assert len(w.calls) == 2 and w.summary == r.reasoning_summary and w.problems


# --- full pipeline -------------------------------------------------------------

def test_analyze_end_to_end_produces_valid_contract():
    client = FakeClient(nano=[NANO_YES], ultra=[ultra_reply()], super=[SUPER_OK])
    trace = []
    res = run.analyze(profile(), reg(), today=TODAY, client=client, trace=trace)
    AnalysisResult.model_validate(res.model_dump())
    assert res.applicability == "applies" and res.priority == "important"
    assert res.next_deadline == date(2027, 2, 1)
    assert res.obligations[0].citation.quote in reg().full_text
    assert res.usage.tokens_in == 6000 and res.usage.cost_usd > 0
    assert res.analysis_id.startswith("ana_") and len(res.analysis_id) == 12
    assert trace == []


def test_analyze_stops_after_filter_when_irrelevant():
    client = FakeClient(nano=['{"relevant": false, "reason": "Mining."}'])
    res = run.analyze(profile(), reg(), today=TODAY, client=client)
    assert res.applicability == "does_not_apply" and res.priority == "info" and not res.obligations


def test_analyze_unreadable_ultra_is_needs_review():
    client = FakeClient(nano=[NANO_YES], ultra=["no json", "still no json"], super=[SUPER_OK])
    res = run.analyze(profile(), reg(), today=TODAY, client=client)
    assert res.applicability == "needs_review" and res.priority == "info"


# --- quote matching tolerance and repair --------------------------------------

def test_find_quote_tolerates_apostrophes_case_and_ellipsis():
    text = reg("reg_026c0000a3_v1").full_text
    i = text.index("’")
    original = text[i - 60:i + 40]
    found = rsn.find_quote(original.replace("’", "'").upper(), text)
    assert found == original
    joined = text[100:160] + " ... " + text[400:470]
    assert rsn.find_quote(joined, text) in text


def test_find_quote_tolerates_arabic_diacritics_and_letter_variants():
    import re
    text = reg("reg_ac04b7a838_v1").full_text
    line = next(m.group(0) for m in re.finditer(r"[^\n]{60,}", text) if re.search(r"[ً-ْ]", m.group(0)))
    plain = re.sub(r"[ً-ْـ]", "", line).replace("أ", "ا").replace("ة", "ه")
    found = rsn.find_quote(plain[:150], text)
    assert found is not None and found in text


def test_ultra_fixes_its_quote_on_repair():
    client = FakeClient(ultra=[ultra_reply(quote="Every cafe must integrate with Fatoora tomorrow."),
                               ultra_reply()])
    r = rsn.reason(profile(), reg(), client=client)
    assert r.applicability == "applies" and len(r.calls) == 2 and not r.problems
    assert r.obligations[0].citation.quote == QUOTE


def test_still_wrong_after_repair_is_needs_review():
    bad = ultra_reply(quote="Every cafe must integrate with Fatoora tomorrow.")
    r = rsn.reason(profile(), reg(), client=FakeClient(ultra=[bad, bad]))
    assert r.applicability == "needs_review" and r.problems[0].startswith("after repair")


def test_no_repair_call_when_quotes_are_fine():
    r = rsn.reason(profile(), reg(), client=FakeClient(ultra=[ultra_reply()]))
    assert len(r.calls) == 1


TABLE_TEXT = "الحالات:\n1-1\nعزل أحد أنواع البكتيريا المسببة لظهور أعراض مرضية\n1-2\nمن المصابين وغرامة (6000) ريال"


def test_find_quote_skips_table_row_numbers():
    quote = "عزل أحد أنواع البكتيريا المسببة لظهور أعراض مرضية من المصابين"
    span = rsn.find_quote(quote, TABLE_TEXT)
    assert span is not None and span in TABLE_TEXT


def test_find_quote_rejects_changed_number_across_table():
    assert rsn.find_quote("من المصابين وغرامة (9000) ريال", TABLE_TEXT) is None


def test_closest_passage_points_repair_at_the_real_text():
    near = rsn.closest_passage("عزل أحد انواع البكتريا المسببة لظهور اعراض", TABLE_TEXT)
    assert near is not None and "البكتيريا" in near


def test_prompt_explains_not_vat_registered():
    assert "taxable person" in rsn.PROMPT and "375,000" in rsn.PROMPT
