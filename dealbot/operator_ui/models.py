from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SourceHealth:
    name: str
    status: str
    reason: str
    offers: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SelectedTarget:
    candidate_id: str = ""
    row_id: str = ""
    title: str = ""
    offer_id: str = ""
    source: str = ""
    platform: str = ""
    post_type: str = ""
    lane: str = ""
    bucket: str = ""
    status: str = ""
    blocker_reason: str = ""
    blocker_detail: str = ""
    already_published: bool = False
    content_family: str = ""
    recommended_post_mode: str = ""
    store_url: str = ""
    current_price: int | float | None = None
    old_price: int | float | None = None
    discount: int | float | None = None
    reviews: int | None = None
    positive_pct: int | float | None = None
    score: int | float | None = None
    total_priority: int | float | None = None
    created_at: str = ""


@dataclass(slots=True)
class CandidateRow:
    candidate_id: str = ""
    row_id: str = ""
    title: str = ""
    offer_id: str = ""
    source: str = ""
    platform: str = ""
    post_type: str = ""
    current_price: int | float | None = None
    old_price: int | float | None = None
    discount: int | float | None = None
    reviews: int | None = None
    positive_pct: int | float | None = None
    status: str = ""
    blocker_reason: str = ""
    blocker_detail: str = ""
    already_published: bool = False
    bucket: str = ""
    lane: str = ""
    score: int | float | None = None
    total_priority: int | float | None = None
    recommended_post_mode: str = ""
    store_url: str = ""
    created_at: str = ""

    @property
    def stable_candidate_id(self) -> str:
        return str(self.candidate_id or self.row_id).strip()


@dataclass(slots=True)
class PreviewPaths:
    workflow_path: Path | None = None
    truth_report_path: Path | None = None
    image_path: Path | None = None
    latest_snapshot_manifest_path: Path | None = None
    latest_publish_outcome_path: Path | None = None
    latest_publish_workflow_path: Path | None = None
    output_dir: Path | None = None


@dataclass(slots=True)
class PreviewFingerprint:
    workflow_path: Path | None = None
    truth_report_path: Path | None = None
    report_path: Path | None = None
    run_key: str | None = None
    offer_id: str | None = None
    selected_offer_id: str | None = None
    idempotency_key: str | None = None
    caption_hash: str | None = None
    image_hash: str | None = None
    image_path: Path | None = None


@dataclass(slots=True)
class ArtifactBundle:
    project_root: Path
    output_dir: Path
    workflow_path: Path | None = None
    truth_report_path: Path | None = None
    workflow_payload: dict[str, Any] | None = None
    truth_payload: dict[str, Any] | None = None
    latest_snapshot_manifest_path: Path | None = None
    latest_publish_outcome_path: Path | None = None
    latest_publish_workflow_path: Path | None = None
    latest_publish_workflow_payload: dict[str, Any] | None = None
    latest_publish_outcome_payload: dict[str, Any] | None = None
    publish_history_records: list[dict[str, Any]] = field(default_factory=list)
    ambiguous: bool = False
    stale: bool = False
    reused_latest_preview: bool = False
    current_run_missing_artifact: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class OperatorPostTypeMode:
    key: str
    label: str
    allowed_post_types: frozenset[str]

    def allows(self, post_type_key: str) -> bool:
        return post_type_key in self.allowed_post_types


@dataclass(slots=True)
class PinnedPublishState:
    contract_version: int | None = None
    source: str = ""
    created_at: str | None = None
    report_run_key: str | None = None
    offer_id: str | None = None
    title: str = ""
    idempotency_key: str | None = None
    caption_html: str = ""
    caption_preview: str = ""
    caption_hash: str | None = None
    image_path: Path | None = None
    image_hash: str | None = None
    template_id: str | None = None
    card_family: str | None = None
    assets_used: list[str] = field(default_factory=list)
    render_diagnostics: dict[str, Any] = field(default_factory=dict)
    caption_debug: dict[str, Any] = field(default_factory=dict)
    image_exists: bool = False
    caption_hash_verified: bool = False
    image_hash_verified: bool = False

    @property
    def present(self) -> bool:
        return self.contract_version is not None

    @property
    def supported_contract(self) -> bool:
        return self.contract_version == 1


@dataclass(slots=True)
class LastPublishState:
    workflow_path: Path | None = None
    publish_outcome_path: Path | None = None
    created_at: str | None = None
    workflow_modified_at: str | None = None
    publish_outcome_modified_at: str | None = None
    command: str = ""
    workflow_status: str = ""
    title: str = ""
    offer_id: str = ""
    message_id: int | None = None
    published: bool = False
    telegram_verified: bool = False
    outbox_status: str = ""
    reason: str = ""
    source_report_path: Path | None = None
    idempotency_key: str | None = None
    caption_hash: str | None = None
    image_hash: str | None = None
    image_path: Path | None = None

    @property
    def present(self) -> bool:
        return self.workflow_path is not None

    @property
    def success(self) -> bool:
        return self.published and self.telegram_verified and self.message_id is not None


@dataclass(slots=True)
class OperatorStatusState:
    kind: str
    status_text: str
    next_action: str
    last_publish_title: str = ""
    last_publish_offer_id: str = ""
    last_publish_message_id: int | None = None
    last_publish_telegram_verified: bool | None = None
    current_preview_title: str = ""
    current_preview_offer_id: str = ""
    current_post_type_label: str = ""


@dataclass(slots=True)
class PreviewState:
    project_root: Path
    status_text: str
    verdict: str = ""
    truth_ready: bool = False
    telegram_verified: bool = False
    post_type_key: str = "unknown"
    post_type_label: str = "Unknown/Unsupported"
    selected_target: SelectedTarget | None = None
    preview_candidate_id: str = ""
    candidate_rows: list[CandidateRow] = field(default_factory=list)
    caption_html: str = ""
    caption_preview: str = ""
    caption_hash: str | None = None
    card_path: Path | None = None
    card_exists: bool = False
    blocker_category: str | None = None
    blocker_reason: str | None = None
    blocker_detail: str | None = None
    ingest_sources: list[SourceHealth] = field(default_factory=list)
    paths: PreviewPaths = field(default_factory=PreviewPaths)
    ambiguous: bool = False
    stale: bool = False
    current_run_missing_artifact: bool = False
    current_run_backend_reason: str | None = None
    selection_diagnostics: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    run_key: str | None = None
    created_at: str | None = None
    command_status: str = ""
    report_exists: bool = False
    pinned_publish: PinnedPublishState = field(default_factory=PinnedPublishState)
    last_publish: LastPublishState = field(default_factory=LastPublishState)
    publish_history: list[LastPublishState] = field(default_factory=list)
    fingerprint: PreviewFingerprint | None = None

    @classmethod
    def empty(cls, project_root: Path) -> PreviewState:
        output_dir = project_root / "output"
        return cls(
            project_root=project_root,
            status_text="No preview loaded.",
            paths=PreviewPaths(output_dir=output_dir),
            warnings=["Run Preview or Refresh Local State to load the latest operator artifacts."],
        )


@dataclass(slots=True)
class SafetyState:
    send_enabled: bool
    send_disabled_reason: str
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    preview_ready: bool = False


SUPPORTED_OPERATOR_POST_TYPES = frozenset({"single_discount", "freebie", "roundup", "roundup_toplist", "toplist"})

OPERATOR_POST_TYPE_MODES = (
    OperatorPostTypeMode(
        key="single_discount",
        label="Одиночные скидки",
        allowed_post_types=frozenset({"single_discount"}),
    ),
    OperatorPostTypeMode(
        key="freebie",
        label="Раздачи",
        allowed_post_types=frozenset({"freebie"}),
    ),
    OperatorPostTypeMode(
        key="roundup",
        label="Подборки",
        allowed_post_types=frozenset({"roundup", "roundup_toplist", "toplist"}),
    ),
    OperatorPostTypeMode(
        key="any",
        label="Любой тип",
        allowed_post_types=SUPPORTED_OPERATOR_POST_TYPES,
    ),
)


def default_operator_post_type_mode() -> OperatorPostTypeMode:
    return OPERATOR_POST_TYPE_MODES[0]


def get_operator_post_type_mode(key: str | None) -> OperatorPostTypeMode:
    normalized = str(key or "").strip()
    for mode in OPERATOR_POST_TYPE_MODES:
        if mode.key == normalized:
            return mode
    return default_operator_post_type_mode()
