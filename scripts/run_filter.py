"""Run the Nano filter on every fixture profile x regulation, plus the
"should be false" probes in eval/filter_probes.json, and print a table.

Run on your own computer (needs NEBIUS_API_KEY in .env):
  python scripts/run_filter.py

Expected: every real regulation is relevant=True for the cafe profiles,
and every probe is relevant=False. Re-runs are free thanks to the cache.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from contracts.models import BusinessProfile, RegulationRecord  # noqa: E402
from pipeline.filter import filter_regulation  # noqa: E402

FIX = ROOT / "contracts" / "fixtures"


def load(folder, model):
    return [model.model_validate(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted((FIX / folder).glob("*.json"))]


def probe_records():
    data = json.loads((ROOT / "eval" / "filter_probes.json").read_text(encoding="utf-8"))
    for i, p in enumerate(data["probes"], 1):
        yield RegulationRecord.model_construct(
            regulation_id=f"probe_{i}", title_original=p["title"], title_en=None,
            full_text=p["text"],
        )


def main() -> int:
    profiles = load("profiles", BusinessProfile)
    regs = load("regulations", RegulationRecord)
    cases = [(r, True) for r in regs] + [(r, False) for r in probe_records()]

    wrong, total_cost, total_ms, n_calls = 0, 0.0, 0, 0
    for profile in profiles:
        print(f"\n== {profile.profile_id} ({profile.sub_activity}) ==")
        for reg, expected in cases:
            result, calls = filter_regulation(profile, reg)
            n_calls += len(calls)
            total_cost += sum(c.cost_usd for c in calls)
            total_ms += sum(c.latency_ms for c in calls)
            ok = result.relevant == expected
            wrong += not ok
            mark = "OK " if ok else "BAD"
            cached = " (cached)" if all(c.cached for c in calls) else ""
            print(f"{mark} {reg.regulation_id:<20} relevant={str(result.relevant):<5} "
                  f"expected={str(expected):<5} {result.reason[:90]}{cached}")

    print(f"\n{n_calls} calls, ${total_cost:.5f}, {total_ms/1000:.1f}s of model time. "
          f"Wrong: {wrong}. Log: logs/llm_calls.jsonl")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
