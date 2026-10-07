"""Offline tests for the Nano filter: no API key or network needed.

Run: python -m pytest tests
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from contracts.models import BusinessProfile, RegulationRecord
from pipeline import filter as flt
from pipeline import llm

FIX = Path(__file__).resolve().parent.parent / "contracts" / "fixtures"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    # Keep tests away from the real cache and log.
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(llm, "LOG_PATH", tmp_path / "calls.jsonl")
    monkeypatch.setenv("USE_LLM_CACHE", "true")


def profile():
    return BusinessProfile.model_validate(
        json.loads((FIX / "profiles" / "prof_demo_cafe.json").read_text(encoding="utf-8")))


def reg():
    return RegulationRecord.model_validate(
        json.loads((FIX / "regulations" / "reg_9a5e4ff6ba_v1.json").read_text(encoding="utf-8")))


class FakeClient:
    """Stands in for the OpenAI client and returns canned replies in order."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        text = self.replies.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=50),
        )


@pytest.mark.parametrize("text,expected", [
    ('{"relevant": true, "reason": "VAT rule."}', True),
    ('Sure!\n```json\n{"relevant": false, "reason": "Mining."}\n```', False),
    ('<think>hmm {x}</think>{"relevant": "true", "reason": "ok"}', True),
])
def test_parse_reads_messy_replies(text, expected):
    assert flt.parse(text).relevant is expected


@pytest.mark.parametrize("text", ["no json here", '{"relevant": "maybe"}', "{broken"])
def test_parse_rejects_unreadable(text):
    assert flt.parse(text) is None


def test_prompt_uses_first_2000_chars_and_no_name():
    p = flt.build_prompt(profile(), reg())
    r = reg()
    assert r.full_text[:2000] in p
    assert r.full_text[:2001] not in p or len(r.full_text) <= 2000
    assert profile().business_name not in p


def test_filter_returns_result_and_logs_cost():
    client = FakeClient('{"relevant": true, "reason": "E-invoicing applies to VAT payers."}')
    result, calls = flt.filter_regulation(profile(), reg(), client=client)
    assert result.relevant is True
    assert calls[0].cost_usd == pytest.approx((1000 * 0.06 + 50 * 0.24) / 1e6)
    rows = llm.LOG_PATH.read_text().splitlines()
    assert json.loads(rows[0])["step"] == "filter"


def test_second_run_is_served_from_cache():
    client = FakeClient('{"relevant": true, "reason": "x"}')
    flt.filter_regulation(profile(), reg(), client=client)
    _, calls = flt.filter_regulation(profile(), reg(), client=client)
    assert client.calls == 1 and calls[0].cached and calls[0].cost_usd == 0


def test_retries_once_then_fails_open():
    client = FakeClient("I think it is relevant", "still not json")
    result, calls = flt.filter_regulation(profile(), reg(), client=client)
    assert client.calls == 2 and len(calls) == 2
    assert result.relevant is True


def test_retry_recovers():
    client = FakeClient("hmm", '{"relevant": false, "reason": "Aviation."}')
    result, _ = flt.filter_regulation(profile(), reg(), client=client)
    assert result.relevant is False
