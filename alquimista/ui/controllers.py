from __future__ import annotations

from typing import Any

from ..client import ConfluenceClient
from ..connectors import ConnectorRegistry, KnowledgeSourceConnector, default_registry
from ..errors import AlquimistaError
from ..models import ProjectConfig, now_iso
from ..runtime import CancellationToken
from ..services import SourceRuntime


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
        runtimes: list[SourceRuntime] = []
        for source in project.sources:
            token.check()
            if not source.enabled:
                continue
            data = self.trees.get(source.id)
            if data is None:
                log(f"Carregando árvore de {source.name}…")
                with ConfluenceClient(
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

    def build_connectors(
        self,
        project: ProjectConfig,
        token: CancellationToken,
        log: Any,
    ) -> list[SourceRuntime]:
        """Build runtimes from the canonical structured selection only."""
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
                log(f"Descobrindo contêineres de {source.name}…")
                containers = connector.list_containers()
                if source.source_type == "confluence_rest" and source.space_key:
                    containers = [
                        item for item in containers if item.id == source.space_key
                    ]
                structured_selection = any(
                    item.source_id == source.id for item in project.selections
                )
                selected_container_ids = {
                    parts[1]
                    for key in requested_keys
                    if (parts := key.split(":", 2))
                    and len(parts) == 3
                    and parts[0] == source.id
                    and parts[1]
                }
                if structured_selection and selected_container_ids:
                    selected_containers = [
                        item for item in containers if str(item.id) in selected_container_ids
                    ]
                    if selected_containers:
                        containers = selected_containers
                container_map = {str(item.id): item for item in containers}
                documents: dict[str, dict[str, Any]] = {}
                available: set[str] = set()
                for container in containers:
                    token.check()
                    metadata = connector.list_documents(container.id)
                    documents[str(container.id)] = {
                        str(item.id): item for item in metadata
                    }
                    available.update(
                        f"{source.id}:{container.id}:{item.id}" for item in metadata
                    )
                selected_keys = self._selected_available_keys(
                    project, source, available
                )
                if not selected_keys:
                    continue
                runtimes.append(
                    SourceRuntime(
                        source=source,
                        root={},
                        pages_by_id={},
                        selected_page_ids=sorted(selected_keys),
                        secret=self.secrets.get(source.id),
                        connector=connector,
                        containers=container_map,
                        documents_by_container=documents,
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
