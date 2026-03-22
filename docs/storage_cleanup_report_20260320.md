# YOTO Storage Cleanup Report (2026-03-20)

## Summary

- Repo size before cleanup: `1,667,377,296` bytes (`1590.13 MB`, `1.553 GB`)
- Repo size after cleanup: `1,418,223,671` bytes (`1352.52 MB`, `1.321 GB`)
- Space reclaimed: `249,153,625` bytes (`237.61 MB`, about `14.94%` of the repo)

The cleanup was intentionally conservative. I removed only generated timestamped reruns, incomplete earlier attempts, small cache folders, and empty scratch output. I did not touch source, tests, docs, configs, DBs in active proof folders, golden snapshots, current freeze-candidate validation artifacts, or the current/final review chain.

## What Was Taking Space

Top-level space before cleanup:

- `output/`: `1249.74 MB`
- `temp/`: `279.59 MB`
- `.venv/`: `39.81 MB`

Main heavy areas before cleanup:

- `output/cards/`: `1003.80 MB`
  - Old card review packs and QA packs were the main driver.
  - Several families had many same-day timestamped reruns.
  - Some packs duplicated large `asset_cache` contents.
- `output/offline_validation/`: `233.45 MB`
  - `snapshots/`: `187.47 MB`
  - `golden/`: `25.49 MB`
  - `review/`: `20.49 MB`
- `temp/`: `279.59 MB`
  - `editorial_stream_validation_nonquiet_20260314T100000Z`: `100.10 MB`
  - `editorial_stream_validation_nonquiet_relaxed_20260314T100000Z`: `86.44 MB`
  - Several older timestamped validation temp runs were also present.

## Conservative Classification

### SAFE TO DELETE NOW

These were deleted because a newer kept run in the same family exists, or because they were cache/empty scratch output:

- `output/cards/discount_family_review_*` older reruns, keeping `discount_family_review_20260319T032825Z`
- `output/cards/typography_system_review_*` older reruns, keeping `typography_system_review_20260319T025740Z`
- `output/cards/premium_finish_review_*` unreferenced older reruns and one empty folder, while keeping the dependency chain:
  - `premium_finish_review_20260319T042046Z`
  - `premium_finish_review_20260319T042059Z`
  - `premium_finish_review_20260319T045615Z`
- Earlier incomplete reruns:
  - `preview_yoto_v43_integration_20260311T225122Z`
  - `smoke_yoto_v451_20260312T005213Z`
  - `validation_yoto_v451_20260312T005213Z`
- Small cache/scratch folders:
  - `output/cards/.yoto_v42_asset_cache`
  - `temp/__pycache__`
  - `temp/roundup_rule_validation_current_tmp2`
  - `.pytest_cache`
- Older temp validation reruns with a later kept run in the same family:
  - `temp/editorial_stream_validation_fresh_20260313T231813Z`
  - `temp/editorial_stream_validation_roundup_publish_20260313T190736Z`
  - `temp/editorial_stream_validation_roundup_publish_20260313T194431Z`
  - `temp/yoto_video_validation_batch_20260314T150323Z`

### SAFE TO ARCHIVE / MOVE OUT OF ACTIVE ROOT

These were left in place, but they are strong candidates to move out of `D:\Telegram` if the operator still wants more space savings:

- `output/cards/preview_yoto_v42_integration_20260311T221545Z`: `43.73 MB`
- `output/cards/preview_yoto_v43_integration_20260311T225501Z`: `44.39 MB`
- `output/cards/preview_yoto_v44_integration_20260311T231905Z`: `45.50 MB`
- `output/cards/gameplay_selection_examples_v1`: `74.14 MB`
- `output/cards/editorial_examples_v5`: `10.22 MB`
- `output/cards/editorial_examples_v51`: `11.94 MB`

These look historical and self-contained, but I left them because they may still be useful review baselines.

### KEEP

These were intentionally preserved:

- `output/offline_validation/golden`
- `output/offline_validation/snapshots`, including the latest `20260320T003516Z`
- `output/offline_validation/review/live_family_review_20260319T011730Z`
- `output/reference_cards`
- Current/final card review packs:
  - `output/cards/discount_family_review_20260319T032825Z`
  - `output/cards/typography_system_review_20260319T025740Z`
  - `output/cards/premium_finish_review_20260319T042046Z`
  - `output/cards/premium_finish_review_20260319T042059Z`
  - `output/cards/premium_finish_review_20260319T045615Z`
  - `output/cards/live_validation_v45`
- Current operator-truth / freeze-adjacent temp artifacts:
  - `temp/editorial_stream_validation_current`
  - `temp/roundup_rule_validation_current`
  - `temp/caption_freeze_backup`
- All source, tests, docs, configs, runtime assets, fonts, and databases outside clearly disposable rerun output

### NEEDS HUMAN DECISION

I did not delete these because they may still represent useful proof history, and they are not clearly disposable:

- `output/cards/steam_live_qa_*` family: about `374.18 MB`
  - This is not a strict rerun family.
  - `steam_live_qa_20260312T054330Z` contains extra `cards_sanity*` trees that are not present in `steam_live_qa_20260312T060207Z`.
  - If these are no longer needed, archive them instead of deleting blindly.
- `temp/editorial_stream_validation_nonquiet_20260314T100000Z`: `100.10 MB`
- `temp/editorial_stream_validation_nonquiet_relaxed_20260314T100000Z`: `86.44 MB`
- `output/offline_validation/snapshots`: `187.47 MB`
  - There are many timestamped snapshots, but this is a high-value proof surface tied to offline validation and freeze work.
  - I recommend a human-approved retention rule instead of ad hoc deletion.
- `output/cards/gameplay_residual_examples_v1`: `7.10 MB`
- `output/cards/_residual_sanity`: `6.57 MB`

## What Was Deleted

Deleted families and reclaimed space:

- Older `discount_family_review` reruns: `127.12 MB`
- Older `typography_system_review` reruns: `26.46 MB`
- Older unreferenced `premium_finish_review` reruns: `47.31 MB`
- Earlier incomplete preview/smoke/validation reruns plus one card cache: `16.07 MB`
- Older temp validation reruns: `20.52 MB`
- Small cache folders and empty scratch dirs: `0.14 MB`

Total deleted: `237.61 MB`

## What Was Preserved On Purpose

- The latest/final review pack in each cleaned family
- The premium finish review dependency chain needed by the latest manifest
- Golden and current offline validation proof
- Current live validation outputs and current temp validation anchors
- Any folder where the artifacts were not clearly replaceable or where a kept artifact still referenced the older output

## Recommended Retention Rules

1. For timestamped review families, keep only the latest final pack and any directly referenced `before_root` / `before_path` dependencies.
2. Keep `output/offline_validation/golden` and the latest freeze-candidate snapshot set untouched unless the owner explicitly approves a retention window.
3. Move historical comparison packs and large QA packs to an archive root outside `D:\Telegram` instead of deleting them from the active repo.
4. Treat `temp/` as disposable only for folders that are both timestamped and clearly superseded by a later run in the same family.
5. Delete cache-only folders (`.pytest_cache`, `__pycache__`, generated asset caches) during storage cleanups when they are outside preserved proof packs.
