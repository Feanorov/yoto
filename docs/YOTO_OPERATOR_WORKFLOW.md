# YOTO Operator Workflow

Use `yoto.bat` as the operator entrypoint. The new launcher layer keeps the existing planner, publish, outbox, and video seams unchanged, but it now ends the main daily commands with a short verdict, the latest artifact paths, and the next step to take.

## Recommended Daily Commands

Daily desktop launch options:

- double-click `yoto-ui.bat`
  - opens the Operator UI from the bundle root through the existing `yoto.bat ui` launcher path

- run `.\yoto.bat ui` from PowerShell
  - opens the same Operator UI entrypoint when you are already working in a terminal

- `yoto.bat ui`
  - opens the desktop Operator UI only
  - uses the same launcher Python resolution and project-root bootstrap as the other safe operator commands

- `yoto.bat daily-check`
  - safest default start of day
  - runs the existing preview path, keeps live logs visible, then prints the operator verdict plus the newest artifact pointers

- `yoto.bat preview`
  - refreshes current publish truth
  - ends with: verdict, selected target, blocker category if blocked, truth report path, latest snapshot path, latest manifest path, and the exact next operator action

- `yoto.bat send-test`
  - runs the existing send-test path only when you intentionally want Telegram proof
  - ends with: whether Telegram proof was verified, message id, card path, caption preview, operator truth report path, and the next action

- `yoto.bat build-voice-package`
  - builds a voice-ready package from the newest `output/video_manifests/*.json` by default
  - ends with: chosen manifest, package dir, preview video path, script path, review path, and whether the package is ready for Reaper dubbing

- `yoto.bat latest-artifacts`
  - prints the newest operator truth report, planning snapshot, run diagnostics, publish outcome, card, caption review, video manifest, voice-ready package, snapshot, and golden snapshot

- `yoto.bat doctor`
  - reads the latest operator truth report and artifact state without running the pipeline
  - use this when you want a quick blocker/next-step read before touching live systems

## Offline Variants

- `yoto.bat preview-offline`
- `yoto.bat preview-golden`
- `yoto.bat send-test-offline`
- `yoto.bat send-test-golden`

These now go through the same operator launcher, so the offline flows also end with the same verdict/report/artifact summary.

## Operator Output Contract

For the daily commands above, the launcher now tries to leave the operator with five answers immediately visible in the terminal:

1. Is the system ready, blocked, or already Telegram-verified?
2. What exact row or manifest is selected right now?
3. Where did the latest report, card, snapshot, or package land?
4. What blocker category applies if the action could not continue?
5. What exact command should be run next?

## Proof And Report Locations

The launcher writes small operator workflow report artifacts under `output/analytics/` with the pattern:

- `*_operator_workflow_preview.json`
- `*_operator_workflow_send-test.json`
- `*_operator_workflow_daily-check.json`
- `*_operator_workflow_latest_artifacts.json`
- `*_operator_workflow_doctor.json`
- `*_operator_workflow_build_voice_package.json`

The underlying core reports stay in their existing locations:

- operator truth: `output/analytics/*_operator_truth_report_*.json`
- planning snapshot: `output/analytics/*_planning_snapshot_*.json`
- run diagnostics: `output/analytics/*_run_diagnostics_pipeline.json`
- publish outcome: `output/analytics/*_publish_outcome_*.json`
- cards: `output/cards/`
- caption reviews: `output/captions/**/review.md`
- video manifests: `output/video_manifests/*.json`
- voice-ready packages: `output/video_voice_ready/**/package_manifest.json`
- offline snapshots: `output/offline_validation/snapshots/*/snapshot_manifest.json`
- golden snapshot: `output/offline_validation/golden/current/snapshot_manifest.json`

## What Stayed Out Of Scope

- no planner or reserve redesign
- no publish/outbox/idempotency redesign
- no card or caption redesign
- no video architecture rewrite
- no GUI rewrite

This layer is intentionally a wrapper and reporting improvement around the existing production seams.
