# YOTO Done Criteria

A task is not done because code was written or explained. It is done only when the requested scope is implemented, validated, and proven at the level of the surface it changes.

## Baseline For Every Task

- Requested behavior is implemented in the repo.
- Targeted validation was run against the touched subsystem.
- Any changed contract now has matching tests, docs, or both.
- No locked architecture boundary was silently redefined.
- If a required validation step could not run, the task is blocked, not done.

## Tier: Code-Only

Use this only when the change does not affect rendered outputs, Telegram posts, manifests, or publish flow.

- Targeted `pytest` coverage passes.
- No output artifact is required.
- Final report includes exact tests run.

## Tier: Output-Facing

Use this when the change affects captions, cards, analytics artifacts, manifests, or generated files.

- Code-only criteria pass.
- At least one real artifact is generated from the changed path.
- Artifact is inspected and reported by exact path.
- If the change touches card or caption quality, compare against `docs/YOTO_QA_MATRIX.md`.

## Tier: Telegram / Media

Use this when the change affects caption text, card image, publish order, outbox state, replay behavior, roundup publish, or video-manifest emission.

- Output-facing criteria pass.
- Publish-path validation is run when applicable; reasoning alone is insufficient.
- Real evidence exists from the actual path changed:
  - preview output, and
  - rendered post artifact, and
  - Telegram publish proof when the task changes live publish behavior
- For current repo operations, the main Telegram channel may be used as a temporary validation target because it is empty; test posts can be deleted manually after review.

## Tier: Architecture-Sensitive

Use this when the change touches planner/reserve logic, editorial ranking, outbox/idempotency/replay, roundup injection, manifest v2, `video_generator/`, scene planning, or renderer selection/fallback.

- Telegram/media or output-facing criteria pass, depending on the surface.
- Relevant architecture-contract tests pass for the touched boundary.
- Any additive payload/schema change is backward-safe and validated against its current consumer.
- If the work would alter a locked foundation instead of fixing/extending within it, the task must stop for escalation.

## Not Done

The task is not done if any of the following is true:

- only code was changed, without validation
- only unit tests ran, but required artifacts were not generated
- artifacts exist, but not from the real execution path that changed
- Telegram-facing behavior changed, but no publish-path proof was produced
- the answer hides blocked validation behind a summary
