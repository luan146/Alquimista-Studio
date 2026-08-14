from __future__ import annotations

from datetime import datetime
from typing import Any

from ...client import ConfluenceClient
from ...connectors import ConnectorRegistry, KnowledgeSourceConnector, default_registry
from ...errors import AlquimistaError
from ...models import (
    KnowledgeContainer,
    KnowledgeDocumentMetadata,
    ProjectConfig,
    now_iso,
)
from ...runtime import CancellationToken
from ...services import SelectedDocumentRef, SourceRuntime


class RuntimeSecrets:
    """Small in-memory vault. Secrets are never serialized or logged."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def get(self, source_id: str, default: str = "") -> str:
        return self._values.get(source_id, default)

    def set(self, source_id: str, secret: str) -> None:
        if secret:
            self._values[source_id] = secret
        else:
            self._values.pop(source_id, None)

    def pop(self, source_id: str, default: None = None) -> str | None:
        return self._values.pop(source_id, default)

    def clear(self) -> None:
        self._values.clear()


class RuntimeBuilder:
    """Build extraction inputs without coupling network work to Qt widgets."""

    def __init__(
        self,
        trees: dict[str, dict[str, Any]],
        secrets: RuntimeSecrets,
        registry: ConnectorRegistry | None = None,
    ) -> None:
        self.trees = trees
        self.secrets = secrets
        self.registry = registry or default_registry()

    def build(
        self,
        project: ProjectConfig,
        token: CancellationToken,
        log: Any,
    ) -> list[SourceRuntime]:
        import alquimista.ui.controllers as c_mod
        confluence_client_cls = getattr(c_mod, "ConfluenceClient", ConfluenceClient)

        runtimes: list[SourceRuntime] = []
        for source in project.sources:
            token.check()
            if not source.enabled:
                continue
            if source.source_type != "confluence_rest":
                raise AlquimistaError(
                    "O RuntimeBuilder legado aceita apenas confluence_rest; "
                    "use build_connectors para outros conectores."
                )
            data = self.trees.get(source.id)
            if data is None:
                log(f"Carregando árvore de {source.name}…")
                with confluence_client_cls(
                    source,
                    project.extraction,
                    secret=self.secrets.get(source.id),
                    token=token,
                    log=log,
                ) as client:
                    root, pages = client.fetch_tree()
                data = {"root": root, "pages": pages, "loaded_at": now_iso()}
            runtimes.append(
                SourceRuntime(
                    source,
                    data["root"],
                    {str(page["id"]): page for page in data["pages"]},
                    list(source.selected_page_ids),
                    self.secrets.get(source.id),
                )
            )
        if not runtimes or not any(runtime.selected_page_ids for runtime in runtimes):
            raise AlquimistaError("Nenhuma fonte ativa possui páginas selecionadas.")
        return runtimes

    @staticmethod
    def _selected_available_keys(
        project: ProjectConfig,
        source: Any,
        available: set[str],
    ) -> set[str]:
        """Resolve UI selections without falling back to every discovered page."""
        requested = project.selected_keys_for(source.id)
        exact = requested.intersection(available)
        has_structured = any(
            item.source_id == source.id for item in project.selections
        )
        if has_structured:
            return exact
        legacy_ids = {str(item) for item in source.selected_page_ids or []}
        return {
            key
            for key in available
            if key in legacy_ids or key.rsplit(":", 1)[-1] in legacy_ids
        }

    @staticmethod
    def _snapshot_metadata(
        connector: Any,
        raw: Any,
        container_id: str,
    ) -> KnowledgeDocumentMetadata | None:
        if isinstance(raw, KnowledgeDocumentMetadata):
            return raw
        if not isinstance(raw, dict):
            return None
        normalizer = getattr(connector, "_metadata", None)
        if callable(normalizer):
            try:
                return normalizer(raw, container_id)
            except (AttributeError, KeyError, TypeError, ValueError):
                # The UI snapshot is intentionally connector-neutral; use the
                # common mapping below when a private connector adapter rejects
                # a stale row.
                pass
        page_id = str(raw.get("id") or "")
        if not page_id:
            return None
        version = raw.get("version") or {}
        updated = raw.get("updated_at") or version.get("when")
        if isinstance(updated, str):
            try:
                updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            except ValueError:
                updated = None
        if not isinstance(updated, datetime):
            updated = None
        ancestors = list(raw.get("ancestors") or [])
        path = list(raw.get("path") or [])
        if not path:
            path = [str(item.get("title", "")) for item in ancestors if item.get("title")]
            if raw.get("title"):
                path.append(str(raw["title"]))
        space = raw.get("space") or {}
        return KnowledgeDocumentMetadata(
            id=page_id,
            container_id=str(raw.get("_container_id") or container_id),
            parent_id=str(raw.get("parent_id") or "") or None,
            title=str(raw.get("title") or page_id),
            original_url=str(raw.get("original_url") or ""),
            updated_at=updated,
            etag=raw.get("etag"),
            has_children=bool(raw.get("has_children") or raw.get("hasChildren")),
            document_type=str(raw.get("type") or raw.get("document_type") or "document"),
            path=path,
            metadata={
                **dict(raw.get("metadata") or {}),
                "space_key": str(space.get("key") or container_id),
                "space_name": str(space.get("name") or ""),
                "ancestors": ancestors,
                "confluence_version": version.get("number"),
            },
        )

    def build_connectors(
        self,
        project: ProjectConfig,
        token: CancellationToken,
        log: Any,
    ) -> list[SourceRuntime]:
        """Build runtimes from selected references without remote inventory scans."""
        runtimes: list[SourceRuntime] = []
        for source in project.sources:
            token.check()
            if not source.enabled:
                continue
            requested_keys = project.selected_keys_for(source.id)
            if not requested_keys:
                log(
                    f"[Runtime] Fonte {source.id} ({source.name}) ignorada: "
                    "nenhum documento selecionado."
                )
                continue
            connector: KnowledgeSourceConnector | None = self.registry.create(
                source,
                options=project.extraction,
                markdown_options=project.markdown,
                secret=self.secrets.get(source.id),
                token=token,
                log=log,
            )
            assert connector is not None
            try:
                log(
                    f"[Runtime] Fonte {source.id} ({source.name}); "
                    f"tipo={source.source_type}; base_url={source.base_url or '<vazia>'}; "
                    f"space_key={source.space_key or '<não definido>'}"
                )
                snapshot = self.trees.get(source.id) or {}
                pages_by_container = snapshot.get("pages_by_container") or {}
                structured = [
                    item
                    for item in project.selections
                    if item.source_id == source.id and item.selected
                ]
                if structured:
                    requested_refs = [
                        (str(item.container_id), str(item.document_id))
                        for item in structured
                    ]
                else:
                    requested_refs = []
                    for key in requested_keys:
                        parts = key.split(":", 2)
                        if len(parts) == 3 and parts[0] == source.id:
                            requested_refs.append((parts[1], parts[2]))
                        else:
                            requested_refs.append(
                                (str(source.space_key or "__legacy__"), str(key))
                            )
                if not requested_refs:
                    continue
                documents: dict[str, dict[str, KnowledgeDocumentMetadata]] = {}
                selected_documents: list[SelectedDocumentRef] = []
                container_map: dict[str, KnowledgeContainer] = {}
                seen: set[str] = set()
                for container_id, document_id in requested_refs:
                    token.check()
                    key = f"{source.id}:{container_id}:{document_id}"
                    if key in seen:
                        continue
                    seen.add(key)
                    raw_items = pages_by_container.get(container_id) or []
                    metadata = next(
                        (
                            item
                            for raw in raw_items
                            if (item := self._snapshot_metadata(connector, raw, container_id))
                            and str(item.id) == document_id
                        ),
                        None,
                    )
                    if metadata is None:
                        metadata = KnowledgeDocumentMetadata(
                            id=document_id,
                            container_id=container_id,
                            title=document_id,
                            metadata={"synthetic": True},
                        )
                    documents.setdefault(container_id, {})[document_id] = metadata
                    container_map.setdefault(
                        container_id,
                        KnowledgeContainer(
                            id=container_id,
                            key=container_id,
                            name=container_id,
                            container_type="container",
                            source_type=source.source_type,
                        ),
                    )
                    selected_documents.append(
                        SelectedDocumentRef(
                            source_id=source.id,
                            container_id=container_id,
                            document_id=document_id,
                            metadata=metadata,
                            summary_trusted=not bool(metadata.metadata.get("synthetic")),
                        )
                    )
                runtimes.append(
                    SourceRuntime(
                        source=source,
                        root={},
                        pages_by_id={},
                        selected_page_ids=[
                            item.document_key for item in selected_documents
                        ],
                        secret=self.secrets.get(source.id),
                        connector=connector,
                        containers=container_map,
                        documents_by_container=documents,
                        inventory_complete_containers=set(),
                        selected_documents=selected_documents,
                    )
                )
                connector = None
            finally:
                if connector is not None:
                    connector.close()
        if not runtimes or not any(runtime.selected_page_ids for runtime in runtimes):
            raise AlquimistaError(
                "Nenhuma fonte ativa possui documentos selecionados. "
                "Selecione ao menos uma página antes de executar."
            )
        return runtimes


__all__ = ["RuntimeBuilder", "RuntimeSecrets"]
