from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .models import KnowledgeSelection

StringSet = set[str]


@dataclass
class SelectionStore:
    """In-memory selection state independent from Qt widgets.

    Keys always contain source, container and document identifiers, so the
    same remote document ID can safely occur in different containers.
    """

    _selected: dict[tuple[str, str, str], bool] = field(default_factory=dict)

    @classmethod
    def from_selections(cls, selections: list[KnowledgeSelection]) -> "SelectionStore":
        store = cls()
        for item in selections:
            store.set(item.source_id, item.container_id, item.document_id, item.selected)
        return store

    def set(self, source_id: str, container_id: str, document_id: str, selected: bool) -> None:
        key = (str(source_id), str(container_id), str(document_id))
        if selected:
            self._selected[key] = True
        else:
            self._selected.pop(key, None)

    def is_selected(self, source_id: str, container_id: str, document_id: str) -> bool:
        return self._selected.get((str(source_id), str(container_id), str(document_id)), False)

    def keys_for_source(self, source_id: str) -> StringSet:
        return {
            f"{source}:{container}:{document}"
            for source, container, document in self._selected
            if source == str(source_id)
        }

    def selections(self) -> list[KnowledgeSelection]:
        return [
            KnowledgeSelection(
                source_id=source,
                container_id=container,
                document_id=document,
                selected=True,
            )
            for source, container, document in sorted(self._selected)
        ]

    def count_by_container(self, source_id: str | None = None) -> Counter[tuple[str, str]]:
        counts: Counter[tuple[str, str]] = Counter()
        for source, container, _document in self._selected:
            if source_id is None or source == str(source_id):
                counts[(source, container)] += 1
        return counts

    def clear(self) -> None:
        self._selected.clear()
