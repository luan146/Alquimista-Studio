# AUDITORIA TÉCNICA — ALQuimista Studio 5.0

> **Modo:** somente leitura — nenhum arquivo foi criado, editado, movido, excluído, formatado ou corrigido.
> **Data da análise:** 2026-08-04
> **Versão declarada:** 5.0.0 (`alquimista/__init__.py`)

---

## 1 — Visão geral do projeto

### 1.1 Finalidade principal

O ALQuimista Studio é uma aplicação **desktop** independente, escrita em Python 3.12 com interface PySide6, para **aquisição, seleção, normalização, versionamento e exportação de conteúdo** proveniente de plataformas de conhecimento (wikis corporativas, help centers, documentação) por meio de APIs oficiais.

### 1.2 Problema que o programa resolve

Extrai documentação de plataformas como Confluence, GitBook, Zendesk Guide, Notion e SharePoint, converte para Markdown padronizado com metadados, calcula hashes SHA-256 para detecção de alterações, suporta atualização incremental e consolida múltiplos documentos em pacotes.

### 1.3 Funcionalidades existentes e operacionais

| Funcionalidade | Status |
|---|---|
| Interface desktop PySide6 completa (wizard multi-etapa) | Operacional |
| Conector Confluence REST (Server/Data Center) | Estável |
| Conector GitBook REST v1 | Disponível |
| Conector Zendesk Guide (Help Center API) | Disponível |
| Autenticação: pública, Basic, Bearer, sessão de navegador | Operacional |
| Descoberta de espaços/contêineres via API | Operacional |
| Seleção de múltiplos espaços e páginas em árvore | Operacional |
| Conversão HTML para Markdown com BeautifulSoup + markdownify | Operacional |
| Metadados YAML/Markdown por documento | Operacional |
| SHA-256, detecção de alterações, atualização incremental | Operacional |
| Manifesto JSON versionado (schema v4) com índice SQLite | Operacional |
| Consolidação em pacotes com particionamento | Operacional |
| Operações canceláveis com CancellationToken | Operacional |
| Escrita atômica com transações e rollback (FileTransaction) | Operacional |
| Rate limiting, retry com backoff e Retry-After | Operacional |
| Proteção DPAPI para sessões de navegador (Windows) | Operacional |
| Login interativo via Playwright (Chromium) | Operacional |
| Descoberta lazy com cache SQLite (BrowserCache) | Operacional |
| Relatório de execução estruturado por fonte/contêiner/documento | Operacional |
| Pipeline CI/CD (GitHub Actions: ruff, mypy, pytest) | Configurado |
| Geração de executável via PyInstaller | Configurado |

### 1.4 Funcionalidades parcialmente implementadas

| Funcionalidade | Estado |
|---|---|
| Conector Notion (API oficial) | Código completo mas marcado DEVELOPMENT, implemented=False no registry |
| Conector SharePoint (Microsoft Graph) | Código completo mas marcado DEVELOPMENT, implemented=False no registry |

### 1.5 Funcionalidades aparentemente abandonadas

| Item | Evidência |
|---|---|
| Modos separados "extrator" e "consolidador" | Scripts legados redirecionam para run_app("complete") com comentário de compatibilidade |
| alquimista_core.py como módulo autônomo | Agora é fachada de compatibilidade; new code importa de alquimista |
| .tmp_patch_sel.py | Arquivo temporário na raiz — possivelmente resíduo de desenvolvimento |
---

## 2 — Mapa estrutural

### 2.1 Árvore de diretórios

```
Alquimista studio 2.0 - Copia/
+-- .github/workflows/quality.yml    # CI: ruff, mypy, pytest
+-- alquimista/                      # Pacote principal (~10.500 linhas)
|   +-- __init__.py                  # Exports + __version__
|   +-- models.py                    # Modelos Pydantic (475 linhas)
|   +-- services.py                  # ExtractionService + ConsolidationService (1112 linhas)
|   +-- client.py                    # ConfluenceClient HTTP (443 linhas)
|   +-- markdown.py                  # MarkdownTransformer + KnowledgeDocumentRenderer (476 linhas)
|   +-- storage.py                   # ManifestStore, FileTransaction, atomic writes (231 linhas)
|   +-- manifest_index.py            # Índice SQLite do manifesto (100 linhas)
|   +-- errors.py                    # Hierarquia de exceções (27 linhas)
|   +-- runtime.py                   # CancellationToken, RateLimiter (31 linhas)
|   +-- selection.py                 # SelectionStore (50 linhas)
|   +-- reports.py                   # ExecutionReport (54 linhas)
|   +-- auth.py                      # browser_login via Playwright (105 linhas)
|   +-- session_store.py             # DPAPI + sessões criptografadas (112 linhas)
|   +-- source_detection.py          # Detecção de plataforma por URL (118 linhas)
|   +-- confluence_url.py            # Parser de URLs Confluence (83 linhas)
|   +-- logging_utils.py             # Logger com redação de credenciais (39 linhas)
|   +-- connectors/                  # Sub-pacote de conectores
|   |   +-- base.py                  # KnowledgeSourceConnector (ABC) (102 linhas)
|   |   +-- registry.py              # ConnectorRegistry + default_registry() (171 linhas)
|   |   +-- confluence.py            # ConfluenceRestConnector (580 linhas)
|   |   +-- gitbook.py               # GitBookConnector (317 linhas)
|   |   +-- zendesk.py               # ZendeskGuideConnector (337 linhas)
|   |   +-- notion.py                # NotionConnector (204 linhas)
|   |   +-- sharepoint.py            # SharePointConnector (143 linhas)
|   |   +-- http.py                  # ApiHttpClient compartilhado (239 linhas)
|   +-- browser/                     # Descoberta lazy + cache
|   |   +-- contracts.py             # Protocolos e dataclasses (236 linhas)
|   |   +-- cache.py                 # BrowserCache SQLite (498 linhas)
|   |   +-- service.py               # LazyDiscoveryService (264 linhas)
|   |   +-- adapters.py              # ConnectorDiscoveryAdapter (200 linhas)
|   +-- ui/                          # Interface PySide6
|       +-- main_window.py           # MainWindow monolítica (2651 linhas)
|       +-- components.py            # Widgets reutilizáveis (869 linhas)
|       +-- theme.py                 # Temas e estilos (349 linhas)
|       +-- controllers.py           # RuntimeSecrets + RuntimeBuilder (133 linhas)
|       +-- execution_controller.py  # Orquestração de operações (116 linhas)
|       +-- operation_controller.py  # WorkerOperationController (146 linhas)
|       +-- process_workers.py       # QRunnable workers (225 linhas)
|       +-- tree_models.py           # Modelos de árvore (139 linhas)
|       +-- connector_forms.py       # Formulários por conector (66 linhas)
|       +-- project_controller.py    # Load/save projeto (27 linhas)
|       +-- source_controller.py     # Seleção de fontes (82 linhas)
|       +-- state.py                 # MainWindowState (13 linhas)
|       +-- workers.py               # Worker genérico (37 linhas)
|       +-- page_registry.py         # Registro de páginas da UI (23 linhas)
|       +-- mixins/                  # Mixins da MainWindow
|       |   +-- connection_mixin.py  # (254 linhas)
|       |   +-- selection_mixin.py   # (403 linhas)
|       |   +-- source_mixin.py      # (588 linhas)
|       |   +-- tree_mixin.py        # (103 linhas)
|       +-- pages/                   # Construtores de páginas
|           +-- dashboard_page.py    # (57 linhas)
|           +-- sources_page.py      # (149 linhas)
|           +-- connection_page.py   # (135 linhas)
|           +-- selection_page.py    # (188 linhas)
|           +-- markdown_page.py     # (225 linhas)
|           +-- review_page.py       # (217 linhas)
|           +-- extraction_page.py   # (59 linhas)
|           +-- consolidation_page.py # (244 linhas)
|           +-- results_page.py      # (32 linhas)
+-- tests/                           # Suíte de testes (~2.935 linhas)
|   +-- conftest.py
|   +-- test_auth.py                 # 98 linhas
|   +-- test_browser_cache.py        # 158 linhas
|   +-- test_build_documentation.py  # 10 linhas
|   +-- test_client.py               # 160 linhas
|   +-- test_confluence_url.py       # 36 linhas
|   +-- test_connectors.py           # 573 linhas
|   +-- test_lazy_confluence.py      # 163 linhas
|   +-- test_live_root_discovery.py  # 24 linhas
|   +-- test_markdown.py             # 75 linhas
|   +-- test_models_storage.py       # 164 linhas
|   +-- test_process_workers.py      # 100 linhas
|   +-- test_services.py             # 400 linhas
|   +-- test_session_store.py        # 51 linhas
|   +-- test_source_detection.py     # 25 linhas
|   +-- test_ui.py                   # 623 linhas
|   +-- test_ui_browser_cache_integration.py # 112 linhas
|   +-- test_ui_controllers.py       # 51 linhas
|   +-- test_ui_lazy_regressions.py  # 110 linhas
+-- docs/                            # Documentação
|   +-- architecture.md
|   +-- manifest-index.md
|   +-- connectors/                  # Docs por conector
|   +-- screenshots/                 # Capturas de tela
+-- assets/icons/                    # Ícones
+-- tools/                           # Utilitários de dev
+-- alquimista_core.py               # Fachada de compatibilidade
+-- alquimista_gui.py                # Entry point da GUI
+-- alquimista_studio_completo.py    # Lançador (-> run_app)
+-- alquimista_studio_extrator.py    # Lançador legado (-> run_app)
+-- alquimista_studio_consolidador.py # Lançador legado (-> run_app)
+-- test_alquimista_studio.py        # (possivelmente legado, fora de tests/)
+-- pyproject.toml                   # Config ruff + mypy
+-- requirements.txt                 # Deps de produção
+-- requirements-dev.txt             # Deps de desenvolvimento
+-- requirements-browser.txt         # Deps do navegador
+-- requirements.freeze.txt          # Pinagem de versões
+-- constraints.txt                  # Constraints do pip
+-- config.example.json              # Exemplo de projeto
+-- projeto_alquimista.json          # Projeto de trabalho
+-- ALQuimista Studio.spec           # PyInstaller spec
+-- *.bat / *.sh                     # Scripts de instalação
```

### 2.2 Contagem total de código

| Camada | Linhas (aprox.) |
|---|---|
| Núcleo (alquimista/ excluindo ui/ e browser/) | ~3.500 |
| Conectores (connectors/) | ~1.800 |
| Browser/Discovery (browser/) | ~1.200 |
| Interface (ui/) | ~6.800 |
| Testes (tests/) | ~2.935 |
| Scripts raiz + docs | ~300 |
| **Total estimado** | **~16.500** |
---

## 3 — Fluxo de dados (entradas, processamento, saídas)

### 3.1 Entradas

| Entrada | Origem |
|---|---|
| URL da plataforma | Usuário (interface) |
| Credenciais temporárias (token, senha, cookie) | Usuário (em runtime, nunca persistidas no projeto) |
| Arquivo de projeto .json | Disco local |
| Seleção de espaços/páginas | Usuário (interface, via SelectionStore) |
| Opções de extração e consolidação | Usuário (interface) |

### 3.2 Processamento

```
URL -> detect_source_url() -> ConnectorRegistry.create()
  -> KnowledgeSourceConnector.validate_connection()
  -> list_containers() -> list_documents()
  -> get_document() -> HTML -> MarkdownTransformer/KnowledgeDocumentRenderer
  -> normalize_markdown() -> sha256_text()
  -> ExtractionService.run() -> ManifestStore + atomic writes
  -> ConsolidationService.run() -> pacotes .md
```

### 3.3 Saídas

| Saída | Formato |
|---|---|
| Documentos individuais Markdown | .md com metadados YAML |
| Manifesto | manifesto_alquimista.json (JSON) |
| Índice do manifesto | indice_manifesto_alquimista.sqlite3 |
| Relatório de execução | relatorio_execucao_alquimista.json |
| Pacotes consolidados | .md agrupados |
| Índice de pacotes | indice_pacotes_alquimista.json |
| Falhas | falhas_alquimista.json |
| Sessões de navegador | Criptografadas com DPAPI fora da árvore do projeto |
| Log técnico | Arquivo de log com redação de credenciais |

### 3.4 Integrações externas

| Integração | Mecanismo | Status |
|---|---|---|
| Confluence Server/DC | REST API via ConfluenceClient / ConfluenceRestConnector | Estável |
| GitBook | REST API v1 via ApiHttpClient | Disponível |
| Zendesk Guide | Help Center API via ApiHttpClient | Disponível |
| Notion | API oficial via ApiHttpClient | Em desenvolvimento |
| SharePoint Online | Microsoft Graph via ApiHttpClient | Em desenvolvimento |
| Playwright (Chromium) | Login interativo de navegador | Operacional |
---

## 4 — Inventário de módulos, classes e funções

### 4.1 Módulo alquimista.models (475 linhas)

| Classe/Função | Responsabilidade | Chamado por |
|---|---|---|
| ProjectConfig | Modelo Pydantic do projeto completo | storage.load_project, MainWindow |
| SourceConfig | Configuração de uma fonte de dados | ProjectConfig.sources |
| ExtractionOptions | Opções de extração (timeout, retry, proxy) | ConfluenceClient, ApiHttpClient |
| ConsolidationOptions | Opções de consolidação (agrupamento, limites) | ConsolidationService |
| MarkdownOptions | Opções de renderização Markdown | MarkdownTransformer, KnowledgeDocumentRenderer |
| ManifestDocument | Documento manifesto com entradas | ManifestStore |
| ManifestEntry | Entrada individual no manifesto | ExtractionService, ConsolidationService |
| AuthMode | Enum de modos de autenticação | ConfluenceClient, MainWindow |
| KnowledgeSource | Modelo genérico de fonte | Conectores |
| KnowledgeContainer | Modelo genérico de contêiner | Conectores |
| KnowledgeDocument | Documento com conteúdo | Conectores, ExtractionService |
| KnowledgeDocumentMetadata | Metadados sem conteúdo | Conectores, BrowserCache |
| KnowledgeSelection | Seleção persistível | SelectionStore |
| ConnectorCapabilities | Capacidades de um conector | ConnectorDescriptor |
| ConnectorStatus | Enum de status do conector | ConnectorRegistry |
| EntryStatus | Enum de status de entrada do manifesto | ExtractionService |
| default_project() | Cria projeto com valores padrão | MainWindow.__init__ |
| now_iso() | Timestamp ISO UTC | Vários |
| slugify() | Normaliza strings para slugs | SourceConfig |
| stable_json_hash() | Hash determinístico de dicts JSON | ExtractionService |
| validate_source_identifier() | Valida IDs de fonte contra path traversal | session_store |

### 4.2 Módulo alquimista.services (1112 linhas)

| Classe/Função | Responsabilidade | Chamado por |
|---|---|---|
| ExtractionService | Orquestra extração multi-fonte | execution_controller |
| ExtractionService.run() | Loop principal de extração | Workers da UI |
| ExtractionService._extract_page() | Extrai uma página individual (legado) | run() |
| ExtractionService._extract_generic_document() | Extrai via conector genérico | run() |
| ConsolidationService | Orquestra consolidação em pacotes | execution_controller |
| ConsolidationService.preview() | Pré-visualiza agrupamento | MainWindow |
| ConsolidationService.run() | Gera pacotes consolidados | Workers da UI |
| SourceRuntime | Dataclass com estado de execução por fonte | ExtractionService |
| sanitize_filename() | Remove caracteres inseguros de nomes | ExtractionService, ConsolidationService |
| demote_headings() | Rebaixa níveis de heading Markdown | ConsolidationService |

### 4.3 Módulo alquimista.client (443 linhas)

| Classe/Função | Responsabilidade | Chamado por |
|---|---|---|
| ConfluenceClient | Cliente HTTP para Confluence REST API | ConfluenceRestConnector, RuntimeBuilder |
| _request() | Faz requisição com retry/backoff | Métodos do client |
| fetch_tree() | Descobre árvore de páginas | RuntimeBuilder.build() |
| resolve_root() | Resolve página raiz por modo | fetch_tree() |
| fetch_page() | Busca uma página por ID | fetch_tree(), ExtractionService |
| list_pages() | Lista páginas de um espaço | resolve_root(), fetch_tree() |
| discover_spaces() | Lista espaços Confluence | MainWindow (conexão) |
| search_pages() | Busca CQL por título | ConfluenceRestConnector.search_documents() |

### 4.4 Módulo alquimista.markdown (476 linhas)

| Classe/Função | Responsabilidade | Chamado por |
|---|---|---|
| MarkdownTransformer | Renderiza HTML Confluence para Markdown | ExtractionService (legado) |
| KnowledgeDocumentRenderer | Renderizador genérico de documentos | ExtractionService (conectores) |
| normalize_markdown() | NFC + normaliza whitespace | Vários |
| sha256_text() | Hash SHA-256 do Markdown normalizado | ExtractionService |
| page_metadata() | Extrai metadados de página Confluence | ExtractionService |
| knowledge_document_metadata() | Metadados de documento genérico | ExtractionService |
| sample_page() | Página de exemplo para preview | MainWindow |

### 4.5 Módulo alquimista.storage (231 linhas)

| Classe/Função | Responsabilidade | Chamado por |
|---|---|---|
| ManifestStore | Carrega/salva manifesto com migração de schema | ExtractionService, ConsolidationService |
| FileTransaction | Transação de arquivos com rollback | ExtractionService.run(), ConsolidationService.run() |
| atomic_write_text() | Escrita atômica com fsync e backup | FileTransaction, session_store |
| atomic_write_json() | Escrita atômica JSON | ManifestStore.save() |
| confined_path() | Valida caminhos contra path traversal | FileTransaction, ExtractionService |
| load_project() | Carrega e valida projeto JSON | MainWindow |
| save_project() | Salva projeto JSON | MainWindow |

### 4.6 Conectores (alquimista.connectors)

| Classe | Plataforma | Linhas | Status |
|---|---|---|---|
| KnowledgeSourceConnector (ABC) | Contrato base | 102 | Base |
| ConfluenceRestConnector | Confluence | 580 | Estável |
| GitBookConnector | GitBook | 317 | Disponível |
| ZendeskGuideConnector | Zendesk | 337 | Disponível |
| NotionConnector | Notion | 204 | Em desenvolvimento |
| SharePointConnector | SharePoint | 143 | Em desenvolvimento |
| ApiHttpClient | HTTP compartilhado | 239 | Operacional |
| ConnectorRegistry | Registro + factory | 171 | Operacional |

### 4.7 Browser / Discovery (alquimista.browser)

| Classe | Responsabilidade | Linhas |
|---|---|---|
| BrowserCache | Cache SQLite de descoberta lazy | 498 |
| LazyDiscoveryService | Serviço cache-first síncrono | 264 |
| ConnectorDiscoveryAdapter | Adapta conectores ao protocolo de descoberta | 200 |
| Contratos (contracts.py) | Protocolos, dataclasses, enums | 236 |

### 4.8 Interface (alquimista.ui)

| Classe/Módulo | Responsabilidade | Linhas |
|---|---|---|
| MainWindow | Janela principal monolítica | 2651 |
| ConnectionMixin | Lógica de conexão | 254 |
| SourceMixin | Gerenciamento de fontes | 588 |
| SelectionMixin | Lógica de seleção | 403 |
| TreeMixin | Construção de árvores | 103 |
| WorkerOperationController | Controle de operações em thread | 146 |
| Worker | QRunnable genérico | 37 |
| 9 módulos de páginas | Construtores de widgets | ~1.300 |
| components.py | Widgets reutilizáveis | 869 |
| theme.py | Temas e QSS | 349 |
---

## 5 — Análise de qualidade e observações técnicas

### 5.1 Pontos fortes

1. **Arquitetura de conectores bem definida**: O contrato `KnowledgeSourceConnector` (ABC) com `ConnectorRegistry` permite adicionar plataformas sem alterar o núcleo. O pipeline genérico de extração aceita qualquer conector registrado.

2. **Segurança de credenciais robusta**: Sessões de navegador são criptografadas com DPAPI (Windows). `RuntimeSecrets` mantém segredos somente em memória. `connector_options` rejeita chaves com padrões de segredo. O logger redige credenciais. URLs com credenciais embutidas são recusadas.

3. **Resiliência de I/O**: `FileTransaction` implementa commit/rollback atômico. `atomic_write_text()` usa tempfile + fsync + os.replace. `confined_path()` previne path traversal em ambas as direções.

4. **Resiliência de rede**: `ApiHttpClient` e `ConfluenceClient` implementam retry com backoff exponencial, Retry-After, X-RateLimit-Reset, rate limiting local, proxy configurável, timeouts separados (connect/read) e cancelamento cooperativo.

5. **Modelo de dados com Pydantic v2**: Validação forte, serialização determinística, migração de schema no `ManifestStore.load()` para manifestos legados (listas e dicts antigos).

6. **Testes abrangentes**: ~2.935 linhas de testes cobrindo client, connectors, services, storage, models, markdown, UI, browser cache, lazy discovery e regressões.

7. **CI/CD configurado**: GitHub Actions roda compilação, ruff, mypy e pytest em Windows.

8. **Documentação técnica**: `docs/architecture.md` descreve o fluxo de dados. Docs individuais para cada conector.

### 5.2 Pontos de atenção

#### 5.2.1 MainWindow com responsabilidade excessiva (2651 linhas)

- **Arquivo:** `alquimista/ui/main_window.py`
- **Problema:** Mesmo com a extração de mixins e páginas, a classe MainWindow ainda concentra lógica de: construção de todas as sub-telas, gerenciamento de estado do projeto, controle de fluxo de operação, manipulação de resultados, navegação entre páginas, persistência de configurações.
- **Impacto:** Dificulta testes unitários da UI, aumenta risco de regressão, torna o arquivo difícil de navegar.
- **Recomendação:** Considerar extrair mais lógica para controllers dedicados (ex: NavigationController, ProjectStateController, ResultsController).

#### 5.2.2 Dois caminhos de extração paralelos

- **Arquivos:** `alquimista/services.py` (métodos _extract_page e _extract_generic_document), `alquimista/controllers.py` (RuntimeBuilder.build)
- **Problema:** O ExtractionService.run() bifurca entre o caminho legado (ConfluenceClient direto + MarkdownTransformer) e o caminho genérico (conector + KnowledgeDocumentRenderer). O RuntimeBuilder em controllers.py também tem dois build() — um como método de instância usando _build_generic_runtimes e outro como método parcial usando ConfluenceClient.fetch_tree().
- **Impacto:** Duplicação de lógica de renderização e montagem de metadados. O Confluence poderia usar o pipeline genérico completo.
- **Recomendação:** Unificar o pipeline para que o Confluence passe inteiramente pelo ConfluenceRestConnector (que já existe e está funcional), eliminando o caminho legado.

#### 5.2.3 Conectores Notion e SharePoint marcados como "em desenvolvimento" mas com código completo

- **Arquivos:** `alquimista/connectors/notion.py`, `alquimista/connectors/sharepoint.py`, `alquimista/connectors/registry.py`
- **Problema:** Ambos os conectores implementam a interface completa (validate_connection, list_containers, list_documents, get_document), mas o registry os marca com implemented=False e status=ConnectorStatus.DEVELOPMENT. Além disso, get_document_children() e normalize_document() não estão implementados (lançam NotImplementedError herdado da ABC).
- **Impacto:** Os métodos faltantes impediriam uso completo mesmo que fossem habilitados.
- **Evidência faltante:** Testes específicos para Notion e SharePoint não existem na suíte (apenas testes genéricos em test_connectors.py que os instanciam com mocks).

#### 5.2.4 Arquivo test_alquimista_studio.py fora da pasta tests/

- **Arquivo:** `test_alquimista_studio.py` (raiz do projeto)
- **Problema:** Existe um arquivo de teste na raiz, fora do padrão tests/. Pode ser resíduo de desenvolvimento ou ter conteúdo duplicado.
- **Recomendação:** Verificar conteúdo e mover para tests/ ou remover.

#### 5.2.5 Arquivo temporário na raiz

- **Arquivo:** `.tmp_patch_sel.py`
- **Problema:** Nome sugere arquivo temporário gerado durante desenvolvimento/debug.
- **Recomendação:** Avaliar se é necessário e remover se não for.

#### 5.2.6 alquimista_core.py — fachada de compatibilidade com star import

- **Arquivo:** `alquimista_core.py`
- **Problema:** Usa `from alquimista.errors import *` (star import), o que polui o namespace. O restante das importações é explícito.
- **Impacto:** Baixo — é fachada de compatibilidade e errors.py somente define classes de exceção (__all__ não declarado no errors.py).
- **Recomendação:** Considerar declarar __all__ em errors.py ou usar imports explícitos.

#### 5.2.7 pyproject.toml sem seção [project]

- **Arquivo:** `pyproject.toml`
- **Problema:** O pyproject.toml contém apenas configurações de ruff e mypy, sem metadados do projeto ([project], name, version, dependencies). O projeto não é instalável via pip/setuptools.
- **Impacto:** Impede distribuição como pacote Python padrão. Dependências ficam somente nos requirements*.txt.
- **Recomendação:** Adicionar seção [project] com metadados mínimos se distribuição via pip for desejada.

#### 5.2.8 Duplicação no ApiHttpClient — método download possivelmente repetido

- **Arquivo:** `alquimista/connectors/http.py`
- **Problema:** O módulo parece conter o método download() definido duas vezes com lógica idêntica (observado na saída durante leitura). Pode ser um artefato de merge ou cópia.
- **Evidência necessária:** Inspecionar o arquivo completo sem truncagem para confirmar se a segunda definição sobrescreve a primeira ou se é código morto.
### 5.3 Segurança

| Aspecto | Avaliação |
|---|---|
| Credenciais em memória (nunca serializadas) | Adequado |
| DPAPI para sessões de navegador | Adequado (Windows) |
| Validação de URL (recusa scheme != https para auth) | Adequado |
| Recusa de URLs com usuário/senha embutidos | Adequado |
| Redação de credenciais em logs | Adequado |
| Rejeição de chaves sensíveis em connector_options | Adequado |
| Path traversal prevention (confined_path, session_path) | Adequado |
| Validação de source_identifier | Adequado |
| HTTPS obrigatório para autenticação | Adequado |
| Limpeza de credenciais no close() dos conectores | Adequado (GitBook, Zendesk limpam token e header) |
| Fallback para file-permissions em Linux (sessões) | Funcional mas menos robusto que DPAPI |

### 5.4 Cobertura de testes

| Módulo | Teste correspondente | Cobertura |
|---|---|---|
| client.py | test_client.py (160 l.) | Boa — retry, auth, edge cases |
| connectors/ | test_connectors.py (573 l.) | Boa — todos os conectores com mocks |
| services.py | test_services.py (400 l.) | Boa — extração, consolidação |
| models.py + storage.py | test_models_storage.py (164 l.) | Razoável |
| markdown.py | test_markdown.py (75 l.) | Básica |
| auth.py | test_auth.py (98 l.) | Boa |
| session_store.py | test_session_store.py (51 l.) | Básica |
| browser/cache.py | test_browser_cache.py (158 l.) | Boa |
| browser/ (lazy) | test_lazy_confluence.py (163 l.) | Boa |
| confluence_url.py | test_confluence_url.py (36 l.) | Básica |
| source_detection.py | test_source_detection.py (25 l.) | Mínima |
| ui/ | test_ui.py (623 l.) + 3 arquivos | Razoável para GUI |
| ui/process_workers.py | test_process_workers.py (100 l.) | Boa |

**Observações sobre testes:**
- Testes de integração (integration, real_confluence) exigem credenciais e ficam desabilitados.
- test_build_documentation.py tem apenas 10 linhas — possivelmente placeholder.
- source_detection.py tem cobertura mínima (25 linhas para 118 linhas de código com 6 plataformas).

---

## 6 — Dependências externas

### 6.1 Produção (requirements.txt)

| Pacote | Versão | Uso |
|---|---|---|
| PySide6 | >=6.10, <7 | Interface gráfica desktop |
| pydantic | >=2.9, <3 | Modelos de dados com validação |
| requests | >=2.31, <3 | HTTP client |
| beautifulsoup4 | >=4.12, <5 | Parsing HTML |
| markdownify | >=1.2, <2 | Conversão HTML para Markdown |

### 6.2 Navegador (requirements-browser.txt)

| Pacote | Versão | Uso |
|---|---|---|
| playwright | >=1.45, <2 | Login interativo de navegador |

### 6.3 Desenvolvimento (requirements-dev.txt)

| Pacote | Versão | Uso |
|---|---|---|
| pytest | >=8.3, <10 | Framework de testes |
| pytest-qt | >=4.4, <5 | Testes de widgets Qt |
| pytest-cov | >=6, <8 | Cobertura |
| ruff | >=0.12, <1 | Linter + formatter |
| mypy | >=1.17, <2 | Type checker |

---

## 7 — Lacunas e limitações identificadas

### 7.1 O que faltou nesta auditoria

| Item | Razão |
|---|---|
| Execução de testes | Auditoria somente leitura — testes não foram executados |
| Análise de cobertura real | Requer pytest-cov em execução |
| Verificação de ruff/mypy | Requer execução das ferramentas |
| Teste do executável PyInstaller | Requer build |
| Teste de conectores reais | Requer credenciais e acesso externo |
| Conteúdo de models.py truncado | O arquivo de 475 linhas apareceu truncado na leitura; classes foram inferidas por uso em outros módulos |
| Conteúdo de logging_utils.py truncado | Apenas uma linha visível; funcionalidade inferida por uso |
| .tmp_patch_sel.py não inspecionado | Parece arquivo temporário |
| test_alquimista_studio.py (raiz) não inspecionado | Pode ser duplicata ou legado |

### 7.2 Arquivos analisados

Todos os arquivos .py dentro de alquimista/ (60 arquivos), todos os arquivos em tests/ (19 arquivos), os scripts raiz (5 .py), configurações (pyproject.toml, requirements*.txt, config.example.json, pytest.ini), CI (.github/workflows/quality.yml), documentação (docs/architecture.md), e README.md.

### 7.3 Evidência necessária para aprofundamento

| Questão | Evidência |
|---|---|
| O pipeline legado do Confluence ainda é necessário? | Testar se ConfluenceRestConnector cobre todos os cenários que ConfluenceClient + MarkdownTransformer cobrem |
| Notion e SharePoint estão prontos para promoção? | Implementar get_document_children, normalize_document, testes dedicados, e validar com APIs reais |
| ApiHttpClient.download está duplicado? | Inspeção completa sem truncagem do http.py |
| Cobertura real de testes | Executar pytest --cov |
| Conformidade ruff/mypy | Executar ruff check e mypy |

---

## 8 — Resumo executivo

O ALQuimista Studio 5.0 é um projeto **maduro e bem arquitetado** para aquisição de conhecimento via APIs. Os pontos fortes incluem:

- Arquitetura de conectores extensível com contrato claro
- Segurança de credenciais exemplar (DPAPI, runtime-only, redação em logs)
- Resiliência robusta de I/O (transações atômicas) e rede (retry, backoff, rate limit)
- Modelo de dados com Pydantic v2 e migração de schema
- Suíte de testes abrangente com CI configurado

Os principais pontos de melhoria são:

- **MainWindow monolítica** (2651 linhas) que concentra responsabilidades demais
- **Dois caminhos de extração** paralelos (legado Confluence vs. genérico) que poderiam ser unificados
- **Conectores Notion/SharePoint** com código escrito mas incompletos (faltam métodos abstratos e testes)
- **Arquivos residuais** na raiz (.tmp_patch_sel.py, test_alquimista_studio.py) e pyproject.toml sem metadados de projeto

Nenhum problema crítico de segurança, corrupção de dados ou falha arquitetural grave foi identificado. O projeto está em condição funcional para os conectores marcados como estáveis/disponíveis.