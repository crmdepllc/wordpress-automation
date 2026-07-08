"""CLI entry point for the eval suite — the CI gate and the local dev command.

Runs every skill's scenario set offline (no Docker, no live API key), writes a
markdown + JSON report, prints the markdown, and exits non-zero if any skill
scores below its committed threshold (``app/evals/thresholds.py``).

Usage:
    uv run python scripts/run_evals.py [--out-dir DIR]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.evals.report import regressions, to_json, to_markdown  # noqa: E402
from app.evals.runner import run_all  # noqa: E402


async def _main(out_dir: Path) -> int:
    reports = await run_all()
    markdown = to_markdown(reports)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "eval-report.md").write_text(markdown, encoding="utf-8")
    (out_dir / "eval-report.json").write_text(to_json(reports), encoding="utf-8")

    print(markdown)
    bad = regressions(reports)
    return 1 if bad else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Sprint 8 eval suite.")
    parser.add_argument(
        "--out-dir", default="eval-out", help="Directory to write the report files to."
    )
    args = parser.parse_args()
    exit_code = asyncio.run(_main(Path(args.out_dir)))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
