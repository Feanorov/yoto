# YOTO QA MATRIX — PROJECT STANDARD

## Purpose
This file is the fixed QA standard for the YOTO project.

Codex or any other coding assistant may:
- run QA checks against this standard
- report failures against this standard
- suggest additions to this standard

Codex or any other coding assistant may NOT:
- modify this standard directly
- delete rules from this standard
- weaken acceptance criteria
- reinterpret failed checks as passed

Any proposed QA additions must be reviewed by the project owner before being added here.

---

## BLOCK 1 — DATA INPUT QA

### Steam
- [ ] game with 90–95% discount
- [ ] game with 70–85% discount
- [ ] game with 30–50% discount
- [ ] game without discount
- [ ] free weekend
- [ ] bundle

### Epic
- [ ] freebie with description
- [ ] freebie without description
- [ ] freebie with very short title
- [ ] freebie with long title

### Events
- [ ] Steam fest
- [ ] Steam publisher sale
- [ ] thematic event

---

## BLOCK 2 — NORMALIZATION QA

### Title
- [ ] short title
- [ ] long title
- [ ] title > 40 chars
- [ ] title > 60 chars

### Description
- [ ] Ukrainian text exists
- [ ] English-only source text
- [ ] empty description

### Genres / Tags
- [ ] 1 genre
- [ ] 3 genres
- [ ] no genres

---

## BLOCK 3 — EDITORIAL ENGINE QA

### Lane detection
- [ ] breaking_freebie
- [ ] high_value_discount
- [ ] backlog_filler
- [ ] event_festival
- [ ] final_push

### Edge cases
- [ ] new discount
- [ ] price improved
- [ ] price worsened
- [ ] same discount

---

## BLOCK 4 — CAPTION QA

### Hook
- [ ] freebie
- [ ] discount
- [ ] event

### Summary
- [ ] normal description
- [ ] fallback description
- [ ] description without genres

### Urgency
- [ ] deadline exists
- [ ] no deadline
- [ ] final push

### Price
- [ ] regular price
- [ ] free
- [ ] unknown price

### Hashtags
- [ ] Steam
- [ ] Epic
- [ ] genre tags

---

## BLOCK 5 — CARD RENDER QA

### Layout
- [ ] no cut-off text
- [ ] title fits
- [ ] price is readable
- [ ] deadline is readable

### Image
- [ ] hero art
- [ ] header art
- [ ] screenshot fallback
- [ ] placeholder fallback

### Crop
- [ ] logo is not cut off
- [ ] characters are not cut off badly
- [ ] art does not look awkward

### Badge
- [ ] FREE badge
- [ ] DISCOUNT badge
- [ ] EVENT badge

### Typography
- [ ] title max 2 lines
- [ ] wrapping works
- [ ] truncation works

---

## BLOCK 6 — EDGE CASE QA

### Data edge cases
- [ ] no image
- [ ] no description
- [ ] no price
- [ ] strange currency

### Content edge cases
- [ ] very long title
- [ ] weird indie titles
- [ ] games with symbols

---

## BLOCK 7 — VISUAL QA

A viewer must understand within 1 second:
- [ ] what game this is
- [ ] discount or free status
- [ ] current price
- [ ] deadline / time window

---

## BLOCK 8 — TELEGRAM UX QA

- [ ] caption is readable
- [ ] card supports the post rather than fighting it
- [ ] no visual clutter
- [ ] core message is understandable without reading a long paragraph

---

## BLOCK 9 — STRESS TEST

Run at least 50 offers:
- [ ] no post breaks
- [ ] no card breaks
- [ ] no caption breaks

---

## Usage Rule

For every accepted render/caption patch:
1. run local tests
2. generate preview/dry-run outputs
3. compare against this QA matrix
4. accept or reject based on result

---

## Codex Instruction Block

When using this file in Codex, provide this instruction:

“The file `docs/YOTO_QA_MATRIX.md` is the fixed project QA standard.
Use it as the source of truth for QA runs and acceptance checks.
Do not modify, weaken, or delete rules from it.
You may suggest additions separately, but you may not rewrite the standard itself.”
