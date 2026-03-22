# TOP_LIST / roundup editorial case

- family: `TOP_LIST`
- source_kind: `roundup_snapshot`
- title: `Що взяти зі знижок просто зараз`
- before signals: {'keep_forever_mentions': 0, 'claim_verb_mentions': 0, 'claim_term_mentions': 0, 'wishlist_mentions': 0, 'comment_bait_mentions': 1, 'shortlist_mentions': 0}
- after signals: {'keep_forever_mentions': 0, 'claim_verb_mentions': 0, 'claim_term_mentions': 0, 'wishlist_mentions': 0, 'comment_bait_mentions': 0, 'shortlist_mentions': 0}
- after debug: {'voice_presence': 'direct', 'voice_style': 'roundup', 'closing_cta': 'Якщо берете щось одне, у цій добірці логічно йти зверху вниз.'}

## Before

```html
<b>Що взяти зі знижок просто зараз</b>

🐱 Йото витягнув ще кілька помітних пропозицій. Зібрали найсильніші резервні знижки цього вікна: тут є і великі імена, і справді сильні пропозиції, які не хочеться втрачати у резерві.

1. <a href="https://store.steampowered.com/app/990080/Hogwarts_Legacy/"><b>Hogwarts Legacy</b></a> - 85% до 239 грн, дуже популярна гра
2. <a href="https://store.steampowered.com/app/1222700/A_Way_Out/"><b>A Way Out</b></a> - 90% до 79 грн, помітний хіт
3. <a href="https://store.steampowered.com/app/1517290/Battlefield_2042/"><b>Battlefield™ 2042</b></a> - 95% до 74 грн, дуже популярна гра
4. <a href="https://store.steampowered.com/app/1361210/Warhammer_40000_Darktide/"><b>Warhammer 40,000: Darktide</b></a> - 75% до 189 грн, сильний франчайз
5. <a href="https://store.steampowered.com/app/1774580/STAR_WARS_Jedi_Survivor/"><b>STAR WARS Jedi: Survivor™</b></a> - 90% до 169 грн, помітний хіт

Якщо з цієї добірки брати щось першим, пишіть у коментарях, що забрали б одразу.
```

## After

```html
<b>Що взяти зі знижок просто зараз</b>

🐱 Йото витягнув кілька позицій, що не губляться на фоні решти. Тут не весь потік знижок, а верхівка тих позицій, які не губляться навіть на фоні великого сейлу.

1. <a href="https://store.steampowered.com/app/990080/Hogwarts_Legacy/"><b>Hogwarts Legacy</b></a> — 85% до 239 грн, великий хіт
2. <a href="https://store.steampowered.com/app/1222700/A_Way_Out/"><b>A Way Out</b></a> — 90% до 79 грн, помітний хіт
3. <a href="https://store.steampowered.com/app/1517290/Battlefield_2042/"><b>Battlefield™ 2042</b></a> — 95% до 74 грн, великий хіт
4. <a href="https://store.steampowered.com/app/1361210/Warhammer_40000_Darktide/"><b>Warhammer 40,000: Darktide</b></a> — 75% до 189 грн, великий франчайз
5. <a href="https://store.steampowered.com/app/1774580/STAR_WARS_Jedi_Survivor/"><b>STAR WARS Jedi: Survivor™</b></a> — 90% до 169 грн, помітний хіт

Якщо берете щось одне, у цій добірці логічно йти зверху вниз.

#toplist #steamsale #steam
```
