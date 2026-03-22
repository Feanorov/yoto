# FREE_GAME / real freebie

- family: `FREE_GAME`
- source_kind: `golden_snapshot`
- title: `Cozy Grove`
- before signals: {'назавжди': 3, 'забрати': 2, 'клейм': 1, 'wishlist': 0, 'коментар': 0, 'shortlist': 0}
- after signals: {'назавжди': 0, 'забрати': 1, 'клейм': 0, 'wishlist': 0, 'коментар': 0, 'shortlist': 0}
- after debug: {'offer_id': 'epic:c367569acede446995c5a3663e993446', 'lane': 'breaking_freebie', 'presence': 'direct', 'style': 'freebie', 'opening': {'selected': '🎁 Йото зловив безкоштовну роздачу.', 'pool_size': 3, 'anti_repeat_window': 4, 'recent_repeat_count': 0, 'recent_window_repeat_count': 0, 'anti_repeat_relaxed': False, 'near_repeat_relaxed': False, 'near_repeat_window_hits': 0, 'repeat_risk': False, 'fallback_used': False, 'line': '🎁 Йото зловив безкоштовну роздачу.'}, 'cta': {'selected': 'Якщо така гра вам підходить, краще забрати її до закриття роздачі без зайвих відкладань.', 'pool_size': 3, 'anti_repeat_window': 4, 'recent_repeat_count': 0, 'recent_window_repeat_count': 0, 'anti_repeat_relaxed': False, 'near_repeat_relaxed': False, 'near_repeat_window_hits': 0, 'repeat_risk': False, 'fallback_used': False}, 'selected_opener': '🎁 Йото зловив безкоштовну роздачу.', 'normalization_applied': {'removed_replacement_chars': False, 'removed_garbage_unicode': False, 'normalized_dashes': False, 'normalized_whitespace': False, 'normalized_punctuation_spacing': False}, 'weird_symbol_detected': False, 'repeat_risk': False, 'fallback_used': True}

## Before

```html
🎁 <a href="https://store.epicgames.com/uk/p/cozy-grove"><b>Cozy Grove</b></a>

🎁 Йото витягнув безкоштовну гру.

Такий клейм зручно забрати зараз і лишити в бібліотеці на потім.

Замість 229 грн гру можна спокійно додати на акаунт без оплати й залишити назавжди.

Забрати назавжди варто до 19 березня 2026, 15:00.

Забирайте на акаунт зараз, поки роздача відкрита й додається назавжди.

#epicgames #freegame #giveaway
```

## After

```html
🎁 <a href="https://store.epicgames.com/uk/p/cozy-grove"><b>Cozy Grove</b></a>

🎁 Йото зловив безкоштовну роздачу.

Це спокійна безкоштовна знахідка з тих, що приємно мати під рукою на свій темп.

Зараз у Epic — 0 грн замість 229 грн; після додавання гра лишається на акаунті.

Роздача відкрита до 19 березня 2026, 15:00.

Якщо така гра вам підходить, краще забрати її до закриття роздачі без зайвих відкладань.

#epicgames #freegame #giveaway
```
