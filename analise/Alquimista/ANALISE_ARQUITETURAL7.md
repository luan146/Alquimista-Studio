# Análise Arquitetural — ALQuimista Studio 3.0

**Data:** 2026-08-12
**Escopo:** Arquitetura, modularização, estabilidade e preparação para expansão
**Base:** Código-fonte real do projeto (não apenas MAPA.md ou documentação)

---

## 1. Resumo Executivo

### Estado Atual

O ALQuimista Studio é uma aplicação desktop PySide6 bem estruturada para extração de conhecimento de plataformas documentais (Confluence, GitBook, Notion, SharePoint, Zendesk). O projeto está **no meio de uma migração arquitetural**: existe um caminho **legado** fortemente acoplado ao Confluence e um caminho **genérico** baseado em um ABC (`KnowledgeSourceConnector`) que já funciona para múltiplos conectores.

A arquitetura genérica (ABC + Registry + KnowledgeDocument + KnowledgeDocumentRenderer + ExtractionService._run_generic) é **a direção correta** e já funciona para GitBook e Zendesk. Entretanto, o caminho legado do Confluence coexiste e gera duplicação funcional, acoplamento residual e risco de regressão.

### Principal Risco

> **Qualquer alteração em `services.py`, `markdown.py` ou `main_window.py` tem blast radius alto porque esses arquivos contêm lógica legada (Confluence) misturada com lógica genérica.** Uma correção para Notion pode inadvertidamente alterar o fluxo que Confluence ainda usa via `_run_legacy`.

### Principal Oportunidade

O modelo intermediário (`KnowledgeDocument`) já existe e funciona. O renderizador genérico (`KnowledgeDocumentRenderer`) já existe e funciona. O ABC do conector (`KnowledgeSourceConnector`) já existe e funciona. **A infraestrutura para uma arquitetura limpa já está em 70% do caminho.** Falta completar a migração do Confluence para o caminho genérico e eliminar o caminho legado.

### Recomendação Arquitetural Central

> **Migrar o Confluence para o fluxo genérico (`_run_generic` + `KnowledgeDocumentRenderer`), eliminando `_run_legacy` e `MarkdownTransformer` como caminhos ativos. Proteger essa migração com golden samples que garantam que o output Markdown do Confluence não mude.**

---

## 2. Como o Projeto Funciona Atualmente

### Pipeline Real (reconstruído do código)

```text
Usuário
  │
  ├─ Cria/Importa Projeto (ProjectConfig)
  │     ↓
  ├─ Configura Fonte (SourceConfig + source_detection.py)
  │     ↓
  ├─ Autenticação (connection_mixin.py → auth.py → browser/service.py)
  │     ↓
  │     RuntimeSecrets (memória, nunca serializado)
  │     ↓
  ├─ Carregamento da Árvore
  │     ↓
  │     ConnectorRegistry → instancia KnowledgeSourceConnector
  │     ↓
  │     connector.list_containers() → KnowledgeContainer[]
  │     ↓
  │     connector.list_documents(container_id) → KnowledgeDocumentMetadata[]
  │     ↓
  │     (lazy: connector.list_root_documents / list_document_children)
  │     ↓
  │     tree_models.py → ordena e estrutura em árvore Qt
  │     ↓
  ├─ Seleção (selection_mixin.py → SelectionStore)
  │     ↓
  │     Chaves: source_id:container_id:document_id
  │     ↓
  ├─ Revisão (review_page.py)
  │     ↓
  ├─ Configuração Markdown (MarkdownOptions)
  │     ↓
  ├─ Extração
  │     ↓
  │     execution_controller.py → prepare_runtimes() → SourceRuntime[]
  │     ↓
  │     operation_controller.py → QThreadPool → Worker
  │     ↓
  │     ┌─────────────────────────────────────────────┐
  │     │ ExtractionService.run(runtime)              │
  │     │   ├── runtime.is_generic == True             │
  │     │   │     → _run_generic()                     │
  │     │   │       → connector.get_document()         │
  │     │   │       → KnowledgeDocumentRenderer.render()│
  │     │   │       → FileTransaction.stage_text()     │
  │     │   │                                          │
  │     │   └── runtime.is_generic == False            │
  │     │         → _run_legacy()                      │
  │     │           → ConfluenceClient.fetch_page()    │
  │     │           → MarkdownTransformer              │
  │     │           → FileTransaction.stage_text()     │
  │     └─────────────────────────────────────────────┘
  │     ↓
  │     ManifestStore → manifesto_alquimista.json
  │     ↓
  ├─ Consolidação (ConsolidationService)
  │     ↓
  │     Lê manifest → agrupa → ordena → junta → FileTransaction
  │     ↓
  └─ Resultados (ExecutionReport → results_page.py)
```

### Dois Caminhos Coexistentes (FATO)

O diagrama acima mostra o **problema central**: existem dois fluxos de extração:

| Aspecto | Caminho Genérico | Caminho Legado |
|---|---|---|
| **Ativação** | `runtime.is_generic == True` | `runtime.is_generic == False` |
| **Conectores** | GitBook, Zendesk, Notion, SharePoint | Confluence (projetos antigos) |
| **Fetching** | `connector.get_document()` | `ConfluenceClient.fetch_page()` |
| **Rendering** | `KnowledgeDocumentRenderer` | `MarkdownTransformer` |
| **Código em** | `services.py:_run_generic` | `services.py:_run_legacy` (~200 linhas) |

> **HIPÓTESE:** Se o Confluence hoje for forçado a usar `_run_generic` (via `ConfluenceRestConnector.get_document()` + `KnowledgeDocumentRenderer`), o output Markdown pode diferir do output do caminho legado (`MarkdownTransformer`), porque `MarkdownTransformer` tem tratamento específico de macros Confluence que `KnowledgeDocumentRenderer` não tem.

---

## 3. Mapa de Responsabilidades

### Módulos Existentes

| Módulo | Arquivo(s) | Responsabilidade | Tamanho |
|---|---|---|---|
| **Modelos** | `models.py` | Contratos de dados (Pydantic): KnowledgeDocument, SourceConfig, etc. | 20KB |
| **Serviços** | `services.py` | ExtractionService + ConsolidationService | 57KB |
| **Markdown** | `markdown.py` | MarkdownTransformer (legado) + KnowledgeDocumentRenderer (genérico) | 24KB |
| **Storage** | `storage.py` | FileTransaction, ManifestStore, save/load project | 14KB |
| **Conectores** | `connectors/*.py` | ABC + 5 implementações + HTTP + Registry | ~70KB total |
| **Cliente Conf.** | `client.py` | Cliente REST legado do Confluence | 24KB |
| **Auth** | `auth.py` | Login interativo via Playwright | 5.6KB |
| **Browser** | `browser/*.py` | Discovery lazy, cache SQLite, adaptadores Playwright | ~50KB total |
| **Erros** | `errors.py` | Hierarquia de exceções | 1KB |
| **Runtime** | `runtime.py` | CancellationToken, RateLimiter | 1.2KB |
| **Seleção** | `selection.py` | SelectionStore (estado sem Qt) | 2.3KB |
| **Detecção** | `source_detection.py` + `confluence_url.py` | Detecta plataforma por URL | 8.7KB |
| **Manifest** | `manifest_index.py` | Índice SQLite para atualização incremental | 4.2KB |
| **Logs** | `logging_utils.py` | Logging JSON com redação de segredos | 2.6KB |
| **Relatórios** | `reports.py` | ExecutionReport, DocumentResult | 1.8KB |
| **UI - Janela** | `ui/main_window.py` | MainWindow — God Class orquestradora | 126.6KB |
| **UI - Mixins** | `ui/mixins/*.py` | Comportamentos separados da MainWindow | ~87KB total |
| **UI - Páginas** | `ui/pages/*.py` | Builders de tela (visuais) | ~40KB total |
| **UI - Controles** | `ui/controllers.py`, `execution_controller.py`, etc. | RuntimeBuilder, workers | ~25KB total |
| **UI - Widgets** | `ui/components.py` | Widgets reutilizáveis | ~15KB |

---

## 4. Problemas Encontrados (por severidade)

### P0 — Críticos

#### P0.1 — Dois Fluxos de Extração Coexistentes

**FATO:** [`services.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/services.py) contém `_run_generic` e `_run_legacy`. O método `_run_legacy` tem ~200 linhas com lógica 100% Confluence: instancia `ConfluenceClient`, usa `MarkdownTransformer`, chama `page_metadata()` diretamente.

**FATO:** A decisão entre os dois caminhos é:
```python
if runtime.is_generic:
    return self._run_generic(runtime, ...)
else:
    return self._run_legacy(runtime, ...)
```

**Consequência:** Qualquer mudança em `_run_generic` (para novo conector) não afeta Confluence se ele estiver no caminho legacy — mas isso cria **duas bases de código paralelas** que divergem silenciosamente. Quando o legacy for removido, a mudança será traumática.

**Blast radius:** CRÍTICO — afeta toda a extração.

#### P0.2 — `MarkdownTransformer` vs `KnowledgeDocumentRenderer`

**FATO:** [`markdown.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/markdown.py) contém dois renderizadores:
- `MarkdownTransformer` — ~80% específico de Confluence (macros `ac:link`, `ac:image`, `ri:attachment`, `ac:structured-macro`)
- `KnowledgeDocumentRenderer` — genérico, opera sobre `KnowledgeDocument`

**Consequência:** A transição para o renderizador genérico pode alterar o output do Confluence, gerando regressão silenciosa.

#### P0.3 — `client.py` Duplica `ApiHttpClient`

**FATO:** [`client.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/client.py) (24KB) implementa retry, rate limit, timeout, session management **de forma independente** de [`connectors/http.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/http.py) (`ApiHttpClient`). Os outros conectores (Notion, GitBook, SharePoint, Zendesk) usam `ApiHttpClient`.

**Consequência:** Uma correção de bug HTTP (ex.: tratamento de proxy, timeout) precisa ser feita em dois lugares. Comportamento HTTP inconsistente entre Confluence e outros conectores.

---

### P1 — Importantes

#### P1.1 — MainWindow é uma God Class (126.6KB, 132 métodos)

**FATO:** [`main_window.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/main_window.py) contém ~25 referências a "confluence" com tratamento especial. Tem métodos como `_review_page_legacy`, `_consolidation_page_legacy`, tratamento especial para `source_type == "confluence_rest"`.

**FATO:** A MainWindow importa e usa `ConfluenceClient` diretamente para lookup de páginas em [`source_mixin.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/mixins/source_mixin.py) (`_lookup_page_details`).

**FATO:** Para adicionar um novo conector na UI, é necessário adicionar o `source_type` em whitelists do tipo `if source.source_type in {"confluence_rest", "gitbook_api", "zendesk_guide"}` em `main_window.py`.

#### P1.2 — Funções Duplicadas nos Mixins

**FATO:** [`selection_mixin.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/mixins/selection_mixin.py) tem 7 funções definidas duas vezes (primeira morta, segunda ativa). [`connection_mixin.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/mixins/connection_mixin.py) tem 3 funções duplicadas. [`auth.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/auth.py) e [`execution_controller.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/execution_controller.py) têm 1 cada.

**Consequência:** Confusão ao editar (editar a versão morta em vez da ativa), aumento do tamanho dos arquivos, dificuldade de manutenção.

#### P1.3 — `ManifestEntry` com campos Confluence hardcoded

**FATO:** Em [`models.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/models.py), `ManifestEntry` tem defaults como `source_type = "confluence_rest"` e campos como `space_key`, `space_name`, `confluence_version`. O `ManifestStore.load` faz migração on-the-fly de schemas antigos com assunções Confluence.

**Consequência:** A persistência de manifestos está amarrada à estrutura de dados do Confluence. Novos conectores precisam "caber" nessa estrutura.

#### P1.4 — Erros Legados Coexistem com Genéricos

**FATO:** [`errors.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/errors.py) tem `ConfluenceConnectionError` e `RateLimitError` (legados) ao lado de `ApiConnectionError` e `ApiRateLimitError` (genéricos). O `RateLimitError` legado herda de `ConfluenceConnectionError`.

**Consequência:** Tratamento de erros na UI pode capturar tipos inesperados. Risco de inconsistência ao tratar rate limit de conectores diferentes.

---

### P2 — Melhorias Desejáveis

#### P2.1 — Testes de Markdown são Insuficientes

**FATO:** [`test_markdown.py`](file:///c:/Dev/Alquimista%20studio%203.0/tests/test_markdown.py) tem apenas 3KB para um componente de 24KB. Não testa `MarkdownTransformer` nem `KnowledgeDocumentRenderer` diretamente. Não há golden samples.

#### P2.2 — Método `enter_confluence` na UI

**FATO:** [`connection_mixin.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/mixins/connection_mixin.py) tem um método chamado `enter_confluence` — nome hardcoded para uma plataforma específica.

#### P2.3 — Dashboard com Cartões Hardcoded

**FATO:** [`dashboard_page.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/pages/dashboard_page.py) tem cartões de fonte com ícones e descrições fixas para cada plataforma.

#### P2.4 — Falta de Erros Específicos para Etapas do Pipeline

**FATO:** Não existem `DiscoveryError`, `NormalizationError` ou `ConsolidationError` em [`errors.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/errors.py).

---

## 5. Hotspots e Blast Radius

### Top 10 Hotspots Arquiteturais

| # | Arquivo/Módulo | Problema | Consequência | Blast Radius | Prioridade |
|---|---|---|---|---|---|
| 1 | [`services.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/services.py) (57KB) | Dois fluxos de extração (_run_generic + _run_legacy) | Mudança em um pode quebrar outro; duplicação | CRÍTICO | P0 |
| 2 | [`main_window.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/main_window.py) (126.6KB) | God Class com lógica de conector, pipeline e UI | Qualquer mudança pode afetar múltiplas telas | CRÍTICO | P1 |
| 3 | [`markdown.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/markdown.py) (24KB) | Dois renderizadores coexistentes | Mudança em um pode gerar regressão no outro | ALTO | P0 |
| 4 | [`client.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/client.py) (24KB) | Duplica ApiHttpClient; legado | Bugs HTTP corrigidos em um lugar não se propagam | ALTO | P1 |
| 5 | [`selection_mixin.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/mixins/selection_mixin.py) (36KB) | 7 funções duplicadas; acoplamento a conectores | Editar versão errada quebra seleção | ALTO | P1 |
| 6 | [`models.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/models.py) (20KB) | ManifestEntry com defaults Confluence | Persistência amarrada a uma plataforma | MÉDIO | P1 |
| 7 | [`connection_mixin.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/mixins/connection_mixin.py) (18KB) | 3 funções duplicadas; nome `enter_confluence` | Confusão ao adicionar nova auth | MÉDIO | P2 |
| 8 | [`source_mixin.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/mixins/source_mixin.py) (30KB) | Importa ConfluenceClient diretamente | UI acoplada a conector específico | MÉDIO | P2 |
| 9 | [`execution_controller.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/ui/execution_controller.py) | Função duplicada; decisão legacy vs generic | Ponto de bifurcação do pipeline | MÉDIO | P1 |
| 10 | [`errors.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/errors.py) (1KB) | Erros legados coexistem com genéricos | Tratamento inconsistente entre conectores | BAIXO | P2 |

### Blast Radius Detalhado

| Arquivo | Se alterado, pode quebrar... | Nível |
|---|---|---|
| `services.py` | Extração de TODOS os conectores, consolidação, manifest | CRÍTICO |
| `main_window.py` | Qualquer tela, navegação, workers, estado | CRÍTICO |
| `markdown.py` | Output Markdown de todos os conectores, frontmatter, preview | ALTO |
| `models.py` | Serialização, manifest, backward compatibility | ALTO |
| `client.py` | Apenas Confluence (via caminho legado) | MÉDIO |
| `connectors/base.py` | Todos os conectores (se contrato mudar) | ALTO |
| `connectors/http.py` | Todos os conectores exceto Confluence legado | ALTO |
| `storage.py` | Persistência de projetos, manifest, transações | ALTO |
| `runtime.py` | Cancelamento e rate limit global | MÉDIO |
| `selection.py` | Seleção de páginas | BAIXO |

---

## 6. Shared Core vs Connector-Specific

### Tabela de Classificação

| Componente | Classificação | Estado Atual | Justificativa |
|---|---|---|---|
| **KnowledgeDocument** | CORE COMPARTILHADO | ✅ Já compartilhado | Modelo intermediário genérico entre conectores e pipeline |
| **KnowledgeDocumentRenderer** | CORE COMPARTILHADO | ✅ Já compartilhado | Renderiza qualquer KnowledgeDocument para Markdown |
| **ExtractionService._run_generic** | CORE COMPARTILHADO | ✅ Funciona | Pipeline genérico de extração |
| **ConsolidationService** | CORE COMPARTILHADO | ✅ Já compartilhado | Opera sobre manifest, não conhece conectores |
| **ApiHttpClient** | INFRAESTRUTURA | ✅ Já compartilhado | HTTP com retry, rate limit, timeout |
| **CancellationToken** | INFRAESTRUTURA | ✅ Já compartilhado | Cancelamento cooperativo |
| **RateLimiter** | INFRAESTRUTURA | ✅ Já compartilhado | Controle de taxa |
| **FileTransaction** | INFRAESTRUTURA | ✅ Já compartilhado | Escrita atômica |
| **ManifestStore** | INFRAESTRUTURA | ⚠️ Parcial (defaults Confluence) | Precisa generalizar defaults |
| **SelectionStore** | CORE COMPARTILHADO | ✅ Já compartilhado | Estado de seleção genérico |
| **ConnectorRegistry** | INFRAESTRUTURA | ✅ Já funciona | Factory/catalog de conectores |
| **Logging** | INFRAESTRUTURA | ✅ Já compartilhado | JSON + redação de segredos |
| **ExecutionReport** | CORE COMPARTILHADO | ✅ Já compartilhado | Relatório genérico |
| **Hierarquia de erros base** | CORE COMPARTILHADO | ⚠️ Parcial (legados) | Precisa remover erros Confluence-specific |
| --- | --- | --- | --- |
| **API do Confluence** | CONNECTOR-SPECIFIC | ✅ Isolado em `confluence.py` | CQL, restrictions, ancestors |
| **API do Notion** | CONNECTOR-SPECIFIC | ✅ Isolado em `notion.py` | Blocos, databases |
| **API do GitBook** | CONNECTOR-SPECIFIC | ✅ Isolado em `gitbook.py` | Content nodes, organizations |
| **API do SharePoint** | CONNECTOR-SPECIFIC | ✅ Isolado em `sharepoint.py` | Microsoft Graph, drive items |
| **API do Zendesk** | CONNECTOR-SPECIFIC | ✅ Isolado em `zendesk.py` | Categories, sections, articles |
| **Paginação** | CONNECTOR-SPECIFIC | ✅ Cada conector implementa | Cursor (Confluence/Notion), offset (Zendesk), page (GitBook) |
| **Descoberta de páginas** | CONNECTOR-SPECIFIC | ✅ Cada conector implementa | Hierarquias completamente diferentes |
| **Conversão para HTML** | CONNECTOR-SPECIFIC | ✅ Cada conector normaliza | Blocos Notion, content nodes GitBook, etc. |
| **Detecção de visibilidade** | CONNECTOR-SPECIFIC | ✅ Só Confluence | Restrictions API |
| --- | --- | --- | --- |
| **ConfluenceClient** | ⚠️ LEGADO | Deveria ser encapsulado em `confluence.py` | Duplica ApiHttpClient |
| **MarkdownTransformer** | ⚠️ LEGADO | Deveria migrar para KnowledgeDocumentRenderer | Macros Confluence no renderizador genérico |
| **_run_legacy** | ⚠️ LEGADO | Deveria ser eliminado | Caminho Confluence fora do pipeline genérico |
| **page_metadata()** | EXTENSÍVEL POR ESTRATÉGIA | Precisa generalizar | Frontmatter com assunções Confluence |
| --- | --- | --- | --- |
| **normalize_markdown()** | UTILITÁRIO | ✅ Já compartilhado | Normalização de espaços/quebras |
| **sha256_text()** | UTILITÁRIO | ✅ Já compartilhado | Hash para deduplicação |
| **demote_headings()** | UTILITÁRIO | ✅ Já compartilhado | Rebaixamento de headings |
| **sanitize_filename()** | UTILITÁRIO | ✅ Já compartilhado | Normalização de nomes de arquivo |
| --- | --- | --- | --- |
| **source_detection.py** | EXTENSÍVEL POR ESTRATÉGIA | ✅ Funciona (regex por URL) | Adicionar padrão = suportar nova plataforma |
| **connector_forms.py** | EXTENSÍVEL POR ESTRATÉGIA | ✅ Funciona (specs estáticas) | Adicionar spec = novo formulário na UI |
| **tree_models.py** | CORE COMPARTILHADO | ✅ Genérico | Opera sobre KnowledgeContainer/Document |
| **BrowserDiscoveryCache** | CORE COMPARTILHADO | ✅ Genérico | Cache de discovery sem lógica de conector |
| --- | --- | --- | --- |
| **MainWindow** | UI | ⚠️ Acoplada a Confluence | God class com lógica de negócio |
| **Pages (builders)** | UI | ✅ Majoritariamente visuais | Constroem widgets |
| **Components** | UI | ✅ Genéricos | Widgets reutilizáveis |
| **Theme** | UI | ✅ Genérico | Cores e estilos QSS |

---

## 7. Arquitetura Recomendada

### Diagrama da Arquitetura Atual

```text
                    ┌───────────────────────────┐
                    │    MainWindow (God Class)   │
                    │  126.6KB, 132 métodos       │
                    │  ├── Mixins (87KB)          │
                    │  ├── Lógica Confluence ⚠️   │
                    │  ├── Workers / ThreadPool    │
                    │  └── Estado global           │
                    └──────────┬────────────────┘
                               │
                ┌──────────────┼──────────────┐
                │              │              │
        ┌───────▼──────┐  ┌───▼────┐  ┌──────▼──────┐
        │ Extraction   │  │ Consol.│  │  Markdown   │
        │ Service      │  │ Service│  │             │
        │ ┌──────────┐ │  │        │  │ ┌─────────┐ │
        │ │_run_     │ │  │ (genér)│  │ │Transform│ │
        │ │ generic  │ │  │   ✅    │  │ │er (leg.)│ │
        │ ├──────────┤ │  │        │  │ ├─────────┤ │
        │ │_run_     │ │  │        │  │ │Renderer │ │
        │ │ legacy ⚠️│ │  │        │  │ │(genéric)│ │
        │ └──────────┘ │  │        │  │ │   ✅     │ │
        └──────┬───────┘  └────────┘  │ └─────────┘ │
               │                      └─────────────┘
    ┌──────────┼──────────┐
    │          │          │
┌───▼───┐ ┌───▼───┐ ┌────▼────┐
│Conflu.│ │Notion │ │GitBook  │ ... (via ABC)
│  ⚠️   │ │  ✅   │ │  ✅     │
│+client│ │       │ │         │
│.py    │ │       │ │         │
│(legado│ │       │ │         │
│24KB)  │ │       │ │         │
└───────┘ └───────┘ └─────────┘
```

⚠️ = contém código legado ou acoplamento

### Diagrama da Arquitetura Recomendada

```text
                    ┌───────────────────────────┐
                    │           UI              │
                    │  MainWindow (orquestração) │
                    │  Pages (visual)            │
                    │  Mixins (comportamento)    │
                    │  ─ sem lógica de conector ─ │
                    └──────────┬────────────────┘
                               │
                    ┌──────────▼────────────────┐
                    │    Application Layer       │
                    │  ExecutionController       │
                    │  RuntimeBuilder            │
                    │  OperationController       │
                    └──────────┬────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
  ┌───────▼──────┐    ┌───────▼──────┐    ┌────────▼───────┐
  │ Extraction   │    │ Consolid.    │    │  Markdown      │
  │ Service      │    │ Service      │    │  Renderer      │
  │ (um caminho) │    │ (genérico)   │    │ (um renderer)  │
  └──────┬───────┘    └──────────────┘    └────────────────┘
         │
         │  KnowledgeDocument (modelo intermediário)
         │
  ┌──────┼───────────────────────────────────────┐
  │      │           │           │           │    │
┌─▼──┐ ┌─▼───┐ ┌────▼──┐ ┌─────▼───┐ ┌─────▼─┐ │
│Conf│ │Notn │ │GitBk  │ │SharePt  │ │Zendesk│ │
│    │ │     │ │       │ │         │ │       │ │
│(ABC│ │(ABC)│ │(ABC)  │ │(ABC)    │ │(ABC)  │ │
│impl│ │     │ │       │ │         │ │       │ │
└────┘ └─────┘ └───────┘ └─────────┘ └───────┘ │
  │                                              │
  └──────────────────────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │    Shared Core      │
              │  ApiHttpClient      │
              │  CancellationToken  │
              │  RateLimiter        │
              │  FileTransaction    │
              │  ManifestStore      │
              │  SelectionStore     │
              │  ConnectorRegistry  │
              └─────────────────────┘
```

### Princípios da Arquitetura Recomendada

1. **Um único fluxo de extração** — eliminar `_run_legacy`
2. **Um único renderizador Markdown** — `KnowledgeDocumentRenderer` (com extensão para macros via hooks)
3. **Confluence usa o mesmo ABC** que todos os outros conectores
4. **UI não conhece conectores específicos** — consulta `ConnectorCapabilities` e `ConnectorFormSpec`
5. **Macros Confluence** migram para o conector (pré-processamento no `get_document` ou `normalize_document`) ou para um hook no renderizador

---

## 8. Estrutura de Diretórios Proposta

### Estrutura Atual Relevante

```text
alquimista/
├── __init__.py
├── __main__.py
├── auth.py
├── client.py              ← legado, duplica ApiHttpClient
├── confluence_url.py
├── connectors/
│   ├── base.py
│   ├── confluence.py
│   ├── gitbook.py
│   ├── http.py
│   ├── notion.py
│   ├── registry.py
│   ├── sharepoint.py
│   └── zendesk.py
├── browser/
│   ├── adapters.py
│   ├── cache.py
│   ├── contracts.py
│   └── service.py
├── errors.py
├── logging_utils.py
├── manifest_index.py
├── markdown.py
├── models.py
├── reports.py
├── runtime.py
├── selection.py
├── services.py            ← 57KB, dois fluxos
├── session_store.py
├── source_detection.py
├── storage.py
└── ui/
    ├── main_window.py     ← 126.6KB
    ├── components.py
    ├── connector_forms.py
    ├── controllers.py
    ├── execution_controller.py
    ├── operation_controller.py
    ├── state.py
    ├── theme.py
    ├── tree_models.py
    ├── workers.py
    ├── mixins/
    │   ├── connection_mixin.py
    │   ├── selection_mixin.py
    │   ├── source_mixin.py
    │   └── tree_mixin.py
    └── pages/
        ├── dashboard_page.py
        ├── sources_page.py
        ├── connection_page.py
        ├── selection_page.py
        ├── review_page.py
        ├── extraction_page.py
        ├── markdown_page.py
        ├── consolidation_page.py
        └── results_page.py
```

### Estrutura Proposta (evolução incremental)

> **Nota:** Não proponho reorganizar diretórios drasticamente. A estrutura atual é funcional. As mudanças são **internas** (eliminar código legado, generalizar contratos).

```text
alquimista/
├── __init__.py
├── __main__.py
├── auth.py
├── confluence_url.py
├── connectors/
│   ├── base.py            # ABC (sem mudança)
│   ├── confluence.py      # Absorve client.py; usa ApiHttpClient
│   ├── gitbook.py         # Sem mudança
│   ├── http.py            # Sem mudança
│   ├── notion.py          # Sem mudança
│   ├── registry.py        # Sem mudança
│   ├── sharepoint.py      # Sem mudança
│   └── zendesk.py         # Sem mudança
├── browser/               # Sem mudança — já bem desacoplado
│   ├── adapters.py
│   ├── cache.py
│   ├── contracts.py
│   └── service.py
├── errors.py              # Remove erros legados
├── logging_utils.py
├── manifest_index.py
├── markdown.py            # Remove MarkdownTransformer; mantém KnowledgeDocumentRenderer
├── models.py              # Generaliza ManifestEntry defaults
├── reports.py
├── runtime.py
├── selection.py
├── services.py            # Remove _run_legacy; um só fluxo
├── session_store.py
├── source_detection.py
├── storage.py
└── ui/                    # Remove referências diretas a client.py e ConfluenceClient
    ├── ...                # Elimina whitelists de source_type
    └── ...

tests/
├── conftest.py
├── fixtures/              # NOVO — fixtures compartilhadas
│   ├── confluence/
│   │   ├── input_html/    # HTML de entrada conhecidas
│   │   └── expected_md/   # Markdown esperado (golden samples)
│   ├── gitbook/
│   ├── notion/
│   └── zendesk/
├── test_connectors.py
├── test_golden_samples.py # NOVO — testes de snapshot por conector
├── test_markdown.py       # EXPANDIR significativamente
├── test_services.py
└── ...
```

**Responsabilidade dos diretórios:**

| Diretório | Responsabilidade |
|---|---|
| `connectors/` | Implementações de conector por plataforma + ABC + HTTP + Registry |
| `browser/` | Discovery lazy via Playwright, cache SQLite, adaptadores |
| `ui/` | Interface PySide6: MainWindow, pages, mixins, controllers, widgets |
| `ui/pages/` | Builders visuais de cada tela |
| `ui/mixins/` | Comportamentos da MainWindow separados por responsabilidade |
| `tests/fixtures/` | Golden samples por conector (HTML entrada → Markdown esperado) |
| raiz `alquimista/` | Core: modelos, serviços, markdown, storage, runtime, erros |

---

## 9. Contratos/Interfaces Recomendados

### 9.1 — O ABC Atual é Suficiente

**RECOMENDAÇÃO:** O contrato `KnowledgeSourceConnector` em [`base.py`](file:///c:/Dev/Alquimista%20studio%203.0/alquimista/connectors/base.py) **não precisa de mudanças estruturais**. Ele já define:

```python
class KnowledgeSourceConnector(ABC):
    def get_source_type(self) -> str: ...
    def get_source(self) -> KnowledgeSource: ...
    def get_capabilities(self) -> ConnectorCapabilities: ...
    def validate_connection(self) -> str: ...
    def list_containers(self) -> list[KnowledgeContainer]: ...
    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]: ...
    def get_document(self, document: KnowledgeDocumentMetadata) -> KnowledgeDocument: ...
    
    # Opcionais (com defaults):
    def list_root_documents(self, container_id, cursor=None): ...
    def list_document_children(self, document, cursor=None): ...
    def search_documents(self, query): ...
    def normalize_document(self, raw): ...
    def close(self): ...
```

O uso de `ConnectorCapabilities` para indicar lazy loading, search e root_documents é **correto e elegante** — evita que conectores simples precisem implementar métodos complexos.

### 9.2 — Hook para Pré-processamento de HTML (sugestão incremental)

Para lidar com macros Confluence sem poluir o renderizador genérico:

```python
class KnowledgeSourceConnector(ABC):
    # ... métodos existentes ...
    
    def preprocess_html(self, html: str, document: KnowledgeDocumentMetadata) -> str:
        """Pré-processa o HTML antes da conversão para Markdown.
        
        Override para tratar elementos específicos da plataforma
        (macros Confluence, blocos especiais, etc.).
        Default: retorna o HTML sem alteração.
        """
        return html
```

O `ConfluenceRestConnector` sobrescreveria para tratar macros `ac:*`, `ri:*`. O `KnowledgeDocumentRenderer` chamaria `connector.preprocess_html()` antes de `markdownify`.

**HIPÓTESE:** Isso pode ser excessivo agora. Se o `get_document()` do Confluence já retornar HTML limpo (com macros convertidas), o hook não é necessário. Avaliar durante a migração.

### 9.3 — Utilitário compartilhado para HTML → Markdown

**FATO:** Confluence e Zendesk usam `BeautifulSoup` + `markdownify` com o mesmo padrão (remover scripts/styles → converter). Extrair:

```python
# Em markdown.py ou em um novo utils_html.py

def html_to_markdown(
    html: str,
    *,
    strip_tags: list[str] | None = None,
    base_url: str | None = None,
) -> str:
    """Converte HTML limpo para Markdown.
    
    Remove scripts/styles, aplica markdownify.
    Usado por conectores que recebem HTML das APIs.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(strip_tags or ["script", "style"]):
        tag.decompose()
    return markdownify.markdownify(str(soup), ...)
```

**Classificação:** UTILITÁRIO — reutilizável mas sem obrigar uso.

---

## 10. Estratégia Contra Regressões

### 10.1 — Golden Samples (Prioridade Máxima)

**O que fazer:** Antes de qualquer refatoração, capturar o output atual do Confluence como baseline.

```text
tests/
  fixtures/
    confluence/
      input/
        page_simple.html           # HTML de uma página real (anonimizada)
        page_with_macros.html      # Página com macros ac:code, ac:info
        page_with_tables.html      # Tabelas complexas
        page_with_attachments.html # Anexos e imagens
        page_with_children.html    # Página com hierarquia
      expected/
        page_simple.md             # Markdown esperado EXATO
        page_with_macros.md
        page_with_tables.md
        page_with_attachments.md
        page_with_children.md
```

**Como testar:**

```python
# tests/test_golden_samples.py

import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.mark.parametrize("case", [
    "page_simple",
    "page_with_macros",
    "page_with_tables",
    "page_with_attachments",
])
def test_confluence_markdown_golden(case: str):
    input_html = (FIXTURES / "confluence/input" / f"{case}.html").read_text("utf-8")
    expected_md = (FIXTURES / "confluence/expected" / f"{case}.md").read_text("utf-8")
    
    # Construir KnowledgeDocument com o HTML
    doc = KnowledgeDocument(
        source_type="confluence_rest",
        content=input_html,
        title=f"Test {case}",
        # ... campos mínimos
    )
    
    renderer = KnowledgeDocumentRenderer()
    result = renderer.render(doc, MarkdownOptions())
    
    # Normalizar variações (timestamps, etc.)
    assert normalize_for_comparison(result) == normalize_for_comparison(expected_md)
```

**Normalização para comparação:**
```python
def normalize_for_comparison(md: str) -> str:
    """Remove variações entre execuções."""
    import re
    # Normalizar timestamps
    md = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", "TIMESTAMP", md)
    # Normalizar espaços em branco no final
    md = "\n".join(line.rstrip() for line in md.splitlines())
    # Normalizar múltiplas linhas em branco
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()
```

### 10.2 — Testes por Conector (Isolados)

Os testes em [`test_connectors.py`](file:///c:/Dev/Alquimista%20studio%203.0/tests/test_connectors.py) já testam conectores isoladamente usando mocks de HTTP — isso é bom. **Expandir para incluir:**

1. **Golden samples de `get_document()`** — verificar que o `KnowledgeDocument` retornado tem a estrutura correta
2. **Testes de paginação** — já existem para Confluence; criar para outros
3. **Testes de falha** — verificar que erros são do tipo correto (`ApiRateLimitError`, não genérico)

### 10.3 — Testes de Contrato (Contract Tests)

Verificar que todo conector respeita o contrato do ABC:

```python
@pytest.mark.parametrize("connector_cls", [
    ConfluenceRestConnector,
    GitBookConnector,
    NotionConnector,
    SharePointConnector,
    ZendeskGuideConnector,
])
def test_connector_contract(connector_cls):
    """Verifica que o conector implementa o contrato mínimo."""
    assert hasattr(connector_cls, 'get_source_type')
    assert hasattr(connector_cls, 'list_containers')
    assert hasattr(connector_cls, 'get_document')
    # etc.
```

### 10.4 — Testes End-to-End do Pipeline por Conector

```python
def test_extraction_pipeline_confluence(tmp_path, fake_confluence_connector):
    """Pipeline completo: conector → extração → arquivo Markdown."""
    service = ExtractionService()
    runtime = SourceRuntime(connector=fake_confluence_connector, ...)
    result = service.run(runtime)
    
    # Verificar que arquivo foi criado
    md_files = list(tmp_path.glob("**/*.md"))
    assert len(md_files) > 0
    
    # Verificar conteúdo
    content = md_files[0].read_text("utf-8")
    assert "# " in content  # Tem heading
```

### 10.5 — CI: Rodar Testes de Todos os Conectores em Cada PR

```yaml
# .github/workflows/test.yml
- name: Run connector tests
  run: pytest tests/ -k "connector" --tb=short
  
- name: Run golden samples
  run: pytest tests/test_golden_samples.py --tb=long
  
- name: Run regression tests
  run: pytest tests/ -k "regression or fixes" --tb=long
```

---

## 11. Estratégia para Generic Web

### Conceito

O `GenericWebConnector` seria um conector como qualquer outro, implementando `KnowledgeSourceConnector`:

```python
class GenericWebConnector(KnowledgeSourceConnector):
    """Conector para websites arbitrários."""
    
    SOURCE_TYPE = "generic_web"
    
    def __init__(self, base_url: str, ...):
        self.base_url = base_url
        self.crawler = WebCrawler(base_url)
    
    def get_source_type(self) -> str:
        return self.SOURCE_TYPE
    
    def list_containers(self) -> list[KnowledgeContainer]:
        """Um 'contêiner' = o site inteiro ou seção."""
        return [KnowledgeContainer(
            container_id=self.base_url,
            name=self.base_url,
            ...
        )]
    
    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        """Descobre páginas via crawling/sitemap."""
        return self.crawler.discover_pages()
    
    def get_document(self, document: KnowledgeDocumentMetadata) -> KnowledgeDocument:
        """Busca e limpa o HTML da página."""
        html = self.crawler.fetch(document.url)
        clean_html = self._extract_content(html)  # Remove nav, footer, ads
        return KnowledgeDocument(
            content=clean_html,
            ...
        )
```

### Integração na Arquitetura

```text
GenericWebConnector
       │
       ├── WebCrawler
       │     ├── SitemapParser
       │     ├── LinkExtractor
       │     └── RobotsParser
       │
       ├── ContentExtractor
       │     ├── ReadabilityAlgorithm (ou similar)
       │     └── Heurísticas de limpeza
       │
       └── Implementa KnowledgeSourceConnector
                    │
                    ↓
            Pipeline genérico existente
            (ExtractionService → KnowledgeDocumentRenderer → ConsolidationService)
```

### Desafios Específicos

| Desafio | Solução | Onde implementar |
|---|---|---|
| SPAs (JavaScript rendering) | Playwright (já existe no subsistema browser) | `browser/service.py` → `GenericWebConnector` |
| Descoberta de páginas | Sitemap.xml + link crawling + URL patterns | `GenericWebConnector.list_documents()` |
| Conteúdo irrelevante (nav, footer) | Extração com readability/heurísticas | `GenericWebConnector._extract_content()` |
| Rate limits / robots.txt | `RateLimiter` (já existe) + parse de robots.txt | Compartilhado + conector |
| Autenticação | Bearer/Basic (já suportados) ou browser login | `auth.py` (já suporta) |
| Canonical URLs / dedup | Normalização de URL + sha256 | Conector |
| Profundidade de crawling | Configurável via `connector_options` | `SourceConfig` |

### O que muda na arquitetura existente

**Nada significativo.** O `GenericWebConnector` é apenas mais um conector. Precisa:

1. Registrar em `registry.py` ✅
2. Adicionar spec em `connector_forms.py` ✅
3. Adicionar padrão em `source_detection.py` (qualquer URL que não match nenhuma plataforma conhecida)
4. Criar o crawler/extractor (código novo, isolado)

**A arquitetura genérica atual já suporta isso — desde que o caminho legado seja eliminado.**

---

## 12. Plano Incremental de Refatoração

### Etapa 0 — Baseline e Proteção (ANTES de qualquer mudança)

| Item | Detalhe |
|---|---|
| **Objetivo** | Criar rede de segurança para proteger o Confluence |
| **Arquivos afetados** | `tests/` (novos arquivos) |
| **Mudança proposta** | Criar golden samples do Confluence: capturar HTML real → processar → salvar Markdown esperado |
| **Risco** | NENHUM (apenas adiciona testes) |
| **Benefício** | Detectar qualquer regressão no output do Confluence |
| **Pré-requisitos** | Acesso a pelo menos 5-10 páginas Confluence reais |
| **Como validar** | `pytest tests/test_golden_samples.py` — todos passam |

---

### Etapa 1 — Eliminar Funções Duplicadas

| Item | Detalhe |
|---|---|
| **Objetivo** | Remover código morto nos mixins |
| **Arquivos afetados** | `selection_mixin.py` (7 funções), `connection_mixin.py` (3), `auth.py` (1), `execution_controller.py` (1) |
| **Mudança proposta** | Remover a primeira definição (morta) de cada função duplicada |
| **Risco** | BAIXO — as primeiras definições são sobrepostas pelas segundas |
| **Benefício** | Reduz ~10-15KB de código morto; elimina confusão |
| **Pré-requisitos** | Verificar com `rg` que nenhum caller usa a primeira definição |
| **Como validar** | `pytest tests/` — todos os testes passam sem mudança de comportamento |

---

### Etapa 2 — Migrar Macros Confluence para o Conector

| Item | Detalhe |
|---|---|
| **Objetivo** | Mover tratamento de macros `ac:*`, `ri:*` de `MarkdownTransformer` para `ConfluenceRestConnector.get_document()` |
| **Arquivos afetados** | `connectors/confluence.py`, `markdown.py` |
| **Mudança proposta** | O `get_document()` do Confluence faz pré-processamento do HTML (substituição de macros) antes de retornar o `KnowledgeDocument`. O HTML retornado já é "limpo" |
| **Risco** | MÉDIO — requer golden samples para validar que o output não muda |
| **Benefício** | Desacopla macros Confluence do renderizador compartilhado |
| **Pré-requisitos** | Etapa 0 completa (golden samples) |
| **Como validar** | Golden samples do Confluence continuam passando |

---

### Etapa 3 — Migrar Confluence para `_run_generic`

| Item | Detalhe |
|---|---|
| **Objetivo** | Eliminar `_run_legacy` em `services.py` |
| **Arquivos afetados** | `services.py`, `execution_controller.py`, `controllers.py` |
| **Mudança proposta** | Confluence usa o mesmo `_run_generic` que os outros conectores. `ConfluenceRestConnector.get_document()` retorna `KnowledgeDocument` com HTML limpo (macros já processadas). `KnowledgeDocumentRenderer` gera o Markdown |
| **Risco** | ALTO — a maior mudança. Pode alterar output do Confluence |
| **Benefício** | Elimina ~200 linhas de código legado; um único fluxo de extração |
| **Pré-requisitos** | Etapa 0 + Etapa 2 completas |
| **Como validar** | Golden samples do Confluence passam; testes de regressão passam; teste manual com Confluence real |

---

### Etapa 4 — Absorver `client.py` no Conector

| Item | Detalhe |
|---|---|
| **Objetivo** | Eliminar `client.py` como módulo separado |
| **Arquivos afetados** | `client.py` (REMOVER), `connectors/confluence.py` |
| **Mudança proposta** | Migrar `ConfluenceClient` para usar `ApiHttpClient` internamente, ou integrar suas funcionalidades diretamente no conector |
| **Risco** | MÉDIO — o client.py tem retry/rate limit próprios |
| **Benefício** | Elimina 24KB de duplicação HTTP; comportamento HTTP uniforme |
| **Pré-requisitos** | Etapa 3 completa; Confluence usando caminho genérico |
| **Como validar** | Testes de integração com Confluence real |

---

### Etapa 5 — Desacoplar UI de Conectores Específicos

| Item | Detalhe |
|---|---|
| **Objetivo** | Eliminar referências a `confluence_rest` na UI |
| **Arquivos afetados** | `main_window.py`, `source_mixin.py`, `connection_mixin.py`, `execution_controller.py` |
| **Mudança proposta** | Substituir whitelists de `source_type` por consultas a `ConnectorCapabilities`. Substituir `_lookup_page_details` (que usa ConfluenceClient) por um método genérico via conector. Renomear `enter_confluence` para algo genérico |
| **Risco** | MÉDIO — a UI é grande e com muitas dependências internas |
| **Benefício** | Adicionar novo conector não exige modificar a UI |
| **Pré-requisitos** | Etapas 3-4 completas |
| **Como validar** | `pytest tests/test_ui*.py` passam; teste manual de todas as telas |

---

### Etapa 6 — Limpar Erros e Manifest

| Item | Detalhe |
|---|---|
| **Objetivo** | Remover erros legados; generalizar ManifestEntry |
| **Arquivos afetados** | `errors.py`, `models.py`, `storage.py` |
| **Mudança proposta** | Remover `ConfluenceConnectionError`, `RateLimitError` (legados). Generalizar defaults de `ManifestEntry` |
| **Risco** | BAIXO — desde que callers sejam atualizados |
| **Benefício** | Hierarquia de erros limpa; persistência genérica |
| **Pré-requisitos** | Etapas 3-5 completas (sem callers do legado) |
| **Como validar** | Grep por erros removidos — zero referências. Testes passam |

---

### Etapa 7 — Preparar Generic Web (futura)

| Item | Detalhe |
|---|---|
| **Objetivo** | Criar `GenericWebConnector` |
| **Arquivos afetados** | `connectors/web.py` (NOVO), `registry.py`, `connector_forms.py`, `source_detection.py` |
| **Mudança proposta** | Novo conector que implementa o ABC. Inclui crawler, sitemap parser, content extractor |
| **Risco** | BAIXO — código novo, não altera existente |
| **Benefício** | Suporta URLs arbitrárias |
| **Pré-requisitos** | Etapas 0-5 completas (arquitetura genérica estável) |
| **Como validar** | Testes unitários do novo conector; golden samples |

---

## 13. Tabela de Prioridades

| Prioridade | Mudança | Benefício | Risco | Esforço |
|---|---|---|---|---|
| **P0** | Golden samples do Confluence (Etapa 0) | **ALTO** — base para tudo | **BAIXO** — só adiciona testes | **BAIXO** — 1-2 dias |
| **P0** | Expandir test_markdown.py | **ALTO** — componente subtestado | **BAIXO** — só adiciona testes | **BAIXO** — 1 dia |
| **P1** | Eliminar funções duplicadas (Etapa 1) | **MÉDIO** — limpeza | **BAIXO** — código morto | **BAIXO** — algumas horas |
| **P1** | Migrar macros para conector (Etapa 2) | **ALTO** — desacopla Markdown | **MÉDIO** — muda fluxo | **MÉDIO** — 2-3 dias |
| **P1** | Migrar Confluence para genérico (Etapa 3) | **ALTO** — elimina bifurcação | **ALTO** — maior mudança | **ALTO** — 3-5 dias |
| **P2** | Absorver client.py (Etapa 4) | **MÉDIO** — elimina duplicação HTTP | **MÉDIO** — client é complexo | **ALTO** — 3-5 dias |
| **P2** | Desacoplar UI (Etapa 5) | **ALTO** — novos conectores sem tocar UI | **MÉDIO** — UI grande | **MÉDIO** — 2-3 dias |
| **P2** | Limpar erros e manifest (Etapa 6) | **MÉDIO** — limpeza | **BAIXO** — após migração | **BAIXO** — 1 dia |
| **P3** | Generic Web (Etapa 7) | **ALTO** — nova funcionalidade | **BAIXO** — código novo | **ALTO** — 5-10 dias |

---

## 14. O que NÃO Modificar Agora

| Componente | Por que preservar |
|---|---|
| **`connectors/base.py` (ABC)** | O contrato atual é adequado. Mudá-lo agora quebraria todos os conectores. Evoluir somente se surgir necessidade concreta |
| **`storage.py` (FileTransaction)** | Funciona perfeitamente. Escrita atômica é robusta. Não mexer |
| **`runtime.py`** | CancellationToken e RateLimiter são simples e corretos. Não precisa de abstração adicional |
| **`selection.py` (SelectionStore)** | Funciona bem, independente de Qt. Preservar |
| **`browser/` (subsistema inteiro)** | Bem desacoplado, com contratos claros, cache SQLite adequado. Não alterar |
| **`connectors/gitbook.py`, `notion.py`, `sharepoint.py`, `zendesk.py`** | Conectores que funcionam no caminho genérico. Não refatorar sem necessidade |
| **`tree_models.py`** | Genérico e limpo. Não precisa de mudança |
| **`reports.py`** | Estrutura simples e funcional |
| **`session_store.py`** | Criptografia DPAPI funciona bem no Windows |
| **`components.py`** | Widgets são reutilizáveis e genéricos |
| **`theme.py`** | Puramente visual, sem acoplamento |
| **Estrutura de diretórios** | Reorganizar pastas sem motivo funcional gera churn e conflitos. A estrutura atual é clara o suficiente |

---

## 15. Teste de Extensibilidade

### Cenário A — Adicionar Google Drive

**Com a arquitetura recomendada (pós-migração):**

| Ação | Arquivo | Tipo |
|---|---|---|
| Criar conector | `connectors/google_drive.py` | NOVO |
| Registrar | `connectors/registry.py` | +2 linhas |
| Form spec | `ui/connector_forms.py` | +10 linhas |
| Detecção URL | `source_detection.py` | +5 linhas |
| Testes | `tests/test_connectors.py` | +50 linhas |
| Golden samples | `tests/fixtures/google_drive/` | NOVO |

**Nenhum outro arquivo precisa ser modificado.** Nenhum conector existente é afetado.

### Cenário B — Adicionar Generic Website

| Ação | Arquivo | Tipo |
|---|---|---|
| Criar conector + crawler | `connectors/web.py` | NOVO |
| Registrar | `connectors/registry.py` | +2 linhas |
| Form spec | `ui/connector_forms.py` | +10 linhas |
| Detecção URL | `source_detection.py` | +3 linhas (fallback para qualquer URL) |
| Testes | `tests/test_connectors.py` ou novo arquivo | NOVO |

**Nenhum conector existente é afetado.**

### Cenário C — Notion exige paginação completamente diferente

**Análise:** A paginação é 100% interna ao conector. `NotionConnector.list_documents()` e `get_document()` implementam a paginação via cursores da API Notion. Mudar a paginação:

- **Altera:** `connectors/notion.py` apenas
- **Não afeta:** Confluence, GitBook, SharePoint, Zendesk, pipeline, UI
- **Verificação:** `pytest tests/test_connectors.py -k notion`

### Cenário D — Mudança na geração de Markdown

**Com a arquitetura recomendada:**

- **Altera:** `markdown.py` (`KnowledgeDocumentRenderer`)
- **Afeta:** Todos os conectores — output Markdown muda para todos
- **Proteção:** Golden samples de cada conector detectam a mudança
- **Verificação:** `pytest tests/test_golden_samples.py` — falhas indicam exatamente quais conectores são afetados e como

**Sem golden samples (estado atual):** Mudança em `markdown.py` afeta todos os conectores **silenciosamente**. Regressões são detectadas apenas por testes manuais.

---

## 16. Avaliação Arquitetural

### Notas Atuais

| Área | Nota | Justificativa |
|---|---|---|
| Modularidade | **6/10** | Boa separação em arquivos/pacotes; porém dois caminhos coexistentes (legacy vs generic) quebram a modularidade real |
| Separação de responsabilidades | **5/10** | Conectores bem separados; porém `services.py` e `markdown.py` misturam genérico com Confluence-specific. MainWindow é God Class |
| Extensibilidade | **7/10** | ABC + Registry + ConnectorCapabilities são excelentes. Mas a UI tem whitelists que bloqueiam novos conectores |
| Testabilidade | **6/10** | Conectores são testáveis isoladamente (bons mocks). Mas `MarkdownTransformer` e `_run_legacy` são difíceis de testar sem Confluence real |
| Proteção contra regressões | **4/10** | Bons testes de regressão pontuais (test_fixes_regression), mas sem golden samples. Mudança em markdown.py é cega |
| Acoplamento | **5/10** | Conectores desacoplados entre si ✅. Mas `services.py` acoplado a `client.py`; UI acoplada a Confluence |
| Coesão | **6/10** | Boa coesão dentro de conectores individuais. `services.py` e `markdown.py` têm coesão reduzida (dois propósitos) |
| Observabilidade | **6/10** | Logging JSON com redação de segredos é bom. Mas falta identificação de conector/etapa nos logs de extração |
| Manutenibilidade | **5/10** | Funções duplicadas nos mixins; MainWindow de 126KB; dois caminhos de extração |
| Preparação para novos conectores | **6/10** | Infraestrutura genérica existe mas não é o caminho default para Confluence |

### Notas Projetadas (após Etapas 0-6)

| Área | Atual | Projetada | Δ |
|---|---|---|---|
| Modularidade | 6 | **8** | +2 |
| Separação de responsabilidades | 5 | **8** | +3 |
| Extensibilidade | 7 | **9** | +2 |
| Testabilidade | 6 | **8** | +2 |
| Proteção contra regressões | 4 | **8** | +4 |
| Acoplamento | 5 | **8** | +3 |
| Coesão | 6 | **8** | +2 |
| Observabilidade | 6 | **7** | +1 |
| Manutenibilidade | 5 | **8** | +3 |
| Preparação para novos conectores | 6 | **9** | +3 |

---

## 17. Top 10 Próximas Ações (em ordem de execução)

| # | Ação | Prioridade | Esforço | Benefício |
|---|---|---|---|---|
| **1** | **Criar golden samples do Confluence** — capturar 5-10 páginas HTML reais e o Markdown esperado. Criar `tests/test_golden_samples.py` | P0 | 1-2 dias | Base de proteção para toda refatoração |
| **2** | **Expandir test_markdown.py** — testar `MarkdownTransformer` e `KnowledgeDocumentRenderer` com casos de uso reais | P0 | 1 dia | Componente mais propenso a regressão está subtestado |
| **3** | **Eliminar funções duplicadas** — remover as 12 definições mortas em `selection_mixin.py`, `connection_mixin.py`, `auth.py`, `execution_controller.py` | P1 | 2-3h | Limpeza que reduz confusão e tamanho de código |
| **4** | **Migrar tratamento de macros Confluence para o conector** — `ConfluenceRestConnector.get_document()` retorna HTML com macros já processadas (não mais no renderizador genérico) | P1 | 2-3 dias | Desacopla o renderizador Markdown de Confluence |
| **5** | **Migrar Confluence para `_run_generic`** — após macros migradas, Confluence usa o mesmo pipeline que todos. Eliminar `_run_legacy` | P1 | 3-5 dias | Elimina a bifurcação mais perigosa do projeto |
| **6** | **Eliminar whitelists de `source_type` na UI** — substituir por consultas a `ConnectorCapabilities`. Remover importação de `ConfluenceClient` na UI | P2 | 2-3 dias | Novos conectores não exigem mudanças na UI |
| **7** | **Generalizar ManifestEntry** — remover defaults `confluence_rest`, `space_key`. Tornar campos genéricos | P2 | 1 dia | Persistência agnóstica de plataforma |
| **8** | **Limpar hierarquia de erros** — remover `ConfluenceConnectionError` e `RateLimitError` legados | P2 | 0.5 dia | Tratamento de erros consistente |
| **9** | **Migrar `ConfluenceClient` para usar `ApiHttpClient`** — ou absorver no conector | P2 | 3-5 dias | Elimina duplicação HTTP de 24KB |
| **10** | **Criar testes de contrato** — verificar que todo conector registrado implementa o ABC corretamente | P2 | 0.5 dia | Protege o contrato de regressão |

---

## 18. Respostas às Perguntas Críticas

| # | Pergunta | Resposta |
|---|---|---|
| 1 | A arquitetura atual escala para 5-20 conectores? | **Sim, com ressalvas.** O ABC + Registry + genérico escalam. Mas o caminho legado e as whitelists na UI limitam. Após migração: sim, escala bem |
| 2 | Onde estão os maiores acoplamentos? | `services.py` (dois fluxos), `main_window.py` (referências Confluence), `markdown.py` (dois renderizadores), `client.py` (duplica HTTP) |
| 3 | Quais partes compartilhadas? | KnowledgeDocument, KnowledgeDocumentRenderer, ExtractionService, ConsolidationService, ApiHttpClient, SelectionStore, FileTransaction |
| 4 | Quais partes isoladas por conector? | API client, paginação, discovery, normalização HTML, autenticação especial |
| 5 | Paginação deve ser específica? | **Sim.** Cada API pagina de forma diferente (cursor, offset, URL). Já está correto |
| 6 | Descoberta deve ser específica? | **Sim.** Hierarquias são completamente diferentes (spaces vs databases vs categories). Já está correto |
| 7 | Parsing deve ser específico? | **Sim.** Formato de dados é único por plataforma. Já está correto |
| 8 | Markdown deve ser compartilhado? | **Sim.** `KnowledgeDocumentRenderer` já é genérico e correto. `MarkdownTransformer` (Confluence-specific) deve ser eliminado |
| 9 | Consolidação deve ser compartilhada? | **Sim.** Opera sobre manifest, não sobre conectores. Já está correto |
| 10 | Preciso de modelo intermediário? | **Já existe!** `KnowledgeDocument` é o modelo intermediário. Está bem definido |
| 11 | Preciso de interface para conectores? | **Já existe!** `KnowledgeSourceConnector` (ABC). Está bem definido |
| 12 | Como impedir regressões? | **Golden samples + testes por conector + contract tests.** A maior lacuna hoje |
| 13 | Como testar isoladamente? | **Mocks de HTTP (já feito) + golden samples (a fazer).** A base está boa |
| 14 | Como permitir novos conectores sem alterar Core? | **Migrar Confluence para genérico + eliminar whitelists na UI.** Após isso, novo conector = novo arquivo + 3 linhas de registro |
| 15 | Como preparar para Generic Web? | **GenericWebConnector implementa o mesmo ABC.** Usa browser/ para SPA. A arquitetura suporta, desde que o legado seja eliminado |
| 16 | Como reduzir responsabilidades da UI? | **Eliminar referências a conectores específicos.** Usar ConnectorCapabilities para decisões |
| 17 | Qual refatoração oferece maior benefício com menor risco? | **Golden samples (Etapa 0).** Zero risco, máxima proteção |
| 18 | O que alterar agora? | **Golden samples → eliminar duplicações → migrar macros** |
| 19 | O que deixar para depois? | **Absorção de client.py, Generic Web, reorganização de diretórios** |
| 20 | O que não alterar? | **storage.py, runtime.py, selection.py, browser/, tree_models.py, connectors não-Confluence** |

---

## 19. Pergunta sobre Paginadores e Leitores por Plataforma

> **Devo separar leitores/paginadores por plataforma?**

**Resposta baseada no código:** Já estão separados. Cada conector implementa sua própria paginação em `list_documents()`, `list_root_documents()` e `list_document_children()`. Não existe um `page_reader.py` compartilhado.

O que **não está separado** é o tratamento de macros HTML (Confluence-specific no renderizador genérico) e o fluxo de extração (dois caminhos). Esses são os pontos a resolver.

A organização proposta no prompt (cada conector com `connector.py`, `page_discovery.py`, `page_reader.py`) é **desnecessária** porque:

1. Cada conector já é um único arquivo (~400-600 linhas) que encapsula tudo
2. A separação em múltiplos arquivos por conector criaria overhead de navegação
3. O ABC já define os pontos de extensão corretos

**RECOMENDAÇÃO:** Manter a estrutura atual de um arquivo por conector. Se um conector crescer demais (ex.: Confluence com 600+ linhas), considerar extrair helpers internos, mas não forçar uma subpasta até haver necessidade real.

---

## 20. Sobre Abstrações Prematuras

As seguintes abstrações **NÃO são recomendadas agora:**

| Abstração | Por que não |
|---|---|
| `ProcessingContext` / `JobContext` genérico | `SourceRuntime` já cumpre esse papel. Criar outro wrapper adicionaria indireção sem benefício |
| Interface para estratégias de paginação (`PaginationStrategy`) | Cada API pagina de forma completamente diferente. Abstrair geraria uma interface com leak de abstração |
| Plugin architecture com load dinâmico | Para 5-10 conectores, registro estático em `registry.py` é perfeitamente adequado |
| Event bus / message broker entre UI e pipeline | QThreadPool + WorkerSignals já funciona. Event bus adicionaria complexidade sem resolver problema real |
| Dependency injection framework | O projeto é pequeno o suficiente para injeção manual via construtores |
| Middleware / interceptor chain no pipeline | O pipeline é linear (extrair → renderizar → gravar). Chain pattern adicionaria complexidade |

---

## Resposta Final

> **Se eu fosse o responsável técnico pelo Projeto Alquimista hoje, a primeira mudança arquitetural que faria antes de desenvolver qualquer nova integração seria criar golden samples do output Markdown do Confluence para proteger o comportamento atual contra regressões, e em seguida migrar o Confluence para o pipeline genérico (`_run_generic`), eliminando a bifurcação `_run_legacy` / `_run_generic` que é a maior fonte de acoplamento e risco do projeto.**
