from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dealbot.video import (
    SceneAssetPlanError,
    SceneLayoutPayloadError,
    VideoOfferExportError,
    VideoOfferValidationError,
    export_video_offer_artifacts,
)


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
        help=(
            "Optional output directory for video_offer.json, draft_video_manifest.json, "
            "and optional scene_asset_plan.json / scene_layout_payload.json."
        ),
    )
    parser.add_argument(
        "--with-scene-plan",
        action="store_true",
        help="Also export scene_asset_plan.json.",
    )
    parser.add_argument(
        "--with-layout-payload",
        action="store_true",
        help="Also export scene_layout_payload.json and imply scene_asset_plan.json.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = export_video_offer_artifacts(
            source_report_path=args.from_report,
            output_dir=args.output_dir,
            with_scene_plan=args.with_scene_plan,
            with_layout_payload=args.with_layout_payload,
        )
    except (
        FileNotFoundError,
        SceneAssetPlanError,
        SceneLayoutPayloadError,
        VideoOfferExportError,
        VideoOfferValidationError,
    ) as exc:
        print(f"status: failed", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1

    print(f"status: {result.status}")
    print(f"source_report_path: {result.source_report_path}")
    print(f"video_offer_json_path: {result.video_offer_json_path}")
    print(f"draft_manifest_json_path: {result.draft_manifest_json_path}")
    if result.scene_asset_plan_json_path is not None:
        print(f"scene_asset_plan_json_path: {result.scene_asset_plan_json_path}")
    if result.scene_layout_payload_json_path is not None:
        print(f"scene_layout_payload_json_path: {result.scene_layout_payload_json_path}")
    print(f"offer_id: {result.offer_id}")
    print(f"template: {result.template}")
    print(f"scene_count: {result.scene_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
