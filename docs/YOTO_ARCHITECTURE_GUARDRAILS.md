# YOTO Architecture Guardrails

This file protects the current YOTO execution foundation from accidental redesign. Use it before changing pipeline code.

## Locked Foundations

These are existing architecture seams, not suggestions:

- Planner and queue split in `application/use_cases/plan_queue.py`: keep `planned` and `reserve`, keep selection outcomes, keep capacity-hold versus hard-suppress semantics.
- Controlled reserve release, editorial stream balancing, and roundup injection in `application/use_cases/publish_next.py`, `application/use_cases/controlled_reserve_release.py`, and `application/use_cases/generate_roundup_artifacts.py`.
- Publish/outbox/idempotency/replay foundation in `application/use_cases/publish_next.py`, `application/use_cases/replay_outbox.py`, and `infrastructure/db/repositories.py`.
- Final-artifact-based `video_manifest` v2 flow in `application/use_cases/generate_video_manifests.py`.
- Standalone `video_generator/` ownership split, including `video_generator/domain/scene_planner.py`.
- Current renderer stack in `infrastructure/render/cards/renderer_selector.py`, `infrastructure/render/cards/yoto_card_engine_v4.py`, `infrastructure/render/cards/roundup_top_list_card_adapter.py`, and the legacy fallback path.

## Surgical Changes Allowed

These are safe only when they stay inside the current seam:

- bug fixes inside existing use cases
- scoring and heuristic tuning that preserves current queue/outbox/manifest contracts
- additive diagnostics, analytics, and non-breaking payload fields
- caption, card, and asset-selection improvements inside the current render stack
- targeted tests, fixtures, and validation tools
- CLI wrappers and repo docs that make the current flow easier to operate

## Changes That Require Escalation

Stop before editing if the task would do any of the following:

- remove, merge, or rename `planned` and `reserve`
- replace controlled reserve release with a different publish model
- bypass `publish_outbox`, finalization, replay, or idempotency checks
- change manifest versioning away from v2 or make manifests no longer artifact-based
- merge `video_generator` back into the main bot or remove the scene-planner seam
- replace the renderer family instead of fixing/extending the current stack
- redefine current analytics artifacts or roundup snapshot ownership in a breaking way
- require destructive state cleanup, history rewrite, or incompatible schema migration

## Required Contract Checks

When touching a locked foundation, run the matching contract tests, for example:

- planner / reserve: `tests/test_plan_queue_arch.py`, `tests/test_lane_rebalance_arch.py`
- publish / outbox / replay: `tests/test_publish_idempotency_arch.py`, `tests/test_replay_outbox_arch.py`, `tests/test_publish_reliability_arch.py`
- roundup publish path: `tests/test_roundup_generator_arch.py`, `tests/test_publish_roundup_integration_arch.py`
- manifest v2: `tests/test_video_manifest_v2_arch.py`
- renderer stack: `tests/test_renderer_selector_arch.py`, `tests/test_render_diagnostics_arch.py`, `tests/test_yoto_card_engine_v4.py`
- standalone video generator: `video_generator/tests/test_scene_planner.py`, `video_generator/tests/test_pipeline.py`

If you are unsure whether a change is surgical or structural, treat it as structural and escalate.
