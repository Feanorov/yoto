# Edge case / no deadline / English-only source

- title: `Steam Automation Fest`
- before debug: {'presence': 'indirect', 'style': 'festival', 'selected_opening': 'У Steam зараз є тематичне вікно, яке варте швидкого проходу.', 'selected_cta': 'Це зручне вікно, щоб за один прохід скласти собі короткий список.', 'repeat_risk': False, 'fallback_used': True}
- after debug: {'presence': 'indirect', 'style': 'festival', 'selected_opening': 'У Steam відкрилося тематичне вікно, яке зручніше проходити точково, ніж суцільним скролом.', 'selected_cta': 'Найкращий хід тут простий: відкласти кілька точних попадань і не тонути в решті каталогу.', 'repeat_risk': False, 'fallback_used': True}
- before signals: {'generic_window_mentions': 0, 'shortlist_mentions': 2, 'wishlist_mentions': 0, 'focused_scan_mentions': 0}
- after signals: {'generic_window_mentions': 0, 'shortlist_mentions': 0, 'wishlist_mentions': 0, 'focused_scan_mentions': 1}

## Before

```html
🎉 <a href="https://store.steampowered.com/category/automation"><b>Steam Automation Fest</b></a>

У Steam зараз є тематичне вікно, яке варте швидкого проходу.

Ключова тема цього фестивалю — симулятор: сторінку зручно пройти як короткий маршрут по демо та знижках.

Подія вже триває, тож короткий список краще скласти без відкладань.

Це зручне вікно, щоб за один прохід скласти собі короткий список.

#steam #festival #gaming #simulation
```

## After

```html
🎉 <a href="https://store.steampowered.com/category/automation"><b>Steam Automation Fest</b></a>

У Steam відкрилося тематичне вікно, яке зручніше проходити точково, ніж суцільним скролом.

Фокус тут — симулятор. Сторінку зручно пройти як короткий маршрут по ключових секціях фестивалю.

Фестиваль уже триває, тож сторінку краще пройти одним заходом.

Найкращий хід тут простий: відкласти кілька точних попадань і не тонути в решті каталогу.

#steam #festival #gaming #simulation
```
