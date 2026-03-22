# YOTO Repo Operating Contract

YOTO is a production system for Ukrainian gaming deals media. Work here by preserving the existing execution model and shipping proof, not by redesigning the stack.

## Default Working Rules

- Inspect the touched flow before editing.
- Prefer the smallest viable patch inside the current architecture.
- Treat architecture tests and `docs/YOTO_QA_MATRIX.md` as binding contracts.
- Do not call work "done" from code inspection alone when the task affects outputs, Telegram posts, or media artifacts.

## Locked Foundations

- Planner plus `planned` / `reserve` split, including controlled reserve release.
- Editorial scoring, ranking, stream balancing, and roundup injection behavior.
- Publish path: render artifact -> `publish_outbox` -> finalize publication -> replay / idempotency.
- `video_manifest` v2 side output and the standalone `video_generator/` worker split, including the scene planner seam.
- Current card stack: `infrastructure/render/cards/renderer_selector.py`, `infrastructure/render/cards/yoto_card_engine_v4.py`, roundup card adapter, and the current fallback path.

## Output Proof Rules

- Output-facing work is not done without real artifacts from the path that changed.
- Telegram-facing tasks are not done without publish-path validation when the change touches captioning, cards, publish sequencing, outbox behavior, or manifest emission.
- Valid proof usually comes from one or more of:
  - targeted `pytest` coverage for the touched contract
  - `python -m dealbot.main --preview`
  - `python -m dealbot.main --send-test` or `send_test_post.bat` when real Telegram validation is required
  - generated artifacts under `output/cards`, `output/analytics`, `output/video_manifests`, `output/videos`, or a tool-specific validation folder

## Stop And Escalate

- Stop if the request implies changing queue model, reserve semantics, outbox semantics, manifest versioning, video-generator split ownership, or renderer-family ownership.
- Stop if you need to weaken acceptance checks, bypass validation, or mark Telegram/media work done without artifacts.

## Response Format

- `Changed:` concrete files and behavior.
- `Validation:` exact commands run and result.
- `Artifacts:` output paths, manifest paths, or Telegram proof.
- `Blockers:` anything not validated or requiring owner decision.
