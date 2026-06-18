from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dealbot.video import VideoOfferExportError, VideoOfferValidationError, export_video_offer_artifacts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export offline YOTO VideoOffer QA artifacts from a preview report or workflow report.",
    )
    parser.add_argument(
        "--from-report",
        required=True,
        help="Path to a preview truth report or an operator workflow report that points to one.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory for video_offer.json and draft_video_manifest.json.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = export_video_offer_artifacts(
            source_report_path=args.from_report,
            output_dir=args.output_dir,
        )
    except (FileNotFoundError, VideoOfferExportError, VideoOfferValidationError) as exc:
        print(f"status: failed", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1

    print(f"status: {result.status}")
    print(f"source_report_path: {result.source_report_path}")
    print(f"video_offer_json_path: {result.video_offer_json_path}")
    print(f"draft_manifest_json_path: {result.draft_manifest_json_path}")
    print(f"offer_id: {result.offer_id}")
    print(f"template: {result.template}")
    print(f"scene_count: {result.scene_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
