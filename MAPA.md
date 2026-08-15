# MAPA DO CÓDIGO — ALQuimista Studio 3.0

Guia de referência rápida para agentes de IA e desenvolvedores. Fonte da verdade é **sempre o código atual**; este mapa indica **onde começar** a investigação.

**Última reconstrução:** 2026-08-14 — gerado por inspeção completa do repositório.

---

## MÉTRICAS REAIS

| Métrica | Valor |
|---|---|
| Arquivos `.py` no pacote `alquimista/` | 129 |
| Linhas de código (pacote) | ~30.500 |
| Conectores implementados | 28 |
| Processadores de documentos | 8 (PDF, Word, Spreadsheet, Presentation, Ebook, HTML, Image, Text) |
| Controllers em `ui/controllers/` | 11 arquivos (10 controllers + `__init__.py`) |
| Mixins em `ui/mixins/` | 3 (connection, selection, source) |
| Páginas em `ui/pages/` | 9 |
| Arquivos de teste | 31 (+ 2 em `contracts/`) |
| Funções de teste | ~233 |
| Linhas de teste | ~6.500 |
| Versão do schema | 4 (`SCHEMA_VERSION` em `models.py`) |
| Versão do pacote | 0.9.5 (`__version__` em `__init__.py`) |
| Python | 3.12 |
| Framework UI | PySide6 ≥ 6.10 |
| Dependências runtime | pydantic ≥ 2.9, requests ≥ 2.31, beautifulsoup4 ≥ 4.12, markdownify ≥ 1.2 |

---

## COMO USAR ESTE MAPA

1. Localize a área ou sintoma na tabela de roteamento abaixo.
2. Abra o arquivo indicado e confirme que os símbolos citados existem.
3. Verifique dependências e callers no código antes de alterar.
4. Faça alteração mínima, rode testes relacionados.

### Quero mudar X → onde investigar

| Quero mudar… | Comece investigando… | Confirme também… |
|---|---|---|
| Adicionar/editar uma fonte | `ui/mixins/source_mixin.py` + `source_detection.py` | `models.py:SourceConfig`, `storage.py` |
| Autenticação de uma fonte | `ui/mixins/connection_mixin.py` + `auth.py` | `connectors/<plataforma>.py`, `controllers/runtime_controller.py:RuntimeSecrets` |
| Árvore de seleção | `ui/mixins/selection_mixin.py` | `tree_models.py`, `controllers/tree_loader_controller.py` |
| Conversão HTML→Markdown | `markdown/transformer.py` | `markdown/renderer.py`, `models.py:MarkdownOptions` |
| Extração de páginas | `services/extraction.py` | conector `get_document`, `services/runtime.py:SourceRuntime` |
| Consolidação de saída | `services/consolidation.py` | `storage.py`, `services/helpers.py:demote_headings` |
| Atualização incremental | `services/extraction.py` (SHA-256) + `manifest_index.py` | `models.py:SCHEMA_VERSION` |
| Adicionar novo conector | `connectors/base.py` (ABC) + conector existente como referência | `connectors/registry.py`, `source_detection.py` |
| Cancelamento de operação | `runtime.py:CancellationToken` | chamador do token no controller/worker |
| Tema/visual de uma tela | `ui/pages/<tela>.py` + `components.py` | `theme.py` |
| Relatório de execução | `reports.py` | `services/extraction.py` (gera `ExecutionReport`) |
| Navegação entre telas | `controllers/navigation_controller.py` | `main_window.py:_show_page` |
| Preview de markdown | `controllers/preview_controller.py` | `markdown/preview.py`, `markdown/renderer.py` |
| Consolidação UI | `controllers/consolidation_controller.py` | `services/consolidation.py` |

---

## VISÃO GERAL DA ARQUITETURA

```
alquimista/                  # Pacote principal (sem UI)
├── __init__.py              # Exports: ProjectConfig, SourceConfig, opções
├── __main__.py              # Entry point: python -m alquimista
├── models.py                # Contrato de dados central (pydantic v2)
├── auth.py                  # Login interativo via Playwright
├── client.py                # Cliente REST legado Confluence
├── errors.py                # Hierarquia de erros tipados
├── runtime.py               # CancellationToken, RateLimiter, ProgressCallback
├── selection.py             # SelectionStore (estado sem Qt)
├── storage.py               # Persistência atômica, FileTransaction, ManifestStore
├── reports.py               # ExecutionReport, DocumentResult, SourceReport
├── logging_utils.py         # Logs JSON com redação de segredos
├── manifest_index.py        # Índice SQLite sidecar do manifest
├── session_store.py         # Sessão de browser criptografada (DPAPI/Windows)
├── source_detection.py      # Detecta plataforma por URL sem rede
├── source_discovery.py      # Facade de compatibilidade → discovery/
├── confluence_url.py        # Parser de URLs Confluence
│
├── services/                # Motor de domínio
│   ├── extraction.py        # ExtractionService (~48KB)
│   ├── consolidation.py     # ConsolidationService (~16KB)
│   ├── sync.py              # IncrementalSyncService (Fase 3 ~27KB)
│   ├── reconciliation.py    # InventoryReconciliationService
│   ├── runtime.py           # SourceRuntime, SelectedDocumentRef
│   └── helpers.py           # sanitize_filename, demote_headings
│
├── connectors/              # 28 conectores por plataforma
│   ├── base.py              # ABC KnowledgeSourceConnector
│   ├── capabilities.py      # Protocols: Hierarchical, Searchable, MarkdownConfigurable
│   ├── registry.py          # ConnectorRegistry, ConnectorDescriptor, default_registry()
│   ├── http.py              # ApiHttpClient compartilhado
│   ├── confluence.py        # Confluence Cloud & Server
│   ├── confluence_parser.py # Parser HTML→MD Confluence
│   ├── notion.py            # Notion API
│   ├── notion_parser.py     # Parser de blocos Notion
│   ├── gitbook.py           # GitBook API v1
│   ├── sharepoint.py        # SharePoint Graph
│   ├── zendesk.py           # Zendesk Guide
│   ├── freshdesk.py         # Freshdesk Solutions
│   ├── outline.py           # Outline KB
│   ├── helpscout.py         # Help Scout Docs
│   ├── document360.py       # Document360 API v2
│   ├── bookstack.py         # BookStack API
│   ├── github_docs.py       # GitHub Repos Docs
│   ├── gitlab.py            # GitLab Wikis & Docs
│   ├── intercom.py          # Intercom Help Center
│   ├── salesforce.py        # Salesforce Knowledge
│   ├── hubspot.py           # HubSpot KB
│   ├── helpjuice.py         # Helpjuice KB
│   ├── guru.py              # Guru Cards
│   ├── slite.py             # Slite Channels
│   ├── mediawiki.py         # MediaWiki API
│   ├── readme.py            # ReadMe Dev Hub
│   ├── wordpress.py         # WordPress REST v2
│   ├── ghost.py             # Ghost Content API
│   ├── strapi.py            # Strapi CMS
│   ├── contentful.py        # Contentful CDA
│   ├── sanity.py            # Sanity GROQ
│   ├── local_files.py       # Importador de arquivos/pastas locais
│   ├── generic_web.py       # Scraping de página web única
│   └── generic_docs.py      # Descoberta de documentações web
│
├── markdown/                # Pipeline HTML→Markdown
│   ├── transformer.py       # MarkdownTransformer (macros, links, imagens)
│   ├── renderer.py          # KnowledgeDocumentRenderer, PreparedKnowledgeDocument
│   ├── metadata.py          # page_metadata, knowledge_document_metadata
│   ├── normalization.py     # normalize_markdown, sha256_text
│   └── preview.py           # sample_page (prévia da tela Markdown)
│
├── discovery/               # Descoberta universal web
│   ├── service.py           # SourceDiscoveryService
│   ├── crawler.py           # WebCrawler (profundidade + rate limit)
│   ├── sitemap.py           # Parsing de sitemaps XML
│   ├── llms_txt.py          # Extração de llms.txt
│   ├── frameworks.py        # Detecção de frameworks (Docusaurus, MkDocs, etc.)
│   ├── normalization.py     # Normalização de URLs e escopo
│   └── models.py            # DiscoveryResult, DiscoveredResource, DiscoveryStrategy
│
├── document_processing/     # Processamento de arquivos locais
│   ├── base.py              # ABC DocumentProcessor
│   ├── registry.py          # DocumentProcessorRegistry singleton
│   ├── pdf.py               # PDF (PyMuPDF/pypdf)
│   ├── word.py              # Word (DOCX, ODT, RTF)
│   ├── spreadsheet.py       # Excel, CSV, TSV, ODS
│   ├── presentation.py      # PowerPoint, ODP
│   ├── ebook.py             # EPUB
│   ├── html.py              # HTML/HTM
│   ├── image.py             # PNG, JPG, etc. (OCR opcional)
│   └── text.py              # TXT, MD, RST
│
├── browser/                 # Navegador embutido (Playwright) + cache
│   ├── contracts.py         # Protocols e tipos de discovery
│   ├── service.py           # LazyDiscoveryService (síncrono, thread-safe)
│   ├── adapters.py          # ConnectorDiscoveryAdapter
│   └── cache.py             # BrowserCache (SQLite, sem credenciais)
│
└── ui/                      # Interface (PySide6)
    ├── __init__.py           # Exports: run_app
    ├── main_window.py        # MainWindow (~90KB, 2369 linhas, 134 métodos)
    ├── components.py         # Widgets reutilizáveis (~39KB)
    ├── theme.py              # Cores, constantes visuais, apply_theme
    ├── tree_models.py        # Dados→árvore (tree_pages, ordered_pages, etc.)
    ├── state.py              # MainWindowState (estado mutável fora de widgets)
    ├── i18n.py               # Internacionalização PT-BR/EN/ES
    ├── translation_fallbacks.py # Fallbacks de tradução
    ├── workers.py            # Worker(QRunnable) + WorkerSignals
    ├── connector_forms.py    # Facade → registry.ConnectorFormSpec
    ├── controllers/          # Controllers (sem acoplamento Qt forte)
    │   ├── runtime_controller.py    # RuntimeBuilder + RuntimeSecrets
    │   ├── execution_controller.py  # prepare_runtimes, run_extraction, etc.
    │   ├── operation_controller.py  # WorkerOperationController
    │   ├── navigation_controller.py # Pilha de páginas e navegação
    │   ├── tree_controller.py       # Apresentação visual de árvores
    │   ├── tree_loader_controller.py # Discovery, lazy loading, browser cache (~34KB)
    │   ├── preview_controller.py    # Preview de Markdown, presets, debounce
    │   ├── consolidation_controller.py # UI de consolidação (~18KB)
    │   ├── results_controller.py    # Resultados, métricas, exportação
    │   ├── project_controller.py    # CRUD de projetos
    │   └── source_controller.py     # Normalização de fontes
    ├── mixins/               # Comportamentos da MainWindow
    │   ├── source_mixin.py      # CRUD de fontes (~37KB, 28 métodos)
    │   ├── selection_mixin.py   # Árvore de seleção (~28KB, 21 métodos)
    │   └── connection_mixin.py  # Autenticação (~17KB, 8 métodos)
    ├── pages/                # Construtores de tela
    │   ├── dashboard_page.py
    │   ├── sources_page.py
    │   ├── connection_page.py
    │   ├── selection_page.py
    │   ├── review_page.py
    │   ├── extraction_page.py
    │   ├── markdown_page.py
    │   ├── consolidation_page.py
    │   └── results_page.py
    ├── translations/         # Catálogos QM/TS (EN, ES, PT-BR)
    ├── page_registry.py      # [INATIVO] Define page_builders — sem callers no runtime
    ├── process_workers.py    # [APENAS TESTES] Workers multiprocessing (testado em test_process_workers)
    ├── execution_controller.py   # [FACADE] → controllers/execution_controller
    ├── operation_controller.py   # [FACADE] → controllers/operation_controller
    ├── project_controller.py     # [FACADE] → controllers/project_controller
    └── source_controller.py      # [FACADE] → controllers/source_controller
```

**Fluxo de uso:** Dashboard → Fontes → Conexão → Seleção → Markdown → Revisão/Extração → Consolidação → Resultados.

---

## 1. MODELOS E CONTRATO DE DADOS

### models.py — Contrato central (584 linhas, 21KB)

`SCHEMA_VERSION = 4` — incrementar ao mudar serialização (invalida manifestos antigos).

| Classe/Função | Responsabilidade |
|---|---|
| `AuthMode` (StrEnum) | Modos: `public`, `browser_session`, `basic`, `bearer` |
| `ConnectorStatus` (StrEnum) | `available`, `experimental`, `development`, `disabled`, `unavailable` |
| `EntryStatus` (StrEnum) | Status de entradas do manifest (12 valores) |
| `Model` (BaseModel) | Base pydantic com `extra="ignore"`, `validate_assignment=True` |
| `ConnectorCapabilities` | 18 flags booleanas de capacidades |
| `KnowledgeAttachment` | Anexo de documento |
| `KnowledgeSource` | Fonte: type, name, base_url |
| `KnowledgeContainer` | Contêiner: espaço/seção/categoria |
| `KnowledgeDocumentMetadata` | Metadados sem conteúdo |
| `KnowledgeDocument` | Documento completo com conteúdo |
| `KnowledgeSelection` | Seleção: source_id/container_id/document_id |
| `SourceConfig` | Configuração de fonte (URL, tipo, auth, root, connector_options) |
| `MarkdownOptions` | 37 opções de conversão + presets (minimum/recommended/traceability/rag) |
| `ExtractionOptions` | Timeout, retry, proxy, lazy budgets, path_layout |
| `ConsolidationOptions` | Grouping, sort, limits, separators, demote_headings |
| `ProjectConfig` | Projeto: sources[], selections[], markdown, extraction, consolidation |
| `ManifestEntry` | Entrada do manifest (hashes, status, metadata) |
| `ManifestDocument` | Documento do manifest (lista de entradas) |
| `stable_json_hash(data)` | Hash SHA-256 estável (sort_keys) |
| `slugify(value)` | Normaliza string → nome de arquivo |
| `now_iso()` | Timestamp ISO UTC |
| `default_project()` | Projeto padrão vazio |

**Regra:** ao adicionar/remover campos, mantenha `stable_json_hash` compatível.

**Callers:** praticamente todo o pacote depende de `models.py`.

---

## 2. PERSISTÊNCIA E STORAGE

### storage.py (314 linhas, 14KB)

| Função/Classe | Responsabilidade |
|---|---|
| `confined_path(base, relative)` | Proteção contra path traversal |
| `atomic_write_text/json(path, content)` | Escrita atômica (tmp + rename) |
| `FileTransaction` | Transação: `stage_text`, `stage_json`, `stage_delete`, `commit`, `close` |
| `load_json(path, default)` | Carrega JSON com fallback |
| `save_project/load_project` | CRUD de `ProjectConfig` com migração de schema |
| `ManifestStore` | Store do manifest (`manifesto_alquimista.json`) |
| Constantes: `MANIFEST_NAME`, `MANIFEST_INDEX_NAME`, `FAILURES_NAME`, `REPORT_NAME`, `PACKAGE_INDEX_NAME` | Nomes canônicos |

**Dependências:** `errors.py`, `manifest_index.py`, `models.py`.
**Callers:** `services/extraction.py`, `services/consolidation.py`, `controllers/project_controller.py`.

### manifest_index.py (45 linhas, 4KB)

| Classe | Responsabilidade |
|---|---|
| `ManifestIndex` | Índice SQLite sidecar. `rebuild(document)` reconstrói atomicamente. |

---

## 3. SERVIÇOS (MOTOR DE DOMÍNIO)

### services/extraction.py — ExtractionService (~48KB, maior arquivo do pacote)

| Método | Responsabilidade |
|---|---|
| `ExtractionService(project, runtimes, project_dir)` | Construtor |
| `run() / _run()` | Despacha `_run_generic` ou `_run_legacy` |
| `_run_generic()` | Extração moderna: fetch → KnowledgeDocumentRenderer → FileTransaction |
| `_run_legacy()` | Extração legada (Confluence antigo, sem lazy) |
| `_relative_page_path()` | Caminho relativo no output |
| `_metadata_hash() / _summary_metadata_hash()` | Hash para detecção incremental |
| `_structured_report()` | Monta `ExecutionReport` |

**Dependências:** `connectors/<plataforma>.py`, `markdown/renderer.py`, `storage.py`, `runtime.py`.
**Callers:** `ui/controllers/execution_controller.py`.

### services/consolidation.py — ConsolidationService (~16KB)

| Método | Responsabilidade |
|---|---|
| `preview()` | Prévia sem gravar |
| `run() / _run()` | Consolida e grava via FileTransaction |
| `_group_key()` | Agrupa por fonte/espaço/módulo |
| `_entries()` | Filtra entradas elegíveis |
| `_sort()` | Ordena (path/title/updated/id) |

**Callers:** `ui/controllers/consolidation_controller.py`, `ui/controllers/execution_controller.py`.

### services/sync.py — IncrementalSyncService (~27KB, Fase 3)

| Método / Modelo | Responsabilidade |
|---|---|
| `IncrementalSyncService(project, project_dir)` | Orquestrador de sincronização incremental |
| `plan_sync(runtimes, scope, target_source_id)` | Varredura de metadados, detecção de +, ~, -, = e checagens fail-safe |
| `apply_sync(plan, runtimes, options)` | Execução atômica sobre ExtractionService e FileTransaction |
| `SyncScope` | `SELECTION`, `SOURCE`, `PROJECT` |
| `SyncPlan / SyncReport / SyncItemChange` | Modelos de plano, relatório e mudanças de documento/anexos |

**Callers:** `ui/controllers/execution_controller.py`, `ui/dialogs/sync_dialog.py`.

### services/reconciliation.py — InventoryReconciliationService

Compara manifest local com fonte remota; marca `REMOVED` entradas deletadas remotamente.

### services/runtime.py — SourceRuntime, SelectedDocumentRef

| Classe | Responsabilidade |
|---|---|
| `SourceRuntime` | Empacota conector + manifest parcial + cancelamento por fonte |
| `SelectedDocumentRef` | Referência a documento selecionado |

### services/helpers.py

| Função | Responsabilidade |
|---|---|
| `sanitize_filename(value)` | Normaliza nomes de arquivo |
| `demote_headings(md, levels)` | Rebaixa cabeçalhos Markdown |

---

## 4. CONECTORES

### connectors/base.py — ABC KnowledgeSourceConnector

| Método | Tipo |
|---|---|
| `get_source_type()` | Obrigatório |
| `get_source()` | Obrigatório |
| `get_capabilities()` | Obrigatório |
| `validate_connection()` | Obrigatório |
| `list_containers()` | Obrigatório |
| `list_documents(container_id)` | Obrigatório |
| `get_document(document, container_id)` | Obrigatório |
| `get_document_children(document_id)` | Opcional |
| `normalize_document(raw)` | Opcional |
| `close()` | Opcional |

### connectors/capabilities.py — Protocols

| Protocol | Métodos |
|---|---|
| `HierarchicalDiscoveryConnector` | `list_root_documents`, `list_document_children` |
| `SearchableConnector` | `search_documents` |
| `MarkdownConfigurableConnector` | `configure_markdown` |

### connectors/registry.py — Catálogo central (1177 linhas, 43KB)

| Classe | Responsabilidade |
|---|---|
| `ConnectorFormSpec` | Metadados de formulário UI |
| `ConnectorCardSpec` | Metadados de card dashboard |
| `ConnectorDescriptor` | Metadados completos: type, factory, capabilities, form, card, status |
| `ConnectorRegistry` | Catálogo. `get(type)`, `create(config)`, `list()`, `list_operational()` |
| `default_registry()` | Singleton com 28 conectores |

### connectors/http.py — ApiHttpClient

HTTP compartilhado: HTTPS obrigatório, retry com backoff exponencial+jitter, rate limit, cancellation, nunca loga Authorization.

**Callers:** todos os conectores que usam APIs REST.

### Tabela de conectores (28)

| Conector | source_type | Auth | Hierárquico | Busca |
|---|---|---|---|---|
| Confluence | `confluence_rest` | Basic/Bearer | ✓ | ✓ |
| Notion | `notion_api` | Bearer | ✓ | ✓ |
| GitBook | `gitbook_api` | Bearer | | |
| SharePoint | `sharepoint_graph` | Bearer | | |
| Zendesk | `zendesk_guide` | Bearer | ✓ | |
| Freshdesk | `freshdesk_solutions` | Bearer | | |
| BookStack | `bookstack_api` | Bearer | ✓ | ✓ |
| Outline | `outline_api` | Bearer | | |
| Help Scout | `helpscout_docs` | Bearer | | |
| Document360 | `document360_api` | Bearer | | |
| GitHub Docs | `github_docs` | Bearer | | |
| GitLab | `gitlab_docs` | Bearer | | |
| Intercom | `intercom_api` | Bearer | | |
| Salesforce | `salesforce_api` | Bearer | | |
| HubSpot | `hubspot_api` | Bearer | | |
| Helpjuice | `helpjuice` | Bearer | | |
| Guru | `guru` | Bearer | | |
| Slite | `slite` | Bearer | | |
| MediaWiki | `mediawiki` | Público | | |
| ReadMe | `readme` | Bearer | | |
| WordPress | `wordpress` | Público/Bearer | | |
| Ghost | `ghost` | Bearer | | |
| Strapi | `strapi` | Bearer | | |
| Contentful | `contentful_api` | Bearer | | |
| Sanity | `sanity` | Bearer | | |
| Local Files | `local_files` | — | | |
| Generic Web | `generic_web` | Público | | |
| Generic Docs | `generic_docs` | Público | | |

### Parsers especializados

| Arquivo | Responsabilidade |
|---|---|
| `confluence_parser.py` | HTML Confluence → Markdown canônico |
| `notion_parser.py` | JSON blocos Notion → Markdown canônico |

---

## 5. MARKDOWN — Pipeline de conversão

### markdown/transformer.py — MarkdownTransformer (11KB)

Converte HTML em Markdown usando BeautifulSoup. Substitui macros Confluence, resolve links/imagens, normaliza.

### markdown/renderer.py — KnowledgeDocumentRenderer (6KB)

| Classe | Responsabilidade |
|---|---|
| `PreparedKnowledgeDocument` | Documento preparado (normalizado, hashado) |
| `KnowledgeDocumentRenderer` | `prepare()` → `render()`/`render_prepared()`. Injeta frontmatter, markers, títulos |

### markdown/metadata.py — Metadados (5KB)

`page_metadata()`, `knowledge_document_metadata()` — extrai metadados para frontmatter.

### markdown/normalization.py

`normalize_markdown()`, `sha256_text()`, `format_updated_at()`.

### markdown/preview.py

`sample_page()` — página de exemplo para preview na UI.

---

## 6. DISCOVERY — Descoberta web

### discovery/service.py — SourceDiscoveryService

Pipeline: platform match → `llms.txt` → sitemap → crawler. Retorna `DiscoveryResult` com `DiscoveryStrategy`.

### discovery/crawler.py — WebCrawler

Crawl seguro com profundidade e rate limit. Retorna lista de `DiscoveredResource`.

### discovery/models.py

`DiscoveredResource`, `DiscoveryResult`, `DiscoveryStrategy` (enum: OFFICIAL_API, LLMS_TXT, SITEMAP, CRAWL).

### discovery/frameworks.py

`detect_documentation_framework()` — assinaturas de Docusaurus, MkDocs, VitePress, etc.

---

## 7. PROCESSAMENTO DE DOCUMENTOS

### document_processing/base.py — ABC DocumentProcessor

`supported_extensions`, `supported_mimetypes`, `can_process()`, `process_file()`, `process_bytes()`.

### document_processing/registry.py — DocumentProcessorRegistry

Singleton: `register()`, `get_processor()`, `process_file()`, `process_bytes()`. MAX 100 MiB. Fallback → TextProcessor.

### Processadores

| Arquivo | Formatos |
|---|---|
| `pdf.py` | PDF (PyMuPDF/pypdf, tabelas) |
| `word.py` | DOCX, ODT, RTF |
| `spreadsheet.py` | XLSX, XLS, CSV, TSV, ODS |
| `presentation.py` | PPTX, ODP |
| `ebook.py` | EPUB |
| `html.py` | HTML, HTM |
| `image.py` | PNG, JPG, WEBP, TIFF, BMP (OCR opcional) |
| `text.py` | TXT, MD, MDX, RST |

---

## 8. BROWSER — Navegador e cache

### browser/contracts.py

Protocols e tipos: `Visibility`, `SpaceMetadata`, `DocumentMetadata`, `DiscoveryPage[T]`, `DiscoveryAdapter`, `CancellationLike`.

### browser/service.py — LazyDiscoveryService

Orquestra discovery com cache SQLite. Síncrono, thread-safe (Lock/RLock). TTL com `stale_if_error`.

### browser/adapters.py — ConnectorDiscoveryAdapter

Adapta conectores `HierarchicalDiscoveryConnector`/`SearchableConnector` ao contrato `DiscoveryAdapter`.

### browser/cache.py — BrowserCache

Cache SQLite de **apenas metadados** (nunca credenciais/conteúdo). `_SENSITIVE_PARTS` garante sanitização.

---

## 9. AUTENTICAÇÃO

### auth.py (162 linhas, 6KB)

| Função | Responsabilidade |
|---|---|
| `browser_login(source, ready, token, timeout_seconds)` | Login OAuth interativo via Playwright |
| `delete_session(source)` | Remove sessão + purga cache de discovery |
| `_authenticated_identity(payload)` | Valida identidade (não anônimo) |
| `_browser_session_closed(browser, page)` | Detecta navegador fechado |

**Dependências:** `browser/cache.py`, `client.py:session_path`, `session_store.py`, `runtime.py`.

### session_store.py (5KB)

Sessão de browser criptografada com Windows DPAPI. Funções: `save_session`, `load_session`, `session_exists`, `delete_session_file`.

**Regra:** tokens bearer NÃO são persistidos aqui. Ficam em `RuntimeSecrets` (memória).

---

## 10. MÓDULOS AUXILIARES DO NÚCLEO

### runtime.py (45 linhas)

| Classe/Type | Responsabilidade |
|---|---|
| `CancellationToken` | `cancel()`, `cancelled`, `check()`, `wait(seconds)` |
| `RateLimiter` | Limita requisições/segundo |
| `ProgressCallback` | `Callable[[int, int, str], None]` |
| `LogCallback` | `Callable[[str], None]` |

### selection.py (65 linhas) — SelectionStore

Estado de seleção **independente do Qt**. Métodos: `set`, `is_selected`, `keys_for_source`, `selections`, `count_by_container`, `clear`, `from_selections`.

### errors.py (56 linhas) — Hierarquia tipada

```
AlquimistaError (RuntimeError)
├── ConnectorError
│   ├── AuthenticationError
│   ├── PermissionDeniedError
│   ├── ResourceNotFoundError
│   └── ApiConnectionError
│       ├── ApiRateLimitError
│       └── InvalidResponseError
├── InvalidProjectError
├── ManifestError
├── StorageError
└── ExtractionCancelledError
```

Aliases de compatibilidade: `ConfluenceConnectionError = ApiConnectionError`, `RateLimitError = ApiRateLimitError`.

### reports.py (69 linhas)

`DocumentResult`, `ContainerReport`, `SourceReport`, `ExecutionReport` — modelos pydantic para relatório de execução.

### logging_utils.py

`configure_logging()`, `redact()` (mascara segredos), `JsonFormatter`, `default_log_path()`.

### source_detection.py (388 linhas, 12KB)

`detect_source_url(value)` — detecta plataforma **sem rede** por padrões de URL. Retorna `DetectedSource`. Suporta: local_files, Confluence, Notion, GitBook, SharePoint, Zendesk, e todos os 28 conectores via registry.

### confluence_url.py

`parse_confluence_url(value)` → `ParsedConfluenceUrl` — múltiplos formatos de URL Confluence.

### source_discovery.py

**Facade de compatibilidade** → `alquimista.discovery`. Não usar em código novo.

### client.py (24KB) — Cliente REST Confluence legado

`ConfluenceClient` com retry, rate limit, cancellation. Usado por `ConfluenceRestConnector`.

---

## 11. UI — INTERFACE (PySide6)

### Hierarquia de herança da MainWindow

```python
class MainWindow(ConnectionMixin, SourceMixin, SelectionMixin, QMainWindow):
```

### main_window.py (2369 linhas, 90KB, 134 métodos)

Orquestrador principal. Herda 3 mixins. Constrói páginas, conecta sinais, gerencia workers.

| Categoria | Métodos representativos |
|---|---|
| Builders de página | `_dashboard_page`, `_sources_page`, `_connection_page`, `_selection_page`, `_markdown_page`, `_consolidation_page`, `_review_page`, `_extraction_page`, `_results_page`, `_settings_page` |
| Navegação | `_show_page(key)`, `_page_go_back` |
| Workers | `_start_worker(...)`, `_on_progress`, `_worker_failed`, `_worker_finished` |
| Estado/Projeto | `save_project`, `save_project_as`, `_load_project_ui`, `_sync_project_ui` |

### mixins/ — Comportamentos da MainWindow

| Mixin | Arquivo | Tamanho | Responsabilidade |
|---|---|---|---|
| `SourceMixin` | `source_mixin.py` | 37KB, 28 métodos | CRUD de fontes, detecção de plataforma, import/export de perfil |
| `SelectionMixin` | `selection_mixin.py` | 28KB, 21 métodos | Árvore de seleção, lazy loading, marcar/desmarcar, filtrar |
| `ConnectionMixin` | `connection_mixin.py` | 17KB, 8 métodos | Autenticação, test_connection, browser_login, runtime secrets |

### controllers/ — Camada de aplicação (10 controllers)

| Controller | Arquivo | Responsabilidade |
|---|---|---|
| `RuntimeSecrets` + `RuntimeBuilder` | `runtime_controller.py` (12KB) | Segredos em memória + construção de runtimes |
| `ExecutionController` (funções) | `execution_controller.py` (7KB) | `prepare_runtimes`, `run_extraction`, `run_consolidation`, `run_complete`, `retry_failures` |
| `WorkerOperationController` | `operation_controller.py` (11KB) | Ciclo de vida do worker Qt, cancelamento |
| `NavigationController` | `navigation_controller.py` (4KB) | Pilha de páginas, botões de navegação |
| `TreeController` | `tree_controller.py` (8KB) | Apresentação de árvores, colunas, ordenação |
| `TreeLoaderController` | `tree_loader_controller.py` (34KB) | Discovery, lazy loading, paginação, browser cache |
| `PreviewController` | `preview_controller.py` (9KB) | Preview Markdown, presets, debounce |
| `ConsolidationController` | `consolidation_controller.py` (18KB) | UI de consolidação, validação, exemplos |
| `ResultsController` | `results_controller.py` (6KB) | Métricas, clipboard, exportação |
| `ProjectController` (funções) | `project_controller.py` (1KB) | CRUD de projetos |
| `SourceController` (funções) | `source_controller.py` (4KB) | Normalização, lookup em combos |

### pages/ — Construtores de tela (9 telas)

Cada arquivo exporta `build_<tela>_page(window) → QWidget`.

| Tela | Arquivo | Rota(s) |
|---|---|---|
| Dashboard | `dashboard_page.py` | `dashboard` |
| Fontes | `sources_page.py` | `sources` |
| Conexão | `connection_page.py` | `connection` |
| Seleção | `selection_page.py` | `pages`, `selection` |
| Revisão | `review_page.py` | `extraction`, `review`, `output` |
| Extração | `extraction_page.py` | (embutido no review) |
| Markdown | `markdown_page.py` | `markdown` |
| Consolidação | `consolidation_page.py` | `consolidation` |
| Resultados | `results_page.py` | `results` |

### components.py (~39KB)

Widgets reutilizáveis: `FlowLayout`, `AlchemistIconAtlas`, `HorizontalScrollArea`, `SourceCard`, `CollapsibleSection`, `SortableTreeItem`, `VisibilityBadgeDelegate`, `ResponsiveOutputControls`, `GlowButton`, `animated_button`, `card()`, `page_header()`, `button()`, `repair_mojibake()`.

### theme.py (15KB)

`LIGHT`/`DARK` dicionários, constantes de card, gradientes, `apply_theme()`.

### tree_models.py (11KB)

`page_container_id()`, `tree_pages()`, `ordered_pages()`, `tree_containers()`, `lazy_state()`.

### state.py — MainWindowState

Dataclass: `trees`, `selection_store`, `connected_sources`, `connection_states`, `last_result`, `last_consolidation_preview`, `operation_status`, `operation_error`.

### workers.py — Worker + WorkerSignals

`Worker(QRunnable)`: executa função com token/progress/log. `WorkerSignals`: `succeeded`, `failed`, `progress`, `log`, `finished`.

### i18n.py (11KB)

`LanguageManager`, `translate_text()`, `create_settings()`, `LANGUAGE_NAMES`. Suporta PT-BR, EN, ES.

---

## 12. FACADES DE COMPATIBILIDADE

Módulos no raiz de `ui/` que apenas re-exportam de `ui/controllers/`:

| Facade | Redireciona para |
|---|---|
| `ui/execution_controller.py` | `controllers/execution_controller` |
| `ui/operation_controller.py` | `controllers/operation_controller` |
| `ui/project_controller.py` | `controllers/project_controller` |
| `ui/source_controller.py` | `controllers/source_controller` |
| `source_discovery.py` | `discovery/` |

**Regra:** código novo importa direto de `controllers/` ou `discovery/`. Facades mantidas apenas para compatibilidade.

---

## 13. CÓDIGO INATIVO / RESERVA

| Arquivo | Status | Evidência |
|---|---|---|
| `ui/page_registry.py` | **Inativo** | `page_builders()` definida mas sem callers no runtime ou testes |
| `ui/process_workers.py` | **Reserva/teste** | Sem callers no pacote; importado apenas por `test_process_workers.py` |
| `ui/components.py.bak*` | **Backups** | 3 arquivos `.bak` — lixo de refatoração |
| `ui/main_window.*.bak*` | **Backups** | 3 arquivos `.bak` — lixo de refatoração |
| `source_discovery.py` | **Facade** | Redireciona para `discovery/` |

---

## 14. ENTRY POINTS, BUILD E SCRIPTS

### Entry points

| Arquivo | Responsabilidade |
|---|---|
| `alquimista/__main__.py` | `python -m alquimista` → `run_app("complete")` |
| `alquimista/__init__.py` | Exports: ProjectConfig, SourceConfig, opções |
| `abrir_completo.bat` | Atalho Windows → `python -m alquimista` |

### Legacy launchers (tools/legacy/)

| Arquivo | Status |
|---|---|
| `alquimista_core.py` | Re-exporta nomes históricos para scripts antigos |
| `alquimista_gui.py` | Entry point legado da UI |
| `alquimista_studio_completo.py` | Launcher legado |
| `alquimista_studio_extrator.py` | Launcher legado → `run_app("complete")` |
| `alquimista_studio_consolidador.py` | Launcher legado → `run_app("complete")` |
| `test_alquimista_studio.py` | Launcher legado de pytest |

### Build e packaging

| Arquivo | Responsabilidade |
|---|---|
| `packaging/ALQuimista Studio.spec` | PyInstaller spec |
| `packaging/ALQuimista Studio.iss` | Inno Setup installer |
| `tools/build/gerar_distribuicoes.ps1` | Portable Windows + Inno Setup |
| `tools/build/gerar_executavel.bat` | Gera executável |
| `tools/build/gerar_pacote_portatil.bat` | Portable Windows |
| `tools/build/gerar_portable_linux.sh` | Portable Linux tar.gz |
| `tools/install/instalar_windows.bat` | Dependências Windows |
| `tools/install/instalar_linux.sh` | Dependências Linux |
| `tools/install/instalar_navegador.bat` | Browsers Playwright |

### Ferramentas

| Arquivo | Responsabilidade |
|---|---|
| `tools/capture_ui.py` | Captura screenshots da UI |
| `tools/normalize_utf8.py` | Normalização UTF-8 |

### Configuração

| Arquivo | Responsabilidade |
|---|---|
| `config/pyproject.toml` | ruff (py312, F/I/B, line 120) + mypy |
| `config/pytest.ini` | `qt_api=pyside6`, markers: `real_confluence`, `integration`, `build`, `slow` |
| `config/requirements.txt` | Runtime: PySide6, pydantic, requests, bs4, markdownify |
| `config/requirements-browser.txt` | playwright |
| `config/requirements-dev.txt` | pytest, ruff, mypy, etc. |
| `config/constraints.txt` | Versões fixas validadas para Python 3.12/Windows |
| `config/python-version.txt` | Python 3.12 |

---

## 15. TESTES

### Suíte (33 arquivos, ~233 funções)

| Arquivo | Área coberta | Qtd testes |
|---|---|---|
| `test_connectors.py` | Todos os 28 conectores | 22 |
| `test_ui.py` | MainWindow, mixins, navegação | 38 |
| `test_services.py` | Extraction, consolidation | 15 |
| `test_client.py` | ConfluenceClient REST | 15 |
| `test_models_storage.py` | Models, storage, FileTransaction | 14 |
| `test_lazy_confluence.py` | Lazy loading Confluence | 13 |
| `test_markdown_goldens.py` | Golden tests de markdown | 12 |
| `test_ui_registry_routing.py` | Registry, routing, metadata | 8 |
| `test_browser_cache.py` | BrowserCache SQLite | 8 |
| `test_ui_controllers.py` | Controllers | 7 |
| `test_i18n.py` | Internacionalização | 6 |
| `test_process_workers.py` | ProcessWorker | 6 |
| `test_error_hierarchy.py` | Hierarquia de erros | 6 |
| `test_registry_metadata.py` | Registry metadata | 6 |
| `test_document_processors.py` | Processadores de documentos | 6 |
| `test_markdown.py` | Transformer, renderer | 6 |
| `test_confluence_url.py` | Parse de URLs | 4 |
| `test_ui_lazy_regressions.py` | Regressões lazy | 4 |
| `test_auth.py` | Autenticação | 3 |
| `test_session_store.py` | Session store DPAPI | 3 |
| `test_source_discovery.py` | Discovery | 3 |
| `test_fixes_regression.py` | Regressões gerais | 3 |
| `test_build_documentation.py` | Build docs | 3 |
| `test_distribution_scripts.py` | Scripts de distribuição | 3 |
| `test_source_detection.py` | Detecção de plataforma | 2 |
| `test_service_desk.py` | Service desk | 2 |
| `test_logging_utils.py` | Logging | 1 |
| `test_live_root_discovery.py` | Root discovery (integration) | 1 |
| `test_local_files.py` | Local files connector | 1 |
| `test_extraction_goldens.py` | Golden tests de extração | 1 |
| `test_ui_browser_cache_integration.py` | Browser cache + UI | 1 |
| `contracts/test_connector_contract.py` | Contrato de conectores | 6 |
| `contracts/cases.py` | Casos de contrato (64KB) | 1 |

### Fixtures

- `conftest.py` — fixtures compartilhadas
- `golden_helpers.py` — helpers para golden tests
- `fixtures/goldens/` — golden files para testes de snapshot

---

## 16. DOCUMENTAÇÃO E ASSETS

| Diretório | Conteúdo |
|---|---|
| `docs/architecture.md` | Arquitetura de alto nível |
| `docs/connectors/` | Docs por conector |
| `docs/manifest-index.md` | Índice do manifest |
| `docs/screenshots/` | PNGs das telas |
| `docs/archive/` | Documentos históricos |
| `assets/icons/` | `alchemist_icon_atlas.png` |
| `ALQuimista_Base/` | Diretório de saída padrão |

---

## 17. DUPLICAÇÕES E ARMADILHAS

### Duplicações resolvidas

As duplicações documentadas no MAPA anterior (selection_mixin, connection_mixin, auth.py, execution_controller) foram **todas resolvidas** na refatoração recente. Cada função agora tem uma única definição ativa.

### Armadilhas ativas

| Risco | Detalhes |
|---|---|
| `page_registry.py` | Sem callers. Se ativar, precisa integrar com `main_window.py:_show_page` |
| `process_workers.py` | Sem callers no runtime. Apenas testado. Se ativar, workers multiprocessing precisam de objetos picklable |
| Facades em `ui/` root | Não editar — são apenas re-exports. Editar em `controllers/` |
| `client.py` | Legado Confluence. Código novo deve usar `connectors/confluence.py` |
| `source_discovery.py` | Facade. Código novo deve usar `discovery/` |
| `main_window.py` | 90KB — alto risco de conflito. Prefira editar mixins/controllers/pages |
| `components.py.bak*` / `main_window.*.bak*` | Backups. Ignorar. |

---

## ROTEAMENTO PARA AGENTES E SKILLS

### Domínios independentes e suas fronteiras

#### 1. DOMÍNIO: Interface (UI)
**Escopo:** Telas, layout, widgets, navegação, tema, i18n.
**Arquivos primários:**
- `ui/pages/` (9 arquivos)
- `ui/components.py`
- `ui/theme.py`
- `ui/main_window.py`
- `ui/controllers/navigation_controller.py`
- `ui/controllers/tree_controller.py`
- `ui/i18n.py`, `ui/translation_fallbacks.py`, `ui/translations/`

**Dependências de leitura:** `models.py` (para tipos), `ui/state.py`, `ui/tree_models.py`.
**Fronteira:** NÃO mexer em services/, connectors/, storage/ ao editar UI. Controllers são a fronteira.

#### 2. DOMÍNIO: Fontes (cadastro e detecção)
**Escopo:** Adicionar/editar/remover fontes, detecção de plataforma por URL.
**Arquivos primários:**
- `ui/mixins/source_mixin.py`
- `source_detection.py`
- `confluence_url.py`
- `models.py:SourceConfig`
- `connectors/registry.py` (metadados de formulário)

**Dependências de leitura:** `storage.py:save_project`, `ui/connector_forms.py`.
**Fronteira:** NÃO mexer em auth, extração ou seleção.

#### 3. DOMÍNIO: Autenticação
**Escopo:** Login, tokens, sessão de browser, teste de conexão.
**Arquivos primários:**
- `ui/mixins/connection_mixin.py`
- `auth.py`
- `session_store.py`
- `ui/controllers/runtime_controller.py:RuntimeSecrets`
- `browser/service.py` (para login Playwright)

**Dependências de leitura:** `connectors/http.py`, `models.py:AuthMode`, `browser/cache.py`.
**Fronteira:** NÃO mexer em seleção, extração ou UI de páginas.

#### 4. DOMÍNIO: Seleção (árvore de páginas)
**Escopo:** Árvore, espaços, páginas, lazy loading, marcar/desmarcar.
**Arquivos primários:**
- `ui/mixins/selection_mixin.py`
- `ui/tree_models.py`
- `ui/controllers/tree_loader_controller.py`
- `ui/controllers/tree_controller.py`
- `selection.py:SelectionStore`

**Dependências de leitura:** conectores `list_containers`/`list_documents`/`list_document_children`, `browser/` (discovery cache).
**Fronteira:** NÃO mexer em extração, consolidação ou auth.

#### 5. DOMÍNIO: Conectores / APIs
**Escopo:** APIs, HTTP, discovery, browser cache, criação de novo conector.
**Arquivos primários:**
- `connectors/base.py`
- `connectors/capabilities.py`
- `connectors/registry.py`
- `connectors/http.py`
- `connectors/<plataforma>.py` (o conector específico)
- `connectors/confluence_parser.py`, `connectors/notion_parser.py`

**Dependências de leitura:** `models.py` (tipos), `errors.py`, `runtime.py:CancellationToken`.
**Fronteira:** NÃO mexer em UI, services ou storage. Conector deve seguir ABC de `base.py`.

#### 6. DOMÍNIO: Extração
**Escopo:** Workers, threads, progresso, cancelamento, manifest, incremental.
**Arquivos primários:**
- `services/extraction.py`
- `services/runtime.py`
- `services/reconciliation.py`
- `services/helpers.py`
- `ui/controllers/execution_controller.py`
- `ui/controllers/operation_controller.py`
- `ui/workers.py`
- `runtime.py:CancellationToken`

**Dependências de leitura:** `connectors/<plataforma>.py:get_document`, `markdown/renderer.py`, `storage.py:FileTransaction`, `manifest_index.py`.
**Fronteira:** NÃO mexer em UI de páginas, seleção ou consolidação.

#### 7. DOMÍNIO: Markdown
**Escopo:** HTML→Markdown, metadados, frontmatter, preview.
**Arquivos primários:**
- `markdown/transformer.py`
- `markdown/renderer.py`
- `markdown/metadata.py`
- `markdown/normalization.py`
- `markdown/preview.py`
- `ui/controllers/preview_controller.py`

**Dependências de leitura:** `models.py:MarkdownOptions`, `connectors/confluence_parser.py`, `connectors/notion_parser.py`.
**Fronteira:** NÃO mexer em extração, storage ou conectores.

#### 8. DOMÍNIO: Consolidação e Resultados
**Escopo:** Juntar arquivos, pacotes, índice, relatórios.
**Arquivos primários:**
- `services/consolidation.py`
- `reports.py`
- `ui/controllers/consolidation_controller.py`
- `ui/controllers/results_controller.py`
- `ui/pages/consolidation_page.py`
- `ui/pages/results_page.py`

**Dependências de leitura:** `storage.py:ManifestStore`, `models.py:ConsolidationOptions`, `services/helpers.py:demote_headings`.
**Fronteira:** NÃO mexer em extração, seleção ou conectores.

#### 9. DOMÍNIO: Discovery web
**Escopo:** llms.txt, sitemap, crawler, frameworks, normalização.
**Arquivos primários:**
- `discovery/service.py`
- `discovery/crawler.py`
- `discovery/sitemap.py`
- `discovery/llms_txt.py`
- `discovery/frameworks.py`
- `discovery/models.py`
- `discovery/normalization.py`

**Dependências de leitura:** `connectors/generic_docs.py`, `connectors/generic_web.py`.
**Fronteira:** NÃO mexer em connectors enterprise, UI ou extração.

#### 10. DOMÍNIO: Processamento de documentos locais
**Escopo:** PDF, Word, Excel, PowerPoint, EPUB, HTML, imagem, texto.
**Arquivos primários:**
- `document_processing/base.py`
- `document_processing/registry.py`
- Cada processador específico

**Dependências de leitura:** `connectors/local_files.py`.
**Fronteira:** Independente de todos os outros domínios exceto `local_files.py`.

### Dependências entre domínios (grafo simplificado)

```
models.py ← (usado por TODOS)
errors.py ← (usado por TODOS)
runtime.py ← (usado por connectors, services, UI)
storage.py ← (usado por services, controllers)

UI ──→ Controllers ──→ Services ──→ Connectors
                   └──→ Storage
                   └──→ Markdown

Seleção ──→ TreeLoader ──→ Browser/Cache ──→ Connectors
Discovery ──→ Connectors (generic_web, generic_docs)
DocumentProcessing ──→ local_files connector
```

### Módulos de alto acoplamento (editar com cuidado)

| Módulo | Acoplamento | Razão |
|---|---|---|
| `models.py` | **Crítico** | Usado por todo o pacote. Mudanças de campo afetam manifest, storage, UI |
| `main_window.py` | **Alto** | 90KB, orquestra tudo. Preferir editar mixins/controllers |
| `connectors/registry.py` | **Alto** | 43KB, todos os conectores registrados aqui |
| `services/extraction.py` | **Alto** | 48KB, motor principal de extração |
| `ui/controllers/tree_loader_controller.py` | **Alto** | 34KB, orquestra discovery e lazy loading |

### Limites arquiteturais que NÃO devem ser atravessados

1. **Connectors NÃO importam UI.** Conectores são agnósticos de interface.
2. **Services NÃO importam UI.** Lógica de domínio separada da apresentação.
3. **Models NÃO importam nada do pacote** exceto `selection.py` (lazy import).
4. **Storage NÃO importa connectors ou services.** Storage é camada inferior.
5. **Facades NÃO contêm lógica.** São re-exports puros.
6. **RuntimeSecrets NÃO é serializado.** Credenciais ficam apenas em memória.
7. **BrowserCache NÃO armazena credenciais ou conteúdo.** Apenas metadados.
