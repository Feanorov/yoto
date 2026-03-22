# FREE_GAME / fallback archive case

- family: `FREE_GAME`
- source_kind: `archive_post_artifact`
- title: `Turnip Boy Robs a Bank`
- before signals: {'keep_forever_mentions': 3, 'claim_verb_mentions': 2, 'claim_term_mentions': 1, 'wishlist_mentions': 0, 'comment_bait_mentions': 0, 'shortlist_mentions': 0}
- after signals: {'keep_forever_mentions': 0, 'claim_verb_mentions': 0, 'claim_term_mentions': 0, 'wishlist_mentions': 0, 'comment_bait_mentions': 0, 'shortlist_mentions': 0}
- after debug: {'presence': 'direct', 'style': 'freebie', 'fallback_used': True, 'repeat_risk': False, 'opening_repeat_risk': False, 'cta_repeat_risk': False, 'lane': 'breaking_freebie'}

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
