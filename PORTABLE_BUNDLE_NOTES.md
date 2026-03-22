# YOTO Portable Bundle Notes

Created: 2026-03-20
Source root: D:\Telegram
Bundle goal: lean working handoff copy for continued development.

Included:
- full source, tests, docs, configs, scripts, and runtime data/assets
- current card-system baseline context via reference cards, live validation, latest premium finish review chain, latest card outputs, and offline validation proof
- current caption/video workflow artifacts that are small enough to preserve operator context
- only the latest offline validation snapshots from 2026-03-20 needed to represent preview and send-test state
- only the small current temp artifacts that still carry freeze-stage review context

Intentionally omitted:
- .venv, __pycache__, .pytest_cache, scratch temp, and broad historical generated output
- large older card example packs, integration previews, smoke/validation reruns, and stale offline snapshots
- .env (machine-specific / secret-bearing config); use .env.example to recreate local settings
- dealbot_iteration3 and tmp_test_script.py because they are not part of the active working surface

Handoff notes:
- The portable bundle keeps the operator docs and proof artifacts needed to understand the current frozen card/caption baseline.
- Some docs still reference larger historical packs that were intentionally excluded to reduce transport size.
- If a future task needs deep historical comparison, return to the original D:\Telegram workspace.
