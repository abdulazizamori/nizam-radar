"""Run the full pipeline (Nano -> Ultra -> Super) on the 7 fixture pairs and
compare with the hand-written answers in contracts/fixtures/analyses/.

Run on your own computer (needs NEBIUS_API_KEY in .env):
  python scripts/run_analysis.py            # all 7
  python scripts/run_analysis.py w25cafe1   # only fixtures whose id contains this

Results are saved to out/analyses/ (not committed). Re-runs are free thanks
to the cache. Expect roughly $0.03-0.10 for the first full run (Ultra reads
whole regulations; the restaurant requirements are about 20k tokens).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from contracts.models import AnalysisResult, BusinessProfile, RegulationRecord  # noqa: E402
from pipeline.run import analyze  # noqa: E402

FIX = ROOT / "contracts" / "fixtures"
OUT = ROOT / "out" / "analyses"


def load(folder, model):
    return {p.stem: model.model_validate(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted((FIX / folder).glob("*.json"))}


def same_class(a: str, b: str) -> bool:
    # Spec section 13: applies and likely_applies count as the same class.
    group = {"applies": "applies", "likely_applies": "applies"}
    return group.get(a, a) == group.get(b, b)


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    profiles = load("profiles", BusinessProfile)
    regs = load("regulations", RegulationRecord)
    expected = load("analyses", AnalysisResult)
    OUT.mkdir(parents=True, exist_ok=True)

    match, total, cost = 0, 0, 0.0
    for exp in expected.values():
        if only and only not in exp.analysis_id:
            continue
        profile, reg = profiles[exp.profile_id], regs[exp.regulation_id]
        trace = []
        res = analyze(profile, reg, trace=trace)
        AnalysisResult.model_validate(res.model_dump())           # contract check
        for o in res.obligations:                                  # trust rule, again
            assert o.citation.quote in reg.full_text, o.citation.quote
        total += 1
        ok = same_class(res.applicability, exp.applicability)
        match += ok
        cost += res.usage.cost_usd
        (OUT / f"{exp.analysis_id}.json").write_text(
            json.dumps(res.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"\n{'OK ' if ok else 'DIFF'} {exp.analysis_id}  {reg.title_en or reg.title_original[:50]}")
        print(f"     got: {res.applicability} ({res.confidence}), priority {res.priority}, "
              f"next deadline {res.next_deadline}, {len(res.obligations)} obligations, "
              f"{len(res.checklist)} checklist items")
        print(f"     expected: {exp.applicability}, priority {exp.priority}")
        print(f"     why: {res.reasoning_summary.en[:160]}")
        print(f"     summary (ar): {res.summary.ar[:120]}")
        if trace:
            print(f"     checks: {'; '.join(trace)}")
        print(f"     cost ${res.usage.cost_usd:.4f}, {res.usage.tokens_in} in / {res.usage.tokens_out} out")

    print(f"\nApplicability matches: {match}/{total}. Total cost ${cost:.4f}. "
          f"Full results: out/analyses/. Every quote verified against the regulation text.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
