# YOTO Command Index

Use the repo-normalized operator layer through `yoto.bat`. It wraps existing repo commands only and keeps the current execution model unchanged.

## Launcher Resolution

- `yoto.bat` resolves Python in this order:
  - `D:\Telegram\.venv\Scripts\python.exe`
  - `D:\Telegram_portable_bundle\.venv\Scripts\python.exe`
- If none of those interpreters exist, the launcher stops with a clear error instead of falling through to `python` on `PATH`.
- The batch file enters the bundle root before every command, so operators can run `D:\Telegram_portable_bundle\yoto.bat ...` without manual `cd` or path hacks.

## Safe vs Dangerous

- Safe commands:
  - `doctor`
  - `latest-artifacts`
  - `preview`
  - `preview-offline`
  - `preview-golden`
  - `daily-check`
  - `ui`
  - `operator-ui`
  - `snapshot-offline`
  - `build-voice-package`
  - `generate-captions`
  - `generate-captions-offline`
  - `generate-captions-golden`
  - `generate-cards`
  - `generate-cards-offline`
  - `generate-cards-golden`
  - `test-planner`
  - `test-caption`
  - `test-cards`
  - `test-publish`
  - `test-video`
  - `video-smoke`
- Dangerous or state-changing commands:
  - `send-test`, `send-test-offline`, `send-test-golden`
    - publish-capable; can send to Telegram
  - `run-once`, `run-once-offline`, `run-once-golden`
    - execute the publish decision path and mutate runtime state
  - `run`
    - long-running publish loop
  - `snapshot-golden`
    - replaces the preserved golden snapshot when the candidate is eligible
  - `video-worker`, `video-loop`
    - background or repeated processing commands, not day-to-day operator checks

For MVP operator verification, prefer the safe commands unless you explicitly intend to publish or overwrite preserved state.

## Core Bot Commands

- `yoto.bat preview`
  - runs `python -m dealbot.main --preview`
  - refreshes the live queue, rebuilds roundup side output, and refreshes the latest offline validation snapshot candidate
  - if no golden snapshot exists yet and the live candidate is truthfully golden-eligible, the command preserves that first golden snapshot automatically

- `yoto.bat preview-offline`
  - runs `python -m dealbot.main --preview --offline-snapshot latest`
  - reads the latest offline validation snapshot candidate without calling live ingest

- `yoto.bat preview-golden`
  - runs `python -m dealbot.main --preview --offline-snapshot golden`
  - reads the preserved golden offline validation snapshot without calling live ingest

- `yoto.bat send-test`
  - runs `python -m dealbot.main --send-test`
  - uses the live planner/publish path and refreshes the latest offline validation snapshot candidate before publish
  - if no golden snapshot exists yet and the pre-publish candidate is truthfully golden-eligible, the command preserves that first golden snapshot automatically before the publish path mutates queue state

- `yoto.bat send-test-offline`
  - runs `python -m dealbot.main --send-test --offline-snapshot latest`
  - replays the publish path from the latest offline validation snapshot working copy without live ingest

- `yoto.bat send-test-golden`
  - runs `python -m dealbot.main --send-test --offline-snapshot golden`
  - replays the publish path from the preserved golden snapshot working copy without live ingest

- `yoto.bat ui`
  - runs `python -m dealbot.operator_ui`
  - opens the desktop Operator UI from the bundle root without triggering preview, send-test, publish-previewed, or Telegram activity

- `yoto.bat operator-ui`
  - alias for `yoto.bat ui`
  - opens the same desktop Operator UI entrypoint with the same safe behavior

- `yoto.bat snapshot-offline`
  - runs `python -m dealbot.main --capture-offline-snapshot`
  - captures the current DB queue/history state into a new offline validation snapshot candidate without refreshing live ingest
  - prints a quality summary so operators can see whether the snapshot is publishable, asset-rich, and golden-eligible

- `yoto.bat snapshot-golden`
  - runs `python -m dealbot.main --capture-offline-snapshot --promote-offline-snapshot`
  - captures the current DB queue/history state, then preserves it as the golden snapshot only if the candidate is truthful and good enough for repeatable offline send-test proof
  - if the candidate is not good enough, the command keeps the existing golden snapshot untouched and prints the blocker reasons

- `yoto.bat run-once`
  - runs `python -m dealbot.main --once`
  - use for one production-style planning/publish cycle without the continuous loop; refreshes the offline validation snapshot candidate first
  - if no golden snapshot exists yet and the pre-publish candidate is truthfully golden-eligible, the command preserves that first golden snapshot automatically before publish mutates queue state

- `yoto.bat run-once-offline`
  - runs `python -m dealbot.main --once --offline-snapshot latest`
  - executes one publish decision from the latest offline validation snapshot working copy

- `yoto.bat run-once-golden`
  - runs `python -m dealbot.main --once --offline-snapshot golden`
  - executes one publish decision from the preserved golden snapshot working copy

- `yoto.bat run`
  - runs `python -m dealbot.main`
  - use for the long-running bot loop

## Targeted Validation

- `yoto.bat test-planner`
  - runs `python -m pytest -q tests/test_plan_queue_arch.py tests/test_lane_rebalance_arch.py`

- `yoto.bat test-caption`
  - runs `python -m pytest -q tests/test_caption_builder_arch.py tests/test_live_caption_validation_tool.py`

- `yoto.bat test-cards`
  - runs `python -m pytest -q tests/test_renderer_selector_arch.py tests/test_render_diagnostics_arch.py tests/test_yoto_card_engine_v4.py`

- `yoto.bat test-publish`
  - runs `python -m pytest -q tests/test_publish_idempotency_arch.py tests/test_replay_outbox_arch.py tests/test_publish_roundup_integration_arch.py tests/test_video_manifest_v2_arch.py`

- `yoto.bat test-video`
  - runs `python -m pytest -q video_generator/tests/test_scene_planner.py tests/test_pipeline.py`

## Artifact Generators

- `yoto.bat generate-captions`
  - runs `python tools/generate_yoto_v1_live_caption_validation.py`
  - writes review packs under `output/captions/yoto_voice_v1_live_validation/<run_key>/`

- `yoto.bat generate-captions-offline`
  - runs `python tools/generate_yoto_v1_live_caption_validation.py --offline-snapshot latest`
  - reads caption validation input from the latest offline validation snapshot DB

- `yoto.bat generate-captions-golden`
  - runs `python tools/generate_yoto_v1_live_caption_validation.py --offline-snapshot golden`
  - reads caption validation input from the preserved golden snapshot DB

- `yoto.bat generate-cards --limit 26`
  - runs `python tools/generate_yoto_v451_live_validation_pack.py --limit 26`
  - writes render packs under `output/cards/live_validation_v45/`

- `yoto.bat generate-cards-offline --limit 26`
  - runs `python tools/generate_yoto_v451_live_validation_pack.py --offline-snapshot latest --limit 26`
  - reads card validation input from the latest offline validation snapshot DB

- `yoto.bat generate-cards-golden --limit 26`
  - runs `python tools/generate_yoto_v451_live_validation_pack.py --offline-snapshot golden --limit 26`
  - reads card validation input from the preserved golden snapshot DB

- `yoto.bat video-worker`
  - runs `python -m video_generator`
  - consumes manifests from `output/video_manifests/` and writes videos to `output/videos/`

- `yoto.bat video-loop`
  - runs `python -m video_generator --loop`
  - use only when you want the standalone worker polling continuously

- `yoto.bat video-smoke`
  - runs `python -m video_generator --manifests-dir video_generator/smoke_test/manifests --videos-dir output/videos/smoke --temp-scenes-dir temp/video_smoke_scenes`
  - use for a repo-local smoke render from the checked-in smoke manifest

## Offline Snapshot Workflow

- Candidate snapshot location:
  - `output/offline_validation/snapshots/<run_key>/`
  - each candidate stores an immutable `dealbot.sqlite3` copy plus localized queue assets and a `snapshot_manifest.json`

- Golden snapshot location:
  - `output/offline_validation/golden/current/`
  - this is the preserved operator-approved snapshot for repeatable offline proof runs

- Snapshot quality metadata:
  - each `snapshot_manifest.json` now includes `quality`
  - key booleans:
    - `send_test_offline_ready`
    - `cards_offline_ready`
    - `captions_offline_ready`
    - `artifact_rich`
    - `usable_for_send_test_offline`
    - `golden_eligible`
  - key counts:
    - `publishable_planned_rows_total`
    - `planned_rows_with_local_assets`
    - `roundup_snapshots_with_local_cards`
    - `archive_posts_total`
  - blocking reasons live under `quality.blocking_reasons`

- Live refresh path:
  - `yoto.bat preview`
  - `yoto.bat send-test`
  - `yoto.bat run-once`
  - these refresh the latest offline snapshot candidate automatically after a successful live plan and roundup side output pass
  - if the candidate is `golden_eligible=yes` and no golden snapshot exists yet, the first golden snapshot is preserved automatically from that live cycle
  - automatic promotion is first-golden-only; later healthy candidates stay manual so operators do not lose a known-good golden snapshot by accident

- Snapshot-only refresh path:
  - `yoto.bat snapshot-offline`
  - use this when the queue is already in `data/dealbot.sqlite3` and you want to seed or inspect offline validation without touching live ingest

- Golden preserve path:
  - `yoto.bat snapshot-golden`
  - use this when you want to refresh the preserved golden snapshot intentionally
  - if the candidate summary prints `golden_eligible=yes`, the snapshot is copied into `output/offline_validation/golden/current/`
  - if the command prints blocker reasons, keep the existing golden snapshot and refresh again later from a better live queue window

- Determinism rule:
  - offline preview reads the immutable snapshot DB directly
  - offline send-test and run-once use a working copy of the selected snapshot DB so repeated validation runs do not mutate the base snapshot
  - golden snapshots stay stable until an operator explicitly runs `snapshot-golden` again after the first automatic golden capture

## Practical Workflows

- First truthful golden capture from a healthy live cycle:
  - `yoto.bat preview`
  - or `yoto.bat send-test`
  - or `yoto.bat run-once`
  - when the first live candidate becomes `golden_eligible=yes`, the runtime prints `golden-auto[...]` and preserves `output/offline_validation/golden/current/` automatically

- Daily operator desktop launch:
  - `yoto.bat ui`
  - or `yoto.bat operator-ui`
  - use this when you want the PySide6 Operator UI without triggering any preview or publish path automatically

- Intentional golden refresh after the first one already exists:
  - `yoto.bat preview`
  - `yoto.bat snapshot-golden`

- Repeatable offline proof from the preserved golden snapshot:
  - `yoto.bat preview-golden`
  - `yoto.bat send-test-golden`
  - `yoto.bat generate-captions-golden`
  - `yoto.bat generate-cards-golden --limit 26`

- Keep vs refresh guidance:
  - keep the current golden snapshot if the new candidate prints `planned_queue_empty` or `planned_assets_not_localized`
  - keep the current golden snapshot if a later live cycle is good but you have not intentionally decided to replace the existing proof target yet
  - refresh the golden snapshot only when the candidate has truthful planned rows and better or equal asset coverage than the current golden
  - treat `latest` as disposable and `golden` as the stable proof target

- Offline caption or card validation when live ingest is unavailable:
  - `yoto.bat preview-golden`
  - `yoto.bat generate-captions-golden`
  - `yoto.bat generate-cards-golden --limit 26`

- Offline publish-path and manifest validation from preserved state:
  - `yoto.bat send-test-golden`
  - successful offline golden send-test runs still exercise render -> outbox -> finalize -> manifest emission, but only against the golden snapshot working copy

- Video smoke:
  - `yoto.bat test-video`
  - `yoto.bat video-smoke`

## Compatibility Entry Points

These now delegate into the normalized layer:

- `preview_queue.bat`
- `send_test_post.bat`
- `run_bot.bat`

## Known Blockers

- `preview`, `send-test`, and `run-once` still depend on live network access to source APIs.
- `send-test`, `send-test-offline`, and `send-test-golden` still depend on valid Telegram credentials and channel settings in `.env` if a publishable item exists.
- The first automatic golden capture still requires a truthful live cycle with planned rows and localized planned assets.
- `snapshot-golden` cannot create a truthful golden snapshot when the current DB has no planned rows or when planned assets were not localized; it will preserve the previous golden snapshot instead of faking readiness.
- Offline commands require at least one existing snapshot, and golden commands require an existing preserved golden snapshot.
- If snapshot capture could not localize a queue asset, offline card rendering will fall back to the renderer's existing placeholder or fallback behavior for that item.
- `video-worker` and `video-smoke` require `ffmpeg` on `PATH`, or pass `--ffmpeg-bin <path>` through `yoto.bat`.
