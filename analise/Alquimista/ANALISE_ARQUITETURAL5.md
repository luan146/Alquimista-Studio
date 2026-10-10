# Relatório de Análise Arquitetural, Modularização, Estabilidade e Expansão
## Projeto ALQuimista Studio 3.0

> **Data da Análise:** Agosto / 2026  
> **Status:** Concluído — Diretrizes Arquiteturais para Preservação do Confluence e Expansão Segura  
> **Modo:** Leitura / Diagnóstico Estático (Sem alteração do código fonte)  

---

## 1. Resumo Executivo

### Estado Atual
O **ALQuimista Studio 3.0** é uma aplicação desktop em Python (PySide6) desenhada para extração, conversão e consolidação de documentações técnicas em Markdown. O projeto evoluiu de uma ferramenta focada em Confluence para um sistema multi-plataforma que já inclui conectores para **Confluence**, **GitBook**, **Notion**, **SharePoint** e **Zendesk**, além de um subsistema de descoberta e cache via Playwright/Browser.

A arquitetura atual possui abstrações importantes (como o ABC `KnowledgeSourceConnector` em [`alquimista/connectors/base.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/base.py), a transação atômica em [`alquimista/storage.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/storage.py) e o isolamento de UI via mixins). No entanto, o pipeline de processamento posterior (transformação para Markdown e extração/consolidação) ainda preserva acoplamentos históricos fortes com a estrutura do Confluence.

### Principal Risco
**Regressão cruzada por acoplamento nos componentes compartilhados.**  
Atualmente, a classe [`MarkdownTransformer`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/markdown.py#L417) em `alquimista/markdown.py` contêm lógica diretamente voltada a tags, macros e URLs de anexos específicas do Confluence (ex: `_replace_macros`, `_attachment_url`). Se um desenvolvedor alterar esses componentes genéricos para tratar idiossincrasias do Notion, GitBook ou de um futuro leitor de Websites, corre um **risco crítico de quebrar a conversão do Confluence**, que hoje é o conector mais estável e testado.

Outro ponto crítico é o acoplamento concentrado na [`MainWindow`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/main_window.py) (~139 KB, ~3.500 linhas), que orquestra estados de seleção, lazy loading, sincronização de controles de UI, preparação de runtimes e despacho de workers.

### Principal Oportunidade
Evoluir a arquitetura para um modelo **Plugin/Adapter com Modelo Intermediário Canônico** e **Estratégia de Renderização por Plataforma**, mantendo o Core do ALQuimista 100% agnóstico. Ao encapsular parsing, extração e transformações específicas dentro de cada conector, o Core passa a orquestrar apenas o contrato intermediário (`KnowledgeDocument`).

### Recomendação Arquitetural Central
**Não reescrever o projeto.** Adoção de uma **Evolução Incremental orientada por Contratos e Golden Samples**:
1. Criar um conjunto de **Golden Samples** (fixtures de HTML/JSON + Markdown esperado) para o Confluence **antes** de qualquer alteração estrutural.
2. Isolar os pipelines de parsing/transformação de HTML/blocos específicos dentro da pasta de cada conector.
3. Manter a [`MainWindow`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/main_window.py) delegando orquestração para controladores de serviço (Application Layer).

---

## 2. Como o Projeto Funciona Atualmente

### Reconstrução do Pipeline Real
Através da inspeção do código-fonte em [`alquimista/ui/main_window.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/main_window.py), [`alquimista/ui/execution_controller.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/execution_controller.py), [`alquimista/services.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/services.py) e nos conectores em [`alquimista/connectors/`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/), o fluxo real do sistema foi mapeado:

```text
[ ENTRADA DO USUÁRIO ]
       │ (Insere URL ou escolhe tipo de fonte na UI)
       ▼
[ DETECÇÃO DE PLATAFORMA ] ──────► source_detection.py (detect_source_url via Regex/Parse de URL)
       │
       ▼
[ PROJETO E CONFIGURAÇÃO ] ──────► models.py (SourceConfig, ProjectConfig) ──► storage.py (save_project/load_project)
       │
       ▼
[ AUTENTICAÇÃO E CONEXÃO ] ──────► ui/mixins/connection_mixin.py ──► auth.py / session_store.py (DPAPI) / controllers.py (RuntimeSecrets)
       │                                                                  │
       │                                                                  ▼
       └─────────────────────────────────────────────────────────► connector.validate_connection() (ApiHttpClient)
       │
       ▼
[ DESCOBERTA DA ESTRUTURA ] ─────► tree_mixin.py + selection_mixin.py
       │                                 │
       ├─────────────────────────────────┼──► connector.list_containers() (Espaços/Bancos/Seções)
       │                                 └──► tree_models.py (tree_containers)
       ▼
[ ARVORE E LAZY LOADING ] ───────► connector.list_root_documents() / list_document_children() / list_documents()
       │                                 │
       │                                 └──► SelectionStore (selection.py) [Guarda estado da seleção independente do Qt]
       ▼
[ REVISÃO E PREPARAÇÃO ] ────────► review_page.py ──► execution_controller.py (prepare_runtimes)
       │                                                   │
       │                                                   └──► Cria SourceRuntime (conector + chaves selecionadas)
       ▼
[ DISPACHO DE EXTRAÇÃO ] ────────► operation_controller.py ──► process_workers.py / workers.py (QThreadPool)
       │
       ▼
[ MOTOR DE EXTRAÇÃO ] ──────────► services.py:ExtractionService._run_generic()
       │                                 │
       ├─────────────────────────────────┼──► connector.get_document(doc_id, container_id)
       │                                 │      └─ Confluence: HTML cru
       │                                 │      └─ Notion: Parsing de blocos JSON
       │                                 │      └─ Zendesk/GitBook/SharePoint: HTML / Markdown
       │                                 │
       ├─────────────────────────────────┼──► Normalização ──► models.py:KnowledgeDocument
       │                                 │
       ├─────────────────────────────────┼──► Checagem Incremental ──► SHA-256 (metadata + etag + transform_hash)
       │                                 │      └─ Se inalterado ──► EntryStatus.UNCHANGED (Reaproveita disco)
       │                                 │
       ├─────────────────────────────────┼──► Renderização ──► markdown.py (KnowledgeDocumentRenderer / MarkdownTransformer)
       │                                 │
       └─────────────────────────────────┴──► Escrita Atômica ──► storage.py (FileTransaction -> tmp -> commit)
                                                └─ Grava .md individual + manifesto_alquimista.json
       │
       ▼
[ CONSOLIDAÇÃO (OPCIONAL) ] ─────► services.py:ConsolidationService
       │                                 │
       │                                 ├──► Modo Arquivo Único / Pacote / Índice
       │                                 ├──► markdown.py (demote_headings para rebaixamento de títulos)
       │                                 └──► FileTransaction (grava consolidado em disco)
       ▼
[ RELATÓRIOS E RESULTADOS ] ─────► reports.py (ExecutionReport) ──► results_page.py (Exibe falhas, métricas e pasta final)
```

---

## 3. Mapa de Responsabilidades Módulo por Módulo

Abaixo está a análise minuciosa de cada módulo do projeto atual:

| Módulo / Arquivo | Responsabilidade Principal | Dependências Diretas | Nível de Acoplamento |
| :--- | :--- | :--- | :--- |
| [`alquimista/models.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/models.py) | Esquema de dados pydantic (`KnowledgeDocument`, `SourceConfig`, `ProjectConfig`, `ManifestEntry`, `SCHEMA_VERSION=4`). | Nenhum (Core Folha). | **Baixo** (Contrato estável). |
| [`alquimista/storage.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/storage.py) | Persistência atômica via `FileTransaction`, validação de path traversal (`confined_path`), `ManifestStore`. | `models.py`, `pathlib`. | **Baixo** (Infraestrutura isolada). |
| [`alquimista/services.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/services.py) | Motor de extração (`ExtractionService`) e consolidação (`ConsolidationService`), orquestração de runtimes. | `connectors/*`, `markdown.py`, `storage.py`, `models.py`, `runtime.py`. | **Médio-Alto** (Conhece fallbacks e adapters legados de Confluence). |
| [`alquimista/markdown.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/markdown.py) | Transformação HTML→Markdown, renderizador de documentos, extração de metadados, frontmatter. | `BeautifulSoup`, `markdownify`, `models.py`. | **Alto** (Mistura lógica genérica com macros e anexos específicos do Confluence). |
| [`alquimista/connectors/base.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/base.py) | Classe base abstrata `KnowledgeSourceConnector`. | `models.py`, `browser.contracts`. | **Médio** (Mistura listagem síncrona e discovery lazy com cursor). |
| [`alquimista/connectors/confluence.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/confluence.py) | Conector de referência para Confluence REST. | `client.py`, `http.py`, `BeautifulSoup`, `markdownify`, `base.py`. | **Médio** (Muito completo, serve de referência do sistema). |
| [`alquimista/connectors/notion.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/notion.py) | Conector Notion API. Converte blocos Notion diretamente em Markdown. | `http.py`, `base.py`, `models.py`. | **Baixo** (Isolado, mas parsing de Markdown fica embutido no conector). |
| [`alquimista/connectors/gitbook.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/gitbook.py) | Conector GitBook API v1 com suporte a organizações e paginação. | `http.py`, `base.py`, `models.py`. | **Baixo** (Isolado). |
| [`alquimista/connectors/sharepoint.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/sharepoint.py) | Conector SharePoint via Microsoft Graph API. | `http.py`, `base.py`, `models.py`. | **Baixo** (Isolado). |
| [`alquimista/connectors/zendesk.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/zendesk.py) | Conector Zendesk Guide Help Center. | `http.py`, `base.py`, `markdownify`, `BeautifulSoup`. | **Baixo** (Isolado). |
| [`alquimista/connectors/http.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/http.py) | Cliente HTTP base com retry exponencial, rate limit e HTTPS obrigatório. | `urllib3` / `requests`, `runtime.py`, `errors.py`. | **Baixo** (Infraestrutura reutilizável). |
| [`alquimista/connectors/registry.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/registry.py) | Registro e catálogo centralizado de conectores disponíveis. | `base.py`, todos os conectores. | **Baixo** (Factory/Registry). |
| [`alquimista/client.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/client.py) | Cliente HTTP/REST de baixo nível legado exclusivo do Confluence. | `urllib3`, `errors.py`, `runtime.py`. | **Médio** (Usado pelo `ConfluenceRestConnector`). |
| [`alquimista/source_detection.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/source_detection.py) | Detector estático de plataforma por regex/padrões de URL. | `confluence_url.py`, `urllib.parse`. | **Baixo** (Utilitário puro). |
| [`alquimista/ui/main_window.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/main_window.py) | Janela principal PySide6, gerenciador de navegação, estado global de páginas. | `mixins/*`, `pages/*`, `controllers.py`, `services.py`. | **CRÍTICO** (Arquivo Monolítico ~139KB, concentra muitas atribuições). |
| [`alquimista/ui/mixins/selection_mixin.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/mixins/selection_mixin.py) | Lógica de marcação/desmarcação e sincronização da árvore de seleção com `SelectionStore`. | `selection.py`, `tree_models.py`, PySide6. | **Alto** (Acessa diretamente atributos da MainWindow). |
| [`alquimista/ui/mixins/tree_mixin.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/mixins/tree_mixin.py) | Gerenciamento de lazy loading de contêineres e páginas na árvore Qt. | `tree_models.py`, PySide6, `connectors/base.py`. | **Médio** (Decide síncrono vs lazy). |

---

## 4. Problemas Encontrados (Ordenados por Severidade)

### [SEVERIDADE CRÍTICA] 1. Lógica Específica de Confluence Embutida no Módulo Shared `markdown.py`
* **Fato Observado:** No arquivo [`alquimista/markdown.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/markdown.py#L274-L350), a classe `MarkdownTransformer` possui métodos utilitários explicitamente voltados ao Confluence, tais como `_attachment_url` (linha 274: constrói URL do tipo `/download/attachments/page_id/filename`), `_replace_links` (linha 278: faz parse de `/display/` e `/pages/viewpage.action`) e `_replace_macros` (linha 310: trata tags HTML `<ac:structured-macro>`, `ac:name="code"`, `ac:name="info"`).
* **Consequência:** Qualquer tentativa de adaptar ou generalizar o `MarkdownTransformer` para tratar elementos HTML de outras plataformas (como callouts do Notion ou cards do GitBook) pode modificar expressões regulares ou comportamentos de remoção de tags do Confluence, causando **regressões silenciosas em documentações Confluence**.

### [SEVERIDADE ALTA] 2. Dualidade e Incompatibilidade no Contrato dos Conectores (`connectors/base.py`)
* **Fato Observado:** Em [`alquimista/connectors/base.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/base.py#L45-L80), o contrato `KnowledgeSourceConnector` força duas estratégias concorrentes no mesmo ABC:
  1. Métodos síncronos legados que retornam listas inteiras em memória: `list_documents(container_id)` e `get_document_children(document_id)`.
  2. Métodos lazy com cursor e paginação: `list_root_documents(...)` e `list_document_children(...)` que retornam `DiscoveryPage[DocumentMetadata]`.
* **Consequência:** O Notion e GitBook implementam `list_documents` retornando listas planas truncadas (ex: 100 itens fixos sem suporte a cursor no método síncrono), enquanto o Confluence implementa o motor completo de paginação lazy. O Core e a UI (`tree_mixin.py`) precisam fazer verificações dinâmicas para saber se o conector "é lazy ou síncrono", gerando tratamento condicional espalhado.

### [SEVERIDADE ALTA] 3. Acoplamento de Execução e Adaptação Legada dentro de `services.py`
* **Fato Observado:** Em [`alquimista/services.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/services.py#L268-L315), a função `_adapt_legacy_runtimes` possui verificações explícitas de strings de conectores:
  ```python
  if runtime.source.source_type != "confluence_rest":
      raise AlquimistaError("Um runtime sem conector só é compatível com Confluence legado.")
  ```
  Além disso, o `ExtractionService` possui dois métodos de execução: `_run_generic` (orientado aos novos conectores) e `_run_legacy` (orientado ao cliente antigo do Confluence).
* **Consequência:** O serviço de extração do Core não é inteiramente agnóstico; ele contém branches e tratamentos de exceção customizados para a estrutura legada do Confluence, dificultando a introdução de novos tipos de conectores sem tocar no `services.py`.

### [SEVERIDADE MÉDIA] 4. Discrepância na Geração de Conteúdo entre Conectores (HTML vs Markdown Direto)
* **Fato Observado:** 
  - O `ConfluenceRestConnector` ([`confluence.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/confluence.py#L512)) retorna HTML cru no campo `content` do `KnowledgeDocument` e delega a conversão HTML->Markdown para o `markdown.py`.
  - O `NotionConnector` ([`notion.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/notion.py#L214)) faz o parsing da árvore de blocos JSON da API do Notion e já constrói a string Markdown diretamente no método `get_document()`.
  - O `ZendeskGuideConnector` ([`zendesk.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/zendesk.py)) executa `BeautifulSoup` + `markdownify` internamente no próprio conector.
* **Consequência:** Não há padronização sobre quem é o responsável pela conversão para Markdown. Em alguns conectores o resultado final é gerado no próprio conector; em outros, passa pelo `MarkdownTransformer` do Core. Isso gera duplicidade de responsabilidades e impede a aplicação uniforme de opções de conversão (como nível de títulos e sanitização).

### [SEVERIDADE MÉDIA] 5. Concentração de Estado e Lógica na MainWindow (`main_window.py`)
* **Fato Observado:** O arquivo [`alquimista/ui/main_window.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/main_window.py) possui ~139 KB. Ele gerencia desde estilos QSS, manipulação da árvore Qt (`QTreeWidget`), controle de formulários dinâmicos de fonte, até a sincronização e preview em tempo real de Markdown (`_update_preview`, `_schedule_preview`).
* **Consequência:** Alto risco de efeitos colaterais ao alterar a UI. Testar regras de interface de forma automatizada sem instanciar a MainWindow completa torna-se uma tarefa complexa.

---

## 5. Hotspots Arquiteturais e Blast Radius

A tabela abaixo lista os **10 maiores hotspots** do projeto, avaliados pelo impacto de regressão (Blast Radius) caso sofram alterações:

| Hotspot | Arquivo / Módulo | Problema Identificado | Consequência de Alterações Incorretas | Blast Radius | Prioridade |
| :---: | :--- | :--- | :--- | :---: | :---: |
| **1** | [`alquimista/markdown.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/markdown.py) | Mistura de transformações genéricas com macros do Confluence. | Quebra de formatação, tabelas e links em extrações Confluence. | **CRÍTICO** | **P0** |
| **2** | [`alquimista/services.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/services.py) | Centraliza extração, hash incremental e compatibilidade legada. | Falha total na gravação de arquivos, perda de manifestos ou bypass de atualização incremental. | **CRÍTICO** | **P0** |
| **3** | [`alquimista/models.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/models.py) | Schema de dados central Pydantic (`SCHEMA_VERSION=4`). | Incompatibilidade de serialização com projetos salvas (`.alquimista`) e invalidação de cache. | **CRÍTICO** | **P1** |
| **4** | [`alquimista/ui/main_window.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/main_window.py) | Monolito de UI (~139KB) acumulando estado e orquestração. | Congelamento da interface, quebra na navegação entre abas ou perda de seleções da árvore. | **ALTO** | **P1** |
| **5** | [`alquimista/connectors/base.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/base.py) | ABC com métodos síncronos e lazy coexistindo sem separação clara. | Quebra da interface de todos os 5 conectores existentes. | **ALTO** | **P1** |
| **6** | [`alquimista/storage.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/storage.py) | Gerenciador de escritas atômicas `FileTransaction` e `ManifestStore`. | Arquivos corrompidos ou parciais durante abort/cancelamento de extração. | **ALTO** | **P1** |
| **7** | [`alquimista/ui/mixins/selection_mixin.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/mixins/selection_mixin.py) | Manipulação direta de nós da árvore Qt e sync com `SelectionStore`. | Seleção de páginas desincronizada da memória; extração de páginas não marcadas. | **MÉDIO** | **P2** |
| **8** | [`alquimista/connectors/confluence.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/confluence.py) | Conector REST principal do Confluence com fallback de CQL. | Falha de extração especificamente na plataforma Confluence. | **MÉDIO** | **P1** |
| **9** | [`alquimista/connectors/http.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/http.py) | Cliente HTTP compartilhado com retries, rate-limit e autorização. | Timeouts e falhas de conexão de rede em todos os conectores remotos. | **MÉDIO** | **P2** |
| **10** | [`alquimista/ui/mixins/tree_mixin.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/mixins/tree_mixin.py) | Lógica de carregamento sob demanda (lazy expansion) da árvore Qt. | Bloqueio ou expansão infinita de nós na UI ao clicar em contêineres. | **MÉDIO** | **P2** |

---

## 6. Shared Core vs. Código Específico de Conectores

Para garantir que o ALQuimista escale para 10 ou 20 conectores sem regressões, cada responsabilidade deve ser classificada de forma rígida entre o **Núcleo Compartilhado (Core)** e a **Implementação por Conector**:

| Componente / Funcionalidade | Classificação | Justificativa Arquitetural |
| :--- | :--- | :--- |
| **Persistência Atômica (`FileTransaction`)** | `CORE COMPARTILHADO` | Todos os conectores devem gravar no disco usando a mesma garantia transacional anti-corrupção. |
| **Indexação Incremental (SHA-256 / Manifest)** | `CORE COMPARTILHADO` | O algoritmo de hash de metadados, verificação de eTag e controle de atualizações pertence exclusivamente ao Core. |
| **Renderização de Frontmatter e Estrutura Markdown** | `CORE COMPARTILHADO` | A inclusão de títulos, IDs, YAML frontmatter e regras gerais de saída é única para todo o projeto. |
| **Consolidação em Arquivo Único / Pacote** | `CORE COMPARTILHADO` | A junção de arquivos Markdown e rebaixamento de títulos (`demote_headings`) opera sobre arquivos `.md` agnósticos. |
| **Controle de Cancelamento e Progresso (`runtime.py`)** | `CORE COMPARTILHADO` | Threads e trabalhadores cooperativos utilizam o mesmo `CancellationToken`. |
| **Gerenciamento de Sessão de Navegador (DPAPI)** | `INFRAESTRUTURA` | O `session_store.py` provê armazenamento seguro criptografado independente de qual conector o utiliza. |
| **Descoberta de Estrutura / Contêineres** | `CONNECTOR-SPECIFIC` | O Confluence lista Espaços; Notion lista Bancos de Dados/Páginas Raiz; SharePoint lista Sites/Bibliotecas. |
| **Parsing de Conteúdo (HTML -> Markdown)** | `CONNECTOR-SPECIFIC` | O HTML gerado pelo Confluence possui tags `<ac:macro>`; o Zendesk possui classes de Help Center; Notion usa blocos JSON. O parsing primário deve residir no conector ou em seu parser dedicado. |
| **Estratégia de Paginação / Cursores** | `CONNECTOR-SPECIFIC` | Confluence usa offset/cql; Notion usa `start_cursor`; GitBook usa `page`; SharePoint usa `@odata.nextLink`. |
| **Tratamento de Autenticação / Tokens** | `CONNECTOR-SPECIFIC` | O Confluence suporta Basic/Bearer/OAuth; Notion usa Integration Tokens com cabeçalho `Notion-Version`; SharePoint usa OAuth Graph. |
| **Captura de Anexos e Imagens** | `EXTENSÍVEL POR ESTRATÉGIA` | Baixar imagens via HTTP genérico é Core, mas resolver URLs privadas de anexos (ex: Confluence `/download/attachments/`) é específico do conector. |
| **Formulários da UI (`connector_forms.py`)** | `UI / PLUGIN` | Cada conector define seu schema de parâmetros exigidos no formulário (ex: `space_key`, `organization_id`, `subdomain`). |

---

## 7. Resposta à Pergunta Crítica: Devo Separar Leitores/Paginadores por Plataforma?

### Resposta Direta
**SIM, a descoberta de páginas, paginação e parsing de conteúdo devem ser 100% isolados por plataforma.** No entanto, a separação **não** deve ser feita duplicando código comum ou criando diretórios excessivos sem necessidade.

### Avaliação do Código Atual
Atualmente, o projeto possui um excelente ponto de partida: os arquivos dentro de [`alquimista/connectors/`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/) já isolam a chamada de API de cada plataforma. No entanto, existem dois problemas que quebram esse isolamento:

1. **Variação de Paginação:** O `ConfluenceRestConnector` possui um motor complexo de descoberta lazy com cursores ([`confluence.py:33-35`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/confluence.py#L33)), enquanto o `NotionConnector` faz requisição fixa de até 100 itens (`page_size: 100` em [`notion.py:95`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/notion.py#L95)).
2. **Variação de Parser:** O Confluence utiliza um parser HTML genérico no `markdown.py` que limpa tags da Atlassian. Se o Notion ou o SharePoint precisarem de sanitização especial, colocar isso no `markdown.py` contamina o Confluence.

### Padrão Arquitetural Recomendado: Strategy + Adapter Pattern

Em vez de criar uma hierarquia profunda de classes, o ALQuimista deve adotar o **Adapter Pattern** onde cada Conector encapsula 3 responsabilidades internas através de composição simples:

```text
                  ┌──────────────────────────────────────────┐
                  │       KnowledgeSourceConnector (ABC)     │
                  └────────────────────┬─────────────────────┘
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            ▼                          ▼                          ▼
 ┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
 │ ConfluenceConnector  │   │   NotionConnector    │   │ GenericWebConnector  │
 └──────────┬───────────┘   └──────────┬───────────┘   └──────────┬───────────┘
            │                          │                          │
  ┌─────────┴─────────┐      ┌─────────┴─────────┐      ┌─────────┴─────────┐
  │ - ConfluenceAPI   │      │ - NotionAPIClient │      │ - WebCrawler      │
  │ - ConfluencePage  │      │ - NotionBlock     │      │ - Sitemaps / DOM  │
  │   Paginator       │      │   Paginator       │      │ - Trafilatura /   │
  │ - ConfluenceHTML  │      │ - NotionBlockTo   │      │   Readability     │
  │   Parser          │      │   Markdown        │      │   HTML Parser     │
  └───────────────────┘      └───────────────────┘      └───────────────────┘
            │                          │                          │
            └──────────────────────────┼──────────────────────────┘
                                       ▼ (Retornam todos o mesmo objeto canônico)
                            ┌─────────────────────┐
                            │  KnowledgeDocument  │ (Modelo Intermediário)
                            └──────────┬──────────┘
                                       ▼
                            ┌─────────────────────┐
                            │    Shared Core      │ (Renderer, FileTransaction, ManifestStore)
                            └─────────────────────┘
```

---

## 8. Arquitetura Baseada em Contratos e Modelo Intermediário Comum

### Modelo Intermediário Canônico
O projeto **já possui** as fundações do modelo intermediário em [`alquimista/models.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/models.py):
- `KnowledgeContainer`: Representa a unidade organizacional (Espaço, Banco Notion, Seção GitBook, Categoria Zendesk).
- `KnowledgeDocumentMetadata`: Dados de cabeçalho e hierarquia sem o corpo do documento (ID, Título, Ancestrais, Parent ID, eTag, updated_at).
- `KnowledgeDocument`: O documento completo carregado, contendo o conteúdo convertido em Markdown agnóstico, metadados e lista de anexos.

### Evolução Recomendada para o Modelo Intermediário
Para eliminar lógicas condicionais no Core do tipo `if connector == "confluence":`, a entidade `KnowledgeDocument` deve ser a única fronteira de entrega do conector:

```python
# Exemplo de Contrato do Modelo Intermediário (alquimista/models.py)
class KnowledgeDocument(Model):
    id: str
    container_id: str
    title: str
    content: str  # Markdown já normalizado pelo conector/parser da plataforma
    parent_id: str | None = None
    original_url: str = ""
    updated_at: datetime | None = None
    created_at: datetime | None = None
    author: str = ""
    path: list[str] = Field(default_factory=list)  # Hierarquia de ancestrais ["Espaço", "Pai", "Título"]
    attachments: list[KnowledgeAttachment] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)  # Propriedades puras sem impacto no Core
```

### Eliminando Lógicas Condicionais do Core
Ao garantir que `KnowledgeDocument.content` já chegue como **Markdown válido e sanitizado** de cada conector, o `ExtractionService` no Core elimina a necessidade de saber qual plataforma gerou o documento:

```python
# NOVO FLUXO DO CORE (alquimista/services.py)
# Zero ifs de plataforma!
document = connector.get_document(document_id, container_id=container_id)
# O Core apenas aplica opções globais do usuário (ex: incluir YAML frontmatter, adicionar cabeçalho)
rendered_markdown = self.renderer.render(
    metadata=document.to_metadata_dict(),
    content=document.content,
    content_hash=content_hash,
    collected_at=collected_at,
    status=status.value
)
transaction.stage_text(absolute_path, rendered_markdown)
```

---

## 9. Expansão para Sites Genéricos (`GenericWebConnector`)

### Requisito Futuro
Permitir que o usuário forneça qualquer URL (ex: `https://exemplo.com/documentacao`) para descobrir páginas relacionadas, extrair o conteúdo principal limpo (sem menus/rodapés), transformar em Markdown e consolidar.

### Desenho da Arquitetura para Web Genérica
A funcionalidade deve ser introduzida **exclusivamente como um novo conector** herdando do contrato `KnowledgeSourceConnector`, sem alterar nenhuma linha dos conectores existentes:

```text
alquimista/connectors/web/
├── __init__.py
├── connector.py          # GenericWebConnector (Implementa KnowledgeSourceConnector)
├── crawler.py            # Sitemaps / HTML Link Crawler (Respeita robots.txt e rate limits)
├── extractor.py          # Extração de conteúdo via Trafilatura / BeautifulSoup + Readability
└── html_converter.py     # Conversão HTML agnóstica -> Markdown
```

### Componentes Internos do `GenericWebConnector`:
1. **Discovery (Crawler):**
   - Tenta primeiramente ler `sitemap.xml` da URL informada.
   - Fallback: Faz parsing de links internos `href` no mesmo domínio/prefixo da URL inicial.
2. **Extraction & Main Content Cleansing:**
   - Utiliza algoritmos de densidade de texto (ex: `trafilatura` ou `readability-lxml`) para remover menus, footers, sidebars e anúncios automaticamente.
3. **Conversão de Imagens:**
   - Converte URLs de imagens relativas em URLs absolutas e agenda download atômico se a opção `download_images` estiver ativa.

---

## 10. Proteção Contra Regressões & "Golden Samples"

### A Regra de Ouro contra Regressões
> **"Nenhuma refatoração no Core ou no Confluence será aceita sem que a suíte de Golden Samples do Confluence passe com 100% de sucesso."**

### Estrutura Proposta de Fixtures e Snapshots (Golden Samples)
Para impedir regressões silenciosas ao adicionar Notion, GitBook ou Generic Web, o diretório de testes (`tests/`) deve ser organizado por conector com arquivos de entrada e saída esperados:

```text
tests/
├── fixtures/
│   ├── confluence/
│   │   ├── raw_page_101.json         # Payload cru retornado pela API do Confluence
│   │   ├── raw_page_with_macros.html # HTML com macros ac:structured-macro
│   │   └── expected_page_101.md      # Markdown final exatamente esperado
│   ├── notion/
│   │   ├── raw_blocks.json           # Payload de blocos Notion
│   │   └── expected_notion.md        # Markdown esperado do Notion
│   └── gitbook/
│       ├── raw_gitbook_page.json
│       └── expected_gitbook.md
└── test_golden_samples.py            # Runner de testes de regressão por comparação exata
```

### Algoritmo do Teste Golden Sample com Normalização
Para evitar falsos negativos causados por atributos voláteis (ex: timestamps dinâmicos, hashes SHA-256 ou ordem de chaves), o teste de regressão aplica um normalizador sanitizador antes da comparação:

```python
# Exemplo de Teste de Regressão (tests/test_golden_samples.py)
def test_confluence_macro_conversion_golden_sample():
    raw_html = load_fixture("confluence/raw_page_with_macros.html")
    expected_md = load_fixture("confluence/expected_page_101.md")
    
    # Executa o parser do conector Confluence
    actual_md = ConfluenceHtmlParser.to_markdown(raw_html, options=default_options())
    
    # Normaliza datas e hashes voláteis antes da comparação
    normalized_actual = normalize_volatile_fields(actual_md)
    normalized_expected = normalize_volatile_fields(expected_md)
    
    assert normalized_actual == normalized_expected
```

---

## 11. Arquitetura da UI e Desacoplamento

### Problema na UI Atual
A `MainWindow` ([`alquimista/ui/main_window.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/main_window.py)) atua como a central de estado global. Ela executa criação de objetos de domínio, chama métodos de IO do projeto e sincroniza widgets Qt.

### Camada de Aplicação Proposta (Application Layer)
Para reduzir a responsabilidade da UI, deve-se reforçar os **Controladores de Aplicação** que já começaram a ser criados em [`alquimista/ui/controllers.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/controllers.py) e [`alquimista/ui/execution_controller.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/execution_controller.py):

```text
[ CAMADA DE UI (PySide6) ]
    MainWindow / Pages (sources_page, selection_page, review_page)
         │
         ▼ (Dispara intenções do usuário via DTOs/sinais)
[ CAMADA DE APLICAÇÃO (Application Layer) ]
    ├── SourceApplicationService      (CRUD de fontes e validação de conexões)
    ├── DiscoveryApplicationService   (Busca contêineres e popula a árvore em background)
    └── ExtractionApplicationService  (Monta runtimes, valida licenças/tokens, dispara workers)
         │
         ▼ (Executa lógica pura de domínio sem dependência do Qt)
[ DOMÍNIO E CONECTORES (Core) ]
    connectors/ | services.py | markdown.py | storage.py
```

---

## 12. Estrutura de Diretórios Recomendada

Sem realizar uma reescrita do zero, a estrutura de pastas deve evoluir gradualmente para a organização abaixo, movendo arquivos de forma incremental:

```text
alquimista/
├── core/                        # Núcleo 100% agnóstico (Sem dependência de plataformas ou UI)
│   ├── models.py                # Contratos Pydantic (KnowledgeDocument, ProjectConfig)
│   ├── services.py              # ExtractionService, ConsolidationService
│   ├── storage.py               # FileTransaction, ManifestStore, confined_path
│   ├── errors.py                # Hierarquia de exceções funcionais
│   ├── runtime.py               # CancellationToken, RateLimiter
│   ├── logging_utils.py         # Formatação JSON e redação de segredos
│   └── reports.py               # ExecutionReport, DocumentResult
│
├── markdown/                    # Motor de renderização e formatação Markdown
│   ├── renderer.py              # KnowledgeDocumentRenderer (Frontmatter, markers)
│   ├── normalizer.py            # normalize_markdown, demote_headings
│   └── presets.py               # Presets de estilo de saída
│
├── connectors/                  # Conectores por plataforma (Adapters)
│   ├── base.py                  # KnowledgeSourceConnector (ABC base)
│   ├── registry.py              # Catálogo de conectores
│   ├── http.py                  # ApiHttpClient (HTTP comum com retries)
│   │
│   ├── confluence/              # Isolamento total do Confluence
│   │   ├── connector.py         # ConfluenceRestConnector
│   │   ├── client.py            # ConfluenceClient (antigo client.py)
│   │   ├── parser.py            # ConfluenceHtmlParser (macros ac: e anexos)
│   │   └── url_parser.py        # confluence_url.py
│   │
│   ├── notion/                  # Isolamento do Notion
│   │   ├── connector.py
│   │   └── block_parser.py      # Converte blocos Notion JSON -> Markdown
│   │
│   ├── gitbook/                 # Isolamento do GitBook
│   │   └── connector.py
│   │
│   ├── sharepoint/              # Isolamento do SharePoint
│   │   └── connector.py
│   │
│   ├── zendesk/                 # Isolamento do Zendesk
│   │   └── connector.py
│   │
│   └── web/                     # [FUTURO] Conector Web Genérico
│       ├── connector.py
│       ├── crawler.py
│       └── extractor.py
│
├── application/                 # Camada de Orquestração (Usada pela UI)
│   ├── source_service.py        # Orquestra fontes e detecção de URL
│   ├── discovery_service.py     # Orquestra busca de árvores e lazy loading
│   └── extraction_service.py    # Bridge entre UI workers e ExtractionService
│
└── ui/                          # Camada Visual (PySide6)
    ├── main_window.py
    ├── components.py
    ├── pages/
    └── mixins/
```

---

## 13. Plano Incremental de Refatoração (Fases 0 a 5)

### Fase 0 — Baseline de Regressão e Golden Samples (Risco ZERO)
* **Objetivo:** Garantir a proteção absoluta do conector Confluence existente antes de qualquer alteração de código.
* **Arquivos Afetados:** [`tests/fixtures/confluence/`](file:///c:/Dev/Alquimista%20studio%203.0/tests/), `tests/test_confluence_golden.py` [NOVOS].
* **Mudança Proposta:** Criar fixtures gravadas contendo payloads reais de páginas do Confluence (com tabelas, macros, anexos e links) e assinalar a saída exata em Markdown esperada.
* **Risco:** Mínimo / Zero.
* **Benefício:** Garantia matemática de que refatorações futuras não quebrarão o Confluence.
* **Validação:** Executar `pytest tests/test_confluence_golden.py` e obter 100% de aprovação.

### Fase 1 — Isolamento do Parser Confluence fora do Core
* **Objetivo:** Mover métodos específicos de Confluence (`_replace_macros`, `_attachment_url`) do `markdown.py` para dentro da pasta do conector Confluence.
* **Arquivos Afetados:** [`alquimista/markdown.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/markdown.py), [`alquimista/connectors/confluence.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/confluence.py).
* **Mudança Proposta:** Extrair a classe `ConfluenceHtmlParser` para o conector do Confluence. O `MarkdownTransformer` no Core passa a receber HTML limpo/Markdown padrão.
* **Risco:** Baixo (protegido pelos testes da Fase 0).
* **Benefício:** Elimina a contaminação do Core por regras da Atlassian.
* **Validação:** Re-executar os testes da Fase 0 e a suíte completa `pytest tests/`.

### Fase 2 — Padronização do Contrato `KnowledgeDocument`
* **Objetivo:** Fazer com que **todos** os conectores entreguem o campo `KnowledgeDocument.content` já convertido em Markdown limpo.
* **Arquivos Afetados:** [`alquimista/connectors/notion.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/notion.py), [`alquimista/connectors/gitbook.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/gitbook.py), [`alquimista/services.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/services.py).
* **Mudança Proposta:** Remover chamadas de conversão HTML condicional dentro de `services.py:_run_generic`. O `ExtractionService` do Core apenas chama `renderer.render(document)`.
* **Risco:** Baixo.
* **Benefício:** Core do `ExtractionService` 100% agnóstico e simplificado.
* **Validação:** Executar `pytest tests/test_services.py` e `pytest tests/test_connectors.py`.

### Fase 3 — Saneamento do ABC `KnowledgeSourceConnector`
* **Objetivo:** Esclarecer o contrato de listagem lazy vs síncrono.
* **Arquivos Afetados:** [`alquimista/connectors/base.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/base.py), [`alquimista/ui/mixins/tree_mixin.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/mixins/tree_mixin.py).
* **Mudança Proposta:** Fornecer implementações padrão no `base.py` para que conectores simples sem lazy loading funcionem sem lançar exceções não tratadas ou exigir `if capabilities.supports_lazy` espalhados.
* **Risco:** Médio.
* **Benefício:** Facilidade total para criar novos conectores com poucas linhas de código.
* **Validação:** Testar a navegação na árvore de seleção para todas as fontes cadastradas.

### Fase 4 — Testes de Contrato para Novos Conectores (Notion / GitBook / SharePoint)
* **Objetivo:** Adicionar testes de regressão específicos para cada um dos conectores secundários.
* **Arquivos Afetados:** `tests/test_notion_contract.py`, `tests/test_sharepoint_contract.py` [NOVOS].
* **Mudança Proposta:** Implementar fixtures com payloads falsos (mocks de resposta HTTP) para validar se o Notion e SharePoint retornam `KnowledgeDocument` válidos.
* **Risco:** Baixo.
* **Benefício:** Segurança total ao mexer nas integrações do Notion ou SharePoint.
* **Validação:** Rodar `pytest`.

### Fase 5 — Adição do Conector Web Genérico (`GenericWebConnector`)
* **Objetivo:** Adicionar capacidade de extração de sites e documentações genéricas por URL.
* **Arquivos Afetados:** `alquimista/connectors/web/` [NOVO PACOTE], [`alquimista/connectors/registry.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/registry.py), [`alquimista/source_detection.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/source_detection.py).
* **Mudança Proposta:** Criar o conector de Web que utiliza crawling de sitemap + extração por densidade de texto (Trafilatura/Readability).
* **Risco:** Baixo (código 100% isolado em um novo módulo).
* **Benefício:** Expansão do produto para qualquer site da Web sem afetar Confluence, Notion ou GitBook.
* **Validação:** Testar a extração de um site estático de documentação público.

---

## 14. Tabela de Prioridades (Benefício × Risco × Esforço)

| Prioridade | Mudança Arquitetural Proposta | Benefício | Risco | Esforço | Fase |
| :---: | :--- | :---: | :---: | :---: | :---: |
| **P0** | Criar Suíte de **Golden Samples** do Confluence | **ALTO** | **BAIXO** | **BAIXO** | Fase 0 |
| **P0** | Mover macros e anexos Confluence do `markdown.py` para o conector Confluence | **ALTO** | **BAIXO** | **MÉDIO** | Fase 1 |
| **P1** | Padronizar a entrega de Markdown no `KnowledgeDocument` | **ALTO** | **BAIXO** | **MÉDIO** | Fase 2 |
| **P1** | Eliminar verificações de string de conector no `services.py` | **ALTO** | **BAIXO** | **BAIXO** | Fase 2 |
| **P2** | Limpar e padronizar o ABC `KnowledgeSourceConnector` | **MÉDIO** | **MÉDIO** | **MÉDIO** | Fase 3 |
| **P2** | Criar fixtures Golden Sample para Notion e GitBook | **MÉDIO** | **BAIXO** | **BAIXO** | Fase 4 |
| **P3** | Criar o módulo `GenericWebConnector` para sites arbitrários | **ALTO** | **BAIXO** | **ALTO** | Fase 5 |
| **P3** | Desmembrar a `MainWindow` extraindo Application Controllers | **MÉDIO** | **ALTO** | **ALTO** | Futura |

---

## 15. O que NÃO Modificar Agora

Para respeitar a premissa de **baixo risco e estabilidade do que já funciona**:

1. **NÃO alterar o `storage.py` (`FileTransaction` / `confined_path`):** O mecanismo de escrita atômica, manipulação de arquivos temporários e proteção contra path traversal funciona perfeitamente.
2. **NÃO alterar o schema Pydantic `models.py` (`SCHEMA_VERSION=4`):** Alterar nomes de campos estruturais agora quebraria a leitura de projetos salvos (`.alquimista`) e invalidaria manifestos de atualização incremental existentes.
3. **NÃO reescrever o cliente de baixo nível `client.py`:** Embora seja código legado exclusivo do Confluence, ele lida corretamente com nuances de APIs antigas da Atlassian, paginação CQL e retries. Deve ser mantido dentro da pasta do conector Confluence.
4. **NÃO substituir o framework visual PySide6 nem refazer componentes de UI:** A interface gráfica atende perfeitamente aos requisitos. A refatoração da UI deve se limitar a extrair controladores de aplicação, sem mudar a camada visual.

---

## 16. Teste Mental de Extensibilidade

Para comprovar a solidez da arquitetura recomendada, submetemos a proposta aos 4 cenários de expansão:

### Cenário A: Adicionar a integração com "Google Drive"
- **Impacto na Arquitetura Proposta:** **ZERO impacto no Core ou nos conectores existentes.**
- **Passos Necessários:**
  1. Criar [`alquimista/connectors/google_drive.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/) herdando de `KnowledgeSourceConnector`.
  2. Implementar autenticação OAuth2 Google no conector.
  3. Mapear Pastas -> `KnowledgeContainer` e Documentos Google Docs -> `KnowledgeDocument`.
  4. Registrar a classe em `registry.py` e adicionar os campos do formulário em `connector_forms.py`.
- **Resultado:** Nenhuma linha do Confluence, Notion ou `services.py` é tocada.

### Cenário B: Adicionar suporte a "Generic Website" (URLs arbitrárias)
- **Impacto na Arquitetura Proposta:** **ZERO impacto nos conectores existentes.**
- **Passos Necessários:**
  1. Criar o pacote `alquimista/connectors/web/`.
  2. Implementar o crawler de sitemap/links e o extrator de HTML (Trafilatura).
  3. O extrator converte o HTML limpo em Markdown e retorna no `KnowledgeDocument`.
- **Resultado:** O Core (`services.py` e `storage.py`) processa o site exatamente como processa o Confluence.

### Cenário C: Notion altera completamente sua API de paginação (v2)
- **Impacto na Arquitetura Proposta:** **ISOLADO exclusivamente em `connectors/notion.py`.**
- **Passos Necessários:**
  1. Alterar o método `list_documents()` ou implementar os cursores em `connectors/notion.py`.
- **Resultado:** O Confluence e o GitBook continuam funcionando sem ciência da mudança no Notion. Os testes Golden Sample do Confluence garantem que nada foi afetado.

### Cenário D: Modificação nas opções de geração de Markdown (ex: novo marcador HTML)
- **Impacto na Arquitetura Proposta:** **Centralizado no `KnowledgeDocumentRenderer` em `markdown.py`.**
- **Passos Necessários:**
  1. Adicionar o novo campo de opção em `MarkdownOptions`.
  2. Atualizar o `KnowledgeDocumentRenderer.render()`.
- **Resultado:** Todos os conectores passam a aceitar a nova opção de saída instantaneamente e de forma uniforme.

---

## 17. Avaliação Arquitetural Quantitativa

Classificação da qualidade do código no **Estado Atual** comparada com o **Estado Projetado** após a implementação da arquitetura recomendada:

| Área de Avaliação | Nota Atual (0–10) | Justificativa do Estado Atual | Nota Projetada | Justificativa do Estado Projetado |
| :--- | :---: | :--- | :---: | :--- |
| **Modularidade** | **6.5** | Conectores já estão em arquivos separados, mas a UI e o módulo de Markdown compartilham lógicas. | **9.0** | Limites rígidos entre Core, Connectors, Application e UI. |
| **Separação de Responsabilidades** | **5.5** | `markdown.py` contém regexes de macros Confluence; `services.py` possui fallbacks para Confluence. | **9.0** | Cada conector é 100% responsável pelo seu parsing; Core é puramente agnóstico. |
| **Extensibilidade** | **7.0** | O registro de conectores via `registry.py` é bom, mas criar conectores com parsing complexo exige alterar o Core. | **9.5** | Novos conectores entram como pacotes auto-contidos sem tocar no Core. |
| **Testabilidade** | **5.0** | Existem testes unitários, mas faltam fixtures de páginas reais (Golden Samples) por plataforma. | **9.0** | Testes de regressão por comparação direta com Golden Samples (fixtures JSON/HTML). |
| **Proteção contra Regressões** | **4.5** | Alterar o `markdown.py` para atender a outro conector traz alto risco de quebrar o Confluence. | **9.5** | Cobertura de testes de Golden Sample impede regressões em conectores existentes. |
| **Acoplamento** | **5.5** | Alto acoplamento da MainWindow com estado de seleção e dependência de regras de Confluence no Core. | **8.5** | Comunicação via DTOs/Contratos e isolamento total entre conectores. |
| **Coesão** | **6.5** | Módulos como `storage.py` e `models.py` são altamente coesos; `main_window.py` tem baixa coesão. | **8.5** | Redução do tamanho da MainWindow e concentração de regras de negócio em serviços. |
| **Observabilidade** | **7.0** | Já existe log estruturado JSON com redação de segredos (`logging_utils.py`), mas falta prefixo por conector. | **8.5** | Logs categorizados com formato `[CONECTOR][ETAPA]` para diagnóstico rápido. |
| **Manutenibilidade** | **6.0** | Manter o Confluence é fácil, mas debugar problemas em conectores secundários é confuso. | **9.0** | Código predizível onde cada plataforma reside na sua própria pasta isolada. |
| **Preparação para novos conectores** | **6.5** | O sistema aceita novos conectores no registro, mas o parser de Markdown atual é inflexível. | **9.5** | Suporte nativo a Web Crawling e conectores de terceiros isolados. |

---

## 18. Respostas Diretas às 20 Questões Críticas da Análise

1. **A arquitetura atual escala bem para 5, 10 ou 20 conectores?**  
   *Não na estrutura atual.* À medida que o número de conectores cresce, a centralização do parsing em `markdown.py` e as verificações condicionais em `services.py` tornarão as regressões frequentes. Com a separação proposta, escalará perfeitamente.

2. **Onde estão hoje os maiores acoplamentos?**  
   Em [`alquimista/markdown.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/markdown.py) (lógica de macros/anexos de Confluence dentro do transformer comum) e em [`alquimista/ui/main_window.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/main_window.py) (monolito visual e de orquestração).

3. **Quais partes deveriam ser compartilhadas?**  
   Persistência atômica (`storage.py`), verificação de SHA-256 e eTags para atualização incremental, cálculo de frontmatter e demarcadores de documento, consolidação de arquivos, infraestrutura HTTP base (`http.py`) e gerenciamento de cancelamento/progresso (`runtime.py`).

4. **Quais partes deveriam ser isoladas por conector?**  
   Parsing de HTML/blocos específicos da plataforma, rotas de API, estratégias de paginação/cursores, autenticação e mapeamento de metadados nativos para o modelo `KnowledgeDocument`.

5. **Paginação deve ser específica por conector?**  
   *Sim.* Cada API remota possui mecanismos distintos de paginação (offset, CQL, cursor, token, oData). Tentar unificar o motor de paginação no Core gera complexidade desnecessária.

6. **Descoberta de páginas deve ser específica por conector?**  
   *Sim.* A árvore de contêineres e a resolução de documentos filhos dependem das capacidades de cada API nativa.

7. **Parsing deve ser específico por conector?**  
   *Sim.* O Confluence produz HTML com tags proprietárias da Atlassian (`ac:macro`); Notion produz blocos em formato JSON; Zendesk produz HTML limpo com CSS do Help Center. Cada conector deve entregar Markdown pronto.

8. **Markdown deve permanecer compartilhado?**  
   *A estrutura final do documento Markdown (YAML frontmatter, título, demarcadores de início/fim, rebaixamento de títulos) SIM.* O parsing primário de HTML->Markdown deve ser específico.

9. **Consolidação deve permanecer compartilhada?**  
   *Sim 100%.* A consolidação opera exclusivamente sobre arquivos `.md` agnósticos ou objetos `KnowledgeDocument` padronizados, sem saber de qual plataforma vieram.

10. **Preciso de um modelo intermediário de documentos?**  
    *Sim.* O projeto já possui a classe `KnowledgeDocument` em `models.py`, que deve ser reforçada como o único contrato de entrega de todos os conectores.

11. **Preciso de uma interface/base para conectores?**  
    *Sim.* O ABC `KnowledgeSourceConnector` em `connectors/base.py` deve continuar existindo, mas limpo de duplicidades entre métodos síncronos e lazy.

12. **Como impedir regressões entre conectores?**  
    Através da suíte de **Golden Samples** (fixtures estáticas de payload -> Markdown esperado) e garantindo que o Core não tenha branches condicionais do tipo `if connector == "x":`.

13. **Como testar cada integração isoladamente?**  
    Criando testes unitários e de contrato em `tests/` que injetam um `ApiHttpClient` simulado (mock) retornando o payload de fixture do conector.

14. **Como permitir novos conectores sem alterar o Core?**  
    Garantindo que o conector herde de `KnowledgeSourceConnector`, registre-se em `registry.py` e devolva um `KnowledgeDocument` com Markdown válido no método `get_document()`.

15. **Como preparar o sistema para URLs/sites genéricos?**  
    Criando o conector `GenericWebConnector` em `connectors/web/` equipado com um crawler (sitemap/links) e um extrator de texto principal (Trafilatura/Readability).

16. **Como reduzir responsabilidades da UI?**  
    Delegando as operações de busca de árvores, CRUD de fontes e montagem de runtimes para controladores de aplicação (Application Services) em `ui/controllers.py`.

17. **Qual refatoração oferece maior benefício com menor risco?**  
    A **Fase 0 + Fase 1**: Criar os testes Golden Sample do Confluence e extrair as funções de conversão de macros Confluence do `markdown.py` para dentro de `connectors/confluence.py`.

18. **O que eu deveria alterar agora?**  
    Criar o arquivo de teste `tests/test_confluence_golden.py` com as fixtures de regressão e sanitizar o `markdown.py`.

19. **O que deveria deixar para depois?**  
    A criação do `GenericWebConnector` e a refatoração profunda dos mixins de UI da `MainWindow`.

20. **O que definitivamente não deveria alterar neste momento?**  
    O `storage.py` (`FileTransaction`), o arquivo de esquemas `models.py` e o cliente legado do Confluence `client.py`.

---

## 19. Top 10 Próximas Ações (Em Ordem Estrita de Execução)

1. **[Ação 1]** Criar o diretório `tests/fixtures/confluence/` e salvar payloads reais de teste de páginas HTML/JSON do Confluence.
2. **[Ação 2]** Criar o teste de regressão `tests/test_confluence_golden.py` validando que a saída em Markdown do Confluence bate 100% com as fixtures esperadas.
3. **[Ação 3]** Criar o módulo `alquimista/connectors/confluence_parser.py` (ou embutir em `confluence.py`) e mover as funções `_replace_macros`, `_replace_links` e `_attachment_url` do `markdown.py` para ele.
4. **[Ação 4]** Executar a suíte de testes `pytest` para confirmar zero quebras no Confluence após a movimentação.
5. **[Ação 5]** Ajustar os conectores Notion, GitBook e Zendesk para garantir que o método `get_document()` sempre retorne o contéudo no campo `KnowledgeDocument.content` já devidamente convertido em Markdown.
6. **[Ação 6]** Simplificar o `ExtractionService._run_generic()` em [`alquimista/services.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/services.py) para remover branches ou conversões condicionais de plataforma.
7. **[Ação 7]** Adicionar fixtures e testes Golden Sample para o conector do Notion (`tests/fixtures/notion/`).
8. **[Ação 8]** Organizar o ABC `KnowledgeSourceConnector` em [`alquimista/connectors/base.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/base.py) para padronizar os métodos de descoberta lazy vs síncrono.
9. **[Ação 9]** Desenvolver o protótipo do conector de Web Genérico em `alquimista/connectors/web/` para suporte a URLs arbitrárias.
10. **[Ação 10]** Iniciar a extração gradual da lógica de orquestração de UI da `MainWindow` para os controladores de aplicação.

---

## Resposta Final Executiva (Frase Única)

> **Se eu fosse o responsável técnico pelo Projeto ALQuimista hoje, a primeira mudança arquitetural que faria antes de desenvolver qualquer nova integração seria criar uma suíte de testes de regressão "Golden Sample" para o Confluence e mover todo o parsing de HTML/macros de Atlassian do `markdown.py` para dentro da pasta do conector Confluence, garantindo que o Core permaneça 100% agnóstico e protegido contra quebras.**
