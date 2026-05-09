# YOTO Project State Report

Generated: 2026-05-05  
Project root: `D:\Telegram_portable_bundle`  
Audit task: `YOTO-PROJECT-AUDIT-STATE-REPORT-01`

## Source Notes

- Primary source of truth: `AGENTS.md`.
- Secondary sources used in this audit: `HEAD_YOTO.md`, `docs/*`, `tools/*`, `tests/*`, `infrastructure/render/cards/*`, Telegram publish modules, recent git history, and current output artifacts.
- `HEAD_YOTO.md` exists, but parts of it appear stale against newer commits, tests, and artifacts dated 2026-03-18 through 2026-03-20. This report uses `HEAD_YOTO.md` only when it matches current code and artifacts.
- No production logic was changed during this audit.

## 1. Executive Summary

YOTO is a Telegram deal-posting pipeline for game offers. The current codebase ingests live deals, enriches them, plans queue output, resolves visuals, renders Telegram cards, generates captions, publishes to Telegram, and emits analytics plus video manifests.

Current maturity level: late pre-MVP / near-MVP, but not release-ready.

Practical status:

- Technically able to post: `YES`
- Ready for a first public push: `NO`
- Current bottleneck: official asset selection quality still allows weaker capsule/logo/placeholder visuals to beat stronger hero/gameplay/action assets.

High-confidence current state from `AGENTS.md` is still broadly true:

- card pipeline works
- renderer works
- `VisualDecisionEngine` exists
- official asset ingestion and cache exist
- ComfyUI fallback is confirmed

What changed since older docs: the image-quality and asset-selection work moved forward, but the main live render path is still not fully owned by `VisualDecisionEngine`.

## 2. Current Capabilities

| Capability | Status | Evidence | Key files | Commands | Tests / coverage |
| --- | --- | --- | --- | --- | --- |
| Collect and prepare game deal data | WORKING | Runtime wires `IngestSourceUseCase`, `EnrichOfferUseCase`, and `PlanQueueUseCase`; live ingest covers Steam specials, Epic freebies, Steam events, and calendar events. | `dealbot/main.py`, `application/use_cases/ingest_source.py`, `application/use_cases/enrich_offer.py`, `application/use_cases/plan_queue.py` | `yoto.bat preview`, `yoto.bat run-once`, `yoto.bat run` | `tests/test_plan_queue_arch.py`, `tests/test_lane_rebalance_arch.py` |
| Resolve official assets | WORKING | `resolve_official_asset_candidates()` builds official candidate pools and `ensure_selected_remote_asset_cached()` caches selected remote assets. | `infrastructure/render/cards/asset_sources/official_asset_source.py` | `D:\Telegram\.venv\Scripts\python.exe tools\ai_card_smoke.py current_env --game-eval --game-set expanded --download-assets` | `tests/test_official_asset_source.py`, `tests/test_ai_card_smoke.py` |
| Select image via VisualDecisionEngine | PARTIAL | `build_cover_decision()` and rescue/safety logic are implemented and tested, but the main live `CardRendererRouter` path still applies its own selector heuristics instead of fully delegating image choice to `VisualDecisionEngine`. | `infrastructure/render/cards/visual_decision_engine.py`, `infrastructure/render/cards/renderer_selector.py`, `infrastructure/render/cards/image_providers/resolver.py` | same expanded eval command above | `tests/test_visual_decision_engine.py`, `tests/test_ai_card_smoke.py` |
| Cache remote assets | WORKING | Remote official assets can be downloaded, verified, and bridged into local cache files. | `infrastructure/render/cards/asset_sources/asset_cache.py`, `infrastructure/render/cards/asset_sources/official_asset_source.py` | same expanded eval command above | `tests/test_asset_cache.py`, `tests/test_official_asset_source.py` |
| Render Telegram cards | WORKING | Production render stack exists and current artifacts show rendered output packs and published cards. | `infrastructure/render/cards/renderer_selector.py`, `infrastructure/render/cards/yoto_card_engine_v4.py` | `yoto.bat generate-cards`, `yoto.bat generate-cards-golden --limit 26` | `tests/test_renderer_selector_arch.py`, `tests/test_render_diagnostics_arch.py`, `tests/test_yoto_card_engine_v4.py` |
| Generate captions | WORKING | `TelegramCaptionBuilder` and `YotoVoiceEngine` build deal and roundup captions; live validation tooling exists. | `infrastructure/telegram/caption_builder.py`, `infrastructure/telegram/roundup_draft_builder.py`, `tools/generate_yoto_v1_live_caption_validation.py` | `yoto.bat generate-captions`, `yoto.bat generate-captions-golden` | `tests/test_caption_builder_arch.py`, `tests/test_live_caption_validation_tool.py` |
| Dry-run / post to Telegram | WORKING | Dry-run render path exists; real Telegram publish path exists; historical analytics prove successful send-test publish. | `application/use_cases/dry_run_render.py`, `application/use_cases/publish_next.py`, `infrastructure/telegram/publisher.py`, `dealbot/operator_cli.py`, `dealbot/main.py` | `yoto.bat preview`, `yoto.bat preview-golden`, `yoto.bat send-test`, `yoto.bat send-test-golden` | `tests/test_publish_idempotency_arch.py`, `tests/test_replay_outbox_arch.py`, `tests/test_publish_roundup_integration_arch.py`, `tests/test_video_manifest_v2_arch.py` |
| Store outputs / manifests | WORKING | Current repo contains analytics payloads, offline snapshots, render packs, and video manifests. | `infrastructure/analytics/artifact_store.py`, `application/use_cases/offline_validation_snapshot.py`, `application/use_cases/generate_video_manifests.py` | `yoto.bat latest-artifacts`, `yoto.bat snapshot-golden` | indirect coverage across publish / snapshot / video tests |
| Run AI fallback | WORKING | ComfyUI fallback is implemented, configured, and protected by safety gates; current audit found real code, tests, and artifacts for the fallback path. | `infrastructure/render/cards/image_providers/comfyui_provider.py`, `infrastructure/render/cards/image_providers/resolver.py`, `tools/ai_card_smoke.py` | expanded eval command above | `tests/test_ai_card_smoke.py`, `tests/test_visual_decision_engine.py` |
| Run video / shorts worker | WORKING | Video manifests are emitted and a standalone worker plus smoke path exist; latest output contains manifests and voice-ready packages. | `application/use_cases/generate_video_manifests.py`, `video_generator/*`, `dealbot/operator_cli.py` | `yoto.bat video-worker`, `yoto.bat video-smoke` | `video_generator/tests/test_scene_planner.py`, `video_generator/tests/test_pipeline.py` |

## 3. Image Pipeline State

### 3.1 Asset ingestion

Status: `WORKING`

- Official asset sourcing lives in `infrastructure/render/cards/asset_sources/official_asset_source.py`.
- Key entry points:
  - `resolve_official_asset_candidates(...)`
  - `ensure_selected_remote_asset_cached(...)`
- Current intent is consistent with `AGENTS.md`: official assets are primary and AI is fallback.

### 3.2 Steam / CDN candidate pool

Status: `WORKING`

- Official candidate pools include Steam/CDN-style remote assets, manifest-backed candidates, and candidate metadata that can be used by later ranking logic.
- Current recent git history supports this area:
  - `7e3d335 fix: cache selected remote official assets`
  - `9bc2a53 fix: improve official asset selection rules`
  - `26ed06e fix: improve visual decision asset quality rules`

### 3.3 Local fixtures

Status: `WORKING`

- Local smoke fixtures still exist for evaluation and fallback testing, but recent logic explicitly rejects local fixture assets from being treated as official proof-quality assets.
- Relevant commit:
  - `b6a86fd fix: reject local fixture as official asset`

### 3.4 Cache bridge

Status: `WORKING`

- Selected remote official assets can be downloaded into local cache via `download_remote_asset(...)`.
- `YotoImageResolver` can bridge a valid selected official asset into the render path when `cover_decision` data is present.
- Relevant files:
  - `infrastructure/render/cards/asset_sources/asset_cache.py`
  - `infrastructure/render/cards/image_providers/resolver.py`

### 3.5 VisualDecisionEngine

Status: `PARTIAL`

- `VisualDecisionEngine` is real and active in tooling/tests.
- Key functions:
  - `build_cover_decision(...)`
  - `build_visual_rescue_decision(...)`
  - `resolve_cover_decision_asset_bridge(...)`
- What is confirmed:
  - card-type strategy
  - visual intent classification
  - visual rescue logic
  - soft safety checks
  - AI gating rules
- What is not fully confirmed:
  - full ownership of the main live Telegram render path

### 3.6 Visual intent

Status: `WORKING`

- Recent commit history confirms explicit visual-intent work:
  - `3cdcfb4 feat: add visual intent debug classification`
  - `ccdbd9c fix: tune visual intent activity routing`
- `ComfyUIImageProvider.select_visual_intent(...)` exists and visual-intent signals are also used in `visual_decision_engine.py`.

### 3.7 Card type

Status: `WORKING`

- Card-type strategy classification exists.
- Relevant commit:
  - `bf6504c feat: add card type strategy classification`
- Canonical semantic families in `YotoCardEngineV4`:
  - `FREE_GAME`
  - `DISCOUNT`
  - `FESTIVAL`
  - `TOP_LIST`

### 3.8 Visual rescue

Status: `WORKING`

- Visual rescue decision layer exists and is reflected in both code and recent commits.
- Relevant commit:
  - `1c039b6 feat: add visual rescue debug classification`

### 3.9 Soft safety

Status: `WORKING`

- Soft safety exists and recent commits explicitly adjusted it:
  - `dd2c1f7 feat: soft safety unlocks gameplay/hero over capsule`
  - `9c0f180 fix: require safe visuals for official rescue`
- This is directly aligned with the current bottleneck in `AGENTS.md`.

### 3.10 AI fallback

Status: `WORKING`

- AI fallback is implemented through `ComfyUIImageProvider`.
- `YotoImageResolver` also includes conservative AI blocking when a usable official bridge exists or when a bridge is invalid and AI is disallowed.
- Relevant commits:
  - `6058f99 fix: block ai fallback on invalid official bridge`
  - `12301d1 fix: keep ai fallback conservative with usable official assets`

### 3.11 Current image-pipeline issue

Main issue: selection quality is improved but not fully solved.

- `AGENTS.md` still identifies the true bottleneck: capsule/logo/placeholder assets can sometimes beat stronger hero/gameplay/action visuals.
- Current live validation artifact `output/cards/live_validation_v45/validation_manifest.json` shows a very small run with:
  - `cards_rendered: 2`
  - `fallback_used: 2`
  - `gameplay_candidates_evaluated: 2`
  - `gameplay_frames_selected: 0`
- This does not prove the image pipeline is broken, but it does show that fallback-heavy output is still happening in current validation artifacts.

## 4. Renderer / Card Design State

### 4.1 Current renderer behavior

Status: `WORKING`

Current production render stack:

1. `application/use_cases/publish_next.py`
2. `infrastructure/render/cards/renderer_selector.py`
3. `CardRendererRouter`
4. `YotoCardRendererV42Adapter`
5. `YotoCardEngineV4`

Important current behavior:

- The live renderer still performs its own artwork download and hero/gameplay heuristic selection from `Offer.assets`.
- `YotoCardEngineV4` can accept `cover_decision`, but the normal `CardRendererRouter` path does not appear to fully populate or depend on `build_cover_decision(...)`.
- This means the renderer is functioning, but the image-decision architecture is still mixed.

### 4.2 Current template style

Current style is a designed overlay card, not a raw image card.

Evidence from `infrastructure/render/cards/yoto_card_engine_v4.py` and card-system docs shows the engine includes:

- lower-third panel logic
- title layout logic
- platform/source badge logic
- brand micro-label / wordmark logic
- overlay / readability gradient logic
- frame / shadow / border treatment
- title compaction and placeholder handling

This matches the current docs:

- `docs/YOTO_CARD_SYSTEM_AUDIT.md`
- `docs/YOTO_CARD_SYSTEM_BLUEPRINT.md`
- `docs/YOTO_PREMIUM_CARD_FINISH_BRIEF.md`

### 4.3 Known visual problems

These are known current problems or current-design risks, based on code plus the audit/finish docs.

- Overcomplicated UI: `docs/YOTO_CARD_SYSTEM_AUDIT.md` explicitly calls out UI-heavy frames and the need for cleaner lower-third coherence.
- Too many frames / lines / badges: `yoto_card_engine_v4.py` contains multiple badge, frame, overlay, and brand-lockup layers; the finish brief recommends calmer badge grammar and one shared lower-third rhythm.
- Scale / crop issues: `YotoCardEngineV4` contains custom crop-box and crop-interest logic, and `docs/YOTO_CARD_SYSTEM_AUDIT.md` calls out title clipping, title sizing, and hero-treatment consistency as active quality concerns.
- Text overload: current system carries title, fact row, urgency/state, platform/source signal, family badge, and brand lockup; the finish docs repeatedly recommend reducing equal-weight panels and keeping the title as the main stable read.

### 4.4 Recommended next renderer direction

This direction is recommended by the current card-system docs, not yet fully implemented:

- clean image-dominant format
- quiet bottom gradient / lower-third for readability
- title as the primary stable read
- discount or free-state signal as one compact high-value badge
- minimal YOTO brand presence

Best source for this direction:

- `docs/YOTO_PREMIUM_CARD_FINISH_BRIEF.md`
- `docs/YOTO_CARD_SYSTEM_BLUEPRINT.md`

The first follow-up task should therefore be a renderer cleanup pass, not a renderer ownership rewrite.

## 5. Telegram / Publish State

### 5.1 Does posting exist?

Status: `WORKING`

- `PublishNextUseCase` exists in `application/use_cases/publish_next.py`.
- `TelegramPublisher.publish_photo(...)` exists in `infrastructure/telegram/publisher.py`.
- Historical proof exists in current artifacts:
  - `output/analytics/20260320T085615Z_publish_outcome_steam_1426210.json`
  - `published: true`
  - `reason: published`
  - `message_id: 173`
  - `outbox_status: published`

### 5.2 Does dry-run exist?

Status: `WORKING`

- Dry-run render logic exists in `application/use_cases/dry_run_render.py`.
- Operational safety flags exist in `dealbot/settings.py`:
  - `DRY_RUN`
  - `FREEZE_PUBLISH`
  - `SALE_EVENT_MODE`
  - `DEGRADED_SOURCES`
- `preview` path exists through `dealbot/operator_cli.py` and `dealbot/main.py`.

### 5.3 How to run it

Core commands:

- Safe preview path:
  - `yoto.bat preview`
  - `yoto.bat preview-offline`
  - `yoto.bat preview-golden`
- Publish-path test:
  - `yoto.bat send-test`
  - `yoto.bat send-test-offline`
  - `yoto.bat send-test-golden`
- One-cycle loop:
  - `yoto.bat run-once`
  - `yoto.bat run-once-offline`
  - `yoto.bat run-once-golden`

### 5.4 Config / env needed

Confirmed mandatory env values in `dealbot/settings.py`:

- `BOT_TOKEN`
- `CHANNEL_USERNAME`

Also relevant render/runtime env:

- `CARD_RENDERER_MODE`
- `CARD_RENDERER_FALLBACK_TO_LEGACY`
- `IMAGE_PROVIDER_MODE`
- `IMAGE_PIPELINE_VERSION`
- `COMFYUI_ENABLED`
- `COMFYUI_URL`
- `COMFYUI_CHECKPOINT`

Audit note:

- `.env.example` includes the render and ComfyUI variables above.
- `.env.example` does not currently document `DRY_RUN` or `FREEZE_PUBLISH`, even though code supports them.

### 5.5 What is safe / unsafe

Safer commands:

- `yoto.bat preview-golden`
- `yoto.bat preview-offline`
- `yoto.bat snapshot-offline`
- `yoto.bat snapshot-golden`
- `yoto.bat generate-captions-golden`
- `yoto.bat generate-cards-golden --limit 26`

Unsafe or potentially publish-capable commands:

- `yoto.bat send-test`
- `yoto.bat send-test-offline`
- `yoto.bat send-test-golden`
- `yoto.bat run-once`
- `yoto.bat run`

Important code-level nuance:

- `dealbot/main.py` passes `force_publish=True` for `--send-test`.
- In `application/use_cases/publish_next.py`, dry-run / freeze-publish guards are checked only when `force_publish` is `False`.
- Therefore `send-test*` is not a harmless preview alias. If there is a publishable row and credentials are valid, it can publish.

### 5.6 What remains before real channel use

- restore green publish-path QA
- verify env safety defaults and operator procedure
- improve visual quality consistency before public posting
- decide whether current mixed image-selection ownership is acceptable for MVP or needs explicit follow-up

## 6. Caption State

### 6.1 Caption generation status

Status: `WORKING`

Key files:

- `infrastructure/telegram/caption_builder.py`
- `infrastructure/telegram/roundup_draft_builder.py`
- `tools/generate_yoto_v1_live_caption_validation.py`

Key classes:

- `YotoVoiceEngine`
- `TelegramCaptionBuilder`

### 6.2 Current format

Current caption builder produces structured Telegram copy with elements such as:

- opening / hook line
- summary / editorial body
- price or claim line
- urgency line where appropriate
- CTA
- hashtags

The builder also includes normalization and anti-repeat handling.

### 6.3 Language support

- Ukrainian: `WORKING`
  - Confirmed by current templates, helpers, and copy in `caption_builder.py` plus `dealbot/utils/ua.py`.
- Russian: `UNKNOWN / NEEDS VERIFICATION`
  - No separate Russian template family was verified in this audit.
- English: `UNKNOWN / NEEDS VERIFICATION`
  - No separate English template family was verified in this audit.

### 6.4 Known caption gaps

Current known gaps from docs and code:

- repetition management is improved but still an active concern
- festival voice can still read generic
- roundup tone still needs stronger editorial polish

Supporting doc:

- `docs/YOTO_CAPTION_SYSTEM_FREEZE_BRIEF.md`

## 7. AI / ComfyUI State

### 7.1 Is ComfyUI fallback implemented?

Status: `WORKING`

- Provider class: `ComfyUIImageProvider`
- Key file: `infrastructure/render/cards/image_providers/comfyui_provider.py`
- Resolver bridge: `infrastructure/render/cards/image_providers/resolver.py`

### 7.2 Provider chain

Current chain is:

1. official or selected asset path if available
2. bridge selected official asset into local cache when possible
3. AI fallback through `ComfyUIImageProvider` when allowed
4. placeholder / fallback path if AI is unavailable or rejected

### 7.3 Environment variables

Confirmed runtime variables:

- `COMFYUI_ENABLED`
- `COMFYUI_URL`
- `COMFYUI_CHECKPOINT`
- `IMAGE_PROVIDER_MODE`
- `IMAGE_PIPELINE_VERSION`

### 7.4 Current role

Current role: `FALLBACK ONLY`

This is consistent with `AGENTS.md`:

- official game assets are primary
- AI / ComfyUI is fallback, not primary

### 7.5 Known limitations

- Main live render path still has mixed ownership between renderer heuristics and cover-decision tooling.
- AI is intentionally conservative and can be blocked when official assets are good enough.
- Quality proof exists in tests/tooling, but not every older doc reflects the current fallback state.

## 8. Video / Shorts State

### 8.1 Does a video worker exist?

Status: `WORKING`

- Entry points:
  - `yoto.bat video-worker`
  - `yoto.bat video-loop`
  - `yoto.bat video-smoke`
- Video manifest generation exists in `application/use_cases/generate_video_manifests.py`.
- Standalone worker lives under `video_generator/*`.

### 8.2 Current maturity

Current maturity: `PARTIAL BUT REAL`

What is confirmed:

- manifest emission after publish exists
- smoke-test manifests exist
- voice-ready output packages exist under `output/video_voice_ready/`
- latest `output/video_manifests/` contains current manifest files

### 8.3 What is implemented

- manifest v2 emission
- scene planning tests
- pipeline tests
- standalone worker
- smoke path
- voice package builder through `dealbot/operator_cli.py`

### 8.4 What is out of MVP scope

Per `AGENTS.md`, video pipeline is a protected area and is outside the core MVP bottleneck. It should not be expanded as part of current MVP stabilization unless a separate task card explicitly chooses it.

### 8.5 Known gap

Status: `WORKING WITH COMMAND INDEX ISSUE`

- `yoto.bat test-video` currently points to `tests/test_pipeline.py`.
- Actual pipeline test file found in this audit is `video_generator/tests/test_pipeline.py`.
- `video_generator/tests/test_scene_planner.py` and `video_generator/tests/test_pipeline.py` do exist and pass when run directly.
- This is a command/index inconsistency, not proof that the video code itself is broken.

## 9. Test Status

Verification date: 2026-05-05

### 9.1 Required validation run

Command:

```powershell
D:\Telegram\.venv\Scripts\python.exe -m pytest -q tests/test_visual_decision_engine.py tests/test_ai_card_smoke.py
```

Result:

- `93 passed in 20.81s`

### 9.2 Additional relevant validation runs

```powershell
D:\Telegram\.venv\Scripts\python.exe -m pytest -q tests/test_asset_cache.py tests/test_official_asset_source.py
```

- `8 passed in 0.18s`

```powershell
D:\Telegram\.venv\Scripts\python.exe -m pytest -q tests/test_caption_builder_arch.py tests/test_live_caption_validation_tool.py
```

- `36 passed in 0.95s`

```powershell
D:\Telegram\.venv\Scripts\python.exe -m pytest -q video_generator/tests/test_scene_planner.py video_generator/tests/test_pipeline.py
```

- `16 passed in 7.37s`

```powershell
D:\Telegram\.venv\Scripts\python.exe -m pytest -q tests/test_publish_idempotency_arch.py tests/test_replay_outbox_arch.py tests/test_video_manifest_v2_arch.py
```

- `6 failed, 7 passed in 2.54s`
- Failure cause observed in this audit:
  - `TypeError: RenderingConfig.__init__() missing 2 required positional arguments: 'image_provider_mode' and 'image_pipeline_version'`
- Failing area is test support / contract setup, not direct proof of runtime publish failure, but it blocks a clean QA sign-off.

### 9.3 Test files explicitly requested in task

- `tests/test_visual_decision_engine.py`: `PASS` in the required combined run above.
- `tests/test_ai_card_smoke.py`: `PASS` in the required combined run above.
- Any other relevant tests:
  - asset cache / official asset source: `PASS`
  - caption validation: `PASS`
  - video scene planning / pipeline: `PASS` when run directly
  - publish / video-manifest contract set: `PARTIAL`, currently red

### 9.4 Recommended validation commands

```powershell
D:\Telegram\.venv\Scripts\python.exe -m pytest -q tests/test_visual_decision_engine.py tests/test_ai_card_smoke.py
D:\Telegram\.venv\Scripts\python.exe -m pytest -q tests/test_asset_cache.py tests/test_official_asset_source.py
D:\Telegram\.venv\Scripts\python.exe -m pytest -q tests/test_caption_builder_arch.py tests/test_live_caption_validation_tool.py
D:\Telegram\.venv\Scripts\python.exe -m pytest -q video_generator/tests/test_scene_planner.py video_generator/tests/test_pipeline.py
D:\Telegram\.venv\Scripts\python.exe -m pytest -q tests/test_publish_idempotency_arch.py tests/test_replay_outbox_arch.py tests/test_publish_roundup_integration_arch.py tests/test_video_manifest_v2_arch.py
```

## 10. Important Recent Commits

Source command used:

```powershell
git log --oneline -n 20
```

Most relevant recent commits in the current local history:

| Commit | Summary | Why it matters |
| --- | --- | --- |
| `dd2c1f7` | `feat: soft safety unlocks gameplay/hero over capsule` | Confirms direct work on the current bottleneck: choosing stronger visuals over weak capsules. |
| `7e3d335` | `fix: cache selected remote official assets` | Confirms the remote asset cache bridge and selected-official download path. |
| `9c0f180` | `fix: require safe visuals for official rescue` | Confirms rescue logic is guarded by safety rules. |
| `55d076d` | `chore: add expanded single-game eval preset` | Confirms dedicated image-eval tooling exists for deeper visual checks. |
| `1c039b6` | `feat: add visual rescue debug classification` | Confirms visual rescue classification and observability. |
| `6058f99` | `fix: block ai fallback on invalid official bridge` | Confirms fallback safety when official bridge data is bad. |
| `ccdbd9c` | `fix: tune visual intent activity routing` | Confirms visual-intent routing work. |
| `3cdcfb4` | `feat: add visual intent debug classification` | Confirms explicit visual-intent instrumentation. |
| `b6a86fd` | `fix: reject local fixture as official asset` | Confirms local fixtures are no longer treated as official proof assets. |
| `bf6504c` | `feat: add card type strategy classification` | Confirms card-type strategy layer in the image pipeline. |
| `12301d1` | `fix: keep ai fallback conservative with usable official assets` | Confirms official-first fallback policy in code. |
| `26ed06e` | `fix: improve visual decision asset quality rules` | Confirms direct tuning of asset-quality scoring. |
| `9bc2a53` | `fix: improve official asset selection rules` | Confirms continued selection tuning. |
| `a4e6c76` | `feat: add yoto image pipeline runtime proof` | Confirms recent proof-oriented work for image pipeline runtime behavior. |
| `ea59baa` | `test: update ai card smoke asset contract` | Confirms tests were updated alongside asset-contract changes. |

Audit note on the requested "asset ingestion fix":

- No last-20 commit used that exact phrase.
- Closest relevant commits are:
  - `9bc2a53`
  - `26ed06e`
  - `7e3d335`

## 11. Current MVP Readiness Score

These are conservative auditor estimates, not system-generated metrics.

| Area | Score | Notes |
| --- | --- | --- |
| Core engine | 82% | Ingest, enrich, queue, render, publish, analytics, and snapshots all exist. |
| Image sourcing | 76% | Official sourcing, cache, and candidate pool exist; this area is real and actively improved. |
| Image selection | 61% | `VisualDecisionEngine` is real, but live ownership is still partial and quality bottleneck remains. |
| Renderer / design | 55% | Renderer works, but visual polish and information hierarchy are not yet public-ready. |
| Caption | 78% | Caption pipeline is working and tested, but language scope and tone polish are limited. |
| Telegram posting | 72% | Real publish proof exists, but operator safety and green publish QA are not yet fully comfortable. |
| QA / testing | 63% | Many important tests pass, but publish/video-manifest contract tests are currently red. |
| Product readiness | 58% | Near-MVP for internal proofing, not ready for first public push. |

## 12. Release Blockers

### HARD BLOCKERS

- For literal internal posting, no code-level hard blocker was confirmed in this audit. Real publish proof exists from 2026-03-20.
- For first public release, the QA gate is currently blocked by failing publish / video-manifest tests:
  - `tests/test_publish_idempotency_arch.py`
  - `tests/test_video_manifest_v2_arch.py`
  - failure cause observed on 2026-05-05: `RenderingConfig` test setup mismatch
- `UNKNOWN / NEEDS VERIFICATION`: live Telegram credentials and channel settings in the current portable-bundle environment were not revalidated during this audit.

### SOFT BLOCKERS

- Main live renderer path still owns part of image selection instead of fully consuming `VisualDecisionEngine`.
- `.env.example` does not document `DRY_RUN` and `FREEZE_PUBLISH`.
- `yoto.bat test-video` points at a missing root-level `tests/test_pipeline.py` instead of `video_generator/tests/test_pipeline.py`.
- `HEAD_YOTO.md` is not fully synchronized with newer image/AI fallback state.

### QUALITY BLOCKERS

- official asset ranking still not consistently strong enough for public-quality cards
- current renderer carries too much UI weight for the desired image-dominant card
- title / crop / badge density still creates visual risk
- current live validation artifact is small and fallback-heavy

## 13. Next 5 Tasks

These are recommended next tasks only. Any task that touches protected zones still needs explicit approval through the normal task-card workflow.

| Task ID | Objective | Files likely touched | Validation | Risk |
| --- | --- | --- | --- | --- |
| `YOTO-MVP-CLEAN-CARD-RENDERER-01` | Simplify the current card surface into a cleaner image-dominant lower-third format without changing renderer ownership. | `infrastructure/render/cards/yoto_card_engine_v4.py`, `tests/test_yoto_card_engine_v4.py`, `tools/generate_yoto_v451_live_validation_pack.py`, `docs/YOTO_PREMIUM_CARD_FINISH_BRIEF.md` | `yoto.bat generate-cards-golden --limit 26`, `yoto.bat test-cards` | Medium |
| `YOTO-MVP-OFFICIAL-ASSET-SELECTION-TUNING-02` | Keep improving official asset ranking so hero/gameplay/action beats capsule/logo/placeholder more reliably. | `infrastructure/render/cards/visual_decision_engine.py`, `infrastructure/render/cards/asset_sources/official_asset_source.py`, `tests/test_visual_decision_engine.py`, `tests/test_ai_card_smoke.py` | required VDE/AI smoke run plus expanded visual eval | Medium |
| `YOTO-MVP-PUBLISH-QA-RESTORE-01` | Restore green publish/video-manifest contract tests by updating test support to the current rendering config contract. | `tests/support.py`, `tests/test_publish_idempotency_arch.py`, `tests/test_video_manifest_v2_arch.py`, possibly `tests/test_publish_roundup_integration_arch.py` | `yoto.bat test-publish` or direct pytest equivalent | Low |
| `YOTO-MVP-OPERATOR-SAFETY-CONFIG-01` | Make operator-safe publish procedure explicit, including `DRY_RUN`, `FREEZE_PUBLISH`, and send-test caveats. | `.env.example`, `docs/YOTO_COMMAND_INDEX.md`, `docs/YOTO_OPERATOR_WORKFLOW.md` | manual review plus `yoto.bat doctor` / `yoto.bat latest-artifacts` | Low |
| `YOTO-MVP-LIVE-VDE-INTEGRATION-DECISION-01` | Decide whether MVP requires wiring live card rendering to fully consume `cover_decision`, or whether current mixed ownership is acceptable for launch. | `infrastructure/render/cards/renderer_selector.py`, `infrastructure/render/cards/image_providers/resolver.py`, `infrastructure/render/cards/visual_decision_engine.py`, architecture docs | architecture review plus card regression suite | High |

## 14. Do Not Touch List

Protected areas repeated from `AGENTS.md` plus audit observations:

- renderer selector
  - `infrastructure/render/cards/renderer_selector.py`
- template system
  - `infrastructure/render/cards/template_system.py`
- publish / outbox path
  - `application/use_cases/publish_next.py`
  - `application/use_cases/replay_outbox.py`
  - Telegram publish modules and outbox-related flow
- caption pipeline
  - `infrastructure/telegram/caption_builder.py`
  - roundup caption builder modules
- video pipeline
  - `video_generator/*`
  - `application/use_cases/generate_video_manifests.py`
- resolver contract
  - `infrastructure/render/cards/image_providers/resolver.py`

Danger zones during manual operation:

- `yoto.bat send-test*`
- `yoto.bat run-once`
- `yoto.bat run`
- any command using live network plus valid Telegram credentials

## 15. Command Cheatsheet

### Run the key image-pipeline tests

```powershell
D:\Telegram\.venv\Scripts\python.exe -m pytest -q tests/test_visual_decision_engine.py tests/test_ai_card_smoke.py
```

### Run caption tests

```powershell
yoto.bat test-caption
```

### Run card renderer tests

```powershell
yoto.bat test-cards
```

### Run publish-path tests

```powershell
D:\Telegram\.venv\Scripts\python.exe -m pytest -q tests/test_publish_idempotency_arch.py tests/test_replay_outbox_arch.py tests/test_publish_roundup_integration_arch.py tests/test_video_manifest_v2_arch.py
```

### Run expanded visual eval

```powershell
D:\Telegram\.venv\Scripts\python.exe tools\ai_card_smoke.py current_env --game-eval --game-set expanded --download-assets
```

### Open the latest stable offline proof folder

```powershell
ii output\offline_validation\golden\current
```

### Inspect recent analytics artifacts

```powershell
Get-ChildItem output\analytics | Sort-Object LastWriteTime -Descending | Select-Object -First 10 Name,LastWriteTime
```

### Safe preview path

```powershell
yoto.bat preview-golden
```

### Live preview path

```powershell
yoto.bat preview
```

### Publish-path replay from preserved offline state

```powershell
yoto.bat send-test-golden
```

Warning: this is still a publish-capable path when credentials and a publishable item exist.

### Inspect git state

```powershell
git status --short
git log --oneline -n 20
```

### Safe docs-only commit flow

```powershell
git add docs\YOTO_PROJECT_STATE_REPORT.md
git commit -m "docs: add YOTO project state report"
```

## 16. Final Verdict

Can YOTO post now?

- Yes, technically. The codebase contains a real publish path, and current analytics artifacts include a successful Telegram send-test publish from 2026-03-20.

Should it post now?

- Not to a public channel yet.

What must be fixed before the first public push?

1. Visual quality must become more reliable, especially official asset selection.
2. The card surface should be cleaned into a more image-dominant format.
3. Publish-path regression tests need to return to green.
4. Operator-safe env and command usage should be tightened and documented clearly.

Bottom line:

- Internal proofing / controlled send-test use: `YES`
- First public push: `NO`
