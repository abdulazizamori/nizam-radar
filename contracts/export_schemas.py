"""Write JSON Schema for every contract model into contracts/schemas/ (for the web app).

Run from the repo root:  python -m contracts.export_schemas
"""

import json
from pathlib import Path

from contracts.models import ALL_MODELS

OUT = Path(__file__).parent / "schemas"

for model in ALL_MODELS:
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{model.__name__}.json"
    path.write_text(json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", path)
