from __future__ import annotations

from alquimista.connectors.intercom import IntercomConnector
from alquimista.connectors.salesforce import SalesforceConnector
from alquimista.models import ExtractionOptions, SourceConfig


class _MockApiClient:
    def __init__(self, data_map: dict | None = None) -> None:
        self.data_map = data_map or {}
        self.closed = False

    def get_json(self, path: str, params: dict | None = None) -> dict | list:
        if path in self.data_map:
            return self.data_map[path]
        for k, v in self.data_map.items():
            if path.startswith(k):
                return v
        return {}

    def close(self) -> None:
        self.closed = True


def test_intercom_service_desk_read_only() -> None:
    source_config = SourceConfig(
        id="intercom-1",
        source_type="intercom_api",
        name="Intercom Suporte",
        base_url="https://api.intercom.io",
    )
    mock_client = _MockApiClient(
        {
            "me": {"name": "Admin", "type": "admin"},
            "help_center/collections": {"data": [{"id": "col-1", "name": "Geral"}]},
            "conversations": {
                "conversations": [
                    {
                        "id": "conv-101",
                        "state": "open",
                        "created_at": 1700000000,
                        "updated_at": 1700000100,
                        "source": {"subject": "Duvida sobre login", "body": "<p>Nao consigo logar</p>"},
                    }
                ]
            },
            "conversations/conv-101": {
                "id": "conv-101",
                "state": "open",
                "created_at": 1700000000,
                "updated_at": 1700000100,
                "source": {
                    "subject": "Duvida sobre login",
                    "body": "<p>Nao consigo logar no sistema.</p>",
                    "author": {"name": "Maria Silva", "email": "maria@cliente.com"},
                },
                "conversation_parts": {
                    "conversation_parts": [
                        {
                            "author": {"name": "Suporte N1", "type": "admin"},
                            "body": "<p>Ola Maria, verifique sua senha.</p>",
                            "created_at": 1700000050,
                        }
                    ]
                },
            },
        }
    )

    connector = IntercomConnector(
        source_config,
        ExtractionOptions(),
        secret="token-123",
        client=mock_client,
    )

    containers = connector.list_containers()
    container_ids = [c.id for c in containers]
    assert "support_conversations" in container_ids
    assert "collection_col-1" in container_ids

    # List conversations
    docs = connector.list_documents("support_conversations")
    assert len(docs) == 1
    assert docs[0].id == "conv-101"
    assert "Duvida sobre login" in docs[0].title

    # Get conversation document
    doc = connector.get_document("conv-101", container_id="support_conversations")
    assert "Duvida sobre login" in doc.title
    assert "Maria Silva" in doc.content
    assert "Nao consigo logar no sistema" in doc.content
    assert "Suporte N1" in doc.content
    assert "Ola Maria, verifique sua senha" in doc.content

    connector.close()
    assert mock_client.closed is True


def test_salesforce_service_desk_read_only() -> None:
    source_config = SourceConfig(
        id="sf-1",
        source_type="salesforce_api",
        name="Salesforce Suporte",
        base_url="https://empresa.my.salesforce.com",
    )

    data_map = {
        "/services/data/v60.0/sobjects": {"sobjects": []},
        "/services/data/v60.0/query": {
            "records": [
                {
                    "Id": "case-500",
                    "CaseNumber": "00001001",
                    "Subject": "Erro na integração",
                    "Description": "O webhook falhou com 500.",
                    "Status": "Closed",
                    "Priority": "High",
                    "CreatedDate": "2026-01-02T10:00:00Z",
                    "ClosedDate": "2026-01-02T12:00:00Z",
                }
            ]
        },
        "/services/data/v60.0/sobjects/Case/case-500": {
            "Id": "case-500",
            "CaseNumber": "00001001",
            "Subject": "Erro na integração",
            "Description": "O webhook falhou com 500.",
            "Status": "Closed",
            "Priority": "High",
            "CreatedDate": "2026-01-02T10:00:00Z",
            "ClosedDate": "2026-01-02T12:00:00Z",
        },
    }
    mock_client = _MockApiClient(data_map)

    connector = SalesforceConnector(
        source_config,
        ExtractionOptions(),
        secret="token-sf",
        client=mock_client,
    )

    containers = connector.list_containers()
    container_ids = [c.id for c in containers]
    assert "salesforce_cases" in container_ids

    docs = connector.list_documents("salesforce_cases")
    assert len(docs) == 1
    assert docs[0].id == "case-500"
    assert "00001001" in docs[0].title

    doc = connector.get_document("case-500", container_id="salesforce_cases")
    assert "Erro na integração" in doc.title
    assert "O webhook falhou com 500." in doc.content
    assert "Closed" in doc.content

    connector.close()
    assert mock_client.closed is True

