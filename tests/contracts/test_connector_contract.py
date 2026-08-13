from __future__ import annotations

import inspect
from typing import cast

import pytest

from alquimista.browser.adapters import ConnectorDiscoveryAdapter
from alquimista.connectors.base import KnowledgeSourceConnector
from alquimista.connectors.registry import default_registry
from alquimista.models import SourceConfig

from .cases import CASES, ConnectorContractCase

ACTIVE_SOURCE_TYPES = ("confluence_rest", "gitbook_api", "zendesk_guide", "notion_api", "generic_web")


@pytest.fixture(params=CASES, ids=lambda case: case.source_type)
def contract_case(request: pytest.FixtureRequest) -> ConnectorContractCase:
    return request.param


def test_active_connector_set_is_exact() -> None:
    registry = default_registry()

    assert tuple(item.source_type for item in registry.available()) == ACTIVE_SOURCE_TYPES


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.source_type)
def test_active_connector_factory_is_concrete(case: ConnectorContractCase) -> None:
    descriptor = default_registry().get(case.source_type)
    factory = cast(type[KnowledgeSourceConnector], descriptor.factory)

    assert factory is case.connector_type
    assert issubclass(case.connector_type, KnowledgeSourceConnector)
    assert not inspect.isabstract(case.connector_type)


def test_identity_source_and_capabilities_match_registry(
    contract_case: ConnectorContractCase,
) -> None:
    built = contract_case.build()
    connector = built.connector
    descriptor = default_registry().get(contract_case.source_type)

    source = connector.get_source()
    assert connector.get_source_type() == contract_case.source_type
    assert source.source_type == contract_case.source_type
    assert source.id
    assert source.name
    assert connector.get_capabilities() == descriptor.capabilities


def test_required_connector_workflow_is_deterministic(
    contract_case: ConnectorContractCase,
) -> None:
    built = contract_case.build()
    connector = built.connector

    validation = connector.validate_connection()
    first_containers = connector.list_containers()
    second_containers = connector.list_containers()
    first_documents = connector.list_documents(contract_case.container_id)
    second_documents = connector.list_documents(contract_case.container_id)
    children = connector.get_document_children(contract_case.document_id)
    fetched = connector.get_document(
        contract_case.document_id,
        container_id=contract_case.container_id,
    )
    fetched_again = connector.get_document(
        contract_case.document_id,
        container_id=contract_case.container_id,
    )
    normalized = connector.normalize_document(contract_case.normalize_payload())
    normalized_again = connector.normalize_document(contract_case.normalize_payload())

    assert validation
    assert [item.model_dump(mode="json") for item in first_containers] == [
        item.model_dump(mode="json") for item in second_containers
    ]
    assert [item.model_dump(mode="json") for item in first_documents] == [
        item.model_dump(mode="json") for item in second_documents
    ]
    assert first_containers
    assert first_documents
    assert len({item.id for item in first_containers}) == len(first_containers)
    assert len({item.id for item in first_documents}) == len(first_documents)
    assert all(item.id for item in first_containers)
    assert tuple(item.id for item in first_containers) == (
        contract_case.expected_container_ids
    )
    assert all(item.id for item in first_documents)
    assert all(item.container_id == contract_case.container_id for item in first_documents)
    assert isinstance(children, list)
    assert tuple(item.id for item in children) == contract_case.expected_child_ids
    assert all(item.id and item.container_id for item in children)
    assert fetched.id == normalized.id == contract_case.document_id
    assert fetched.container_id == normalized.container_id == contract_case.container_id
    assert fetched.source_type == normalized.source_type == contract_case.source_type
    assert fetched.content == normalized.content
    assert fetched.model_dump(mode="json") == fetched_again.model_dump(mode="json")
    assert normalized.model_dump(mode="json") == normalized_again.model_dump(mode="json")

    connector.close()
    assert built.client.closed is True


def test_runtime_credentials_are_not_exposed_by_public_source(
    contract_case: ConnectorContractCase,
) -> None:
    marker = "contract-secret-not-real"
    built = contract_case.build()

    serialized_config = built.source.model_dump_json()
    serialized_source = built.connector.get_source().model_dump_json()
    assert marker not in serialized_config
    assert marker not in serialized_source

    with pytest.raises(ValueError, match="Credenciais"):
        SourceConfig(
            source_type=contract_case.source_type,
            connector_options={"access_token": marker},
        )

    built.connector.close()
    assert getattr(built.connector, "secret", "") == ""


def test_optional_discovery_capabilities_are_explicit(
    contract_case: ConnectorContractCase,
) -> None:
    built = contract_case.build()
    connector = built.connector
    adapter = ConnectorDiscoveryAdapter(connector)

    assert adapter.capabilities - {"list_containers"} == contract_case.optional_capabilities

    if contract_case.source_type == "confluence_rest":
        roots = connector.list_root_documents(contract_case.container_id)
        children = connector.list_document_children(
            contract_case.container_id,
            contract_case.document_id,
        )
        search = connector.search_documents(
            contract_case.container_id,
            "Contrato",
        )
        assert [item.id for item in roots.items] == [contract_case.document_id]
        assert children.items == ()
        assert [item.document.id for item in search.items] == [
            contract_case.document_id
        ]

    connector.close()
