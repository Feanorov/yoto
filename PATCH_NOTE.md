# YOTO patch: comfyui_provider -> minimal safe stub

## Файлы в архиве
- `Telegram_portable_bundle/infrastructure/render/cards/image_providers/comfyui_provider.py`
- `Telegram_portable_bundle/PATCH_NOTE.md`

## Что заменить
Заменить файл в локальном проекте:
- `D:\Telegram_portable_bundle\infrastructure\render\cards\image_providers\comfyui_provider.py`

## Что меняет patch
- Убирает HTTP/network-логику, polling, timeout и зависимость от внешнего ComfyUI endpoint.
- Оставляет минимальный stub-provider.
- Provider принимает `ImageResolutionRequest` и возвращает `ResolvedImage`.
- В metadata выставляет:
  - `provider = "comfyui"`
  - `status = "success"`
- Использует локальный валидный image path, а если его нет — строит простой локальный stub image, чтобы не возвращать `None`.

## Инструкция применения
1. Скачать ZIP-архив.
2. Распаковать его в `D:\` или открыть архив.
3. Скопировать содержимое папки `Telegram_portable_bundle` поверх локального проекта `D:\Telegram_portable_bundle`.
4. Подтвердить замену файла `comfyui_provider.py`.

## Команды проверки
Из корня проекта `D:\Telegram_portable_bundle`:

```powershell
python -m py_compile infrastructure\render\cards\image_providers\comfyui_provider.py
```

```powershell
$env:PYTHONPATH = "D:\Telegram_portable_bundle"
python -c "from infrastructure.render.cards.image_providers.comfyui_provider import ComfyUIImageProvider; from infrastructure.render.cards.image_providers.base import ImageResolutionRequest; p=ComfyUIImageProvider(enabled=True); req=ImageResolutionRequest(artwork_path=None,title='Test',platform='Steam',slug='test',card_type='discount',lane=None,mode='artwork_then_ai',priority='NORMAL',image_size=(640,360)); r=p.resolve(req); print(type(r).__name__); print(r.metadata); print(r.image.size)"
```

## Ожидаемый результат
- `py_compile` проходит без ошибок.
- Provider импортируется без ошибок.
- Возвращается `ResolvedImage`, а не `None`.
- В `metadata` есть:
  - `provider: comfyui`
  - `status: success`
- В файле больше нет HTTP/network логики.
