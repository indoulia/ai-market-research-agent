from __future__ import annotations

import argparse
import json
from datetime import date

from app.db import SessionLocal
from app.market_data.quality import validate_market_prices


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate canonical daily market data and persist an audit report")
    parser.add_argument("--from-date", type=date.fromisoformat, required=True)
    parser.add_argument("--to-date", type=date.fromisoformat, required=True)
    parser.add_argument("--stock-id", type=int, action="append", dest="stock_ids")
    args = parser.parse_args()
    with SessionLocal() as session:
        run = validate_market_prices(session, args.from_date, args.to_date, args.stock_ids)
        print(json.dumps({"validation_run_id": run.id, **run.report_json}, indent=2))
        return 0 if run.status == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
