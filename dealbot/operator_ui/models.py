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
    title: str = ""
    offer_id: str = ""
    source: str = ""
    lane: str = ""
    bucket: str = ""
    content_family: str = ""
    recommended_post_mode: str = ""
    store_url: str = ""


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
    ambiguous: bool = False
    stale: bool = False
    warnings: list[str] = field(default_factory=list)


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

    @property
    def present(self) -> bool:
        return self.workflow_path is not None

    @property
    def success(self) -> bool:
        return self.published and self.telegram_verified and self.message_id is not None


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
    warnings: list[str] = field(default_factory=list)
    run_key: str | None = None
    created_at: str | None = None
    command_status: str = ""
    report_exists: bool = False
    pinned_publish: PinnedPublishState = field(default_factory=PinnedPublishState)
    last_publish: LastPublishState = field(default_factory=LastPublishState)
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
