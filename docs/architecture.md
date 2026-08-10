# Arquitetura do ALQuimista

## Fluxo de dados

Cada plataforma fica isolada no seu conector. O restante da aplicação recebe
somente modelos comuns:

```text
ConnectorRegistry
    -> KnowledgeSourceConnector
    -> KnowledgeContainer / KnowledgeDocumentMetadata
    -> KnowledgeDocument
    -> ExtractionService
    -> Markdown + manifesto + SHA-256
    -> ConsolidationService
```

O pipeline de extração genérico é utilizado pelos conectores registrados no
fluxo principal, incluindo Confluence, GitBook e Zendesk Guide. O caminho
legado de `RuntimeBuilder.build()` permanece somente para compatibilidade com
projetos antigos e prévias baseadas em árvores já carregadas.

## Seleção

As seleções usam a chave composta:

```text
source_id:container_id:document_id
```

O `SelectionStore` mantém o estado fora dos widgets, evitando que a navegação
entre contêineres apague escolhas anteriores.

## Configuração e segredos

`SourceConfig.connector_options` aceita somente parâmetros não sensíveis. O
validador rejeita chaves que aparentem conter token, senha, segredo, cookie,
refresh token ou autorização. Segredos são fornecidos ao conector somente em
runtime e não entram no projeto, manifesto, relatório ou Markdown.

## HTTP

`ApiHttpClient` centraliza HTTPS, timeout, proxy, User-Agent, cancelamento,
limitação de requisições, retry finito, backoff e `Retry-After`. Ele oferece
operações JSON GET/POST e download binário para os conectores que precisarem
de conteúdo externo autorizado.

## Relatórios

O `ExecutionReport` organiza a execução por fonte, contêiner e documento. O
JSON continua mantendo `counters`, `pages_found` e `pages_selected` para
compatibilidade com a interface existente.

## Consolidação

Os arquivos individuais continuam sendo a unidade de rastreabilidade. Os
pacotes consolidados podem ser divididos por grupo, quantidade de páginas ou
quantidade de caracteres sem cortar uma página no meio. A opção de repetir a
árvore transforma os níveis do caminho em títulos Markdown no pacote; sem ela,
a hierarquia permanece no índice, caminho e ordem dos documentos.
