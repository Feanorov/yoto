# YOTO Validation Playbook

Normalized operator commands live in `yoto.bat`. Use [YOTO_COMMAND_INDEX.md](YOTO_COMMAND_INDEX.md) as the command map; it points to the underlying repo-truthful commands.

Use this workflow for production-facing work:

`repro -> fix -> validate -> generate artifacts -> publish proof / review`

## 1. Repro

- Reproduce the issue with the smallest real surface available.
- Prefer targeted contract tests first.
- Use repo entrypoints that already exist:
  - `python -m dealbot.main --preview`
  - `python -m dealbot.main --send-test`
  - `python -m video_generator`
  - `python tools/generate_yoto_v1_live_caption_validation.py`
  - `python tools/generate_yoto_v451_live_validation_pack.py --limit 26`

## 2. Fix

- Patch the smallest existing seam that owns the behavior.
- Do not redesign planner/reserve, outbox, manifest flow, or renderer ownership while fixing a local defect.

## 3. Validate

Run targeted tests for the touched boundary before broader validation.

Common contract commands:

- `python -m pytest -q tests/test_plan_queue_arch.py`
- `python -m pytest -q tests/test_publish_idempotency_arch.py tests/test_replay_outbox_arch.py`
- `python -m pytest -q tests/test_publish_roundup_integration_arch.py tests/test_video_manifest_v2_arch.py`
- `python -m pytest -q tests/test_renderer_selector_arch.py tests/test_render_diagnostics_arch.py tests/test_yoto_card_engine_v4.py`
- `python -m pytest -q video_generator/tests/test_scene_planner.py video_generator/tests/test_pipeline.py`

Pick the smallest set that proves the changed contract.

## 4. Generate Artifacts

Produce real artifacts from the path you changed.

- Caption changes: generate a live caption review pack under `output/captions` with `python tools/generate_yoto_v1_live_caption_validation.py`.
- Card / hero / gameplay changes: generate a live render pack under `output/cards/live_validation_v45` with `python tools/generate_yoto_v451_live_validation_pack.py --limit 26`.
- Publish / roundup / manifest changes: run `python -m dealbot.main --preview` and then `python -m dealbot.main --send-test` when real publish validation is required.
- Video-generator changes: confirm manifests land in `output/video_manifests`, then run `python -m video_generator` and inspect `output/videos` and `temp/video_scenes`.

If card or caption output changed, review against `docs/YOTO_QA_MATRIX.md`.

## 5. Publish Proof / Review

For any output-facing task, report:

- exact commands run
- pass/fail result
- artifact paths
- Telegram message id if a real test post was sent
- any manual cleanup needed

## Telegram Validation Rule

- If the task changes Telegram-facing behavior, dry reasoning is not enough.
- When applicable, use the real publish path, not only mocks.
- The main Telegram channel may currently be used as a temporary validation target because it is empty; test posts can be deleted manually afterward.
- Do not force a staging-only policy when the real path is the correct validation surface.

## Failure Rule

If repro, artifact generation, or publish-path validation fails, report the failure and stop calling the task done.
