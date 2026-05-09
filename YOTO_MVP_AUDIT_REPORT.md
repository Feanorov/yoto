# YOTO MVP Audit Report

Audit date: 2026-05-09

Scope: internal audit of the current YOTO project as it exists in this repository and runtime bundle.

Audit basis:

- Code inspection of the current pipeline, renderer stack, Telegram publish flow, operator CLI, database layer, and validation tools.
- Real test execution against the current repository.
- Review of current output artifacts in `output/analytics`, `output/cards`, `output/offline_validation`, and `output/video_manifests`.
- Direct inspection of the latest visual validation contact sheet.
- Runtime health checks through the current operator surface and SQLite state.

This report is intentionally blunt. It is meant to stop fragmented work and answer one question: is YOTO actually close to public MVP release as a product?

## 1. Project Overview

YOTO is a Telegram content pipeline that turns game offers into publishable posts. The current system ingests store data, enriches offers, ranks and queues them, resolves a visual asset, renders a card, generates a caption, stages the post in an outbox, publishes to Telegram, and stores analytics and supporting artifacts.

Current architecture, in practical terms:

1. Ingest offers and event context.
2. Enrich and score offers.
3. Plan a queue with lane and priority rules.
4. Resolve imagery through official assets first, with AI and ComfyUI as fallback.
5. Render the final card.
6. Build the caption.
7. Stage and publish through the Telegram outbox flow.
8. Persist artifacts, truth reports, snapshots, and optional video manifests.

Current MVP goal from the project instructions:

- stable Telegram cards
- good resolved visual
- generated caption
- dry-run / auto-post flow

Current bottleneck:

- official asset selection quality
- capsule / logo / placeholder / weak assets can still beat stronger hero / gameplay / action assets

Current maturity verdict:

YOTO is no longer a prototype in the narrow technical sense. It has a real publish pipeline, real Telegram proof, a real queue, real artifacts, real snapshots, and a real validation surface. However, it is also not release-ready today. The core blocker is not missing infrastructure. The core blocker is that the visual output is still inconsistent enough to undermine public channel quality, and the regression net is not currently trustworthy enough to support confident release mode.

## 2. Current System Map

### Asset Ingestion

- Purpose: pull raw offers and event context into the system.
- Current state: working. The latest truth report shows live ingestion from Steam and Epic, with 2000 Steam offers and 2 Epic offers in the sampled run.
- Stability: medium-high.
- Known problems: source quality and source mix are uneven; ingest breadth is not the main bottleneck, but downstream selection quality is highly sensitive to what ingest provides.
- Production readiness: largely ready for MVP use.
- Dependencies: store clients, settings, ingest use case, repository layer.
- Current risks: source degradation or poor upstream metadata can still poison later ranking and visual selection.

### Asset Sourcing

- Purpose: collect candidate official visuals and choose what should be considered before rendering.
- Current state: implemented and active. Official asset sourcing builds candidate pools, applies cover decision logic, and downloads a limited top-ranked set of remote assets.
- Stability: medium.
- Known problems: this is the current product bottleneck. Real smoke artifacts show capsule-like or otherwise weak assets still winning in some cases. Placeholder outcomes still happen. There is also at least one decision bridge mismatch where official selection says "do not use AI" but the actual resolver falls through because the selected asset path is invalid or non-local.
- Production readiness: not ready.
- Dependencies: store metadata, official manifest logic, VDE scoring, asset cache, resolver.
- Current risks: low-quality asset selection directly causes low-quality public cards.

### Cache Layer

- Purpose: download, validate, and reuse remote assets safely.
- Current state: present and functional. The cache validates content type, readability, and size limits and is used by official asset sourcing.
- Stability: medium-high.
- Known problems: artifact paths and manifests still leak absolute environment-specific paths. That weakens portability and makes some artifact packs less self-contained than they should be.
- Production readiness: ready for controlled MVP use, not fully polished operationally.
- Dependencies: filesystem, network availability, cache configuration.
- Current risks: portability issues and stale path references can create confusing failures outside the original environment.

### VisualDecisionEngine

- Purpose: score and choose the strongest visual route.
- Current state: sophisticated and heavily instrumented. The engine already has readability and focus thresholds, source preferences, and AI gating behavior.
- Stability: medium.
- Known problems: the engine is clearly doing real work, but it has not solved the quality problem yet. Real validation outputs still show placeholder-heavy outcomes, and real smoke batches still include capsule wins. One current renderer-selector test also disagrees with expected placeholder behavior.
- Production readiness: not ready for public-facing visual quality.
- Dependencies: asset sourcing, scoring heuristics, resolver integration, cache health.
- Current risks: the product can look technically stable while still looking visually weak in the feed.

### Renderer

- Purpose: composite the already resolved image, typography, pricing, and layout into a Telegram card.
- Current state: working and consistent. The current stack routes to `yoto_v4`, and the live validation manifest shows 10 of 10 cards rendered through `yoto_v4` with no renderer fallback.
- Stability: high as a compositor.
- Known problems: when the upstream selected asset is weak or placeholder-like, the renderer faithfully turns that weakness into a dark, low-impact final card. The renderer is not the main failure point, but it cannot save bad image selection.
- Production readiness: the renderer itself is close to MVP-ready; the end visual result is not.
- Dependencies: resolved image asset, typography assets, render configuration.
- Current risks: false confidence. A stable renderer can mask an unstable visual-selection system.

### Caption Generation

- Purpose: generate the Telegram caption and CTA text.
- Current state: working. Current operator truth artifacts contain clean, usable Ukrainian captions with structured formatting.
- Stability: medium-high.
- Known problems: some older review artifacts are mojibake-corrupted, which means not every artifact/export surface is trustworthy even if the live caption path is working.
- Production readiness: close to ready.
- Dependencies: offer metadata, caption builder, formatting rules.
- Current risks: inconsistent encoding in secondary review artifacts can create confusion during QA and operator review.

### Publish Pipeline

- Purpose: choose the next queued item, stage it, send it to Telegram, and finalize publication safely.
- Current state: real and mature. The current pipeline includes outbox staging, publication state tracking, quiet-hour logic, lane limits, roundup injection, backoff, and final publication logging.
- Stability: high relative to the rest of the system.
- Known problems: the publish pipeline is only as good as the queued content it receives. It is operationally stronger than the visual pipeline feeding it.
- Production readiness: close to ready for MVP.
- Dependencies: queue repository, outbox repository, caption builder, renderer, Telegram publisher.
- Current risks: bad visuals can still be published cleanly and consistently.

### Dry-Run Flow

- Purpose: generate a complete post artifact without sending it.
- Current state: working. Dry-run render builds card, caption, hashes, diagnostics, and artifact persistence.
- Stability: high.
- Known problems: dry-run quality currently inherits the same visual-selection weakness as live publish.
- Production readiness: ready.
- Dependencies: full upstream pipeline except actual Telegram send.
- Current risks: a passing dry-run is not enough proof of public-ready visuals.

### Auto-Post Flow

- Purpose: run the system continuously and publish on a schedule.
- Current state: implemented. The runtime loop exists and uses interval-based scheduling between configured minimum and maximum minutes.
- Stability: medium.
- Known problems: the current portable bundle is not self-sufficient. `yoto.bat` falls back to plain `python`, but no local `.venv` exists in this bundle and `python` is not available on PATH here. In practice, the system currently depends on an external interpreter to operate.
- Production readiness: not ready for portable hands-off deployment.
- Dependencies: launcher, Python environment, settings, runtime loop, Telegram credentials.
- Current risks: operator automation can appear healthy in the original environment while failing in the portable bundle.

### AI Fallback

- Purpose: provide a secondary visual route when official assets are inadequate.
- Current state: implemented and intentionally secondary, which matches the MVP instructions.
- Stability: medium.
- Known problems: fallback behavior is not the main issue, but it is still involved in awkward edge cases. In one smoke case, the system selected AI at runtime because the official decision asset was invalid or non-local, despite the decision logic preferring official.
- Production readiness: partially ready as a fallback only.
- Dependencies: resolver logic, prompt generation, model/service availability.
- Current risks: if official-first logic remains unstable, fallback behavior becomes more important than intended and can hide upstream issues.

### ComfyUI Integration

- Purpose: provide AI generation fallback through ComfyUI.
- Current state: confirmed and working in smoke artifacts. In the inspected batch, all 3 AI-attempted runs succeeded and passed the quality check path.
- Stability: medium.
- Known problems: it is still fallback infrastructure, not the main release path. It also carries operational dependency weight outside the core official-asset MVP.
- Production readiness: usable as fallback, not something the MVP should depend on heavily.
- Dependencies: ComfyUI service, prompt/reference flow, resolver integration.
- Current risks: external service dependency adds complexity that MVP does not need as a primary escape hatch.

### Smoke Tools

- Purpose: prove current behavior through validation packs, smoke batches, doctor checks, and artifact inspection.
- Current state: present and useful. There are live validation packs, AI smoke batch summaries, offline snapshots, and operator doctor outputs.
- Stability: medium.
- Known problems: tool quality is uneven. `latest-artifacts` can report an image from `official_asset_cache` as the "latest card", which is operationally misleading. Root test collection is also polluted by duplicate untracked task-bundle tests in this workspace.
- Production readiness: partially ready.
- Dependencies: artifact writers, filesystem, operator CLI, pytest.
- Current risks: operator tooling can misreport the most relevant artifact and erode confidence during QA.

### Testing Infrastructure

- Purpose: protect the product against regressions.
- Current state: broad but not currently healthy. The suite covers renderer, visual decisioning, publish logic, snapshots, planning, video manifests, and architecture-level behaviors. However, it is not green.
- Stability: low-medium.
- Known problems: `pytest -q tests` currently produces 236 passed and 72 failed. The largest cluster is 62 failures from outdated `RenderingConfig` construction in test support. Another 9 failures come from API drift around `GenerateVideoManifestsUseCase`, which no longer exposes the expected `execute()` surface. There is also 1 real visual assertion mismatch. In addition, bare `pytest -q` at repo root fails collection because untracked task-bundle directories contain duplicate test module names.
- Production readiness: not ready.
- Dependencies: test fixtures, support utilities, current config surface, isolated workspace hygiene.
- Current risks: the team does not currently have a trustworthy red/green signal for release gating.

### Debug and Logging

- Purpose: show what the system did and why.
- Current state: strong. Truth reports, publish outcomes, validation manifests, snapshots, and video manifests leave a substantial artifact trail.
- Stability: high.
- Known problems: some older review outputs have encoding corruption, and many artifacts still reference absolute `D:\Telegram\...` paths from the original environment.
- Production readiness: good for internal debugging, not fully clean operationally.
- Dependencies: artifact writers, filesystem, analytics serializers.
- Current risks: review packs can be harder to trust than raw JSON artifacts.

### Telegram Integration

- Purpose: send the finished card and caption to Telegram.
- Current state: proven. The doctor output confirms verified Telegram proof with a published `It Takes Two` message and `message_id: 173`.
- Stability: medium-high.
- Known problems: the send wrapper itself is simple and fine, but end-to-end reliability still depends on the launcher environment, credentials, and upstream content quality.
- Production readiness: ready for controlled MVP operations.
- Dependencies: bot token, chat/channel configuration, network, publisher wrapper.
- Current risks: successful sending does not equal successful content quality.

### Batch Generation

- Purpose: generate batches for validation, smoke review, and artifact comparison.
- Current state: active. There are AI smoke batches, live validation batches, and video manifest batches in current outputs.
- Stability: medium.
- Known problems: the latest live validation pack is a product warning sign, not a success story. All 10 sampled cards used intentional fallback placeholder hero imagery.
- Production readiness: partially ready as an internal QA tool.
- Dependencies: renderer, resolver, artifact pipeline.
- Current risks: batch tooling currently proves that a stable bad outcome can be reproduced at scale.

## 3. Visual Pipeline Status

This is the most important product section because YOTO is a visual Telegram product, not just a data pipeline.

### Renderer Quality

The compositor itself is not the immediate problem. The current `yoto_v4` output is consistent, the text hierarchy is readable, discount treatment is legible, and the cards look structurally coherent. The live validation manifest showed zero renderer fallback and ten successful `yoto_v4` renders.

### Asset Quality

This is the release blocker.

The latest inspected live validation pack in `output/cards/live_validation_v45` produced the following result:

- 10 cards rendered
- 10 fallback hero outcomes
- 0 gameplay frames selected out of 48 evaluated candidates
- hero source type was `placeholder` for all 10 cards
- hero selection reason was `intentional_fallback` for all 10 cards

The direct contact sheet inspection matches the data. The cards are readable, but the hero area is visually weak, dark, and in some cases close to empty. They do not look like strong public Telegram promo cards.

### Mobile Readability

Text readability is decent. Titles and discount blocks remain readable at a glance. This is a strength.

### Feed Visibility

Feed visibility is not good enough yet. Readable text is not enough if the artwork does not stop the scroll. The current placeholder-heavy hero outcomes reduce emotional pull and make multiple cards feel flat.

### Current Visual Strengths

- consistent layout
- readable title and pricing hierarchy
- stable renderer routing
- detailed visual diagnostics
- official-first strategy is implemented
- AI fallback exists when needed

### Current Visual Weaknesses

- placeholder fallback is still too common in important validations
- some real smoke cases still choose capsule-like art
- gameplay strip usage is effectively absent in the inspected live validation run
- public card energy is too low when hero resolution fails
- official decision and actual runtime resolution can diverge in edge cases

### Placeholder and Fallback Behavior

Fallback behavior is technically functioning, but the current fallback outcomes are not public-ready. The system is successfully avoiding total failure, but it is often failing gracefully into bland cards instead of strong cards. That is still a product failure for a visual channel.

### Remaining Bad Cases

Real examples from current artifacts:

- `Civilization VI` and `Dave the Diver` still resolve to capsule-like official assets in the inspected AI smoke batch.
- `Ultimate Strategy Collection` shows a resolver mismatch where official selection won at decision time, but runtime fell through because the asset path was invalid or non-local.
- The latest live validation pack devolved into placeholder hero output across the entire 10-card sample.

### Consistency Across Games

Layout consistency is strong.

Visual quality consistency is not.

This is an important distinction. YOTO has solved the card format more than it has solved the image-selection quality.

### Visual MVP Verdict

Visual MVP is **not ready for public Telegram posting**.

The renderer is stable enough. The resolved visual is not. Until official asset selection stops collapsing into placeholders, dark weak heroes, and occasional capsule wins, YOTO is not ready to represent itself publicly as a polished Telegram product.

## 4. Automation Status

### How Autonomous The Pipeline Really Is

The pipeline is meaningfully automated:

- ingest is automated
- queue planning is automated
- dry-run generation is automated
- outbox staging and Telegram send are automated
- scheduled runtime loop exists
- analytics and snapshot outputs are automated

This is real automation, not a mock workflow.

### Remaining Manual Steps

- final human judgment on visual quality still appears necessary
- environment setup is not portable enough to trust blindly
- QA interpretation of artifacts still requires experience
- public-launch gating still requires manual confidence checks because the regression net is not green

### Fragile Areas

- bundle launcher is broken in the current portable environment
- visual selection can fail into placeholder quality
- absolute path leakage makes artifact portability messy
- some review artifacts are encoding-corrupted
- current batch tooling can expose failure, but not automatically prevent release mistakes

### Retry Behavior

There is real retry/backoff behavior. The publish pipeline has failure handling and backoff logic rather than a single-shot fire-and-forget send. This is a strength.

### Duplicate Protection

Duplicate protection appears materially present through the outbox and publication tracking model. This is one of the healthier parts of the product.

### Scheduling

Scheduling exists through the runtime loop and interval configuration. This is enough for MVP-level automation, assuming the environment is fixed.

### Monitoring and Logging

Monitoring is artifact-based rather than dashboard-based, but it is real:

- operator truth reports
- publish outcome logs
- offline validation snapshots
- doctor checks
- batch summaries

This is adequate for an MVP operator workflow.

### Failure Recovery

Recovery is partially there:

- backoff exists
- snapshots exist
- state persists in SQLite
- outbox tracking exists

But recovery is still operationally fragile because the bundle is not self-contained and artifact paths are environment-specific.

### Operational Risks

- public runtime currently depends on environment assumptions outside this bundle
- current launch surface is better for an experienced operator than for a clean deployment
- current monitoring can tell you what happened after the fact, but it does not yet create strong release confidence by itself

### Automation Verdict

YOTO is semi-autonomous in a real sense, but not truly release-ready autonomous yet. It can run itself. It cannot yet be trusted to run itself publicly without careful operator oversight.

## 5. Content Quality Status

### Caption Quality

Current live caption output is usable. The inspected operator truth artifact contains coherent Ukrainian-language caption text with a clear structure and readable flow. This is ahead of the visual system in terms of MVP readiness.

### Formatting Consistency

Formatting in the live truth and publish artifacts looks consistent. The system is not producing obviously random or malformed caption structure in the inspected current outputs.

### CTA Quality

CTA quality is functional. It supports the post purpose. It does not appear to be the current bottleneck.

### Localization

Localization is clearly oriented around Ukrainian output and appears intentional rather than accidental. For the inspected current live artifacts, this is a strength.

### Readability

Caption readability is good in the inspected live artifacts. The content is more mature than the visual selection layer.

### Metadata Quality

Metadata quality appears acceptable in the sampled current outputs, but it depends heavily on upstream store data. It is good enough for MVP if the source data is good.

### Discount Formatting

Discount formatting is visible and effective in both caption and card contexts. This is a strength.

### Title Quality

Title quality appears source-driven and acceptable in current samples. No major title formatting blocker was found.

### Content Risks

- some older review/export artifacts are encoding-corrupted and should not be treated as authoritative
- content quality still depends on upstream source cleanliness
- the strongest caption in the world cannot compensate for a visually weak card in the Telegram feed

### Content Verdict

Content quality is near MVP-ready. It is not perfect, but it is not what is blocking launch.

## 6. Test Infrastructure

### Existing Tests

The repository has a meaningful architecture and behavior test suite covering at least the following areas:

- visual decision engine
- official asset source
- renderer and renderer selector
- publish priority and roundup integration
- ingestion architecture
- queue planning
- launch reliability
- publish reliability
- offline validation snapshot flow
- operator visibility
- AI card smoke behavior
- video manifest behavior

### Current Coverage

There is broad behavioral coverage, but no trustworthy "all green" release signal right now.

Current observed results:

- `pytest -q tests` -> 236 passed, 72 failed
- total cases in parsed JUnit output -> 308
- largest failure cluster -> 62 failures from `RenderingConfig` constructor drift in test support
- second large cluster -> 9 failures from `GenerateVideoManifestsUseCase` surface drift
- remaining visual mismatch -> 1 failing renderer-selector assertion

Separate targeted visual subset:

- 121 passed
- 1 failed

This is useful because it shows the visual stack is not universally broken, but it is also not fully stable at the edges.

### Smoke Tooling

Smoke tooling is better than average for an MVP. The project has:

- AI card smoke batches
- live validation card batches
- offline validation snapshots
- operator doctor checks
- latest-artifacts summary

That said, the tools expose product truth more effectively than they enforce release quality.

### Dangerous Blind Spots

- no current green end-to-end regression gate
- bare root `pytest` collection is polluted by duplicate untracked task-bundle tests
- visual acceptability still requires human judgment beyond automated pass/fail
- portable-bundle launch health is not being protected by a simple always-on test
- encoding consistency across review artifacts is not reliably covered

### Areas Not Covered Well Enough

- public-feed aesthetic quality
- portability of artifact packs across environments
- launcher self-sufficiency inside this bundle
- edge-case bridge consistency between official decisioning and runtime image resolution

### Reliability Confidence

Current confidence level by domain:

- publish mechanics: medium-high
- renderer compositing: high
- visual selection quality: low-medium
- operator portability: low-medium
- overall release confidence: medium at best

### Test Infrastructure Verdict

The testing story is broad but not healthy enough for release mode. YOTO has many tests, but not currently the kind of green test surface that lets the team move fast with confidence.

## 7. Current Known Blockers

### Hard Blockers

1. Visual asset selection is not stable enough for public launch.
   Evidence: the latest live validation pack rendered 10 of 10 cards with placeholder hero imagery, and real smoke batches still allow capsule-like official assets to win.

2. The regression net is not green.
   Evidence: `pytest -q tests` currently fails with 72 failures, mostly from test-support drift and API drift, which means release gating is unreliable right now.

3. The current portable bundle is not operationally self-sufficient.
   Evidence: `yoto.bat` fails in this bundle because there is no local `.venv` and no `python` on PATH, while many current artifacts still reference absolute paths from `D:\Telegram\...`.

### Soft Blockers

1. Review/export encoding is inconsistent.
   Live operator truth artifacts look clean, but some older review artifacts are mojibake-corrupted.

2. Snapshot and roundup support still show asset-readiness warnings.
   Current offline validation manifests still contain `roundup_card_assets_missing` warnings.

3. Some operator tooling is misleading.
   `latest-artifacts` can surface a cached asset JPG as the latest card instead of the latest rendered Telegram card.

4. Resolver edge cases still exist.
   At least one current smoke case shows official decisioning and actual runtime resolution diverging because the chosen asset path is invalid or non-local.

### Cosmetic Issues

1. Gameplay strip usage is currently low, but this should not block MVP if hero selection becomes strong enough.
2. Card aesthetic polish beyond the current template should not delay release.
3. Future theme variety and richer visual personality should not delay release.

## 8. MVP Readiness Score

These scores are intentionally conservative and based on current inspected evidence, not hope.

| Category | Score | Verdict |
| --- | ---: | --- |
| Visual quality | 40 / 100 | Main release blocker |
| Automation | 70 / 100 | Real automation exists, but still needs operator oversight |
| Infrastructure | 75 / 100 | Substantial system already exists |
| Reliability | 55 / 100 | Publish flow is decent, regression confidence is not |
| Content quality | 72 / 100 | Near MVP-ready |
| Operational readiness | 50 / 100 | Bundle portability and release confidence still weak |
| Scalability | 60 / 100 | Reasonable for MVP scale, not yet polished for broader operations |

Overall MVP readiness: **60 / 100**

Interpretation:

YOTO is closer to release mode than to greenfield development. It is a real product system already. But it is not close enough to launch publicly today, because the one thing the audience actually sees first, the card visual, is still inconsistent, and the current test and operator surface do not give enough confidence to publish at will.

## 9. Release Path

This section is intentionally minimal. No redesigns. No speculative architecture. No feature creep.

### 1. Fix official visual selection quality

Focus:

- stop placeholder-first outcomes in representative validation packs
- stop capsule/logo-like wins when stronger hero or action art exists
- fix edge cases where official decisioning and runtime resolution diverge because the selected asset is invalid or non-local

Release exit criteria:

- representative validation pack no longer collapses into placeholder heroes
- targeted smoke titles such as `Civilization VI` and `Dave the Diver` stop producing weak capsule-like outcomes
- at least one clean send-test card from the current bundle is visually public-worthy

### 2. Revalidate the visual pipeline with current artifacts

Focus:

- rerun live validation after the visual fix
- review the resulting contact sheet as a product artifact, not just a test artifact

Release exit criteria:

- strong visual consistency across a representative set
- no obvious dark/empty hero failures
- human review says "this is a channel-quality card set"

### 3. Restore a trustworthy regression gate

Focus:

- align test support with the current `RenderingConfig` surface
- align video manifest tests with the current use-case API
- clean up or isolate duplicate test-module pollution from task-bundle directories

Release exit criteria:

- `pytest -q tests` is green
- the team has a single reliable test command for release gating

### 4. Make the current bundle actually launchable

Focus:

- fix the current bundle launcher path assumptions
- ensure `doctor`, `latest-artifacts`, `preview`, and `send-test` work from `D:\Telegram_portable_bundle` without depending on the external `D:\Telegram` environment
- reduce path leakage in the places where it breaks portable operation

Release exit criteria:

- the portable bundle can perform operator checks and a send-test without hidden external dependencies

### 5. Run one final release-mode proving pass

Focus:

- dry-run
- doctor
- snapshot capture
- send-test
- short scheduled run without manual rescue

Release exit criteria:

- one complete release-mode proving cycle succeeds cleanly
- team confidence is based on current evidence, not memory of older passes

### Release Path Verdict

YOTO does not need a rewrite to reach MVP. It needs a focused stabilization pass centered on visual selection, test confidence, and bundle operability.

## 10. Post-MVP Roadmap

Everything below is **NOT REQUIRED FOR MVP RELEASE**.

- TikTok / Shorts pipeline
- AI video generation expansion
- advanced analytics and performance dashboards
- adaptive templates or genre-specific themes
- more aggressive AI cover generation
- recommendation systems
- large-scale scaling and multi-channel orchestration
- advanced operator UX layers
- experimental theme systems
- broader content diversification beyond the current Telegram MVP

These ideas may be valuable later, but they should not be allowed to delay MVP release. The current project does not need more ambition. It needs release discipline.

## Final Product Verdict

YOTO is a real product system with real publishing proof, real automation pieces, and real internal maturity.

It is also not ready for public launch today.

The reason is simple:

- the card generator is stable
- the post pipeline is real
- the captions are usable
- the visuals are still not consistently good enough
- the tests are not currently trustworthy enough
- the portable operator surface is not self-contained enough

That means YOTO should now move into a narrow release-mode phase:

1. fix visual selection quality
2. restore test confidence
3. fix bundle operability
4. run final proofing
5. launch

That is the shortest honest path from current state to MVP release.
