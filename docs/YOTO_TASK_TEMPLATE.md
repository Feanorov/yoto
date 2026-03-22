# YOTO Task Contract Template

Use this template for future Codex work. Replace placeholders; do not leave fake commands or fake paths in place.

## Objective

`<one sentence repo outcome>`

## Context

- Subsystem: `<files / modules / tests / outputs involved>`
- Current behavior: `<what exists today>`
- Contract to preserve: `<architecture tests / docs / payload versions / output rules>`

## Allowed Scope

- `<exact files or directories that may change>`
- `<tests, scripts, docs, or fixtures that may be added or updated>`

## Forbidden Scope

- No redesign of planner / reserve architecture.
- No redesign of controlled reserve release or editorial ranking.
- No bypass of outbox, idempotency, replay, or finalization.
- No manifest-version change or collapse of the standalone `video_generator/` split.
- No renderer-stack replacement unless the task explicitly authorizes architecture work.
- No weakening of `docs/YOTO_QA_MATRIX.md`.

## Acceptance Criteria

- [ ] `<behavior change is implemented>`
- [ ] `<affected contract tests pass>`
- [ ] `<required output artifacts exist>`
- [ ] `<no locked architecture boundary was changed>`

## Validation Steps

- `python -m pytest -q <targeted_test_or_tests>`
- `<repo-verified preview / render / publish command>`
- `<artifact inspection step>`

If a command is unknown, inspect the repo and replace it with a real one before running.

## Proof Requirements

- Tests: exact commands and pass/fail result.
- Artifacts: exact output paths.
- Telegram/media: message id or publish-path evidence when applicable.
- If validation is blocked, say blocked. Do not relabel blocked work as done.

## Response Format

- `Changed:` files and behavior.
- `Validation:` commands run and result.
- `Artifacts:` paths and output proof.
- `Blockers:` remaining risk, missing credential, or owner decision.

## Escalation Rule

Stop and escalate before editing if the task would change a locked foundation, schema/version boundary, publish semantics, or any behavior that cannot be validated safely with the current repo surfaces.
