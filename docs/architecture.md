# Arquitetura do ALQuimista 3.0

## Fluxo de Dados Universal

Cada plataforma e tipo de dado fica isolado em seu respectivo conector ou processador de documento. O restante da aplicação recebe somente contratos e modelos comuns:

```text
ConnectorRegistry / DocumentProcessorRegistry
    -> KnowledgeSourceConnector / DocumentProcessor
    -> KnowledgeContainer / KnowledgeDocumentMetadata / KnowledgeAttachment
    -> KnowledgeDocument
    -> ExtractionService
    -> Markdown normalizado + manifesto + SHA-256
    -> ConsolidationService (pacote único / particionado / com índice RAG)
```

O pipeline universal de extração atende 28 conectores integrados cobrindo:
1. **Knowledge Bases & Enterprise**: Confluence, Notion, SharePoint, GitBook, BookStack, Document360, Outline, Guru, Helpjuice, Slite.
2. **Customer Support / Service Desk (Read-Only)**: Zendesk (Guide & Support), Intercom, Freshdesk, Salesforce (Knowledge & Cases), HubSpot (KB & Tickets), Help Scout.
3. **Developer Docs**: GitHub Docs, GitLab Wikis & Repositories, ReadMe Hubs.
4. **Headless CMS & Portais**: WordPress, Ghost, Strapi, Contentful, Sanity.
5. **Web & Frameworks de Documentação**: Generic Web, Generic Docs (com detecção de Docusaurus, MkDocs, VitePress, Sphinx, Mintlify, Nextra, Hugo, Jekyll, llms.txt, sitemaps e crawler bounded seguro).
6. **Arquivos & Pastas Locais**: PDF, Excel/Planilhas (XLSX, XLS, XLSM sem macros, CSV, TSV, ODS), Apresentações (PPTX, ODP com notas do apresentador), Word/Texto (DOCX, ODT, RTF, TXT, MD, MDX, RST), E-books (EPUB), HTML e Imagens com OCR opcional.

## Subsistema de Processamento de Documentos (`alquimista.document_processing`)

Camada completamente desacoplada dos conectores de rede:
- `DocumentProcessorRegistry`: Singleton que seleciona o processador por extensão, assinatura de bytes (magic numbers) e MIME type.
- Processadores especializados: `PdfProcessor`, `SpreadsheetProcessor`, `PresentationProcessor`, `WordProcessor`, `EbookProcessor`, `HtmlProcessor`, `TextProcessor`, `ImageProcessor`.
- Segurança: Bloqueio estrito de macros/código ativo (`data_only=True`), limite de tamanho de arquivos (100MB por padrão) e proteção contra decompression bombs.

## Descoberta Universal Web & Crawler (`alquimista.source_discovery`)

`SourceDiscoveryService` atua em cascata determinando a estratégia ótima ao receber qualquer URL:
1. Detecção de API oficial ou conector de plataforma.
2. Sonda automática de `/llms-full.txt` e `/llms.txt`.
3. Parser de `sitemap.xml` e `sitemap_index.xml`.
4. Detecção de frameworks estáticos de documentação.
5. WebCrawler breadth-first restrito ao domínio/subdomínio com rate limit, controle de profundidade e cancelamento cooperativo.

## Seleção

As seleções usam a chave composta:

```text
source_id:container_id:document_id
```

O `SelectionStore` mantém o estado fora dos widgets, evitando que a navegação entre contêineres apague escolhas anteriores.

## Configuração e Segredos

`SourceConfig.connector_options` aceita somente parâmetros não sensíveis. O validador rejeita chaves que aparentem conter token, senha, segredo, cookie, refresh token ou autorização. Segredos são fornecidos ao conector somente em runtime (`RuntimeSecrets`) e são zerados da memória no método `close()`.

## HTTP e Resiliência

`ApiHttpClient` centraliza HTTPS, timeout, proxy, User-Agent, cancelamento, limitação de requisições, retry finito com exponential backoff, jitter e respeito a cabeçalhos `Retry-After` (HTTP 429/5xx).

## Relatórios

O `ExecutionReport` organiza a execução por fonte, contêiner e documento, mantendo métricas completas para a interface e auditoria.

## Consolidação

Os arquivos individuais continuam sendo a unidade de rastreabilidade com SHA-256. Os pacotes consolidados podem ser divididos por grupo, quantidade de páginas ou quantidade de caracteres sem cortar documentos, gerando tabelas de conteúdo e índices otimizados para RAG/LLMs.

