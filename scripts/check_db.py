"""Check your DATABASE_URL works and pgvector is on.

  python scripts/check_db.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api import db  # noqa: E402

try:
    info = db.check()
    print(f"Database OK: Postgres {info['postgres']}, pgvector {info['pgvector']}")
except Exception as e:
    print(f"Database FAILED: {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}")
    sys.exit(1)
