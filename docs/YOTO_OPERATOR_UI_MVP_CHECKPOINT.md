# YOTO Operator UI MVP Checkpoint

## Current Status

YOTO Operator UI MVP is live verified and daily-operator ready.

Current checkpoint includes:

- desktop PySide6 Operator UI
- Russian UI
- dark gaming UI
- simplified operator-first layout
- operator status banner
- current preview panel
- caption preview
- safe `publish-previewed` send
- pinned preview contract
- publish-previewed backend command
- doctor publish proof visibility
- last publish status
- publish history panel
- launcher aliases and one-click desktop launcher

Current live proof:

- Subnautica
- `offer_id: steam:264710`
- `message_id: 182`
- `published: yes`
- `telegram_verified: yes`

## Launch UI

Use any of these entrypoints:

- `.\yoto-ui.bat`
- `.\yoto.bat ui`
- `.\yoto.bat operator-ui`

All three open the same Operator UI entrypoint.

## Safe Daily Workflow

1. Open the UI.
2. Click `Собрать превью` or `Собрать следующий пост`.
3. Inspect the card.
4. Inspect the caption.
5. Confirm the selected type.
6. Click `Отправить в Telegram`.
7. Confirm the modal.
8. Check `message_id` in the UI and in `doctor`.

## What Safe Send Means

Safe send in the Operator UI means:

- the UI uses `publish-previewed`, not `send-test`
- send is not automatic
- the selected preview must be pinned in the current preview report
- send stays disabled if the preview is ambiguous, stale, missing required artifacts, or missing pinned publish data
- the UI keeps the send-disabled reason visible in the main operator area
- the send confirmation modal shows pinned publish details before publish starts
- send verifies identity and hashes before the UI treats the publish as successful

## What Publish-Previewed Does

`publish-previewed` is the backend publish path used by the Operator UI safe send flow.

It is expected to:

- publish exactly the pinned preview payload from the current report
- use preview contract fields such as `report_path`, `idempotency_key`, `caption_hash`, `image_hash`, and `image_path`
- preserve the normal publish/outbox backend behavior
- avoid selecting a new item during send

For normal operator work, the UI should use `publish-previewed` rather than the older `send-test` path.

## What Doctor Confirms

Use:

- `.\yoto.bat doctor`
- `.\yoto.bat latest-artifacts`
- `git status`

`doctor` confirms the latest operator truth and publish proof state, including whether the latest publish-previewed workflow matches the previewed item and whether Telegram proof is present.

At this checkpoint, doctor is expected to show the publish-previewed proof for:

- Subnautica / `steam:264710` / `message_id 182`

`latest-artifacts` helps locate the newest report, card, publish outcome, and related runtime files.

`git status` helps verify that no unexpected repo changes are mixed into operator work.

## Artifact Locations

Operator UI and related workflow artifacts are written under:

- `output/analytics/`
- `output/cards/`
- `output/captions/`
- `output/offline_validation/`
- `output/video_manifests/`
- `output/video_voice_ready/`

Important files commonly checked during operator work:

- operator truth reports in `output/analytics/*_operator_truth_report_*.json`
- publish outcomes in `output/analytics/*_publish_outcome_*.json`
- operator workflow summaries in `output/analytics/*_operator_workflow_*.json`
- rendered cards in `output/cards/`

## Runtime Cache Cleanup

If the runtime Steam cache should be cleaned back to git state, run:

- `git restore data/steam_cache`

Use this only for runtime cache cleanup, not as a general-purpose reset for other working files.

## Hard Safety Notes

- The UI must use `publish-previewed`, not `send-test`.
- There is no auto-send.
- Preview must be pinned.
- Send should verify identity and hashes.
- Do not bypass the UI with old `send-test` for normal daily operation.

## Known Non-Goals

This checkpoint is not:

- a planner redesign
- a renderer redesign
- a selector or VDE redesign
- a caption system redesign
- a publish/outbox redesign
- an automation or auto-send expansion
- a replacement for `doctor` or `latest-artifacts`

## Next Suggested Improvements

- add a small operator-facing release note or history view inside the UI
- add a clearer surfaced path from the UI to the latest truth report and publish outcome pair
- add a concise recovery checklist for blocked or stale previews
- add a small operator QA checklist for image, caption, and type review before send
