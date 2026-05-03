# AGENTS.md — YOTO MVP Source of Truth

## Status

This file is the single source of truth for YOTO MVP development workflow and protected scope.

If chat memory, previous prompts, README, HEAD docs, or older instructions conflict with this file, this file wins unless a new accepted TASK_CARD explicitly updates it.

## MVP Goal

YOTO MVP goal:

- stable Telegram cards
- good resolved visual
- generated caption
- dry-run / auto-post flow

The MVP is not a redesign, not a large refactor, and not a feature expansion project.

## Current State

Current confirmed YOTO state:

- card pipeline works
- renderer works
- VisualDecisionEngine exists
- official asset ingestion/cache exists
- ComfyUI fallback is confirmed
- tests baseline: `30 passed`

## Current Bottleneck

Current bottleneck:

- official asset selection quality
- capsule / logo / placeholder / weak assets can sometimes beat stronger hero / gameplay / action assets

## Image Strategy

YOTO image strategy:

- official game assets are primary
- AI / ComfyUI is fallback, not primary
- renderer does not choose image source
- renderer only composites the already resolved image

## Protected Areas

Do not touch:

- renderer selector
- template system
- publish / outbox
- caption pipeline
- video pipeline
- resolver contract

## Workflow

1. HQ chooses one task
2. BUILD implements
3. QA verifies
4. No QA = no commit

## Scope Rules

- no refactor without task
- no architecture change without task
- no new features outside MVP

## Deprecated

- AI as primary
- renderer choosing source