"""Checkpoint 1: every fixture must load into contracts/models.py.

Also checks the trust rules from the spec: ids and hashes match the content,
and every citation quote appears word for word in the regulation's full_text.

Run from the repo root:  python -m contracts.validate_fixtures
"""

import hashlib
import json
import sys
from pathlib import Path

from contracts.models import AnalysisResult, BusinessProfile, RegulationRecord

ROOT = Path(__file__).parent / "fixtures"


def load(folder, model):
    items = {}
    for path in sorted((ROOT / folder).glob("*.json")):
        obj = model.model_validate(json.loads(path.read_text(encoding="utf-8")))
        items[path.stem] = obj
    return items


def main() -> int:
    errors = []
    profiles = load("profiles", BusinessProfile)
    regs = load("regulations", RegulationRecord)
    analyses = load("analyses", AnalysisResult)

    for name, p in profiles.items():
        if p.profile_id != name:
            errors.append(f"{name}: profile_id does not match file name")

    for name, r in regs.items():
        if r.regulation_id != name:
            errors.append(f"{name}: regulation_id does not match file name")
        expected = "reg_" + hashlib.sha1(r.source_url.encode()).hexdigest()[:10] + f"_v{r.version}"
        if r.regulation_id != expected:
            errors.append(f"{name}: regulation_id should be {expected}")
        if r.content_hash != hashlib.sha256(r.full_text.encode()).hexdigest():
            errors.append(f"{name}: content_hash does not match full_text")

    for name, a in analyses.items():
        if a.analysis_id != name:
            errors.append(f"{name}: analysis_id does not match file name")
        reg = regs.get(a.regulation_id)
        if reg is None:
            errors.append(f"{name}: unknown regulation {a.regulation_id}")
            continue
        if a.profile_id not in profiles:
            errors.append(f"{name}: unknown profile {a.profile_id}")
        for o in a.obligations:
            if o.citation.quote not in reg.full_text:
                errors.append(f"{name}/{o.obligation_id}: quote not found verbatim in full_text")
        deadlines = [o.deadline for o in a.obligations if o.deadline]
        if a.next_deadline != (min(deadlines) if deadlines else None):
            errors.append(f"{name}: next_deadline is not the earliest obligation deadline")

    print(f"profiles: {len(profiles)}  regulations: {len(regs)}  analyses: {len(analyses)}")
    for e in errors:
        print("ERROR", e)
    print("OK" if not errors else f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
