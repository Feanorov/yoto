from __future__ import annotations

from pathlib import Path

from .models import (
    OperatorPostTypeMode,
    OperatorStatusState,
    PreviewState,
    SafetyState,
    default_operator_post_type_mode,
)


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
SEND_DISABLED_ALREADY_PUBLISHED_RU = "Этот оффер уже опубликован."
SEND_DISABLED_NO_NEW_PREVIEW_RU = "Новый preview не создан."
SEND_DISABLED_NO_READY_POST_RU = "Нет готового поста для публикации."
SEND_DISABLED_POST_TYPE_MODE_RU = "Отключено: тип поста не выбран в текущем режиме."
SEND_DISABLED_ALREADY_SENT_RU = "Этот оффер уже отправлен и ждёт финализации."
SEND_ENABLED_READY_RU = "Превью готово к безопасной публикации."

PREVIEW_ACTION_DEFAULT_RU = "Собрать превью"
PREVIEW_ACTION_NEXT_POST_RU = "Собрать следующий пост"
PREVIEW_ACTION_TOOLTIP_RU = "Запускает preview и подбирает следующий кандидат для публикации."
DEFAULT_PREVIEW_BANNER_ACTION_RU = "Соберите новое превью."
NEXT_PREVIEW_BANNER_ACTION_RU = "Соберите новое превью для следующего поста."

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
    "This preview was already published in Telegram.": "Этот оффер уже опубликован.",
    "already_published": "этот оффер уже опубликован",
    "already_sent_finalize_only": "этот preview уже отправлен и ждёт финализации",
    "blocked:already_published_recently": "Этот оффер уже опубликован.",
    "queue_empty": "Нет готового поста для публикации.",
    "planner_window_empty": "Нет готового поста для публикации.",
    "no_publishable_candidate": "Нет готового поста для публикации.",
    "controlled_reserve_release_held": "Нет готового поста для публикации.",
    "quiet_hours_reserve_hidden": "Нет готового поста для публикации.",
    "No preview workflow artifact exists yet.": "Артефакты превью ещё не созданы.",
    "No new preview workflow or truth artifact was created after the current run.": (
        "После текущего запуска не появился новый preview workflow/truth."
    ),
    "No new preview workflow artifact was created after the current run; showing the latest known preview.": (
        "После текущего запуска не появился новый workflow preview; показано последнее известное превью."
    ),
    "Preview artifacts are ambiguous; multiple preview artifacts were created.": (
        "Артефакты превью неоднозначны: создано несколько preview-артефактов."
    ),
    "The bound preview workflow artifact is missing; showing the latest known preview instead.": (
        "Привязанный workflow preview отсутствует; показано последнее известное превью."
    ),
    "Preview artifacts are stale; a newer preview workflow artifact exists on disk.": (
        "Артефакты превью устарели: на диске есть более новый workflow preview."
    ),
    "Run Preview or Refresh Local State to load the latest operator artifacts.": (
        "Соберите превью или обновите локальное состояние, чтобы загрузить последние артефакты оператора."
    ),
    "Current run produced no new preview artifact; the latest known preview is already published.": (
        "Текущий запуск не создал новое превью; последнее известное превью уже опубликовано."
    ),
}


def localize_ui_message(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    if normalized.startswith("Backend blocker:"):
        reason = normalized.removeprefix("Backend blocker:").strip()
        localized_reason = _UI_TEXT_TRANSLATIONS.get(reason, reason)
        return f"Блокировка backend: {localized_reason}" if reason else "Блокировка backend."
    return _UI_TEXT_TRANSLATIONS.get(normalized, normalized)


def build_preview_action_copy(state: PreviewState | None) -> tuple[str, str]:
    label = PREVIEW_ACTION_NEXT_POST_RU if _should_prepare_next_post(state) else PREVIEW_ACTION_DEFAULT_RU
    return label, PREVIEW_ACTION_TOOLTIP_RU


def evaluate_preview_safety(
    state: PreviewState | None,
    post_type_mode: OperatorPostTypeMode | None = None,
) -> SafetyState:
    mode = post_type_mode or default_operator_post_type_mode()
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
    if state.current_run_backend_reason:
        warnings.append(localize_ui_message(f"Backend blocker: {state.current_run_backend_reason}"))

    if state.current_run_missing_artifact:
        blockers.append(SEND_DISABLED_NO_NEW_PREVIEW_RU)
        if state.stale:
            warnings.append(localize_ui_message("Preview artifacts are stale."))
        return SafetyState(
            send_enabled=False,
            send_disabled_reason=SEND_DISABLED_NO_NEW_PREVIEW_RU,
            blockers=_dedupe(blockers),
            warnings=_dedupe(warnings),
            preview_ready=False,
        )

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

    backend_blocked_without_active_candidate = bool(
        state.blocker_reason and not _has_preview_candidate(state) and not state.truth_ready
    )

    if state.blocker_reason:
        blockers.append(localize_ui_message(f"Backend blocker: {state.blocker_reason}"))
        send_disabled_reason = _first_disabled_reason(
            send_disabled_reason,
            _backend_blocker_disabled_reason(state) if backend_blocked_without_active_candidate else SEND_DISABLED_BACKEND_BLOCKER_RU,
        )

    if state.post_type_key == "unknown":
        blockers.append(localize_ui_message("Selected post type is Unknown/Unsupported."))
        send_disabled_reason = _first_disabled_reason(send_disabled_reason, SEND_DISABLED_UNKNOWN_POST_RU)

    if is_post_type_mode_mismatch(state, mode):
        blockers.append(SEND_DISABLED_POST_TYPE_MODE_RU)
        send_disabled_reason = _first_disabled_reason(send_disabled_reason, SEND_DISABLED_POST_TYPE_MODE_RU)

    if _has_preview_candidate(state):
        if state.card_path is None:
            blockers.append(localize_ui_message("Preview card path is missing."))
        elif not state.card_exists:
            blockers.append(localize_ui_message("Preview card file is missing on disk."))
        if not state.caption_html and not state.caption_preview:
            blockers.append(localize_ui_message("Preview caption is missing."))

    if not state.truth_ready:
        blockers.append(localize_ui_message("Preview is not truth-ready yet."))
        send_disabled_reason = _first_disabled_reason(
            send_disabled_reason,
            _backend_blocker_disabled_reason(state) if state.blocker_reason else SEND_DISABLED_TRUTH_NOT_READY_RU,
        )

    pinned = state.pinned_publish
    if state.truth_ready or state.caption_html or state.caption_preview or state.card_path or pinned.present:
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

    if is_preview_already_published(state):
        blockers.append(localize_ui_message("This preview was already published in Telegram."))
        send_disabled_reason = SEND_DISABLED_ALREADY_PUBLISHED_RU

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


def is_post_type_mode_mismatch(
    state: PreviewState | None,
    post_type_mode: OperatorPostTypeMode | None = None,
) -> bool:
    if state is None:
        return False
    if state.post_type_key in {"", "unknown"}:
        return False
    if not state.truth_ready:
        return False
    mode = post_type_mode or default_operator_post_type_mode()
    return not mode.allows(state.post_type_key)


def is_preview_already_published(state: PreviewState) -> bool:
    if not state.last_publish.success:
        return False
    current_offer_id = _text(
        state.pinned_publish.offer_id
        or (state.selected_target.offer_id if state.selected_target is not None else "")
        or (state.fingerprint.offer_id if state.fingerprint is not None else "")
    )
    published_offer_id = _text(state.last_publish.offer_id)
    if not current_offer_id or current_offer_id != published_offer_id:
        return False

    report_path = _normalized_path(state.paths.truth_report_path or (state.fingerprint.report_path if state.fingerprint else None))
    publish_report_path = _normalized_path(state.last_publish.source_report_path)
    if report_path and publish_report_path and report_path == publish_report_path:
        return True

    current_idempotency_key = _text(
        state.pinned_publish.idempotency_key or (state.fingerprint.idempotency_key if state.fingerprint is not None else "")
    )
    published_idempotency_key = _text(state.last_publish.idempotency_key)
    if current_idempotency_key and published_idempotency_key and current_idempotency_key == published_idempotency_key:
        return True

    current_caption_hash = _text(
        state.pinned_publish.caption_hash
        or state.caption_hash
        or (state.fingerprint.caption_hash if state.fingerprint is not None else "")
    )
    current_image_hash = _text(
        state.pinned_publish.image_hash or (state.fingerprint.image_hash if state.fingerprint is not None else "")
    )
    published_caption_hash = _text(state.last_publish.caption_hash)
    published_image_hash = _text(state.last_publish.image_hash)
    return bool(
        current_caption_hash
        and current_image_hash
        and published_caption_hash
        and published_image_hash
        and current_caption_hash == published_caption_hash
        and current_image_hash == published_image_hash
    )


def build_operator_status(state: PreviewState | None, safety: SafetyState) -> OperatorStatusState:
    if state is not None and state.current_run_missing_artifact:
        next_action = localize_ui_message(f"Backend blocker: {state.current_run_backend_reason}") if state.current_run_backend_reason else SEND_DISABLED_NO_READY_POST_RU
        return OperatorStatusState(
            kind="preview_blocked",
            status_text="Новый preview не создан.",
            next_action=next_action,
            last_publish_title=state.last_publish.title,
            last_publish_offer_id=state.last_publish.offer_id,
            last_publish_message_id=state.last_publish.message_id,
            last_publish_telegram_verified=state.last_publish.telegram_verified if state.last_publish.present else None,
        )
    if _is_no_preview_loaded(state):
        if state is not None and _is_last_publish_failed(state):
            return OperatorStatusState(
                kind="failed",
                status_text="последняя публикация не выполнена",
                next_action="Проверьте причину ошибки и соберите новое превью при необходимости.",
                last_publish_title=state.last_publish.title,
                last_publish_offer_id=state.last_publish.offer_id,
                last_publish_message_id=state.last_publish.message_id,
                last_publish_telegram_verified=state.last_publish.telegram_verified,
            )
        return OperatorStatusState(
            kind="ready",
            status_text="готов к работе",
            next_action=NEXT_PREVIEW_BANNER_ACTION_RU if _should_prepare_next_post(state) else DEFAULT_PREVIEW_BANNER_ACTION_RU,
            last_publish_title=state.last_publish.title if state is not None else "",
            last_publish_offer_id=state.last_publish.offer_id if state is not None else "",
            last_publish_message_id=state.last_publish.message_id if state is not None else None,
            last_publish_telegram_verified=state.last_publish.telegram_verified
            if state is not None and state.last_publish.present
            else None,
        )

    assert state is not None
    if is_preview_already_published(state):
        return OperatorStatusState(
            kind="published",
            status_text="Этот оффер уже опубликован.",
            next_action=NEXT_PREVIEW_BANNER_ACTION_RU,
            last_publish_title=state.last_publish.title,
            last_publish_offer_id=state.last_publish.offer_id,
            last_publish_message_id=state.last_publish.message_id,
            last_publish_telegram_verified=state.last_publish.telegram_verified,
        )
    if state.blocker_reason and not _has_preview_candidate(state):
        return OperatorStatusState(
            kind="preview_blocked",
            status_text=_backend_blocker_status_text(state),
            next_action=_backend_blocker_next_action(state),
            last_publish_title=state.last_publish.title,
            last_publish_offer_id=state.last_publish.offer_id,
            last_publish_message_id=state.last_publish.message_id,
            last_publish_telegram_verified=state.last_publish.telegram_verified if state.last_publish.present else None,
        )
    if safety.send_enabled:
        return OperatorStatusState(
            kind="preview_ready",
            status_text="превью готово к публикации",
            next_action="Проверьте карточку и описание, затем отправьте в Telegram.",
            last_publish_title=state.last_publish.title,
            last_publish_offer_id=state.last_publish.offer_id,
            last_publish_message_id=state.last_publish.message_id,
            last_publish_telegram_verified=state.last_publish.telegram_verified if state.last_publish.present else None,
            current_preview_title=state.selected_target.title if state.selected_target else "",
            current_preview_offer_id=state.selected_target.offer_id if state.selected_target else "",
            current_post_type_label=state.post_type_label,
        )
    show_current_preview = bool(
        state.truth_ready
        and not state.current_run_missing_artifact
        and not state.stale
        and not is_preview_already_published(state)
    )
    return OperatorStatusState(
        kind="preview_blocked",
        status_text="превью не готово к публикации",
        next_action=safety.send_disabled_reason,
        last_publish_title=state.last_publish.title,
        last_publish_offer_id=state.last_publish.offer_id,
        last_publish_message_id=state.last_publish.message_id,
        last_publish_telegram_verified=state.last_publish.telegram_verified if state.last_publish.present else None,
        current_preview_title=state.selected_target.title if show_current_preview and state.selected_target else "",
        current_preview_offer_id=state.selected_target.offer_id if show_current_preview and state.selected_target else "",
        current_post_type_label=state.post_type_label if show_current_preview else "",
    )


def _has_preview_candidate(state: PreviewState) -> bool:
    return state.selected_target is not None and bool(state.selected_target.offer_id or state.selected_target.title)


def _has_already_published_blocker(state: PreviewState) -> bool:
    if state.blocker_reason == "already_published":
        return True
    detail = _text(state.blocker_detail or state.current_run_backend_reason)
    if "blocked:already_published_recently" in detail:
        return True
    return any("blocked:already_published_recently" in item for item in state.selection_diagnostics)


def _backend_blocker_disabled_reason(state: PreviewState) -> str:
    if _has_already_published_blocker(state):
        return SEND_DISABLED_ALREADY_PUBLISHED_RU
    if state.blocker_reason == "already_sent_finalize_only":
        return SEND_DISABLED_ALREADY_SENT_RU
    if state.blocker_reason in {
        "queue_empty",
        "planner_window_empty",
        "no_publishable_candidate",
        "controlled_reserve_release_held",
        "quiet_hours_reserve_hidden",
    }:
        return SEND_DISABLED_NO_READY_POST_RU
    return SEND_DISABLED_BACKEND_BLOCKER_RU


def _backend_blocker_status_text(state: PreviewState) -> str:
    if _has_already_published_blocker(state):
        return "Этот оффер уже опубликован."
    return "Нет готового поста для публикации."


def _backend_blocker_next_action(state: PreviewState) -> str:
    if _has_already_published_blocker(state):
        return NEXT_PREVIEW_BANNER_ACTION_RU
    if state.blocker_detail:
        return localize_ui_message(state.blocker_detail)
    if state.blocker_reason:
        return localize_ui_message(f"Backend blocker: {state.blocker_reason}")
    return SEND_DISABLED_NO_READY_POST_RU


def _first_disabled_reason(current: str, candidate: str) -> str:
    if current == SEND_DISABLED_REASON_RU:
        return candidate
    return current


def _is_no_preview_loaded(state: PreviewState | None) -> bool:
    if state is None:
        return True
    has_target = state.selected_target is not None and bool(state.selected_target.offer_id or state.selected_target.title)
    has_report = bool(state.paths.truth_report_path and state.report_exists)
    has_preview_payload = bool(state.truth_ready or state.pinned_publish.present or state.caption_html or state.caption_preview or state.card_path)
    return not (has_target or has_report or has_preview_payload)


def _text(value: object) -> str:
    return str(value or "").strip()


def _should_prepare_next_post(state: PreviewState | None) -> bool:
    if state is None:
        return False
    if is_preview_already_published(state):
        return True
    return _is_no_preview_loaded(state) and state.last_publish.success


def _is_last_publish_failed(state: PreviewState) -> bool:
    return bool(
        state.last_publish.present
        and not state.last_publish.success
        and (state.last_publish.workflow_status == "failed" or not state.last_publish.published)
    )


def _normalized_path(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def _dedupe(values: list[str]) -> list[str]:
    ordered: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in ordered:
            ordered.append(text)
    return ordered
