from __future__ import annotations

from .models import PreviewState, SafetyState


SEND_DISABLED_REASON_RU = "Отключено: нужно собрать превью."
SEND_DISABLED_NO_REPORT_RU = "Отключено: preview report не найден."
SEND_DISABLED_PINNED_MISSING_RU = "Отключено: в preview report нет pinned_publish."
SEND_DISABLED_PINNED_INCOMPLETE_RU = "Отключено: pinned_publish неполный."
SEND_DISABLED_PINNED_VERSION_RU = "Отключено: неподдерживаемая версия pinned_publish."
SEND_DISABLED_AMBIGUOUS_RU = "Отключено: артефакты превью неоднозначны."
SEND_DISABLED_STALE_RU = "Отключено: превью устарело."
SEND_DISABLED_UNKNOWN_POST_RU = "Отключено: выбранный тип поста не поддерживается."
SEND_DISABLED_IMAGE_MISSING_RU = "Отключено: файл карточки из pinned_publish отсутствует."
SEND_DISABLED_CAPTION_HASH_RU = "Отключено: проверка caption_hash не пройдена."
SEND_DISABLED_IMAGE_HASH_RU = "Отключено: проверка image_hash не пройдена."
SEND_DISABLED_TRUTH_NOT_READY_RU = "Отключено: превью не готово к отправке."
SEND_DISABLED_BACKEND_BLOCKER_RU = "Отключено: backend заблокировал отправку."
SEND_ENABLED_READY_RU = "Превью готово к безопасной публикации."

_UI_TEXT_TRANSLATIONS = {
    "No preview state is loaded.": "Состояние превью не загружено.",
    "Preview report path is missing.": "Путь к preview report отсутствует.",
    "Preview report file is missing on disk.": "Файл preview report отсутствует на диске.",
    "Preview artifacts are ambiguous.": "Артефакты превью неоднозначны.",
    "Preview artifacts are stale.": "Артефакты превью устарели.",
    "Selected post type is Unknown/Unsupported.": "Выбранный тип поста не определён или не поддерживается.",
    "Preview card path is missing.": "Путь к карточке превью отсутствует.",
    "Preview card file is missing on disk.": "Файл карточки превью отсутствует на диске.",
    "Preview caption is missing.": "Описание превью отсутствует.",
    "Pinned publish payload is missing.": "В preview report нет pinned_publish.",
    "Pinned publish payload is incomplete.": "В pinned_publish отсутствуют обязательные поля.",
    "Pinned publish contract version is unsupported.": "Версия pinned_publish не поддерживается.",
    "Pinned publish image is missing on disk.": "Файл pinned_publish.image_path отсутствует на диске.",
    "Pinned publish caption hash verification failed.": "Проверка pinned caption_hash не пройдена.",
    "Pinned publish image hash verification failed.": "Проверка pinned image_hash не пройдена.",
    "Preview is not truth-ready yet.": "Превью ещё не готово к отправке.",
    "No preview workflow artifact exists yet.": "Артефакты превью ещё не созданы.",
    "No new preview workflow artifact was created after the current run; showing the latest known preview.": (
        "После текущего запуска не появился новый workflow preview; показано последнее известное превью."
    ),
    "The bound preview workflow artifact is missing; showing the latest known preview instead.": (
        "Привязанный workflow preview отсутствует; показано последнее известное превью."
    ),
    "Preview artifacts are stale; a newer preview workflow artifact exists on disk.": (
        "Артефакты превью устарели: на диске есть более новый workflow preview."
    ),
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
    send_disabled_reason = SEND_DISABLED_REASON_RU
    send_enabled = False
    preview_ready = False

    if state is None:
        blockers.append(localize_ui_message("No preview state is loaded."))
        return SafetyState(
            send_enabled=False,
            send_disabled_reason=send_disabled_reason,
            blockers=_dedupe(blockers),
            warnings=warnings,
            preview_ready=False,
        )

    warnings.extend(localize_ui_message(item) for item in state.warnings)

    if state.paths.truth_report_path is None:
        blockers.append(localize_ui_message("Preview report path is missing."))
        send_disabled_reason = SEND_DISABLED_NO_REPORT_RU
    elif not state.report_exists:
        blockers.append(localize_ui_message("Preview report file is missing on disk."))
        send_disabled_reason = SEND_DISABLED_NO_REPORT_RU

    if state.ambiguous:
        blockers.append(localize_ui_message("Preview artifacts are ambiguous."))
        send_disabled_reason = _first_disabled_reason(send_disabled_reason, SEND_DISABLED_AMBIGUOUS_RU)
    if state.stale:
        blockers.append(localize_ui_message("Preview artifacts are stale."))
        send_disabled_reason = _first_disabled_reason(send_disabled_reason, SEND_DISABLED_STALE_RU)
    if state.post_type_key == "unknown":
        blockers.append(localize_ui_message("Selected post type is Unknown/Unsupported."))
        send_disabled_reason = _first_disabled_reason(send_disabled_reason, SEND_DISABLED_UNKNOWN_POST_RU)
    if state.card_path is None:
        blockers.append(localize_ui_message("Preview card path is missing."))
    elif not state.card_exists:
        blockers.append(localize_ui_message("Preview card file is missing on disk."))
    if not state.caption_html and not state.caption_preview:
        blockers.append(localize_ui_message("Preview caption is missing."))
    if state.blocker_reason:
        blockers.append(localize_ui_message(f"Backend blocker: {state.blocker_reason}"))
        send_disabled_reason = _first_disabled_reason(send_disabled_reason, SEND_DISABLED_BACKEND_BLOCKER_RU)
    if not state.truth_ready:
        blockers.append(localize_ui_message("Preview is not truth-ready yet."))
        send_disabled_reason = _first_disabled_reason(send_disabled_reason, SEND_DISABLED_TRUTH_NOT_READY_RU)

    pinned = state.pinned_publish
    if not pinned.present:
        blockers.append(localize_ui_message("Pinned publish payload is missing."))
        send_disabled_reason = _first_disabled_reason(send_disabled_reason, SEND_DISABLED_PINNED_MISSING_RU)
    else:
        if (
            not pinned.offer_id
            or not pinned.idempotency_key
            or not pinned.caption_hash
            or not pinned.image_hash
            or pinned.image_path is None
        ):
            blockers.append(localize_ui_message("Pinned publish payload is incomplete."))
            send_disabled_reason = _first_disabled_reason(send_disabled_reason, SEND_DISABLED_PINNED_INCOMPLETE_RU)
        if not pinned.supported_contract:
            blockers.append(localize_ui_message("Pinned publish contract version is unsupported."))
            send_disabled_reason = _first_disabled_reason(send_disabled_reason, SEND_DISABLED_PINNED_VERSION_RU)
        if not pinned.image_exists:
            blockers.append(localize_ui_message("Pinned publish image is missing on disk."))
            send_disabled_reason = _first_disabled_reason(send_disabled_reason, SEND_DISABLED_IMAGE_MISSING_RU)
        if not pinned.caption_hash_verified:
            blockers.append(localize_ui_message("Pinned publish caption hash verification failed."))
            send_disabled_reason = _first_disabled_reason(send_disabled_reason, SEND_DISABLED_CAPTION_HASH_RU)
        if not pinned.image_hash_verified:
            blockers.append(localize_ui_message("Pinned publish image hash verification failed."))
            send_disabled_reason = _first_disabled_reason(send_disabled_reason, SEND_DISABLED_IMAGE_HASH_RU)

    preview_ready = bool(state.truth_ready and not blockers)
    send_enabled = preview_ready
    if send_enabled:
        send_disabled_reason = SEND_ENABLED_READY_RU

    return SafetyState(
        send_enabled=send_enabled,
        send_disabled_reason=send_disabled_reason,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        preview_ready=preview_ready,
    )


def _first_disabled_reason(current: str, candidate: str) -> str:
    if current == SEND_DISABLED_REASON_RU:
        return candidate
    return current


def _dedupe(values: list[str]) -> list[str]:
    ordered: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in ordered:
            ordered.append(text)
    return ordered
