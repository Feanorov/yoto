# Sparse source case

- title: `Steam Next Fest`
- before debug: {'presence': 'indirect', 'style': 'festival', 'selected_opening': 'Тематичний фестиваль, який краще дивитися як добірку, а не як шумну вітрину.', 'selected_cta': 'Такі фестивалі найкраще працюють, коли швидко відсікаєте своє прямо зі сторінки.', 'repeat_risk': False, 'fallback_used': True}
- after debug: {'presence': 'indirect', 'style': 'festival', 'selected_opening': 'Цей фестиваль краще читати як коротку добірку по темі, а не як ще одну довгу вітрину.', 'selected_cta': 'Почніть із верхівки сторінки та тематичних секцій: цього вже вистачить, щоб швидко відмітити своє.', 'repeat_risk': False, 'fallback_used': True}
- before signals: {'generic_window_mentions': 1, 'shortlist_mentions': 0, 'wishlist_mentions': 0, 'focused_scan_mentions': 0}
- after signals: {'generic_window_mentions': 0, 'shortlist_mentions': 0, 'wishlist_mentions': 0, 'focused_scan_mentions': 0}

## Before

```html
🎉 <a href="https://store.steampowered.com/sale/nextfest"><b>Steam Next Fest</b></a>

Тематичний фестиваль, який краще дивитися як добірку, а не як шумну вітрину.

Фестиваль варто читати як коротке вікно для відбору свого, а не як чергову шумну вітрину.

Подія триватиме до 26 березня 2026, 17:00.

Такі фестивалі найкраще працюють, коли швидко відсікаєте своє прямо зі сторінки.

#steam #festival #gaming
```

## After

```html
🎉 <a href="https://store.steampowered.com/sale/nextfest"><b>Steam Next Fest</b></a>

Цей фестиваль краще читати як коротку добірку по темі, а не як ще одну довгу вітрину.

Це коротке тематичне вікно, яке краще читати через ключові секції, а не довгим суцільним скролом.

Вікно фестивалю — до 26 березня 2026, 17:00.

Почніть із верхівки сторінки та тематичних секцій: цього вже вистачить, щоб швидко відмітити своє.

#steam #festival #gaming
```
