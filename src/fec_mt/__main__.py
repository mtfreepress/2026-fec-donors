from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from .config import PipelineConfig
from .pipeline import run_pipeline
from .schedule_a import ScheduleAFetchFailure


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fec_mt")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build the candidate contribution dataset")
    build.add_argument("--cycle", type=int, default=2026)
    build.add_argument("--state", default="MT")
    build.add_argument("--office", action="append", choices=["H", "S", "P"], dest="offices")
    build.add_argument("--start-date", type=_date)
    build.add_argument("--end-date", type=_date)
    build.add_argument("--refresh", action="store_true")
    build.add_argument("--output-dir", type=Path, default=Path("data"))
    build.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    try:
        config = PipelineConfig(
            cycle=args.cycle,
            state=args.state,
            offices=tuple(args.offices or ("H", "S")),
            start_date=args.start_date,
            end_date=args.end_date,
            output_dir=args.output_dir,
            refresh=args.refresh,
        )
        result = run_pipeline(config)
    except ScheduleAFetchFailure as exc:
        logging.error("Build failed. Schedule A retrieval failed for: %s", ", ".join(exc.failed_committee_ids))
        return 2
    except (ValueError, RuntimeError, OSError) as exc:
        logging.error("Build failed: %s", exc)
        return 1

    metadata = result["metadata"]
    print(f"Built {metadata['donor_attribution_record_count']:,} donor-attributable rows in {config.final_dir}")
    if metadata["unknown_record_count"] or metadata["duplicate_transaction_id_row_count"]:
        print(
            "REVIEW REQUIRED: "
            f"{metadata['unknown_record_count']} unknown/uncertain records; "
            f"{metadata['duplicate_transaction_id_row_count']} duplicate transaction-ID rows",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

