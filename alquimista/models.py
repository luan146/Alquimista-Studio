from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = 4


class AuthMode(StrEnum):
    PUBLIC = "public"
    BROWSER = "browser_session"
    BASIC = "basic"
    BEARER = "bearer"


class ConnectorStatus(StrEnum):
    """Operational state shown by the application for a connector."""

    AVAILABLE = "available"
    EXPERIMENTAL = "experimental"
    DEVELOPMENT = "development"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"


class EntryStatus(StrEnum):
    NEW = "new"
    UPDATED = "updated"
    METADATA_UPDATED = "metadata_updated"
    FORMAT_UPDATED = "format_updated"
    UNCHANGED = "unchanged"
    REPAIRED = "repaired"
    PRESERVED_AFTER_ERROR = "preserved_after_error"
    EMPTY_SKIPPED = "empty_skipped"
    UNSELECTED = "unselected"
    REMOVED = "removed"
    FAILED = "failed"
    SOURCE_DISABLED = "source_disabled"
    SOURCE_REMOVED = "source_removed"


class Model(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class ConnectorCapabilities(Model):
    """Capabilities exposed by a knowledge-source connector."""

    supports_collections: bool = False
    supports_hierarchy: bool = False
    supports_incremental_updates: bool = False
    supports_attachments: bool = False
    supports_permissions: bool = False
    supports_search: bool = False
    supports_archived_content: bool = False
    supports_updated_at: bool = False
    supports_webhooks: bool = False
    supports_public_access: bool = False
    supports_oauth: bool = False
    supports_bearer_token: bool = False
    supports_multiple_languages: bool = False
    supports_document_download: bool = False
    supports_lazy_discovery: bool = False


class KnowledgeSource(Model):
    id: str
    source_type: str
    name: str
    base_url: str
    connector_version: str = "1"
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeContainer(Model):
    id: str
    key: str | None = None
    name: str
    description: str | None = None
    container_type: str
    source_type: str
    parent_id: str | None = None
    updated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeDocumentMetadata(Model):
    id: str
    container_id: str
    parent_id: str | None = None
    title: str
    original_url: str = ""
    updated_at: datetime | None = None
    created_at: datetime | None = None
    etag: str | None = None
    has_children: bool = False
    document_type: str = "document"
    path: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeDocument(Model):
    id: str
    container_id: str
    parent_id: str | None = None
    title: str
    content: str = ""
    original_url: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    etag: str | None = None
    source_type: str
    container_name: str = ""
    path: list[str] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSelection(Model):
    source_id: str
    container_id: str
    document_id: str
    selected: bool = True

    @property
    def document_key(self) -> str:
        return f"{self.source_id}:{self.container_id}:{self.document_id}"


SOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def validate_source_identifier(value: str) -> str:
    value = value.strip()
    if not SOURCE_ID_PATTERN.fullmatch(value):
        raise ValueError(
            "O identificador da fonte deve conter apenas letras ASCII, números, "
            "hífen ou sublinhado e ter no máximo 128 caracteres."
        )
    return value


class SourceConfig(Model):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str = "Nova fonte"
    source_type: str = "confluence_rest"
    base_url: str = ""
    space_key: str = ""
    space_name: str = ""
    root_mode: Literal["title", "id", "space"] = "title"
    root_value: str = ""
    root_page_id: str = ""
    auth_mode: AuthMode = AuthMode.PUBLIC
    username: str = ""
    include_root: bool = False
    enabled: bool = True
    # Non-secret connector-specific settings. Secrets remain runtime-only.
    connector_options: dict[str, Any] = Field(default_factory=dict)
    selected_page_ids: list[str] = Field(default_factory=list)
    consolidation_excluded_page_ids: list[str] = Field(default_factory=list)
    # Accepted only while loading schema v2. It is never exported.
    state_file: str | None = Field(default=None, exclude=True)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        return validate_source_identifier(value)

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value:
            return ""
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("A URL deve começar com http:// ou https:// e conter um host.")
        if parsed.username or parsed.password:
            raise ValueError("Não inclua usuário ou senha na URL.")
        return value

    @model_validator(mode="after")
    def require_https_for_authenticated_access(self) -> "SourceConfig":
        if self.base_url and self.auth_mode != AuthMode.PUBLIC and urlparse(self.base_url).scheme != "https":
            raise ValueError("A autenticação exige uma URL HTTPS.")
        return self

    @field_validator("connector_options")
    @classmethod
    def reject_secret_options(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Prevent accidental persistence of credentials in project files."""
        forbidden = ("token", "secret", "password", "cookie", "refresh", "authorization")
        for key in value:
            if any(part in str(key).casefold() for part in forbidden):
                raise ValueError(
                    "Credenciais devem permanecer somente durante a sessão; "
                    "não inclua segredos na configuração do projeto."
                )
        return value

    @property
    def source_slug(self) -> str:
        return f"{slugify(self.name)}_{self.id[:8]}"


class MarkdownOptions(Model):
    metadata_style: Literal["markdown", "yaml", "both", "none"] = "markdown"
    title_heading_level: int = Field(1, ge=1, le=6)
    include_title: bool = True
    include_page_id: bool = False
    include_source_url: bool = True
    include_source_name: bool = False
    include_space_key: bool = False
    include_space_name: bool = False
    include_root: bool = False
    include_module: bool = True
    include_submodule: bool = False
    include_path: bool = True
    include_version: bool = False
    include_updated_at: bool = True
    include_author: bool = False
    include_labels: bool = False
    include_hash: bool = True
    include_collected_at: bool = False
    include_status: bool = False
    include_document_markers: bool = False
    marker_include_ids: bool = True
    include_content_heading: bool = True
    content_heading_text: str = "Conteúdo técnico"
    include_empty_pages: bool = False
    include_images: bool = True
    include_image_alt_text: bool = True
    include_attachments: bool = True
    include_videos: bool = True
    include_links: bool = True
    include_tables: bool = True
    include_code_blocks: bool = True
    include_panels: bool = True
    include_expand_macros: bool = True
    include_content_macros: bool = True
    remove_html_comments: bool = True
    remove_noise: bool = True
    normalize_spaces: bool = True
    absolute_links: bool = True
    separators: bool = True
    auto_demote_headings: bool = False
    hash_scope: Literal["content", "title_content", "stable_metadata"] = "title_content"

    def signature(self) -> str:
        return stable_json_hash(self.model_dump())

    @classmethod
    def preset(cls, name: str) -> "MarkdownOptions":
        presets: dict[str, dict[str, Any]] = {
            "minimum": {
                "metadata_style": "none",
                "include_page_id": False,
                "include_source_url": False,
                "include_source_name": False,
                "include_space_key": False,
                "include_root": False,
                "include_module": False,
                "include_submodule": False,
                "include_path": False,
                "include_version": False,
                "include_updated_at": False,
                "include_hash": False,
                "include_document_markers": False,
            },
            "recommended": {},
            "traceability": {
                "metadata_style": "both",
                "include_space_name": True,
                "include_author": True,
                "include_labels": True,
                "include_collected_at": True,
                "include_status": True,
            },
            "rag": {
                "metadata_style": "yaml",
                "include_space_name": True,
                "include_author": True,
                "include_labels": True,
                "include_status": True,
                "include_document_markers": True,
                "marker_include_ids": True,
            },
        }
        if name not in presets:
            raise ValueError(f"Predefinição desconhecida: {name}")
        return cls(**presets[name])


class ExtractionOptions(Model):
    # Individual Markdown files are kept separate from consolidated packages.
    pages_subdir: str = "arquivos_soltos"
    path_layout: Literal["source_space", "source", "space", "flat"] = "source_space"
    use_version_shortcut: bool = True
    force_reprocess: bool = False
    cleanup_unselected_files: bool = False
    keep_unselected_manifest_entries: bool = True
    detect_remote_removals: bool = True
    delete_removed_files: bool = False
    preserve_previous_on_error: bool = True
    retry_count: int = Field(3, ge=1, le=10)
    connect_timeout_seconds: int = Field(15, ge=3, le=300)
    timeout_seconds: int = Field(60, ge=5, le=600)
    request_delay_ms: int = Field(150, ge=0, le=60_000)
    max_requests_per_second: float = Field(4.0, ge=0.1, le=100)
    proxy_mode: Literal["system", "direct", "custom"] = "system"
    proxy_url: str = ""
    # Optional overrides for lazy discovery budgets. When None (the default) the
    # connector falls back to its module-level constants, keeping historical
    # behavior and existing tests that monkeypatch those constants intact.
    lazy_max_items: int | None = Field(None, ge=1, le=100_000)
    lazy_batch_limit: int | None = Field(None, ge=1, le=1000)

    @field_validator("pages_subdir")
    @classmethod
    def safe_subdir(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("A subpasta de páginas deve permanecer dentro da base.")
        return str(path)

    @field_validator("proxy_url")
    @classmethod
    def safe_proxy(cls, value: str) -> str:
        if not value:
            return ""
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Proxy inválido.")
        if parsed.username or parsed.password:
            raise ValueError("Credenciais não podem ser incluídas no proxy.")
        return value


class ConsolidationOptions(Model):
    enabled: bool = True
    # Consolidated packages always live in their own child directory.
    output_subdir: str = "arquivos_consolidados"
    grouping: Literal[
        "single",
        "source",
        "space",
        "module",
        "module_submodule",
        "source_module",
        "source_module_submodule",
        "manual",
    ] = "module"
    module_depth: int = Field(
        1,
        ge=1,
        le=10,
        description="Quantidade de níveis da hierarquia usada para agrupar módulos.",
    )
    max_pages: int = Field(100, ge=1, le=10_000)
    max_chars: int = Field(2_000_000, ge=1_000)
    clean_output: bool = True
    active_only: bool = True
    selected_only: bool = True
    include_package_header: bool = False
    include_package_index: bool = True
    include_source_links_in_index: bool = True
    include_ids_in_index: bool = True
    include_page_separator: bool = True
    include_hierarchy_headings: bool = False
    include_package_manifest: bool = True
    demote_page_headings: int = Field(0, ge=0, le=5)
    filename_prefix: str = ""
    sort_mode: Literal["path", "title", "updated", "id"] = "path"
    manual_groups: dict[str, str] = Field(default_factory=dict)

    @field_validator("output_subdir")
    @classmethod
    def safe_subdir(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("A saída consolidada deve permanecer dentro da base.")
        return str(path)


class ProjectConfig(Model):
    schema_version: int = SCHEMA_VERSION
    project_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    project_name: str = "Projeto ALQuimista"
    output_dir: str = "ALQuimista_Base"
    sources: list[SourceConfig] = Field(default_factory=list)
    selections: list[KnowledgeSelection] = Field(default_factory=list)
    markdown: MarkdownOptions = Field(default_factory=MarkdownOptions)
    extraction: ExtractionOptions = Field(default_factory=ExtractionOptions)
    consolidation: ConsolidationOptions = Field(default_factory=ConsolidationOptions)

    @model_validator(mode="after")
    def unique_sources(self) -> "ProjectConfig":
        ids = [source.id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("O projeto contém fontes com identificadores duplicados.")
        return self

    def to_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["schema_version"] = self.schema_version
        for source in data["sources"]:
            source.pop("state_file", None)
        return data

    def selected_keys_for(self, source_id: str) -> set[str]:
        """Return the new global selection keys plus legacy page selections."""
        # Import lazily to keep the domain models independent from the state
        # service while still centralizing selection semantics.
        from .selection import SelectionStore

        selected = SelectionStore.from_selections(self.selections).keys_for_source(source_id)
        source = next((item for item in self.sources if item.id == source_id), None)
        # New selections carry the source/container/document identity and are
        # authoritative. Mixing them with the old page-id-only list duplicates
        # every item in counts and makes high-volume selection unnecessarily
        # expensive. Keep the fallback only for projects migrated from the old
        # format, where no structured selection exists yet.
        has_structured_source_selection = any(
            item.source_id == source_id for item in self.selections
        )
        if source and not has_structured_source_selection:
            selected.update(
                f"{source.id}:{source.space_key}:{page_id}"
                for page_id in source.selected_page_ids
            )
        return selected

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectConfig":
        migrated = dict(data)
        version = int(migrated.get("schema_version", 2))
        if version < SCHEMA_VERSION:
            # Keep the historical v2 -> v3 behavior for one save cycle. A
            # subsequent load upgrades the same file to the connector schema.
            migrated["schema_version"] = 3 if version < 3 else SCHEMA_VERSION
            migrated.setdefault("project_id", uuid.uuid4().hex)
            for source in migrated.get("sources", []):
                source.setdefault("source_type", "confluence_rest")
                source.setdefault("space_name", "")
                source.setdefault("root_page_id", "")
                source.setdefault("consolidation_excluded_page_ids", [])
            selections = migrated.setdefault("selections", [])
            for source in migrated.get("sources", []):
                container_id = str(source.get("space_key", "") or "__legacy__")
                for page_id in source.get("selected_page_ids", []) or []:
                    candidate = {
                        "source_id": str(source.get("id", "")),
                        "container_id": container_id,
                        "document_id": str(page_id),
                        "selected": True,
                    }
                    if candidate not in selections:
                        selections.append(candidate)
            extraction = migrated.setdefault("extraction", {})
            extraction.setdefault("connect_timeout_seconds", 15)
            extraction.setdefault("max_requests_per_second", 4.0)
            extraction.setdefault("proxy_mode", "system")
            extraction.setdefault("proxy_url", "")
        return cls.model_validate(migrated)


class ManifestEntry(Model):
    schema_version: int = SCHEMA_VERSION
    source_id: str
    source_type: str = "confluence_rest"
    container_id: str = ""
    container_type: str = ""
    container_name: str = ""
    document_id: str = ""
    parent_id: str | None = None
    page_id: str
    document_key: str
    title: str
    source_url: str = ""
    source_name: str = ""
    space_key: str = ""
    space_name: str = ""
    root_page_id: str = ""
    root_title: str = ""
    module: str = ""
    submodule: str = ""
    path: list[str] = Field(default_factory=list)
    ancestors: list[dict[str, str]] = Field(default_factory=list)
    confluence_version: int | None = None
    created_at: str | None = None
    document_type: str = "document"
    metadata: dict[str, Any] = Field(default_factory=dict)
    author: str = ""
    labels: list[str] = Field(default_factory=list)
    updated_at: str | None = None
    etag: str | None = None
    collected_at: str | None = None
    checked_at: str | None = None
    first_collected_at: str | None = None
    last_successful_at: str | None = None
    content_hash: str = ""
    metadata_hash: str = ""
    transform_config_hash: str = ""
    document_hash: str = ""
    markdown_path: str = ""
    packages: list[str] = Field(default_factory=list)
    status: EntryStatus = EntryStatus.NEW
    error_message: str = ""
    active: bool = True
    selected: bool = True


class ManifestDocument(Model):
    schema_version: int = SCHEMA_VERSION
    project_id: str = ""
    project_name: str = ""
    generated_at: str = ""
    entries: list[ManifestEntry] = Field(default_factory=list)


def stable_json_hash(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def slugify(value: str, maxlen: int = 80) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value.casefold())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return (normalized or "fonte")[:maxlen]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def default_project() -> ProjectConfig:
    return ProjectConfig(
        sources=[
            SourceConfig(name="Nova fonte"),
        ]
    )
