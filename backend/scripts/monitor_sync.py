"""Read-only monitor for the Google Sheets feeds. Prints the alerts of /sync-status and exits 1 when any non-INFO alert exists,
so it can be run from a scheduler (Railway cron, GitHub Action, or by hand).

    python -m scripts.monitor_sync --expect b1819f,66800c          # run inside the Backend service
"""
from __future__ import annotations

import argparse
import json
import sys

from app.api.routes.integrations import google_sheets_sync_status
from app.core.db import SessionLocal
from app.models import IntegrationConfig


def check(db, expect: str | None = None) -> dict:
    rows = db.query(IntegrationConfig).filter(IntegrationConfig.provider == "GOOGLE_SHEETS").all()
    if len(rows) != 1:
        return {"error": f"expected exactly one GOOGLE_SHEETS integration, found {len(rows)}", "critical": ["monitor misconfigured"]}
    st = google_sheets_sync_status(rows[0].id, expect, db, None)
    critical = [a for a in st["alerts"] if not a.startswith("INFO:")]
    return {"critical": critical, "info": [a for a in st["alerts"] if a.startswith("INFO:")], "last_successful_import_at": str(st["last_successful_import_at"]),
            "imported_per_day": st["imported_per_day"], "feeds": {k: {"last_seen": str(v["last_seen"]), "version": v["version"], "inserted_7d": v["inserted"]} for k, v in st["feeds_last_7_days"].items()},
            "recovered_leads_total": st["recovered_leads_total"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect", default=None, help="comma-separated feed ids (md5 prefixes), e.g. b1819f,66800c")
    args = ap.parse_args()
    out = check(SessionLocal(), args.expect)
    print(json.dumps(out, indent=1))
    sys.exit(1 if out["critical"] else 0)


if __name__ == "__main__":
    main()
