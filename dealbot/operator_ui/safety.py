from __future__ import annotations

from .models import PreviewState, SafetyState


SEND_DISABLED_REASON_RU = (
    "Отключено: send-test ещё не закреплён за текущим превью; "
    "backend может выбрать другой пост перед публикацией."
)

_UI_TEXT_TRANSLATIONS = {
    "No preview state is loaded.": "Состояние превью не загружено.",
    "Preview artifacts are ambiguous.": "Артефакты превью неоднозначны.",
    "Preview artifacts are stale.": "Артефакты превью устарели.",
    "Selected post type is Unknown/Unsupported.": "Выбранный тип поста не определён или не поддерживается.",
    "Preview card path is missing.": "Путь к карточке превью отсутствует.",
    "Preview card file is missing on disk.": "Файл карточки превью отсутствует на диске.",
    "Preview caption is missing.": "Описание превью отсутствует.",
    "Run Preview or Refresh Local State to load the latest operator artifacts.": (
        "Соберите превью или обновите локальное состояние, "
        "чтобы загрузить последние артефакты оператора."
    ),
}


def localize_ui_message(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    if normalized.startswith("Backend blocker:"):
        reason = normalized.removeprefix("Backend blocker:").strip()
        return f"Блокировка backend: {reason}" if reason else "Блокировка backend."
    return _UI_TEXT_TRANSLATIONS.get(normalized, normalized)


def evaluate_preview_safety(state: PreviewState | None) -> SafetyState:
    blockers: list[str] = []
    warnings: list[str] = []
    preview_ready = False

    if state is None:
        blockers.append(localize_ui_message("No preview state is loaded."))
    else:
        warnings.extend(localize_ui_message(item) for item in state.warnings)
        if state.ambiguous:
            blockers.append(localize_ui_message("Preview artifacts are ambiguous."))
        if state.stale:
            blockers.append(localize_ui_message("Preview artifacts are stale."))
        if state.post_type_key == "unknown":
            blockers.append(localize_ui_message("Selected post type is Unknown/Unsupported."))
        if state.card_path is None:
            blockers.append(localize_ui_message("Preview card path is missing."))
        elif not state.card_exists:
            blockers.append(localize_ui_message("Preview card file is missing on disk."))
        if not state.caption_html and not state.caption_preview:
            blockers.append(localize_ui_message("Preview caption is missing."))
        if state.blocker_reason:
            blockers.append(localize_ui_message(f"Backend blocker: {state.blocker_reason}"))
        preview_ready = bool(state.truth_ready and not blockers)

    return SafetyState(
        send_enabled=False,
        send_disabled_reason=SEND_DISABLED_REASON_RU,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        preview_ready=preview_ready,
    )


def _dedupe(values: list[str]) -> list[str]:
    ordered: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in ordered:
            ordered.append(text)
    return ordered
