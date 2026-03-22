# FESTIVAL / sparse source

- family: `FESTIVAL`
- source_kind: `fixture`
- title: `Steam Next Fest`
- before signals: {'keep_forever_mentions': 0, 'claim_verb_mentions': 0, 'claim_term_mentions': 0, 'wishlist_mentions': 0, 'comment_bait_mentions': 0, 'shortlist_mentions': 0}
- after signals: {'keep_forever_mentions': 0, 'claim_verb_mentions': 0, 'claim_term_mentions': 0, 'wishlist_mentions': 0, 'comment_bait_mentions': 0, 'shortlist_mentions': 2}
- after debug: {'presence': 'indirect', 'style': 'festival', 'fallback_used': True, 'repeat_risk': False, 'opening_repeat_risk': False, 'cta_repeat_risk': False, 'lane': 'event_festival'}

## Before

```html
🎉 <a href="https://store.steampowered.com/sale/nextfest"><b>Steam Next Fest</b></a>

Steam Next Fest збирає знижки, демо та жанрові знахідки в одному місці.

Тематична подія зі знижками, демоверсіями та тематичними добірками, тож це хороший момент пройтися по фестивалю.

Фестиваль триває до 26 березня 2026, 17:00.

Перегляньте фестиваль зараз, поки він у розпалі.

#steam #festival #gaming
```

## After

```html
🎉 <a href="https://store.steampowered.com/sale/nextfest"><b>Steam Next Fest</b></a>

Це один із тих фестивалів, де зручно за один раз скласти shortlist.

Фестиваль варто читати як коротке вікно для відбору свого, а не як чергову шумну вітрину.

Подія триватиме до 26 березня 2026, 17:00.

Це зручне вікно, щоб за один прохід скласти собі короткий shortlist.

#steam #festival #gaming
```
