# FREE_GAME / fallback archive case

- family: `FREE_GAME`
- source_kind: `archive_post_artifact`
- title: `Turnip Boy Robs a Bank`
- before signals: {'назавжди': 3, 'забрати': 2, 'клейм': 1, 'wishlist': 0, 'коментар': 0, 'shortlist': 0}
- after signals: {'назавжди': 0, 'забрати': 0, 'клейм': 0, 'wishlist': 0, 'коментар': 0, 'shortlist': 0}
- after debug: {'offer_id': 'epic:68d9f0e261464ba284e10418d98532ea', 'lane': 'breaking_freebie', 'presence': 'direct', 'style': 'freebie', 'opening': {'selected': '🎁 Йото помітив ще один тайтл за 0 грн.', 'pool_size': 3, 'anti_repeat_window': 4, 'recent_repeat_count': 0, 'recent_window_repeat_count': 0, 'anti_repeat_relaxed': False, 'near_repeat_relaxed': False, 'near_repeat_window_hits': 0, 'repeat_risk': False, 'fallback_used': False, 'line': '🎁 Йото помітив ще один тайтл за 0 грн.'}, 'cta': {'selected': 'Тут вистачає одного швидкого кліку зараз, щоб не згадувати про цю роздачу запізно.', 'pool_size': 3, 'anti_repeat_window': 4, 'recent_repeat_count': 0, 'recent_window_repeat_count': 0, 'anti_repeat_relaxed': False, 'near_repeat_relaxed': False, 'near_repeat_window_hits': 1, 'repeat_risk': False, 'fallback_used': False}, 'selected_opener': '🎁 Йото помітив ще один тайтл за 0 грн.', 'normalization_applied': {'removed_replacement_chars': False, 'removed_garbage_unicode': False, 'normalized_dashes': False, 'normalized_whitespace': False, 'normalized_punctuation_spacing': False}, 'weird_symbol_detected': False, 'repeat_risk': False, 'fallback_used': True}

## Before

```html
🎁 <a href="https://store.epicgames.com/uk/p/turnip-boy-robs-a-bank-3fae0e"><b>Turnip Boy Robs a Bank</b></a>

🎁 Йото спіймав гру за 0 грн.

Такий клейм зручно забрати зараз і лишити в бібліотеці на потім.

Замість 275 грн гру можна спокійно додати на акаунт без оплати й залишити назавжди.

Забрати назавжди варто до 12 березня 2026, 15:00.

Забирайте на акаунт зараз, поки роздача відкрита й додається назавжди.

#epicgames #freegame #giveaway
```

## After

```html
🎁 <a href="https://store.epicgames.com/uk/p/turnip-boy-robs-a-bank-3fae0e"><b>Turnip Boy Robs a Bank</b></a>

🎁 Йото помітив ще один тайтл за 0 грн.

Такий безкоштовний тайтл беруть радше за шанс спокійно відкрити щось нове, ніж за шум навколо.

Зараз у Epic — 0 грн замість 275 грн; після додавання гра лишається на акаунті.

Роздача відкрита до 12 березня 2026, 15:00.

Тут вистачає одного швидкого кліку зараз, щоб не згадувати про цю роздачу запізно.

#epicgames #freegame #giveaway
```
