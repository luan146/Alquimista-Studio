## Análise Arquitetural, Modularização, Estabilidade e Expansão — Projeto Alquimista Studio 3.0

> **Nota metodológica:** Esta análise foi produzida a partir da documentação de código detalhada fornecida (`MAPA.md`, `README.md`, `AGENTS.md`). O `MAPA.md` (67 KB) contém assinaturas de funções, dependências, tamanhos de arquivo, problemas documentados e fluxos. Tratamos essa documentação como fonte primária, com o devido cuidado de separar **fatos observados na documentação** de **hipóteses** e **recomendações**.

---

## 1. Resumo executivo

**Estado atual:** O Projeto Alquimista possui uma arquitetura funcional que escala bem para o Confluence (conector maduro), mas apresenta acoplamentos significativos que tornam arriscado o desenvolvimento dos demais conectores (Notion, SharePoint, GitBook, Zendesk). O sistema já possui um modelo intermediário de dados (`models.py`), um contrato ABC para conectores (`connectors/base.py`) e um subsistema de browser bem delimitado. No entanto, componentes centrais como `services.py`, `markdown.py` e `ui/main_window.py` carregam lógica específica do Confluence ou responsabilidades excessivas.

**Principal risco:** `services.py` (52,7 KB, 1.145 linhas) e `markdown.py` (22,3 KB) contêm modo legado e lógica específica de Confluence. Ao corrigir Notion ou SharePoint, uma alteração nesses arquivos compartilhados pode quebrar o Confluence, que é hoje a única integração estável.

**Principal oportunidade:** O projeto já tem as peças certas (modelo intermediário, ABC de conectores, transações atômicas, browser isolado). O gap não é arquitetural radical — é de **higiene de fronteiras**: mover lógica específica de Confluence para dentro do conector, estabilizar contratos e criar testes de regressão por conector (golden samples).

**Recomendação arquitetural central:** Adotar uma arquitetura de **"Conectores como Plugins sobre um Core Estável"**, onde o Core (`models`, `storage`, `pipeline` genérico) nunca conhece plataformas, e cada conector empacota sua própria estratégia de paginação, descoberta, parsing e normalização. O Core deve operar exclusivamente sobre o modelo intermediário (`KnowledgeDocument`, `KnowledgeContainer`).

---

## 2. Como o projeto funciona atualmente

### 2.1. Pipeline real (reconstruído do MAPA.md)

```
┌─────────────────┐
│   Dashboard     │  ui/pages/dashboard_page.py
│   (PySide6)     │
└────────┬────────┘
         ▼
┌─────────────────┐
│  Sources / UI   │  ui/mixins/source_mixin.py (~30KB)
│  CRUD de fontes │  source_detection.py, connector_forms.py
└────────┬────────┘
         ▼
┌─────────────────┐
│   Connection    │  ui/mixins/connection_mixin.py (~18KB)
│   Auth modes    │  auth.py, session_store.py (DPAPI)
│   (public/basic/│  controllers.py:RuntimeSecrets
│    bearer/browser)│
└────────┬────────┘
         ▼
┌─────────────────┐
│    Selection    │  ui/mixins/selection_mixin.py (~36KB)
│   Árvore lazy   │  tree_mixin.py, tree_models.py
│   /síncrona     │  selection.py:SelectionStore
└────────┬────────┘
         ▼
┌─────────────────┐
│  Review/Extract │  execution_controller.py
│   Prévia +      │  operation_controller.py (QThreadPool)
│   disparo       │  process_workers.py, workers.py
└────────┬────────┘
         ▼
┌─────────────────┐
│    Markdown     │  ui/pages/markdown_page.py
│   Opções de     │  markdown.py:MarkdownTransformer
│   conversão     │  models.py:MarkdownOptions
└────────┬────────┘
         ▼
┌─────────────────┐
│  Consolidation  │  ui/pages/consolidation_page.py
│  (arquivo único/│  services.py:ConsolidationService
│   pacote/índice)│  storage.py:FileTransaction
└────────┬────────┘
         ▼
┌─────────────────┐
│    Results      │  ui/pages/results_page.py
│   Relatórios    │  reports.py:ExecutionReport
└─────────────────┘
```

### 2.2. Pipeline de extração (núcleo)

```
SourceConfig
    ↓
ConnectorRegistry → conector específico (confluence.py, notion.py...)
    ↓
list_containers() → list_documents() / list_document_children() [lazy]
    ↓
get_document() → KnowledgeDocument (HTML cru ou similar)
    ↓
KnowledgeDocumentRenderer (markdown.py) → Markdown com opções
    ↓
ExtractionService._run_generic() ou _run_legacy()
    ↓
FileTransaction (atomic_write_text/json) → disco
    ↓
ManifestStore + ManifestIndex (SQLite) → manifesto_alquimista.json
```

**Fato observado:** O `ExtractionService` possui dois modos: `_run_generic` e `_run_legacy`. O legado é específico do Confluence antigo (`client.py`). Isso indica que o projeto está em transição arquitetural incompleta.

---

## 3. Mapa de responsabilidades

| Módulo | Responsabilidade | Tamanho | Risco |
|---|---|---|---|
| `ui/main_window.py` | Orquestração da UI, 132 métodos, herda 4 mixins | 126,6 KB | **CRÍTICO** |
| `services.py` | Motor de extração e consolidação; contém modos legacy | 52,7 KB | **CRÍTICO** |
| `ui/mixins/selection_mixin.py` | Árvore de seleção, lazy loading, marcação | ~36 KB | **Alto** |
| `ui/mixins/source_mixin.py` | CRUD de fontes, detecção de URL | ~30 KB | **Médio** |
| `connectors/confluence.py` | Conector completo (lazy, search, visibilidade) | 25,3 KB | **Médio** |
| `markdown.py` | HTML→Markdown; contém lógica Confluence-specific | 22,3 KB | **Alto** |
| `client.py` | Cliente REST legado Confluence | 21,1 KB | **Médio** |
| `ui/mixins/connection_mixin.py` | Autenticação por modo | ~18 KB | **Médio** |
| `models.py` | Contrato de dados central (pydantic) | 19,4 KB | **Médio** |
| `storage.py` | Persistência atômica, FileTransaction | 12,9 KB | **Baixo** |
| `browser/*` | Discovery com cache Playwright | ~4 arquivos | **Baixo** |
| `errors.py` | Hierarquia de erros | Pequeno | **Baixo** |

---

## 4. Problemas encontrados (ordenados por severidade)

### P0 — Crítico

1. **`services.py` com 30 menções a Confluence e modo legado:** O motor de domínio conhece detalhes do Confluence (`_run_legacy`, `_run_generic`). Isso viola o princípio de que o Core deve ser agnóstico a conectores. **Consequência:** ao modificar extração para Notion, o risco de quebrar Confluence é alto.

2. **`markdown.py` contém lógica Confluence-specific:** Métodos como `_replace_macros`, `_replace_links`, `_attachment_url` mencionam explicitamente Confluence. **Consequência:** se Notion ou SharePoint usarem formatos diferentes de anexo/link, uma mudança para atendê-los pode quebrar a conversão do Confluence.

3. **`main_window.py` com 2.733 linhas e 132 métodos:** Classe orquestradora gigante que herda de 4 mixins (~87 KB de lógica). **Consequência:** qualquer alteração na UI pode afetar múltiplas telas simultaneamente; testabilidade é baixa.

4. **Duplicações de funções (12 no total):** `selection_mixin.py` tem 7 funções duplicadas (primeira ocorrência morta), `connection_mixin.py` tem 3, `execution_controller.py` e `auth.py` têm 1 cada. **Consequência:** código morto aumenta a superfície de confusão; editores podem modificar a função errada.

### P1 — Alto

5. **`client.py` legado coexistindo com `connectors/confluence.py`:** O cliente REST legado (21,1 KB) ainda existe e é usado pelo modo legado. **Consequência:** duplicação de responsabilidade de HTTP (também existe `connectors/http.py:ApiHttpClient`).

6. **`ui/connector_forms.py` e `source_detection.py` conhecem conectores específicos:** `form_spec(source_type)` retorna spec por `source_type` (confluence_rest, gitbook_api, etc.). `detect_source_url` reconhece plataformas por URL. **Consequência:** adicionar um novo conector exige editar múltiplos arquivos da UI/Core.

7. **Hierarquia de erros misturada:** Existem erros genéricos (`ApiConnectionError`) e erros legado específicos (`ConfluenceConnectionError`, `RateLimitError`). **Consequência:** tratamento de erro inconsistente entre conectores.

8. **Conectores "Available" e "In development" sem lazy loading:** GitBook, Zendesk, Notion, SharePoint não suportam lazy loading ou search, segundo o MAPA. **Consequência:** a árvore de seleção pode ter comportamentos diferentes entre conectores, aumentando a complexidade da UI (`tree_mixin.py:_lazy_method` decide síncrono vs lazy).

### P2 — Médio

9. **`ui/mixins/selection_mixin.py` (~36 KB) maior que muitos conectores:** A lógica de árvore de seleção é excessivamente complexa para um mixin de UI.

10. **Ausência de testes organizados por conector com golden samples:** Os 19 arquivos de teste existem (`test_markdown`, `test_services`, etc.), mas não há estrutura `tests/confluence/fixtures/expected/`.

---

## 5. Hotspots e blast radius

| Módulo | Blast radius | Justificativa |
|---|---|---|
| `services.py` | **CRÍTICO** | Alterar extração ou consolidação afeta TODOS os conectores. Contém `_run_legacy` e `_run_generic`. |
| `markdown.py` | **ALTO** | Alterar conversão HTML→Markdown afeta todos os conectores. Tem lógica Confluence-specific. |
| `ui/main_window.py` | **CRÍTICO** | 132 métodos, orquestra toda a aplicação. Alteração em navegação ou workers afeta todas as telas. |
| `ui/mixins/selection_mixin.py` | **ALTO** | 36 KB, 7 funções duplicadas. Afeta a tela mais sensível do sistema. |
| `models.py` | **ALTO** | Mudança em `SCHEMA_VERSION` ou `stable_json_hash` invalida manifestos antigos. |
| `connectors/base.py` | **ALTO** | Mudança no ABC quebra todos os conectores. |
| `connectors/confluence.py` | **MÉDIO** | Afeta apenas Confluence, mas é o conector estável em produção. |
| `storage.py` | **BAIXO** | `FileTransaction` é bem encapsulado; mudanças internas não afetam o pipeline. |
| `runtime.py` | **BAIXO** | `CancellationToken` e `RateLimiter` são genéricos e estáveis. |

---

## 6. Shared Core vs Connector-Specific

| Componente | Classificação | Justificativa |
|---|---|---|
| `models.py` (KnowledgeDocument, Container, etc.) | **CORE COMPARTILHADO** | Modelo intermediário já existe e deve ser a fronteira principal. |
| `storage.py` (FileTransaction, atomic writes) | **CORE COMPARTILHADO** | Persistência atômica é genérica; não conhece plataforma. |
| `runtime.py` (CancellationToken, RateLimiter) | **CORE COMPARTILHADO** | Infraestrutura de execução; agnóstico. |
| `errors.py` (hierarquia genérica) | **CORE COMPARTILHADO** | Mas precisa remover `ConfluenceConnectionError` legado. |
| `reports.py` | **CORE COMPARTILHADO** | Relatórios consomem modelo intermediário. |
| `logging_utils.py` | **INFRAESTRUTURA** | Redação de segredos é transversal. |
| `auth.py` (browser_login) | **EXTENSÍVEL POR ESTRATÉGIA** | OAuth interativo é comum, mas cada plataforma pode ter fluxo diferente. |
| `session_store.py` | **INFRAESTRUTURA** | DPAPI é genérico. |
| `source_detection.py` | **CONNECTOR-SPECIFIC** | Hoje conhece URLs de cada plataforma. Deveria ser extensível por registro. |
| `connector_forms.py` | **CONNECTOR-SPECIFIC** | Cada conector deveria declarar seu próprio formulário. |
| `markdown.py` (transformer genérico) | **CORE COMPARTILHADO** | Mas `_replace_macros`, `_attachment_url`, `_replace_links` deveriam ser **CONNECTOR-SPECIFIC** ou **EXTENSÍVEL POR ESTRATÉGIA**. |
| `services.py` (pipeline genérico) | **CORE COMPARTILHADO** | Mas `_run_legacy` deveria morrer. O genérico deve operar só sobre `KnowledgeDocument`. |
| `connectors/http.py` | **INFRAESTRUTURA** | Cliente HTTP compartilhado é correto. |
| `browser/*` | **INFRAESTRUTURA / EXTENSÍVEL** | Cache e contratos são genéricos; adaptadores são bridge. |
| `ui/*` (pages, mixins) | **UI** | Mas `main_window.py` e mixins estão inchados com lógica que deveria estar em controllers. |

---

## 7. Arquitetura recomendada

A arquitetura recomendada é uma evolução incremental do que já existe, não uma reescrita. O conceito central é o **"Modelo Intermediário como Fronteira"**.

```
                    ┌─────────────────────────────────────────────┐
                    │                    UI                        │
                    │  (Pages + ViewModels leves, sem lógica de   │
                    │   negócio de plataforma)                    │
                    └──────────────────┬──────────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────────┐
                    │           Application Layer                 │
                    │  (execution_controller, operation_controller,│
                    │   project_controller, source_controller)     │
                    │   → orquestra, NÃO implementa plataforma    │
                    └──────────────────┬──────────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────────┐
                    │              Pipeline Core                  │
                    │  (ExtractionPipeline, ConsolidationPipeline)│
                    │   → opera exclusivamente sobre:             │
                    │     KnowledgeDocument, KnowledgeContainer   │
                    └──────────────────┬──────────────────────────┘
                                       │
                      ┌──────────────┼──────────────┐
                      │              │              │
                      ▼              ▼              ▼
                ┌────────┐   ┌────────┐   ┌────────────┐
                │Confl.  │   │Notion  │   │GenericWeb  │
                │Connector│   │Connector│   │  Connector │
                └────┬───┘   └────┬───┘   └─────┬──────┘
                     │            │              │
                     └────────────┼──────────────┘
                                  ▼
                        ┌─────────────────┐
                        │  Connector Base │
                        │  (ABC + Capab.) │
                        └─────────────────┘
                                  │
                       ┌────────────┼────────────┐
                       ▼            ▼            ▼
                  ┌─────────┐ ┌─────────┐ ┌──────────┐
                  │Discovery  │ │  Fetch  │ │Normalize │
                  │Strategy  │ │Strategy │ │Strategy  │
                  └─────────┘ └─────────┘ └──────────┘
```

**Princípio:** O Core nunca conhece "Confluence", "Notion" ou "SharePoint". Ele conhece apenas `KnowledgeSourceConnector` e `KnowledgeDocument`. Cada conector empacita:
- **DiscoveryStrategy:** como descobrir containers e páginas (lazy ou síncrono)
- **FetchStrategy:** como baixar conteúdo bruto
- **NormalizeStrategy:** como converter o payload bruto em `KnowledgeDocument`
- **RenderStrategy:** como converter `KnowledgeDocument` para Markdown (opcional; default no Core)

---

## 8. Estrutura de diretórios proposta

### 8.1. Estrutura atual (relevante)

```
alquimista/
├── models.py, services.py, storage.py, markdown.py
├── client.py (legado Confluence)
├── confluence_url.py (específico Confluence)
├── connectors/
│   ├── base.py, http.py, registry.py
│   ├── confluence.py, gitbook.py, notion.py, sharepoint.py, zendesk.py
├── browser/
├── ui/
│   ├── main_window.py (126KB)
│   ├── mixins/ (4 arquivos, ~87KB total)
│   ├── pages/
│   └── connector_forms.py
└── tests/ (19 arquivos genéricos)
```

### 8.2. Estrutura proposta (evolução incremental)

```
alquimista/
├── core/                          # NÚCLEO ESTÁVEL (nunca muda por conector)
│   ├── __init__.py
│   ├── models.py                  # Contratos pydantic (hoje models.py)
│   ├── storage.py                 # FileTransaction, atomic writes
│   ├── runtime.py                 # CancellationToken, RateLimiter
│   ├── errors.py                  # Somente erros genéricos
│   ├── logging_utils.py           # JSON + redação
│   └── pipeline/
│       ├── extraction.py          # ExtractionPipeline (refatorado de services.py)
│       ├── consolidation.py       # ConsolidationPipeline
│       └── manifest.py            # ManifestStore + ManifestIndex
│
├── connectors/
│   ├── base.py                    # ABC KnowledgeSourceConnector
│   ├── http.py                    # ApiHttpClient (compartilhado)
│   ├── registry.py                # Catálogo
│   ├── capabilities.py            # ConnectorCapabilities (hoje em models.py)
│   │
│   ├── confluence/                # Conector como pacote
│   │   ├── __init__.py
│   │   ├── connector.py           # Implementa ABC
│   │   ├── discovery.py           # list_containers, list_documents, lazy
│   │   ├── fetcher.py             # get_document (chama API)
│   │   ├── normalizer.py          # raw JSON → KnowledgeDocument
│   │   ├── markdown_strategy.py   # _replace_macros, _attachment_url (move de markdown.py)
│   │   ├── url_parser.py          # parse_confluence_url (move da raiz)
│   │   └── fixtures/              # Golden samples + respostas HTTP reais
│   │       ├── expected/
│   │       └── http/
│   │
│   ├── notion/                    # Mesma estrutura
│   ├── gitbook/
│   ├── zendesk/
│   ├── sharepoint/
│   └── generic_web/               # Futuro
│       ├── __init__.py
│       ├── connector.py
│       ├── crawler.py             # crawling + sitemap
│       ├── extractor.py           # HTML→texto (readability/trafilatura)
│       └── markdown_strategy.py   # Regras específicas de site
│
├── markdown/                      # Core Markdown genérico
│   ├── __init__.py
│   ├── core.py                    # MarkdownTransformer genérico
│   ├── renderer.py                # KnowledgeDocumentRenderer
│   └── plugins/                   # Estratégias por conector
│       ├── base.py                # Protocol MarkdownStrategy
│       ├── confluence.py          # Move _replace_macros, _attachment_url
│       └── generic.py             # Default (beautifulsoup + markdownify)
│
├── browser/                       # Mantém como está (já está bem)
│   ├── contracts.py
│   ├── service.py
│   ├── adapters.py
│   └── cache.py
│
├── ui/                            # UI mais enxuta
│   ├── main_window.py             # Reduzido: apenas orquestração de páginas
│   ├── pages/                     # Builders de tela (hoje pages/)
│   ├── components.py              # Widgets reutilizáveis
│   ├── theme.py
│   ├── viewmodels/                # NOVO: estado por tela, sem lógica de negócio
│   │   ├── sources_vm.py
│   │   ├── selection_vm.py
│   │   └── connection_vm.py
│   └── controllers/               # Hoje execution_controller, etc.
│       ├── project_controller.py
│       ├── source_controller.py
│       └── execution_controller.py
│
└── tests/
    ├── core/                      # Testes do pipeline genérico
    ├── connectors/
    │   ├── confluence/
    │   ├── notion/
    │   └── test_registry.py
    ├── ui/
    └── integration/               # Markers: real_confluence, integration
```

---

## 9. Contratos/interfaces recomendados

### 9.1. Connector ABC (já existe, mas precisa ser enriquecido)

```python
# connectors/base.py (evolução)

from typing import Protocol, runtime_checkable
from alquimista.core.models import (
    KnowledgeSource, KnowledgeContainer, KnowledgeDocument,
    ConnectorCapabilities, DiscoveryPage, PageRequest
)

class KnowledgeSourceConnector(Protocol):
    """Contrato mínimo. O Core opera apenas sobre este protocolo."""

    def get_source_type(self) -> str: ...
    def get_source(self) -> KnowledgeSource: ...
    def get_capabilities(self) -> ConnectorCapabilities: ...
    def validate_connection(self) -> None: ...

    # Discovery
    def list_containers(self) -> list[KnowledgeContainer]: ...
    def list_documents(self, container_id: str) -> list[KnowledgeDocument]: ...
    def list_root_documents(self) -> list[KnowledgeDocument]: ...  # opcional
    def list_document_children(self, document) -> list[KnowledgeDocument]: ...  # opcional
    def search_documents(self, query: str) -> list[KnowledgeDocument]: ...  # opcional

    # Fetch
    def get_document(self, document) -> KnowledgeDocument: ...

    # Lifecycle
    def close(self) -> None: ...
```

### 9.2. MarkdownStrategy (NOVO — elimina lógica específica do Core)

```python
# markdown/plugins/base.py

from typing import Protocol
from alquimista.core.models import KnowledgeDocument, MarkdownOptions

class MarkdownStrategy(Protocol):
    """Estratégia de conversão de HTML bruto para Markdown técnico."""

    def can_handle(self, document: KnowledgeDocument) -> bool: ...

    def to_technical_markdown(
        self, 
        document: KnowledgeDocument,
        options: MarkdownOptions
    ) -> str: ...

    def normalize_links(self, html_soup, context) -> None: ...
    def normalize_attachments(self, html_soup, context) -> None: ...
    def normalize_macros(self, html_soup, context) -> None: ...
```

**Uso:** `KnowledgeDocumentRenderer` seleciona a estratégia pelo `source_type` do documento. Confluence usa `ConfluenceMarkdownStrategy`; Zendesk usa `BeautifulSoupMarkdownStrategy`; Generic Web usa `ReadabilityMarkdownStrategy`.

### 9.3. DiscoveryAdapter (já existe em `browser/adapters.py`)

Manter como está — é uma boa abstração.

---

## 10. Estratégia contra regressões

### 10.1. O que existe hoje

- 19 arquivos de teste (`test_auth`, `test_markdown`, `test_services`, etc.)
- Markers pytest: `real_confluence`, `integration`, `build`, `slow`
- Não há estrutura por conector com golden samples

### 10.2. Estratégia recomendada

#### Fase 1 — Golden Samples por conector (P0)

Para cada conector, manter:

```
tests/connectors/confluence/fixtures/
├── raw_pages/
│   ├── page_simple.json          # Resposta real da API (sanitizada)
│   ├── page_with_macro.json
│   └── page_with_table.json
├── expected/
│   ├── page_simple.md            # Markdown esperado
│   ├── page_with_macro.md
│   └── page_with_table.md
└── test_regression.py            # Parametrizado: raw → expected
```

**Teste parametrizado:**

```python
@pytest.mark.parametrize("fixture_name", load_fixtures("confluence"))
def test_confluence_markdown_regression(fixture_name):
    raw = load_raw(fixture_name)
    expected = load_expected(fixture_name)

    doc = ConfluenceNormalizer.normalize(raw)
    md = MarkdownRenderer.render(doc, strategy=ConfluenceMarkdownStrategy())

    assert normalize_for_comparison(md) == normalize_for_comparison(expected)
```

**Normalização para comparação:** remover timestamps dinâmicos, IDs aleatórios, URLs temporárias.

#### Fase 2 — Contract Tests (P1)

Testar que cada conector respeita o ABC:

```python
@pytest.mark.parametrize("connector_class", all_connectors)
def test_connector_contract(connector_class):
    instance = connector_class(...)
    assert hasattr(instance, "get_document")
    # ... verifica tipos de retorno
```

#### Fase 3 — Integration Tests isolados (P1)

- `real_confluence`: testa contra instância real (marker existente)
- Um job de CI por conector, para que falha em Notion não quebre build de Confluence

#### Fase 4 — Snapshot Tests para UI (P2)

- Testar que `main_window.py` monta páginas sem crash
- Não testar comportamento visual (frágil), mas sim que builders retornam `QWidget` válido

---

## 11. Estratégia para Generic Web

### Opção recomendada: `GenericWebConnector` como conector de primeira classe

Não é uma camada separada — é apenas mais um conector que implementa o mesmo ABC.

**Arquitetura do GenericWebConnector:**

```
connectors/generic_web/
├── connector.py          # Implementa ABC
├── crawler.py            # Descoberta: sitemap.xml + links internos
├── fetcher.py            # Playwright/requests para obter HTML renderizado
├── extractor.py          # Trafilatura/Readability/Boilerpipe para extrair conteúdo principal
├── markdown_strategy.py  # BeautifulSoup + markdownify
└── robots.py             # Respeita robots.txt, rate limits, canonical URLs
```

**Diferenças tratadas no conector, não no Core:**
- SPA vs estático: `fetcher.py` decide se usa Playwright ou requests
- Autenticação: suporta `browser` mode (já existe no `auth.py`)
- Crawling: `crawler.py` implementa `list_containers` (domínios) e `list_documents` (páginas)
- Rate limits: usa `robots.txt` + delay configurável
- Conteúdo duplicado: `canonical` + hash de conteúdo

**O Core não muda.** O pipeline genérico recebe `KnowledgeDocument` do `GenericWebConnector` exatamente como recebe do `ConfluenceConnector`.

---

## 12. Plano incremental de refatoração

### Etapa 0 — Baseline (1-2 semanas)

**Objetivo:** Proteger o Confluence antes de qualquer mudança.

- Criar `tests/connectors/confluence/fixtures/` com 5-10 páginas reais
- Gerar `expected/` Markdown para cada uma
- Commitar como baseline
- Criar teste de regressão que falha se o Markdown gerado mudar

**Arquivos afetados:** `tests/` apenas  
**Risco:** ZERO (só adiciona testes)  
**Benefício:** Protege Confluence de regressões futuras

### Etapa 1 — Extrair MarkdownStrategy (2-3 semanas)

**Objetivo:** Isolar lógica Confluence-specific de `markdown.py`.

- Criar `markdown/plugins/base.py` (Protocol)
- Mover `_replace_macros`, `_replace_links`, `_attachment_url` para `markdown/plugins/confluence.py`
- `markdown.py` passa a delegar para a strategy pelo `source_type`
- Rodar golden samples do Confluence para garantir igualdade

**Arquivos afetados:** `markdown.py`, novo diretório `markdown/plugins/`  
**Risco:** BAIXO (mudança mecânica, testes protegem)  
**Benefício:** Notion/SharePoint podem ter suas próprias strategies sem tocar no Core

### Etapa 2 — Matar `_run_legacy` (2-3 semanas)

**Objetivo:** Eliminar `client.py` e modo legado de `services.py`.

- Migrar todo uso de `client.py` para `connectors/confluence.py`
- Remover `_run_legacy` de `services.py`; manter apenas `_run_generic`
- Deletar `client.py` e `confluence_url.py` da raiz (mover para `connectors/confluence/`)

**Arquivos afetados:** `services.py`, `connectors/confluence.py`, `client.py`  
**Risco:** MÉDIO (testes de regressão do Etapa 0 são obrigatórios aqui)  
**Benefício:** `services.py` fica 30% menor e 100% agnóstico a plataforma

### Etapa 3 — Empacotar conectores (2 semanas)

**Objetivo:** Cada conector vira um pacote Python.

- `connectors/confluence.py` → `connectors/confluence/connector.py`
- Mover `confluence_url.py` para `connectors/confluence/url_parser.py`
- Criar `connectors/notion/`, `connectors/gitbook/`, etc. com a mesma estrutura
- `connector_forms.py` e `source_detection.py` passam a ler metadados do `registry.py` (cada conector declara sua URL e formulário)

**Arquivos afetados:** `connectors/`, `ui/connector_forms.py`, `source_detection.py`  
**Risco:** MÉDIO (reorganização de imports)  
**Benefício:** Novo conector = novo diretório, zero alteração em arquivo existente

### Etapa 4 — Generic Web (3-4 semanas)

**Objetivo:** Adicionar conector de websites arbitrários.

- Criar `connectors/generic_web/`
- Reutilizar `browser/service.py` para fetch
- Implementar `crawler.py` (sitemap + links)

**Arquivos afetados:** apenas `connectors/generic_web/`  
**Risco:** BAIXO (não altera código existente)  
**Benefício:** Valida se a arquitetura realmente suporta novos conectores sem tocar no Core

### Etapa 5 — Reduzir main_window.py (contínuo)

**Objetivo:** Diminuir a orquestradora.

- Mover lógica de workers para `ui/controllers/`
- Mover estado mutável para `ui/viewmodels/`
- `main_window.py` fica com ~60 métodos (meta: <80 KB)

**Arquivos afetados:** `ui/main_window.py`, `ui/controllers/`, `ui/viewmodels/`  
**Risco:** MÉDIO (refatoração de UI é visível ao usuário)  
**Benefício:** Testabilidade e manutenibilidade da UI

---

## 13. Tabela de prioridades

| Prioridade | Mudança | Benefício | Risco | Esforço |
|---|---|---|---|---|
| **P0** | Golden samples Confluence | Alto | Baixo | Baixo |
| **P0** | Extrair `MarkdownStrategy` do `markdown.py` | Alto | Baixo | Médio |
| **P1** | Matar `_run_legacy` e `client.py` | Alto | Médio | Médio |
| **P1** | Empacotar conectores em diretórios | Alto | Médio | Médio |
| **P1** | Contract tests para todos os conectores | Alto | Baixo | Baixo |
| **P2** | Generic Web connector | Alto | Baixo | Alto |
| **P2** | Reduzir `main_window.py` | Médio | Médio | Alto |
| **P2** | Limpar duplicações de funções (12 no total) | Médio | Baixo | Baixo |
| **P3** | ViewModels para UI | Médio | Médio | Alto |
| **P3** | Erros legado → hierarquia genérica pura | Baixo | Baixo | Baixo |

---

## 14. O que NÃO modificar agora

1. **`models.py` (contratos pydantic):** O `SCHEMA_VERSION = 4` e o `stable_json_hash` são críticos para compatibilidade de manifestos. Não alterar campos sem migração planejada.

2. **`storage.py` (FileTransaction):** A persistência atômica (tmp + rename) está correta e estável. Não reinventar.

3. **`runtime.py` (CancellationToken, RateLimiter):** Infraestrutura de threads está funcionando. Não tocar.

4. **`browser/contracts.py` e `browser/cache.py`:** O subsistema de browser já tem boa separação. Preservar.

5. **`connectors/http.py` (ApiHttpClient):** O cliente HTTP compartilhado (HTTPS obrigatório, retries, redação de logs) é uma boa abstração. Manter.

6. **Fluxo de telas do usuário:** Dashboard → Fontes → Conexão → Seleção → ... funciona. Não reorganizar a navegação sem necessidade de produto.

---

## 15. Teste de extensibilidade

### Cenário A — Adicionar Google Drive

**Módulos a criar:**
- `connectors/google_drive/connector.py` — implementa ABC
- `connectors/google_drive/discovery.py` — lista folders e files
- `connectors/google_drive/fetcher.py` — exporta Google Docs → HTML → KnowledgeDocument
- `connectors/google_drive/markdown_strategy.py` — conversão específica

**Módulos a alterar:**
- `connectors/registry.py` — registrar novo conector (1 linha)
- `source_detection.py` — adicionar padrão de URL do Google Drive (se quiser autodetect)

**Core afetado?** ZERO. O pipeline genérico recebe `KnowledgeDocument` do mesmo jeito.

### Cenário B — Adicionar Generic Website

**Módulos a criar:**
- `connectors/generic_web/` (pacote completo, ver seção 11)

**Módulos a alterar:**
- `connectors/registry.py` — registrar
- `source_detection.py` — detectar URLs genéricas (ou deixar como fallback)

**Core afetado?** ZERO.

### Cenário C — Notion exige paginação diferente

**Impacto no Confluence?** ZERO, se a arquitetura recomendada for adotada.

- A paginação vive em `connectors/notion/discovery.py`
- `connectors/confluence/discovery.py` não muda
- O Core (`services.py`) chama `list_document_children()` e recebe `list[KnowledgeDocument]`. Não sabe como a lista foi paginada.

**Hipótese:** Hoje, se Notion precisar de paginação diferente, a mudança provavelmente tocaria em `services.py` ou `tree_mixin.py`. Após a refatoração, não tocaria.

### Cenário D — Mudamos a geração de Markdown

**Impacto nos conectores?** DEPENDE.

- Se a mudança for no **Core Markdown** (ex.: como renderizar tabelas em geral), afeta todos os conectores. Isso é correto — é comportamento compartilhado.
- Se a mudança for específica de **macros do Confluence**, afeta apenas `markdown/plugins/confluence.py`. Notion, GitBook, etc. não sentem nada.

**Hoje,** uma mudança em `markdown.py` afeta todos os conectores porque a lógica Confluence-specific está misturada. Após a refatoração, o impacto é controlado.

---

## 16. Avaliação arquitetural

### 16.1. Notas atuais (baseadas na documentação)

| Área | Nota | Justificativa |
|---|---|---|
| **Modularidade** | 5 | Conectores separados, mas Core mistura legacy e específico |
| **Separação de responsabilidades** | 4 | `main_window.py` e `services.py` fazem demais; UI conhece plataformas |
| **Extensibilidade** | 5 | ABC existe, mas adicionar conector exige tocar UI e Core |
| **Testabilidade** | 5 | Testes existem, mas sem isolamento por conector; duplicações dificultam |
| **Proteção contra regressões** | 4 | Sem golden samples; `services.py` é hotspot compartilhado |
| **Acoplamento** | 4 | Confluence-specific em `markdown.py`, `services.py`, `client.py` |
| **Coesão** | 5 | Mixins são coesos por tema, mas inchados; `main_window.py` é incoeso |
| **Observabilidade** | 6 | Logs JSON com redação são bons; falta identificação de etapa no log |
| **Manutenibilidade** | 5 | Código bem documentado (MAPA.md), mas arquivos grandes e duplicações |
| **Preparação para novos conectores** | 5 | Estrutura base existe, mas prática é arriscada (modifica Core) |

**Média atual: ~4.8**

### 16.2. Notas projetadas (após Etapas 0-3)

| Área | Nota | Justificativa |
|---|---|---|
| **Modularidade** | 8 | Conectores empacotados; Core enxuto |
| **Separação de responsabilidades** | 7 | `main_window.py` ainda grande, mas lógica movida para controllers |
| **Extensibilidade** | 8 | Novo conector = novo diretório + 1 linha no registry |
| **Testabilidade** | 8 | Golden samples + contract tests por conector |
| **Proteção contra regressões** | 8 | Golden samples detectam mudanças silenciosas |
| **Acoplamento** | 7 | Core agnóstico; conectores isolados |
| **Coesão** | 7 | Mixins ainda existem, mas menores |
| **Observabilidade** | 7 | Logs por etapa de pipeline |
| **Manutenibilidade** | 7 | Sem duplicações; arquivos <50 KB |
| **Preparação para novos conectores** | 8 | Generic Web valida a arquitetura |

**Média projetada: ~7.5**

---

## 17. Top 10 próximas ações (ordem exata de execução)

1. **Criar golden samples do Confluence** — 5-10 páginas reais sanitizadas + Markdown esperado; teste de regressão parametrizado.
2. **Extrair `ConfluenceMarkdownStrategy` de `markdown.py`** — Mover `_replace_macros`, `_replace_links`, `_attachment_url` para `markdown/plugins/confluence.py`; `markdown.py` passa a delegar por `source_type`.
3. **Rodar testes de regressão do Confluence** — Garantir que Etapa 2 não alterou saída.
4. **Eliminar `_run_legacy` de `services.py`** — Migrar últimos usos para `_run_generic`; deletar `client.py`.
5. **Rodar testes de regressão do Confluence novamente** — Validar Etapa 4.
6. **Transformar `connectors/confluence.py` em pacote `connectors/confluence/`** — Criar `connector.py`, `discovery.py`, `fetcher.py`, `normalizer.py`, `markdown_strategy.py`, `url_parser.py`.
7. **Refatorar `connector_forms.py` e `source_detection.py`** — Ler specs do registry; cada conector declara sua URL e formulário.
8. **Criar contract tests para todos os conectores** — Verificar que todos implementam o ABC corretamente.
9. **Criar `connectors/generic_web/`** — Validar que a arquitetura suporta novo conector sem tocar Core.
10. **Limpar as 12 duplicações de funções** — `selection_mixin.py` (7), `connection_mixin.py` (3), `execution_controller.py` (1), `auth.py` (1).

---

## 18. Respostas às 23 questões críticas

1. **A arquitetura atual escala bem para 5, 10 ou 20 conectores?**  
   Não. Hoje adicionar um conector exige tocar em `services.py`, `markdown.py`, `connector_forms.py`, `source_detection.py`. Com 20 conectores, `services.py` seria inmanutenível.

2. **Onde estão hoje os maiores acoplamentos?**  
   `services.py` (30 menções a Confluence), `markdown.py` (lógica de macros/links/attachments do Confluence), `ui/main_window.py` (orquestra tudo).

3. **Quais partes deveriam ser compartilhadas?**  
   `models.py`, `storage.py`, `runtime.py`, `reports.py`, `errors.py` (genéricos), `connectors/http.py`, `browser/*`.

4. **Quais partes deveriam ser isoladas por conector?**  
   Discovery, paginação, parsing de URL, normalização de HTML, estratégia de Markdown, formulários de UI, detecção de URL.

5. **Paginação deve ser específica por conector?**  
   Sim. Confluence usa cursor; Notion usa offset; SharePoint usa `@odata.nextLink`. O Core deve apenas chamar `list_document_children()` e receber uma lista.

6. **Descoberta de páginas deve ser específica por conector?**  
   Sim. Cada API tem seu próprio conceito de espaço/seção/folder.

7. **Parsing deve ser específico por conector?**  
   Sim. Confluence tem macros; Zendesk tem HTML de Help Center; Notion tem blocks. Cada conector normaliza para `KnowledgeDocument`.

8. **Markdown deve permanecer compartilhado?**  
   Parcialmente. O engine HTML→Markdown genérico (beautifulsoup, markdownify) é compartilhado. Mas regras específicas (macros Confluence, links internos) devem ser plugins por conector.

9. **Consolidação deve permanecer compartilhada?**  
   Sim. `ConsolidationService` opera sobre `ManifestDocument` e arquivos Markdown já gerados. É agnóstico.

10. **Preciso de um modelo intermediário de documentos?**  
    Já existe (`KnowledgeDocument`, `KnowledgeContainer`, etc.), mas precisa ser mais rigorosamente usado como fronteira. O Core não deve ver HTML cru de Confluence.

11. **Preciso de uma interface/base para conectores?**  
    Já existe (`connectors/base.py:KnowledgeSourceConnector`), mas precisa ser a única interface que o Core conhece.

12. **Como impedir regressões entre conectores?**  
    Golden samples por conector + testes de regressão automatizados + Core 100% agnóstico.

13. **Como testar cada integração isoladamente?**  
    Fixtures com respostas HTTP reais sanitizadas + mocks para a camada HTTP + golden samples de Markdown.

14. **Como permitir novos conectores sem alterar o Core?**  
    Registry pattern: conector se registra; Core opera sobre ABC. `connector_forms.py` e `source_detection.py` leem metadados do registry.

15. **Como preparar o sistema para URLs/sites genéricos?**  
    Tratar como mais um conector (`connectors/generic_web/`) que implementa o mesmo ABC.

16. **Como reduzir responsabilidades da UI?**  
    Mover lógica de negócio dos mixins para `ui/controllers/` e `ui/viewmodels/`. `main_window.py` deve apenas orquestrar.

17. **Qual refatoração oferece maior benefício com menor risco?**  
    Extrair `MarkdownStrategy` do `markdown.py` + criar golden samples do Confluence. Benefício imediato, risco quase zero.

18. **O que eu deveria alterar agora?**  
    Golden samples + `MarkdownStrategy`. Depois, matar `_run_legacy`.

19. **O que deveria deixar para depois?**  
    Reduzir `main_window.py` (é importante, mas não bloqueia novos conectores).

20. **O que definitivamente não deveria alterar neste momento?**  
    `models.py` (sem migração de schema), `storage.py` (FileTransaction estável), `runtime.py`.

21. **Onde abstrações seriam prematuras?**  
    Criar uma camada de "Adapter de Autenticação" genérica demais seria prematuro — cada plataforma tem OAuth, Basic, Bearer de formas diferentes. Manter `auth.py` como está, com extensão por conector quando necessário.

22. **Qual é o maior gargalo arquitetural atual?**  
    `services.py` com 1.145 linhas e modos legado/genérico misturados. É o coração do sistema e conhece detalhes do Confluence.

23. **A duplicação de funções (12 no total) é um risco de segurança?**  
    Não é risco de segurança, mas é risco de manutenção. Editores podem modificar a função morta em vez da ativa, introduzindo bugs silenciosos.

---

> **Frase final:** Se eu fosse o responsável técnico pelo Projeto Alquimista hoje, a primeira mudança arquitetural que faria antes de desenvolver qualquer nova integração seria: **criar golden samples do Confluence e extrair a lógica Confluence-specific de `markdown.py` para uma `MarkdownStrategy` isolada** — porque sem uma baseline testada e um Core realmente agnóstico, cada novo conector será uma ameaça à única integração que funciona.

---

*Análise produzida em 2026-08-12. Baseada em `MAPA.md` (67.179 bytes), `README.md`, `AGENTS.md` e o prompt de análise arquitetural.*
