# YOTO Caption System Freeze Brief

Date: 2026-03-19

This document audits the current caption and post-text system as it exists in the repo today. It is a freeze-stage brief, not a pipeline redesign. The goal is to map the active caption architecture, the canonical families, the current weaknesses, the legacy behaviors still leaking through the text layer, and the freeze contract the implementation should satisfy.

## Evidence Base

Primary code paths:
- `infrastructure/telegram/caption_builder.py`
- `infrastructure/telegram/roundup_draft_builder.py`
- `dealbot/utils/ua.py`
- `application/use_cases/dry_run_render.py`
- `application/use_cases/generate_roundup_artifacts.py`
- `application/use_cases/publish_next.py`

Repo contracts and operator docs:
- `docs/YOTO_QA_MATRIX.md`
- `docs/YOTO_VALIDATION_PLAYBOOK.md`
- `docs/YOTO_COMMAND_INDEX.md`
- `AGENTS.md`

Tests:
- `tests/test_caption_builder_arch.py`
- `tests/test_live_caption_validation_tool.py`
- `tests/test_roundup_draft_builder_arch.py`
- `tests/test_publish_roundup_integration_arch.py`
- `tests/test_ua_utils.py`

Validation / review tools and artifacts:
- `tools/generate_yoto_v1_live_caption_validation.py`
- `output/captions/yoto_voice_v1_live_validation/20260312T215227Z/validation_manifest.json`
- `output/captions/yoto_voice_v1_live_validation/20260318T210428Z/validation_manifest.json`
- `output/analytics/20260319T011757Z_roundup_snapshot_roundups.json`
- `output/offline_validation/golden/current/snapshot_manifest.json`
- `output/analytics/20260312T183416Z_publish_outcome_event_category_tower_defense.json`
- `output/analytics/20260318T215316Z_publish_outcome_epic_c367569acede446995c5a3663e993446.json`

## 1. Current Caption Architecture

### 1.1 Canonical semantic families

The active text layer already maps to four semantic post families even though the solo caption builder is still organized mostly by source and offer kind:

| Family | Active owner | Primary mapping today |
| --- | --- | --- |
| `FREE_GAME` | `TelegramCaptionBuilder` | `Offer.is_freebie` across Epic and Steam |
| `DISCOUNT` | `TelegramCaptionBuilder` | standard Steam discount offers |
| `FESTIVAL` | `TelegramCaptionBuilder` | `Offer.is_event` / `festival_event` |
| `TOP_LIST` | `TelegramRoundupDraftBuilder` | roundup / digest posts built from reserve |

The solo path is selected in `TelegramCaptionBuilder._compose(...)`, which routes to:
- `_build_epic_caption(...)`
- `_build_event_caption(...)`
- `_build_steam_caption(...)`

The roundup path is separate:
- `GenerateRoundupArtifactsUseCase` builds `RoundupPost`
- `TelegramRoundupDraftBuilder.build(...)` renders the Telegram caption HTML
- `publish_next.py` publishes `decision_json["roundup_caption_html"]` directly for roundup posts

### 1.2 Current solo-caption pipeline

The active solo path today is:

`publish_next / preview -> DryRunRenderUseCase -> TelegramCaptionBuilder.build(...) -> PostArtifact.caption_html -> publish_outbox / Telegram publish`

Within `TelegramCaptionBuilder`, the current assembly order is:
- title line with store link
- hook line
- summary line
- value / price / claim line
- improvement note when relevant
- urgency line when relevant
- review / achievements / cards support line
- CTA
- hashtags

The line-level raw material comes from three places:
- `YotoVoiceEngine`: chooses presence (`direct` / `indirect` / `neutral`), opening pools, some CTA pools, and anti-repeat state
- `dealbot.utils.ua.build_offer_copy(...)`: provides generic hook / summary / urgency fallback copy
- `TelegramCaptionBuilder`: overrides or refines that copy and normalizes punctuation / mojibake / whitespace

### 1.3 Current roundup-caption pipeline

Roundup captions are owned by `TelegramRoundupDraftBuilder`, not by `TelegramCaptionBuilder`.

Current roundup structure:
- roundup title
- one intro paragraph built from a direct opener plus a fixed group-type intro
- numbered item lines
- one closing CTA

Current roundup text does not currently have a first-class family contract for:
- curated framing versus queue-summary framing
- hashtag policy
- anti-repeat policy for repeated roundup generations
- clear distinction between “editorial selection” tone and “reserve dump” tone

## 2. How Family Voice Differs Today

### 2.1 `FREE_GAME`

Current freebie voice is the most explicit and the most templated.

Evidence in `caption_builder.py`:
- direct freebie openers live in `DIRECT_OPENING_POOLS["freebie"]`
- indirect freebie hooks live in `INDIRECT_HOOK_POOLS["freebie"]`
- claim/value language is hardcoded in `_build_epic_claim_line(...)` and `_build_steam_value_line(...)`
- default CTA is hardcoded in `_build_cta(...)`

Observed behavior:
- strong direct YOTO presence for breaking freebies
- multiple lines in the same caption often repeat the same semantic action: claim now, add to account, keep forever, library, deadline, CTA
- fallback freebie summaries still carry legacy “клейм / забрати / лишити на потім” DNA

### 2.2 `DISCOUNT`

Current discount voice is split by editorial style instead of by a single family contract:
- `finder`
- `recommend`
- `first_price_move`
- `alert`
- `neutral`

That style logic is useful, but the actual composed caption still collapses into a familiar skeleton:
- opener about price relevance
- summary that may also mention price relevance
- value line with exact price and savings
- urgency for larger discounts
- CTA that often repeats “повернути на радар / перевірити ціну”

Observed behavior on current golden-snapshot planned rows:
- `Titanfall® 2`, `Need for Speed™ Heat`, `Hearts of Iron IV`, `Crusader Kings III`, `Battlefield™ V` all share closely related hook / CTA skeletons
- the builder is already rotating exact strings, but the semantic shape still clusters too tightly
- long source descriptions like `Satisfactory` and `Deep Rock Galactic` read more like imported store blurbs than YOTO feed copy

### 2.3 `FESTIVAL`

Current festival voice is the weakest canonical family.

Evidence:
- events do not have a dedicated voice style in `YotoVoiceEngine`
- `_build_caption_hook_line(...)` falls back to `"{title} збирає знижки, демо та жанрові знахідки в одному місці."`
- event summary falls back to `EVENT_GENERIC_SUMMARY`
- event CTA falls back to `Перегляньте фестиваль зараз, поки він у розпалі.`

Observed result:
- family separation is thin
- captions feel safe but stock
- sparse-source events collapse into generic announcement copy instead of editorial framing

### 2.4 `TOP_LIST`

Current top-list voice is structurally useful but under-edited.

Evidence:
- title rules live in `TelegramRoundupDraftBuilder._title(...)`
- intro copy is fixed per `group_type` in `_intro(...)`
- item lines are currently `rank + title + discount/value signal + short qualifier`
- CTA is mostly comment-prompt oriented in `_closing_cta(...)`

Observed result in `output/analytics/20260319T011757Z_roundup_snapshot_roundups.json`:
- intro still reads as roundup plumbing rather than a sharp editorial frame
- list items are readable but feel like score-card rows, not a deliberate curation stack
- closing CTA trends toward engagement prompts instead of selection guidance

## 3. Where Repetition Is Coming From

### 3.1 Voice pools are rotating phrases, not rotating line roles

`YotoVoiceEngine` already rotates openers and can avoid direct near-repeats, but repetition still survives because:
- CTA pools are small
- freebie and event CTAs still fall back to single hardcoded lines
- the summary, value, urgency, and CTA often repeat the same idea in different wording

### 3.2 Legacy fallback summaries still leak store-template language

`dealbot/utils/ua.py` still owns generic fallback summary construction.

Legacy patterns still visible there:
- “Це гра, яку можна спокійно додати до бібліотеки...”
- “Ціна вже виглядає достатньо привабливою...”
- “Гарний варіант для тих, хто любить...”

`caption_builder.py` already replaces some of these with `GENERIC_COPY_REPLACEMENTS`, which is a strong signal that the repo is currently post-processing legacy sentence skeletons instead of owning a cleaner canonical contract directly.

### 3.3 Value, urgency, and CTA lines are competing for the same job

Current overlap by family:
- `FREE_GAME`: claim line, urgency line, and CTA all fight over “забрати / назавжди / бібліотека”
- `DISCOUNT`: opener, summary fallback, value line, and CTA all fight over “ціна / повернути на радар / перевірити”
- `FESTIVAL`: hook, summary, and CTA all repeat “фестиваль / знижки / демо / переглянути”
- `TOP_LIST`: intro, item list, and CTA all repeat “добірка / резерв / знижки” with little tonal escalation

### 3.4 Existing live review coverage under-exercises the family surface

`tools/generate_yoto_v1_live_caption_validation.py` is truthful and useful, but current packs are often dominated by whatever is live in queue or archive.

Observed artifact evidence:
- `20260318T210428Z` has no live planned rows and no roundups, only two archive freebies
- this is enough for sanity checks but not enough for a family-freeze decision

## 4. Lines That Currently Feel Mechanical

These are not all “wrong,” but they are clear freeze-stage liabilities because they recur as system voice:

- `Такий клейм зручно забрати зараз і лишити в бібліотеці на потім.`
- `Забирайте на акаунт зараз, поки роздача відкрита й додається назавжди.`
- `Для такого тайтлу пропозиція вже виглядає дуже робочою.`
- `Для такого тайтлу це вже ціна, яку варто перевірити без зайвого шуму.`
- `Якщо давно чекали приводу повернути цю гру на радар, він уже є.`
- `Тематична подія зі знижками, демоверсіями та тематичними добірками...`
- `Перегляньте фестиваль зараз, поки він у розпалі.`
- roundup intros framed as “reserve bundle” instead of deliberate editorial selection

## 5. What The Canonical Text Contract Should Be

### 5.1 Shared freeze contract

Every canonical family should have a stable role order:
- headline
- one supporting line that tells the reader what this is or why it matters
- one value line when the family benefits from price / free / list evidence
- one urgency line only when it adds new information
- one CTA that tells the reader what to do next without repeating the value line
- tag line at the end when the surface uses tags

Shared tone targets:
- fast to scan in Telegram
- clean Ukrainian
- factual and non-inflated
- premium editorial, not ad copy
- deterministic and testable

### 5.2 `FREE_GAME` contract

Target hierarchy:
- headline: game title + source cue
- supporting line: what kind of game or why it is worth noticing
- value line: “0 грн now / was X before”
- urgency line: deadline or access-window clarity
- CTA: one clear action line

Policy:
- “claim/keep forever” semantics should appear once, not in three different lines
- temporary free access must never borrow permanent-library language
- fallback summaries must describe the game, not the act of claiming it

### 5.3 `DISCOUNT` contract

Target hierarchy:
- headline
- supporting line: genre / hook / why the title matters
- value line: current price, old price, savings
- optional urgency: only when deadline or final-push context adds actual information
- support line: reviews / achievements / cards when helpful
- CTA: selection guidance, not another price line

Policy:
- price numbers belong mainly in the value line
- opener and CTA should not both say “this price is interesting”
- long imported descriptions should be compressed to one feed-scale supporting line

### 5.4 `FESTIVAL` contract

Target hierarchy:
- headline
- supporting line: the theme, angle, or why the event matters
- optional detail line: demos / discounts / event structure if not already covered
- urgency line: event window
- CTA: scan / explore / shortlist guidance

Policy:
- the family must read as editorial event framing, not “generic store announcement”
- sparse-source events still need a confident YOTO summary
- title-theme extraction and fallback behavior need to be explicit

### 5.5 `TOP_LIST` contract

Target hierarchy:
- title
- one framing paragraph that explains what this list is and why these entries were chosen
- ordered list of items with one clean value signal each
- CTA that tells the reader how to use the list
- tag line when the roundup surface uses tags

Policy:
- top-list tone should feel curated, not auto-dumped
- list intros should describe the editorial cut, not the reserve mechanism
- closing CTAs should favor action / scanning guidance over generic comment bait

## 6. Anti-Repeat Rules For Freeze

Freeze-stage anti-repeat should be explicit rather than accidental.

Target rules:
- no duplicate opener within the recent anti-repeat window when alternatives exist
- no near-duplicate CTA within the same recent window when alternatives exist
- no caption should carry two body lines that express the same semantic action with only minor rewording
- no family should rely on a single fallback CTA
- summary, value, urgency, and CTA should each own a different editorial job

## 7. CTA Policy

Target CTA policy by family:

| Family | CTA job | What to avoid |
| --- | --- | --- |
| `FREE_GAME` | tell the reader to grab / try it before the window closes | repeating “назавжди / бібліотека / забрати” across multiple lines |
| `DISCOUNT` | tell the reader to verify it against wishlist / backlog / purchase timing | repeating exact price logic already present above |
| `FESTIVAL` | tell the reader to scan the event page with a clear reason | generic “перегляньте фестиваль зараз” filler |
| `TOP_LIST` | tell the reader how to use the ranked list | engagement bait as the default closing move |

## 8. Urgency / Deadline Policy

Current repo utilities already normalize deadlines to Ukrainian month format via `format_deadline(...)`.

Freeze-stage deadline policy should be:
- show deadlines where they materially change behavior
- freebie and festival deadlines are usually worth showing
- discount deadlines should be reserved for high-urgency or explicit deadline-sensitive cases
- final-push language should remain a separate urgency mode, not bleed into normal discounts
- deadline lines must add information instead of paraphrasing the CTA

## 9. Fallback Behavior That Should Stay

These are useful and should remain:
- HTML-safe output and link escaping
- Cyrillic detection before trusting source descriptions
- mojibake / zero-width / whitespace cleanup
- deterministic phrase selection using stable hashing
- price / deadline formatting utilities
- temporary-access detection for Steam freebies

## 10. Legacy Behavior That Should Be Considered Legacy

These behaviors should be treated as legacy text behavior even if they still work technically:
- generic post-processing of template fallback sentences instead of owning a direct family contract
- “клейм / лишити на потім / повернути на радар” as the dominant fallback vocabulary
- festival captions that remain effectively neutral / generic
- roundup framing built around reserve mechanics instead of curation logic
- CTA behavior that repeats the value line instead of resolving the post

## 11. Freeze Criteria

The caption layer should be considered freeze-ready only if all of the following are true:
- canonical family separation is obvious across `FREE_GAME`, `DISCOUNT`, `FESTIVAL`, and `TOP_LIST`
- repeated semantic lines are materially reduced, not just reworded
- fallback summaries no longer feel like legacy template text
- festival copy has a distinct editorial contract
- roundup / top-list copy reads as curated selection
- tests pin family contracts, anti-repeat behavior, deadline wording, punctuation hygiene, HTML safety, and deterministic output
- a fresh review pack shows before/after differences clearly across multiple representative cases
- truthful preview and, when a publishable live row exists, real Telegram test-post proof are attempted through the existing operator path
