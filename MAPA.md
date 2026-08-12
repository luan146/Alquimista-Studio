# MAPA DO CÓDIGO — ALQuimista Studio 3.0

Guia de referência rápida para direcionar a IA ao arquivo certo quando um problema
ocorrer em uma tela específica do programa. Use junto com o prompt:
"Problema na <tela>: <sintoma>. Comece investigando <arquivo> e confirme o fluxo antes de alterar."

## COMO USAR ESTE MAPA

Este mapa indica **onde começar a investigação** diante de um sintoma ou solicitação — não é fonte absoluta da verdade. A estrutura do código muda; confirme sempre os fluxos lendo os arquivos antes de alterar. Use o mapa como ponto de partida, não como substituto de inspeção.

**Fluxo recomendado:**
1. Localize a tela ou componente no mapa (ou use a tabela abaixo).
2. Abra o arquivo indicado e confirme que os símbolos citados ainda existem.
3. Verifique dependências e raio de impacto listados na seção do componente.
4. Faça a alteração seguindo o checklist de validação, quando houver.
5. Rode os testes diretamente relacionados listados em `tests/`.

### Quero mudar X → onde investigar

| Quero mudar… | Comece investigando… | Confirme também… |
|---|---|---|
| Adicionar/editar uma fonte | `ui/mixins/source_mixin.py` + `source_detection.py` | `models.py:SourceConfig`, `storage.py` |
| Autenticação de uma fonte | `ui/mixins/connection_mixin.py` + `auth.py` | `connectors/<plataforma>.py`, `controllers.py:RuntimeSecrets` |
| Comportamento da árvore de seleção | `ui/mixins/selection_mixin.py` + `tree_mixin.py` | `tree_models.py`, conector `list_document_children` |
| Conversão HTML→Markdown | `markdown.py:MarkdownTransformer` | `models.py:MarkdownOptions` |
| Extração de páginas | `services.py:ExtractionService` | conector `get_document`, `process_workers.py` |
| Consolidação de saída | `services.py:ConsolidationService` | `storage.py`, `markdown.py:demote_headings` |
| Atualização incremental | `services.py` (SHA-256) + `manifest_index.py` | `models.py:SCHEMA_VERSION` |
| Adicionar novo conector | `connectors/base.py` (ABC) + conector existente como referência | `registry.py`, `connector_forms.py`, `source_detection.py` |
| Cancelamento de operação | `runtime.py:CancellationToken` | chamador do token (worker/mixin) |
| Tema/visual de uma tela | `ui/pages/<tela>.py` + `components.py` | `theme.py`, mixin correspondente |
| Relatório de execução | `reports.py` | `services.py` (gera `ExecutionReport`) |

---

## VISÃO GERAL DA ARQUITETURA

```
alquimista/                  # Núcleo (sem UI)
├── models.py                # Contrato de dados central
├── client.py                # Cliente REST legado (Confluence)
├── services.py              # Motor de domínio (extração/consolidação)
├── storage.py               # Persistência atômica
├── markdown.py              # Conversão HTML→Markdown
├── auth.py                  # Autenticação (browser/basic/bearer)
├── selection.py             # Estado de seleção do usuário
├── runtime.py               # Cancelamento cooperativo (threads)
├── errors.py                # Hierarquia de erros tipados
├── reports.py               # Relatórios de execução
├── logging_utils.py          # Logs JSON com redação de segredos
├── manifest_index.py        # Indexação p/ atualização incremental
├── session_store.py         # Persistência local criptografada (DPAPI) de sessão de browser
├── source_detection.py      # Detecta plataforma pela URL
├── confluence_url.py        # Parse de URLs do Confluence
├── connectors/              # Conectores por plataforma
│   ├── base.py              # Contrato ABC comum
│   ├── confluence.py        # Conector de referência
│   ├── gitbook.py
│   ├── notion.py
│   ├── sharepoint.py
│   ├── zendesk.py
│   ├── http.py              # HTTP compartilhado
│   └── registry.py          # Catálogo/instanciação
└── browser/                 # Navegador embutido (Playwright)
    ├── contracts.py         # Tipos de discovery
    ├── service.py           # Orquestração
    ├── adapters.py          # Adaptação Playwright
    └── cache.py             # Cache SQLite de metadados/discovery (sem credenciais nem conteúdo)

alquimista/ui/               # Interface (PySide6)
├── main_window.py           # MainWindow (orquestra tudo)
├── components.py            # Widgets reutilizáveis
├── theme.py                 # Estilos QSS
├── tree_models.py           # Dados→estrutura de árvore
├── controllers.py           # RuntimeBuilder + RuntimeSecrets
├── execution_controller.py  # Prepara runtimes de extração
├── operation_controller.py  # Dispatcher de workers (QThreadPool)
├── process_workers.py       # Workers de processos pesados
├── workers.py               # Worker Qt (wrapper threadpool)
├── page_registry.py         # Roteamento página→builder
├── connector_forms.py       # Formulários dinâmicos por conector
├── project_controller.py     # Carregar/salvar projetos
├── source_controller.py     # Operações de fonte (alto nível)
├── state.py                 # Estado global compartilhado
├── mixins/                  # Comportamentos da MainWindow
│   ├── selection_mixin.py   # Seleção na árvore
│   ├── source_mixin.py      # CRUD de fontes
│   ├── connection_mixin.py  # Autenticação
│   └── tree_mixin.py        # Lazy loading da árvore
└── pages/                   # Telas (uma por arquivo)
    ├── dashboard_page.py
    ├── sources_page.py
    ├── connection_page.py
    ├── selection_page.py
    ├── review_page.py       # Revisão/Extração
    ├── extraction_page.py
    ├── consolidation_page.py
    ├── markdown_page.py
    └── results_page.py
```

Fluxo de uso: **Dashboard → Fontes → Conexão → Seleção → Revisão → Markdown → Consolidação → Resultados**.

---

## 1. DASHBOARD — Tela inicial

**Arquivo da tela:** `alquimista/ui/pages/dashboard_page.py`
**Método na MainWindow:** `_dashboard_page`
**Widgets:** `components.py` — `SourceCard`, `AlchemistIconAtlas`, `card`

**O que faz:** Mostra hero icon, título, subtítulo e cards de fontes. Click num card → navega para Fontes (`_source_card_clicked`).

**Problemas típicos:**
| Sintoma | Arquivo |
|---|---|
| Layout/visual quebrado | `pages/dashboard_page.py` + `components.py` |
| Ícone não aparece | `components.py` (`AlchemistIconAtlas`) |
| Click não navega | `main_window.py:_source_card_clicked` |
| Métricas erradas | `main_window.py:_metric` / `_refresh_dashboard` |

---

## 2. FONTES — Lista e edita fontes

**Arquivo da tela:** `alquimista/ui/pages/sources_page.py`
**Mixin de lógica:** `alquimista/ui/mixins/source_mixin.py` (~29KB)
**Método na MainWindow:** `_sources_page`
**Modelo:** `models.py` — `SourceConfig`
**Persistência:** `storage.py` — `save_project`/`load_project`
**Detecção:** `source_detection.py`

**O que faz:** Adicionar/editar/remover fontes. Cola URL, escolhe plataforma, define nome. Botão "detectar plataforma" usa `source_detection.py`.

**Problemas típicos:**
| Sintoma | Arquivo |
|---|---|
| "Não mostra a fonte que adicionei" | `pages/sources_page.py` + `mixins/source_mixin.py` |
| "Não salva a fonte" | `mixins/source_mixin.py` + `models.py:SourceConfig` + `storage.py` |
| "Não detecta plataforma pela URL" | `source_detection.py` |
| "Campo do formulário some/erra" | `ui/connector_forms.py` (`form_spec`) |

---

## 3. CONEXÃO — Autenticação

**Arquivo da tela:** `alquimista/ui/pages/connection_page.py`
**Mixin de lógica:** `alquimista/ui/mixins/connection_mixin.py`
**Método na MainWindow:** `_connection_page`
**Núcleo:** `auth.py` — `browser_login`, `delete_session`
**Navegador:** `browser/service.py`, `browser/cache.py`
**Cofre:** `controllers.py` — `RuntimeSecrets` (segredos em memória, nunca serializados)

**O que faz:** Autenticação por fonte. Modos: Pública, Basic (usuário+token), Bearer (token), Navegador (OAuth interativo). Botão "Testar conexão" chama `validate_connection` do conector.

**Problemas típicos:**
| Sintoma | Arquivo |
|---|---|
| "Botão testar conexão não funciona" | `mixins/connection_mixin.py` + `connectors/<plataforma>.py` |
| "Login pelo navegador não abre/fecha" | `auth.py` (`browser_login`) + `browser/service.py` |
| "Credencial não persiste" | Por design em `session_store.py` + `controllers.py:RuntimeSecrets` |
| "Formulário erra por conector" | `ui/connector_forms.py` (`form_spec`) |
| "Erro de auth/token expirado" | `auth.py` + `connectors/http.py` (retries) |

---

## 4. SELEÇÃO — Árvore de páginas (tela mais sensível)

**Arquivo da tela:** `alquimista/ui/pages/selection_page.py`
**Mixin de seleção:** `alquimista/ui/mixins/selection_mixin.py` (~35KB)
**Mixin de árvore:** `alquimista/ui/mixins/tree_mixin.py` (~4,4KB)
**Modelos de árvore:** `alquimista/ui/tree_models.py`
**Widgets:** `components.py` — `SortableTreeItem`, `VisibilityBadgeDelegate`
**Método na MainWindow:** `_selection_page` / `_pages_page`

**O que faz:** Mostra (1) contêineres (espaços/sections/categorias) e (2) páginas em árvore hierárquica. Usuário marca o que extrair. Lazy loading: ao expandir um nó, carrega filhos do conector.

### Fluxo de carregamento
1. UI pede contêineres → `connector.list_containers()` → `tree_models.tree_containers`
2. Expande contêiner → `tree_models.tree_pages` + `ordered_pages` ordenam
3. Se conector suporta filhos → `tree_mixin._lazy_method` decide síncrono vs lazy
4. Expande página → `connector.list_document_children()` → `_lazy_state` guarda cursor
5. Seleção → `selection_mixin._selection_changed` coleta leafs → `SelectionStore`

### Funções-chave da árvore (main_window.py)
- `_populate_page_tree_lazy` — versão lazy (Confluence)
- `_populate_page_tree` — versão síncrona
- `_page_tree_item_expanded` — dispara ao expandir nó
- `_load_document_children` — carrega filhos de um documento
- `_load_expanded_document` — carrega documento expandível

### Funções-chave de seleção (selection_mixin.py)
- `_populate_selection_tree` — monta QTreeWidget
- `_selection_tree_item_expanded` — lazy loading na seleção
- `_selection_changed` — reage a check/uncheck
- `_leaf_items` — coleta itens-folha marcados
- `walk` — percorre árvore recursivamente

### Funções-chave de tree_models.py
- `page_container_id` — id do contêiner de uma página
- `tree_pages` — extrai páginas planas de `data[container_id]`
- `ordered_pages` — ordena páginas por posição/parent/title
- `tree_containers` — lista de contêineres para raiz da árvore
- `lazy_state` — estado de lazy loading (cursor pendente)

### Funções-chave de tree_mixin.py
- `_lazy_method` — decide síncrono vs lazy por capacidade do conector
- `_lazy_state` — accessor do estado de cursor
- `_leaf_items` — percorre folhas

**Problemas típicos:**
| Sintoma | Arquivo |
|---|---|
| "Árvore não carrega" | `mixins/tree_mixin.py` + `connectors/<plataforma>.py` |
| "Demora/para no meio" | `connectors/confluence.py:_collect_lazy_pages` |
| "Páginas fora de ordem" | `tree_models.py:ordered_pages` |
| "Filhos aparecem antes do pai" | `tree_models.py:tree_pages` + `page_container_id` |
| "Não consigo marcar/desmarcar" | `mixins/selection_mixin.py:_selection_changed` |
| "Seleção some ao trocar de aba" | `mixins/selection_mixin.py` + `selection.py:SelectionStore` |
| "Badge público/privado errado" | `connectors/confluence.py:_explicit_visibility` + `tree_models.py` |
| "Não expande filhos" | `mixins/tree_mixin.py:_lazy_method` + `main_window.py:_load_document_children` |
| "Contêineres vazios" | `connectors/<plataforma>.py:list_containers` + `registry.py` |

---

## 5. REVISÃO / EXTRAÇÃO — Prévia e disparo

**Arquivo da tela:** `alquimista/ui/pages/review_page.py`
**Método na MainWindow:** `_review_page`, `_review_page_legacy`
**Controle de execução:** `execution_controller.py` — `prepare_runtimes`
**Dispatcher:** `operation_controller.py` — submete workers em QThreadPool
**Workers:** `process_workers.py` (processos pesados), `workers.py` (wrapper Qt)
**Cancelamento:** `runtime.py` — `CancellationToken`
**Núcleo:** `services.py` — `ExtractionService`, `SourceRuntime`

**O que faz:** Antes de extrair, mostra prévia da seleção e dispara a extração. `page_registry.py` mapeia "extraction" e "review" pro mesmo builder.

**Funções-chave (main_window.py):**
- `_refresh_review` — atualiza prévia
- `run_extraction` — dispara extração
- `execute_selected_operation` — operação selecionada
- `retry_failures` — retentar falhas
- `run_complete` — fluxo completo
- `_prepare_runtimes` — prepara runtimes

**Problemas típicos:**
| Sintoma | Arquivo |
|---|---|
| "Prévia não mostra tudo" | `pages/review_page.py` + `mixins/selection_mixin.py` |
| "Contagem errada" | `mixins/selection_mixin.py:_leaf_items` |
| "Extração não inicia" | `execution_controller.py:prepare_runtimes` |
| "Trava/congela" | `operation_controller.py` + `process_workers.py` |
| "Não cancela" | `runtime.py:CancellationToken` |
| "Extrai mas arquivo sai errado" | `services.py:ExtractionService` + conector `get_document` |
| "Atualização incremental não detecta mudança" | `services.py` (SHA-256) + `manifest_index.py` |

---

## 6. MARKDOWN — Opções de conversão

**Arquivo da tela:** `alquimista/ui/pages/markdown_page.py`
**Método na MainWindow:** `_markdown_page`
**Núcleo:** `markdown.py` — `MarkdownTransformer`, `page_metadata`, `sample_page`, `sha256_text`
**Modelo:** `models.py` — `MarkdownOptions`

**O que faz:** Opções de conversão HTML→Markdown: normalizar títulos, preservar links, baixar imagens, frontmatter, etc.

**Funções-chave (main_window.py):**
- `_load_markdown_controls` — carrega opções salvas
- `_sync_markdown_controls` — sincroniza UI→modelo
- `_apply_preset` — aplica preset (Confluence/GitBook/etc.)
- `_schedule_preview` — agenda prévia
- `_update_preview` — renderiza prévia
- `_render_preview_mode` — modo de renderização

**Problemas típicos:**
| Sintoma | Arquivo |
|---|---|
| "Sai com formatação estranha" | `markdown.py` (`MarkdownTransformer`) |
| "Tabelas quebradas" | `markdown.py` (conversão HTML tabela) |
| "Imagens não vêm" | `markdown.py` (download de imagens) |
| "Links quebrados" | `markdown.py` (normalização de links) |
| "Opções não aplicam" | `pages/markdown_page.py` + `models.py:MarkdownOptions` |
| "Frontmatter errado" | `markdown.py:page_metadata` |
| "Prévia não atualiza" | `main_window.py:_update_preview` + `markdown.py:sample_page` |

---

## 7. CONSOLIDAÇÃO — Junção em arquivo único

**Arquivo da tela:** `alquimista/ui/pages/consolidation_page.py`
**Método na MainWindow:** `_consolidation_page`, `_consolidation_page_legacy`
**Núcleo:** `services.py` — `ConsolidationService`, `demote_headings`
**Modelo:** `models.py` — `ConsolidationOptions`
**Persistência:** `storage.py` — `PACKAGE_INDEX_NAME`

**O que faz:** Define modo de consolidação (arquivo único, pacote, índice), separadores, profundidade. Junta páginas num arquivo ou pacote.

**Funções-chave (main_window.py):**
- `_sync_consolidation_ui` — sincroniza UI
- `_sync_consolidation_controls` — sincroniza controles
- `_depth_choice_changed` — mudança de profundidade
- `_consolidation_example_paths` — exemplos de caminhos
- `_update_depth_examples` — atualiza exemplos
- `_update_consolidation_summary` — resumo
- `_mark_consolidation_preview_stale` — marca prévia stale

**Problemas típicos:**
| Sintoma | Arquivo |
|---|---|
| "Consolidação não junta nada" | `pages/consolidation_page.py` + `services.py:ConsolidationService` |
| "Ordem errada" | `services.py` (ordenação) |
| "Arquivo consolidado mal formatado" | `services.py:demote_headings` + `markdown.py` |
| "Índice do pacote errado" | `storage.py:PACKAGE_INDEX_NAME` + `services.py` |
| "Profundidade não respeita" | `pages/consolidation_page.py` + `services.py` |

---

## 8. RESULTADOS — Pós-extração

**Arquivo da tela:** `alquimista/ui/pages/results_page.py`
**Método na MainWindow:** `_results_page`, `_output_page`
**Núcleo:** `reports.py` — geração de relatórios
**Serviço:** `services.py` — gera `FAILURES_NAME`/`REPORT_NAME`

**Problemas típicos:**
| Sintoma | Arquivo |
|---|---|
| "Relatório não mostra falhas" | `pages/results_page.py` + `reports.py` |
| "Lista incompleta" | `reports.py` + `services.py` |
| "Não abre pasta de saída" | `pages/results_page.py` (QDesktopServices) |

---

## 9. CONFIGURAÇÕES — Preferências globais

**Método na MainWindow:** `_settings_page`
**Visual:** `theme.py`

**Problemas típicos:**
| Sintoma | Arquivo |
|---|---|
| "Tema não aplica" | `theme.py` + `main_window.py:_settings_page` |
| "Preferência não salva" | `main_window.py` + `models.py:ProjectConfig` |

---

## NÚCLEO — Referência rápida por arquivo

### models.py — Contrato de dados (19.4 KB, 480 linhas)
Contrato central do pydantic. `SCHEMA_VERSION = 4` — incrementar ao mudar a serialização (invalida manifestos antigos).

| Classe/Função | Responsabilidade |
|---|---|
| `AuthMode` (StrEnum) | Modos: `public`/`basic`/`bearer`/`browser`. |
| `ConnectorStatus` (StrEnum) | Status do conector: `active`/`inactive`. |
| `EntryStatus` (StrEnum) | Status da entrada do manifest. |
| `Model` | BaseModel pydantic base de todos os modelos (config serialização). |
| `ConnectorCapabilities` | Capacidades do conector (lazy, search, root_documents). |
| `KnowledgeSource` | Fonte de conhecimento (conector + containers). |
| `KnowledgeContainer` | Contêiner (espaço/seção/categoria). |
| `KnowledgeDocumentMetadata` | Metadados de documento (sem conteúdo). |
| `KnowledgeDocument` | Documento com conteúdo. |
| `KnowledgeSelection` | Seleção do usuário. |
| `SourceConfig` | Configuração de uma fonte (URL, tipo, auth, root_mode, root_value). |
| `MarkdownOptions` | Opções de conversão Markdown (frontmatter, títulos, imagens, links). |
| `ExtractionOptions` | Opções de extração (página por arquivo, override, etc.). |
| `ConsolidationOptions` | Opções de consolidação (arquivo único/pacote/índice, ordenação, prefixos). |
| `ProjectConfig` | Projeto completo: `sources[]`, `options`, metadados. |
| `ManifestEntry` | Entrada do manifest (uma página extraída: key, status, hashes). |
| `ManifestDocument` | Documento do manifest (lista de `ManifestEntry`). (Não confundir com `MarkdownDocument` legado.) |
| `validate_source_identifier(value)` | Valida identificador de fonte via `SOURCE_ID_PATTERN`. |
| `stable_json_hash(data)` | Hash estável p/ comparação incremental (independe de ordem de chaves). |
| `slugify(value, maxlen=80)` | Normaliza string p/ nome de arquivo. |
| `now_iso()` | Timestamp ISO atual (UTC). |
| `default_project()` | Projeto padrão vazio. |

**Regra de ouro:** ao adicionar/remover campos, mantenha `stable_json_hash` compatível para não invalidar manifestos existentes.

### services.py — Motor de domínio (52.7 KB, 1145 linhas)
O coração do pipeline de extração e consolidação. Cada classe orquestra conectores, markdown e storage.

| Classe/Função | Responsabilidade |
|---|---|
| `SourceRuntime` | Runtime por fonte: empacota conector + manifest parcial + cancelamento. |
| `SourceRuntime.is_generic` | Indica modo genérico (seleção não-lazy) vs legado. |
| `SourceRuntime.selected_document_keys` | Documentos marcados pelo usuário (keys estáveis). |
| `sanitize_filename(value, maximum=120)` | Normaliza nome de arquivo (remove acentos, junto). |
| `ExtractionService` | Extração de páginas via conector + escrita atômica via `FileTransaction`. |
| `ExtractionService.run` / `_run` | Ponto de entrada: despacha `_run_generic` ou `_run_legacy`. |
| `ExtractionService._run_generic` | Modo genérico: extrai selecionados, converte via `KnowledgeDocumentRenderer`, atualiza manifest. |
| `ExtractionService._run_legacy` | Modo legado (Confluence antigo): extração síncrona sem lazy. |
| `ExtractionService._relative_page_path` | Caminho relativo da página no diretório de saída. |
| `ExtractionService._metadata_hash` / `_summary_metadata_hash` | Hash de metadados p/ detectar mudança (atualização incremental). |
| `ExtractionService._structured_report` | Monta `ExecutionReport` a partir dos resultados. |
| `demote_headings(markdown, levels)` | Rebaixa todos os cabeçalhos Markdown em `levels` (usado na consolidação). |
| `ConsolidationService` | Consolidação em arquivo único / pacote / índice. |
| `ConsolidationService.preview` | Prévia do resultado da consolidação (sem gravar). |
| `ConsolidationService.run` / `_run` | Dispara consolidação real (grava via `FileTransaction`). |
| `ConsolidationService._group_key` | Agrupa entradas por fonte/espaço/sessão conforme opções. |
| `ConsolidationService._entries` | Carrega `ManifestDocument` + filtra entradas selecionadas. |
| `ConsolidationService._page_text` | Lê o Markdown gravado de uma entrada. |
| `ConsolidationService._sort` | Ordena entradas (por título, data, manual, etc.). |
| `ConsolidationService._estimate_overhead` | Estima overhead de cabeçalhos para calcular tamanho final. |
| `ConsolidationService._unique_package_filename` | Evita colisão de nome de arquivo no pacote. |

**Sintoma-chave:** "extração não grava nada" → `ExtractionService._run_generic`/`_run` + `FileTransaction.commit`. "consolidação faltam páginas" → `_entries`/`_group_key` filtraram.

**Dependências:** `ExtractionService` depende de `connectors/<plataforma>.py` (conector), `markdown.py` (`KnowledgeDocumentRenderer`), `storage.py` (`FileTransaction`, `ManifestStore`) e `runtime.py` (`CancellationToken`). `ConsolidationService` depende de `storage.py` (`ManifestStore`, `PACKAGE_INDEX_NAME`), `markdown.py` (`demote_headings`) e `models.py` (`ConsolidationOptions`).

### storage.py — Persistência atômica (12.9 KB, 262 linhas)
Todas as escritas são **atómicas** (tmp + rename). `FileTransaction` acumula mudanças e só grava no `commit`.

| Função/Classe | Responsabilidade |
|---|---|
| `confined_path(base, relative)` | Protege path traversal — rejeita `..` e caminhos fora de `base`. |
| `atomic_write_text(path, content, backup=False)` | Escrita atômica de texto (tmp + rename). `backup` preserva `.bak`. |
| `atomic_write_json(path, data, backup=False)` | Escrita atômica de JSON (usa `atomic_write_text` + `json.dumps`). |
| `FileTransaction` | Transação de arquivos: `stage_text`/`stage_json`/`stage_delete` acumulam; `commit` grava tudo de uma vez. |
| `FileTransaction.stage_text` / `stage_json` / `stage_delete` | Adiciona operação à transação (não grava ainda). |
| `FileTransaction.commit` | Efetiva: renomeia todos os tmp e remove os deletados. |
| `FileTransaction.close` | Aborta transação (remove tmp sem gravar). |
| `load_json(path, default=None)` | Carrega JSON; retorna `default` se não existir. |
| `save_project(path, project)` | Salva `ProjectConfig` (via `atomic_write_json`). |
| `load_project(path)` | Carrega `ProjectConfig`; migra schemas antigos se preciso. |
| `ManifestStore` | Store do manifest (`manifesto_alquimista.json`): carrega e salva `ManifestDocument`. |
| `MANIFEST_NAME` / `MANIFEST_INDEX_NAME` / `FAILURES_NAME` / `REPORT_NAME` / `PACKAGE_INDEX_NAME` | Nomes canônicos dos arquivos de saída. |

**Sintoma-chave:** "arquivo gravado mas desaparece" → `commit` não foi chamado (transação abortou). "arquivo temporário sobra" → transação não fechou.

**Dependências:** `FileTransaction` é usado por `services.py` (`ExtractionService`, `ConsolidationService`). `save_project`/`load_project` consomem `models.py` (`ProjectConfig`). `ManifestStore` consome `models.py` (`ManifestDocument`). `confined_path` protege todos os caminhos de saída contra path traversal.

### connectors/confluence.py — Conector de referência (25.3 KB, 625 linhas)
O conector mais completo. Implementa o ABC `KnowledgeSourceConnector` com lazy loading, busca e detecção de visibilidade.

| Método/Função | Responsabilidade |
|---|---|
| `ConfluenceRestConnector.__init__(...)` | Configura URL, auth, root, `ConfluenceClient`. |
| `get_source_type` / `get_source` / `get_capabilities` | Metadados do conector. |
| `validate_connection` | Testa conexão/credencial (botão "Testar conexão"). |
| `list_containers` | Lista espaços (`KnowledgeContainer[]`). |
| `_client_for_container(container_id)` | Cria `ConfluenceClient` p/ o contêiner. |
| `list_documents(container_id)` | Lista páginas-raiz de um espaço. |
| `get_document(document)` | Conteúdo de uma página (via `ConfluenceClient.fetch_page`). |
| `get_document_children(document)` | Filhos de uma página (síncrono). |
| `_lazy_request(...)` / `_collect_lazy_pages(...)` | **Motor de paginação** com cursor (lazy loading). |
| `list_root_documents` / `list_document_children` | Raízes e filhos no modo lazy. |
| `search_documents(query)` | Busca por texto (CQL). |
| `normalize_document(raw)` | Converte documento cru em `KnowledgeDocument`. |
| `_metadata` / `_browser_metadata` | Constrói metadados a partir de payload cru. |
| `_discovery_metadata` | Metadados p/ o subsistema browser (lazy discovery). |
| `_explicit_visibility(page)` | Detecção público/privado (campo restrictions). |
| `_visibility_from_restriction_payload(payload)` | Detecção por payload de restrição (view/edit). |
| `_explicit_has_children(page)` | Indica se a página tem filhos (p/ ícone de expandir). |
| `_ordered_pages(client, container_id)` | Ordena páginas por ancestralidade/posição. |
| `close` | Fecha o cliente HTTP. |

**Sintoma-chave:** "páginas não carregam/buscam/expandem" → este arquivo. "extração de conteúdo falha" → `get_document` + `client.py:fetch_page`.

**Dependências:** `ConfluenceRestConnector` depende de `connectors/http.py` (`ApiHttpClient`), `connectors/base.py` (ABC), `client.py` (`ConfluenceClient`), `models.py` (`KnowledgeDocument`, `KnowledgeContainer`) e `browser/cache.py` (cache de discovery quando aplicável).

### ui/tree_models.py — Dados→árvore
| Função | Responsabilidade |
|---|---|
| `page_container_id` | Id do contêiner |
| `tree_pages` | Páginas planas de `data` |
| `ordered_pages` | Ordena páginas |
| `tree_containers` | Contêineres para raiz |
| `lazy_state` | Estado de cursor lazy |

### errors.py — Hierarquia de erros tipados
Erros **funcionais** (não crash). A UI captura e mostra amigavelmente. Use o erro mais específico no `raise`.

| Classe | Quando usar / capturar |
|---|---|
| `AlquimistaError` | Base de todos os erros funcionais. `except AlquimistaError` pega tudo. |
| `AuthenticationError` | Falha de login/token. UI mostra "não autenticado". |
| `PermissionDeniedError` | Usuário sem acesso ao recurso. |
| `ResourceNotFoundError` | Página/espaço não existe (404). |
| `ApiConnectionError` | Falha genérica de conexão com API (reutilizável p/ qualquer conector). |
| `ApiRateLimitError` | API retornou 429 / limite excedido. |
| `ConfluenceConnectionError` | Falha específica de Confluence (legado). |
| `RateLimitError` | Rate limit específico de Confluence (legado). |
| `InvalidResponseError` | Confluence devolveu JSON inválido. |
| `InvalidProjectError` | `ProjectConfig` inválido (campo obrigatório faltando). |
| `ManifestError` | Manifest corrompido / incompatível. |
| `StorageError` | Falha de leitura/escrita em disco. |
| `ExtractionCancelledError` | Usuário cancelou a extração (não é bug). |

**Dica didática:** ao adicionar tratamento de erro numa tela, capture o erro mais específico, não `AlquimistaError`. Ex.: `except ApiRateLimitError` para mostrar "aguarde e tente de novo".

### runtime.py — Cancelamento e rate limit
| Classe/Função | Responsabilidade |
|---|---|
| `CancellationToken` | Cancelamento cooperativo entre threads. Métodos: `cancel()`, `cancelled`, `check()` (levanta se cancelado), `wait(seconds)`. |
| `RateLimiter` | Limita requisições/segundo com suporte a cancelamento. |
| `ProgressCallback` | Type alias: `Callable[[int, int, str], None]` (atual, total, mensagem). Usado em todo o sistema p/ reportar progresso. |
| `LogCallback` | Type alias: `Callable[[str], None]`. Para mensagens de log no worker. |

**Onde aparece:** passado a quase todo método de extração. Se "extração não cancela" ou "progresso não atualiza", o token/callback foi ignorado no chamador.

### selection.py — Estado de seleção do usuário
| Classe/Função | Responsabilidade |
|---|---|
| `SelectionStore` | Estado de seleção **independente do Qt**. Sobrevive a troca de aba porque não é widget. |
| `SelectionStore.set(key, value)` | Marca/desmarca item. Chave = `(source, container, document)`. |
| `SelectionStore.is_selected(key)` | Consulta se está selecionado. |
| `SelectionStore.keys_for_source(source)` | Todas as chaves de uma fonte. |
| `SelectionStore.selections()` | Lista de seleções para extração. |
| `SelectionStore.count_by_container(source_id=None)` | Conta seleções agrupadas por (source, container). |
| `SelectionStore.clear()` | Limpa toda a seleção. |
| `SelectionStore.from_selections(list)` | Cria store a partir de lista. |

**Sintoma-chave:** "seleção some ao trocar de aba" → seElect/store não está sendo usado; widget guarda estado local que some.

### session_store.py — Persistência local criptografada de sessão (DPAPI)
Cookies e estado de sessão de browser são persistidos localmente e criptografados com **Windows DPAPI** (`CryptProtectData`). **Não contém credenciais de API** — tokens bearer e segredos ficam em memória, em `controllers.py:RuntimeSecrets`, e nunca são serializados. O `session_store.py` apenas persiste a sessão de browser entre execuções para reaproveitar login (logout via `delete_session`).

| Função | Responsabilidade |
|---|---|
| `session_directory()` | Caminho seguro (anti path traversal) da pasta de sessões. |
| `session_path(source_id)` | Caminho do arquivo de sessão de uma fonte. |
| `save_session(source_id, state)` | Grava sessão criptografada com DPAPI. |
| `load_session(source_id)` | Carrega e descriptografa sessão. |
| `session_exists(source_id)` | Verifica se existe sessão salva. |
| `delete_session_file(source_id)` | Remove arquivo de sessão (logout). |
| `_crypt_protect` / `_crypt_unprotect` | Wrappers de Windows DPAPI (não usar diretamente). |
| `_DataBlob` | Struct ctypes para interoperar com DPAPI. |

**Sintoma-chave:** "credencial não persiste entre sessões" → por design para tokens; já "login pelo navegador perdeu sessão" → verifica DPAPI/disponibilidade do `LOCALAPPDATA`.

### source_detection.py — Detecção de plataforma por URL
| Classe/Função | Responsabilidade |
|---|---|
| `DetectedSource` | Dataclass: `source_type`, `display_name`, `base_url`, `api_name`, `space_key`, `space_name`, `root_mode`, `root_value`. |
| `detect_source_url(value)` | Detecta plataforma **sem chamada de rede** (parser de URL). Reconhece: Confluence, Notion (`api.notion.com`), GitBook, Zendesk, SharePoint. |
| `_extract_notion_id(path)` | Extrai ID 32-hex de URLs Notion. |
| `_origin(parsed)` | Normaliza origem (scheme/host). |
| `_last_path_value(path)` | Último segmento da URL. |

**Sintoma-chave:** "não detecta plataforma X pela URL" → adicione/ajuste padrão aqui. Normalmente não é necessário alterar o conector.

### confluence_url.py — Parse de URLs Confluence
| Classe/Função | Responsabilidade |
|---|---|
| `ParsedConfluenceUrl` | Dataclass: `base_url`, `space_key`, `root_mode`, `root_value`, `title`, `page_id`, `entire_space`. |
| `parse_confluence_url(value)` | Aceita múltiplos formatos: `/display/SPACE/Title`, `/spaces/SPACE/pages/ID`, query params `pageId`/`spaceKey`. |

**Onde aparece:** base de `source_detection.py` para Confluence. Se "URL Confluence não parseia", comece aqui.

### manifest_index.py — Índice SQLite do manifest
| Classe/Função | Responsabilidade |
|---|---|
| `ManifestIndex` | Índice sidecar SQLite para lookup rápido em manifestos grandes. |
| `ManifestIndex.rebuild(document)` | Reconstrói atomicamente a partir do JSON (fonte da verdade). Cria tabela `manifest_entries` com `document_key` como PK. |

**Por que importa:** atualização incremental e revisão dependem desse índice. Se "atualização incremental não detecta mudança", o índice pode estar desatualizado — `rebuild` recria do JSON.

### auth.py — Autenticação interativa (browser)
| Função | Responsabilidade |
|---|---|
| `browser_login(source, ready, token, timeout_seconds)` | Login OAuth interativo via Playwright. Abre navegador, espera, fecha. |
| `_authenticated_identity(payload)` | Valida se o payload de login tem identidade real (não anônimo). |
| `delete_session(source)` | Remove sessão salva (logout). |
| `_browser_session_closed(browser, page)` | Detecta se sessão foi fechada manualmente. |

**Sintoma-chave:** "login pelo navegador não abre/fecha/trava" → `browser_login` + `browser/service.py`.

**Dependências:** `browser_login` usa `browser/service.py` (Playwright) e persiste sessão via `session_store.py` (DPAPI). `delete_session` remove a sessão persistida. Tokens bearer ficam em `controllers.py:RuntimeSecrets` (memória), não neste módulo.

### logging_utils.py — Logs JSON com redação de segredos
| Classe/Função | Responsabilidade |
|---|---|
| `JsonFormatter` | Formatador de log em JSON com timestamp ISO. |
| `redact(value)` | Mascara `authorization`, `bearer`, `token`, `password`, `senha`, `cookie`, `secret` → `***`. |
| `SENSITIVE` | Regex de detecção de segredos. |
| `configure_logging(log_path)` | Configura logger "alquimista" com handler de arquivo UTF-8. Fallback p/ temp se pasta não gravável. |
| `default_log_path()` | Caminho padrão (`LOCALAPPDATA\ALQuimista Studio`). |

**Sintoma-chave:** "vazamento de segredo em log" → redação aqui. **Nunca** logue headers de Authorization brutos.

### reports.py — Relatórios de execução
| Classe | Responsabilidade |
|---|---|
| `DocumentResult` | Resultado de uma página (sucesso/falha, erro, caminho). |
| `ContainerReport` | Relatório por contêiner (espaço/seção). |
| `SourceReport` | Relatório por fonte. |
| `ExecutionReport` | Relatório estável (pydantic) consumido pela tela de Resultados e exportável a JSON. |

**Onde aparece:** `services.py` gera `ExecutionReport`; `results_page.py` consome. Se "relatório não mostra falhas", verifique `DocumentResult` preenchido aqui.

### client.py — Cliente REST legado Confluence (21.1 KB, 513 linhas)
Cliente REST de baixo nível para Confluence. Conectores usam este via `ConfluenceRestConnector`.

| Método/Função | Responsabilidade |
|---|---|
| `session_directory()` / `session_path(source_id)` | Caminhos de sessão (legado; `session_store.py` é o atual). |
| `ConfluenceClient.__init__(...)` | Configura URL/auth, cria sessão HTTP. |
| `ConfluenceClient.base_url` | URL base normalizada. |
| `_configure_session` / `close` / `__enter__` / `__exit__` | Session HTTP + context manager. |
| `_retry_delay(response, attempt)` | Backoff exponencial + jitter para 429/5xx. |
| `_request(...)` | **Motor de requisições** com retry, rate limit e cancelamento. |
| `test_connection` | Testa conexão (GET no endpoint base). |
| `list_spaces(maximum=1000)` | Lista espaços. |
| `list_pages(maximum=5000)` | Lista todas as páginas (top-level). |
| `_list_content_page(...)` | Paginação interna de conteúdo. |
| `list_root_pages` / `list_child_pages` | Raízes e filhos de uma página. |
| `fetch_page(page_id)` | **Busca conteúdo de uma página** (HTML + metadados). |
| `fetch_tree` | Busca árvore de páginas de uma vez (modo síncrono antigo). |
| `fetch_html_fallback(page_id)` | Fallback de HTML quando a API principal falha. |
| `search_pages(query)` | Busca por texto (CQL). |
| `resolve_root` | Resolve a raiz de extração (root_mode/root_value). |
| `_enrich_page_restrictions(page)` / `_has_restriction_details` / `_read_restriction_payload` | Enriquece página com restrições (p/ visibilidade). |
| `source_url(base_url, page)` | Monta URL canônica de uma página. |
| `_deduplicate(items)` | Remove duplicatas de listas de páginas. |

**Onde aparece:** usado por `ConfluenceRestConnector`. **Prefira `connectors/confluence.py`** para código novo. Aqui só se a camada HTTP estiver com problema (timeout, retry, rate limit).

### markdown.py — Conversão HTML→Markdown (22.3 KB, 476 linhas)
Converte HTML de páginas em Markdown. Lida com Confluence macros, anexos, links, tabelas.

| Função/Classe | Responsabilidade |
|---|---|
| `normalize_markdown(text)` | Normaliza espaços/quebras do Markdown final. |
| `format_updated_at(value)` | Formata timestamp ISO p/ exibição. |
| `sha256_text(text)` | Hash p/ dedup de imagens/conteúdo/identidade incremental. |
| `_normalize_ancestors(value)` | Normaliza lista de ancestores de uma página. |
| `relative_ancestor_titles(page, root_id)` | Títulos de ancestores relativos à raiz de extração (ignora acima da raiz). |
| `page_metadata(...)` | Extrai metadados (título, ancestors, data, space) p/ frontmatter. |
| `MarkdownTransformer` | Classe principal: HTML → Markdown com `MarkdownOptions`. |
| `MarkdownTransformer._attachment_url(page_id, filename)` | Monta URL de anexo de Confluence. |
| `MarkdownTransformer._replace_links(soup, page_id)` | Substitui links internos do Confluence por links relativos (se local). |
| `MarkdownTransformer._replace_macros(soup, page_id)` | Substitui macros do Confluence (códã, info, etc.) por Markdown. |
| `MarkdownTransformer.technical_markdown(page)` | Markdown técnico (sem frontmatter). |
| `MarkdownTransformer.hash_input(metadata, technical)` | Hash do conteúdo p/ atualização incremental. |
| `MarkdownTransformer.full_document(...)` | Documento completo (frontmatter + corpo). |
| `MarkdownTransformer.knowledge_document_metadata(...)` | Metadados no formato `KnowledgeDocument`. |
| `KnowledgeDocumentRenderer` | Renderiza `KnowledgeDocument` aplicando `MarkdownOptions` (frontmatter, níveis de cabeçalho, etc.). |
| `KnowledgeDocumentRenderer.render(...)` | Renderiza documento completo com opções. |
| `sample_page()` | Página de exemplo p/ prévia da tela Markdown. |

**Sintoma-chave:** "tabelas/links/imagens/macros saem errados" → `MarkdownTransformer` (métodos `_replace_*`). "frontmatter errado" → `page_metadata`. "prévia da tela não funciona" → `sample_page`.

**Dependências:** `MarkdownTransformer` consome `models.py` (`MarkdownOptions`) e é chamado por `services.py` (`ExtractionService._run_generic` via `KnowledgeDocumentRenderer`). `sample_page` alimenta a prévia em `main_window.py:_update_preview`.

### models.py — Classes adicionais (complemento)
A tabela anterior lista o essencial. O modelo tem ainda (pydantic `BaseModel`):

| Classe/Função | Responsabilidade |
|---|---|
| `ConnectorStatus` (StrEnum) | Status do conector (active/inactive). |
| `EntryStatus` (StrEnum) | Status da entrada do manifest. |
| `ConnectorCapabilities` | Capacidades do conector (lazy, search, root_documents). |
| `KnowledgeSource` | Fonte de conhecimento (conector + containers). |
| `KnowledgeContainer` | Contêiner (espaço/seção/categoria). |
| `KnowledgeDocumentMetadata` | Metadados de documento (sem conteúdo). |
| `KnowledgeDocument` | Documento com conteúdo. |
| `KnowledgeSelection` | Seleção do usuário. |
| `ManifestDocument` | Documento do manifest (não confundir com `MarkdownDocument` legado). |
| `validate_source_identifier(value)` | Valida identificador de fonte. |

> _Dica: ao adicionar um campo a qualquer modelo, a serialização (`from_dict`/`to_dict`) e o `stable_json_hash` precisam continuar estáveis para não invalidar manifestos antigos._


---

## CONECTORES — Referência por plataforma
Cada conector implementa o ABC `KnowledgeSourceConnector`.

> **Atenção — possível desatualização:** os conectores são a parte mais volátil do projeto. Antes de editar, confirme assinaturas e campos em `connectors/base.py` e `models.py`. Se a tabela abaixo divergir do código, o código prevalece; atualize o mapa.

Confluence é o mais completo; os demais seguem o mesmo contrato mas podem não ter lazy loading.

### connectors/base.py — Contrato ABC comum
| Método | Responsabilidade |
|---|---|
| `get_source_type()` | String única da plataforma (ex.: `confluence_rest`). |
| `get_source()` | Metadados da fonte (`KnowledgeSource`). |
| `get_capabilities()` | `ConnectorCapabilities` (lazy? search? root_documents?). |
| `validate_connection()` | Testa conexão/credencial. Usado pelo botão "Testar conexão". |
| `list_containers()` | Lista espaços/seções/categorias. |
| `list_documents(container)` | Lista páginas-raiz de um contêiner. |
| `get_document(document)` | Conteúdo de uma página. |
| `list_root_documents()` | (opcional) Raízes lazy. |
| `list_document_children(document)` | (opcional) Filhos lazy. |
| `search_documents(query)` | (opcional) Busca por texto. |

**Adicionar novo conector:** crie classe herdando de `KnowledgeSourceConnector`, registre em `registry.py`, adicione spec em `ui/connector_forms.py` e detector em `source_detection.py`.

**Checklist de validação (`tests/`):**
1. Cadastre a nova fonte na UI e salve o projeto (.alquimista) → recarregue, confirme persistência.
2. "Testar conexão" com credencial válida e inválida (erro esperado e tratado).
3. Carregue a árvore de seleção (síncrono e, se aplicável, lazy) e expanda um contêiner.
4. Extraia 1–2 páginas e verifique o método `get_document` no `manifest_index.json`.
5. Rode `pytest tests/ -k <conector>` e `tests/test_registry.py` se existirem.
6. Gere o relatório de execução via `reports.py` e confira a presença do novo `source_type`.

### connectors/http.py — API HTTP compartilhada
| Classe | Responsabilidade |
|---|---|
| `ApiHttpClient` | HTTP compartilhado: **exige HTTPS**, retries com backoff exponencial+jitter, respeita `RateLimiter` e `CancellationToken`, **nunca loga Authorization**. |

**Sintoma-chave:** "timeout", "rate limit", "conexão recusada" em **qualquer** conector → `ApiHttpClient`. Normalmente a correção fica no cliente HTTP, não no conector.

### connectors/registry.py — Catálogo e instanciação
| Classe/Função | Responsabilidade |
|---|---|
| `ConnectorDescriptor` | Frozen dataclass: metadados do conector (`source_type`, classe, status). |
| `ConnectorRegistry` | Catálogo de conectores por `source_type`. Normaliza status legado p/ `ConnectorStatus`. |
| `default_registry()` | Instância singleton com todos os conectores registrados. |

**Sintoma-chave:** "conector não aparece" ou "não registrado" → `registry.py`.

### connectors/gitbook.py
| Classe/Função | Responsabilidade |
|---|---|
| `GitBookConfig` | Pydantic: valida `organization_id`, aceita `access_token`. |
| `GitBookConnector` | Implementa `KnowledgeSourceConnector` via `ApiHttpClient`. `page_limit` até 1000. |

### connectors/notion.py
| Classe/Função | Responsabilidade |
|---|---|
| `NotionConnector` | `SOURCE_TYPE="notion_api"`. Header `Notion-Version: 2022-06-28`. Via `ApiHttpClient`. |

### connectors/sharepoint.py
| Classe/Função | Responsabilidade |
|---|---|
| `SharePointConnector` | `SOURCE_TYPE="sharepoint_graph"`. Usa Microsoft Graph (`graph.microsoft.com/v1.0`). |

### connectors/zendesk.py
| Classe/Função | Responsabilidade |
|---|---|
| `ZendeskConfig` | Pydantic: valida `subdomain`, `page_size` até 100. |
| `ZendeskGuideConnector` | Converte HTML do Help Center via `BeautifulSoup`+`markdownify`. |

---

## BROWSER — Navegador embutido (Playwright)
Subsistema de discovery com cache. ** importante:** contratos são serializáveis mas **sem credenciais, sem conteúdo de documento**.

### browser/contracts.py — Tipos de discovery
| Classe | Responsabilidade |
|---|---|
| `Visibility` (StrEnum) | Público/privado/restrito. |
| `SpaceMetadata` | Metadados de espaço (sem credenciais). |
| `DocumentMetadata` | Metadados de documento (sem conteúdo). |
| `PageRequest` | Requisição de página (cursor/offset). |
| `DiscoveryPage[T]` | Página genérica de resultados (cursor p/ próxima). |
| `SearchResult` | Resultado de busca. |
| `CancellationLike` | Protocol de cancelamento (compat com `CancellationToken`). |
| `DiscoveryAdapter` | Protocol que conectores implementam p/ discovery. |

### browser/service.py — Orquestração
| Classe | Responsabilidade |
|---|---|
| `LazyDiscoveryService` | Orquestra discovery com cache, **síncrono** (thread-safe com `Lock`/`RLock`). TTL e `stale_if_error`. |
| `CacheMissError` | Erro: `not-modified` sem cache local. |

### browser/adapters.py — Adaptação de conectores
| Classe/Função | Responsabilidade |
|---|---|
| `ConnectorDiscoveryAdapter` | Adapta conectores ao contrato `DiscoveryAdapter`. |
| `DiscoveryCapabilityError` | Conector não suporta lazy. |
| `_offset(cursor)` | Converte cursor em offset. |
| `_space_metadata` / `_document_page` / `_document_metadata` | Conversões de tipos. |

### browser/cache.py — Cache SQLite durável
| Função/Classe | Responsabilidade |
|---|---|
| `BrowserCache` | Cache SQLite de **apenas metadados**. |
| `_SENSITIVE_PARTS` | Garante que cookies/content/body **nunca** sejam armazenados. |
| `_query_key(query)` | Normaliza chave de busca. |
| `_safe_metadata` / `_safe_space` / `_safe_document` | Sanitiza antes de gravar. |

**Sintoma-chave:** "cache desatualizado" → `BrowserCache` + TTL em `service.py`. "vazamento em cache" → `_SENSITIVE_PARTS`.

---

## UI — Controllers e auxiliares
Camadas entre `main_window.py` e o núcleo. Alguns são **sem Qt** (testáveis isoladamente).

### ui/state.py — Estado mutável fora dos widgets
| Classe | Responsabilidade |
|---|---|
| `MainWindowState` | Dataclass: `trees`, `selection_store`, `connected_sources`, `connection_states`, `last_result`, `last_consolidation_preview`, `operation_status`, `operation_error`. |

**Sintoma-chave:** "perde estado entre telas" → aqui, não nos widgets.

### ui/page_registry.py — Rotas → builders
| Função | Responsabilidade |
|---|---|
| `page_builders(window)` | Mapeia rotas → builders: `dashboard`, `sources`, `connection`, `pages`/`selection` (mesmo builder), `markdown`, `consolidation`, `extraction`/`review`/`output` (mesmo builder), `results`, `settings`. |

**Sintoma-chave:** "navegação quebrada/loop" → verifique aliases aqui (`pages`→`selection`, `extraction`/`review`/`output`→`review_page`).

### ui/controllers.py — Segredos e runtimes
| Classe | Responsabilidade |
|---|---|
| `RuntimeSecrets` | Segredos em **memória**, nunca serializados. Tokens bearer ficam aqui. |
| `RuntimeBuilder` | `build_connectors()`: descobre contêineres e documenta runtimes. |

**Sintoma-chave:** "token some ao salvar projeto" → por design (`RuntimeSecrets` não persiste).

### ui/execution_controller.py — Preparação e disparo
| Função | Responsabilidade |
|---|---|
| `prepare_runtimes(...)` | Prepara runtimes antes de extrair. |
| `validated_project_snapshot(window)` | Valida `ProjectConfig`; retorna `None` se inválido. |
| `run_extraction(...)` | Dispara extração. |
| `execute_selected_operation(window)` | Executa operação selecionada (extração/consolidação). |
| `retry_failures(window)` | Retenta falhas. |
| `run_complete(window)` | Fluxo completo. |

**Sintoma-chave:** "extração não inicia" → `validated_project_snapshot` rejeitou o projeto.

### ui/operation_controller.py — Ciclo de vida do worker
| Classe | Responsabilidade |
|---|---|
| `WorkerOperationController` | Dono do worker. `start()` rejeita se já existe worker ativo. Gerencia `operation_status`/`token`. |

**Sintoma-chave:** "UI trava/congela" → worker ativo sem descartar (bug aqui ou chamador não chamou cleanup).

### ui/process_workers.py — Workers em processo
| Classe/Função | Responsabilidade |
|---|---|
| `WorkerMessage` | Frozen dataclass serializável (cross-process). |
| `TaskContext` | Cancelamento cooperativo no child process. |
| `ProcessWorker` | Worker em processo separado (multiprocessing `spawn`). |
| `TaskSerializationError` | Erro de pickling. |
| `TaskCancelled` | Cancelamento no child process. |
| `_worker_main(...)` | Entry point do child process. |

**Sintoma-chave:** "pickling falhou" ou "processo filho morre" → aqui. Objetos não serializáveis (ex.: widgets Qt) não podem ser passados.

### ui/workers.py — Wrapper Qt para threadpool
| Classe | Responsabilidade |
|---|---|
| `Worker(QRunnable)` | Wrapper Qt p/ QThreadPool. |
| `WorkerSignals` | Sinais: `succeeded`, `failed(str, str)`, `progress(int,int,str)`, `log(str)`, `finished`. |

**Sintoma-chave:** "progresso/log não chega à UI" → `WorkerSignals` não conectado ou payload não serializável.

### ui/project_controller.py — CRUD de projeto (sem Qt)
| Função | Responsabilidade |
|---|---|
| `resolve_project_dir(...)` | Resolve diretório do projeto. |
| `validate_project_snapshot(project)` | Valida `ProjectConfig`. |
| `load_project_file(path)` | Carrega `ProjectConfig`. |
| `save_project_file(path, project)` | Salva `ProjectConfig`. |

**Sintoma-chave:** "projeto não carrega/salva" → aqui antes de `storage.py`.

### ui/source_controller.py — Normalização de fonte (sem Qt)
| Função/Classe | Responsabilidade |
|---|---|
| `normalize_source_config(...)` | Constrói `SourceConfig` a partir de `DetectedSource`. |
| `ComboDataProvider` | Protocol p/ data provider de combo de fontes. |
| `source_by_index` / `source_by_identifier` / `source_by_combo` | Lookup de fonte por diferentes chaves. |
| `build_source_snapshot` / `build_source_snapshots` | Snapshots p/ UI. |

**Sintoma-chave:** "URL detectada mas fonte criada errada" → `normalize_source_config`.

### ui/connector_forms.py — Especificação de formulários por conector
| Classe/Função | Responsabilidade |
|---|---|
| `ConnectorFormSpec` | Dataclass: `url_label`, `url_placeholder`, `scope_label`, `supports_scope`, `supports_root`, `bearer_only`, `help_text`. |
| `form_spec(source_type)` | Retorna spec por `source_type` (confluence_rest, gitbook_api, zendesk_guide, notion_api, sharepoint_graph). |

**Sintoma-chave:** "campo errado aparece no formulário da fonte" → spec do conector aqui.

### ui/theme.py — Cores e constantes visuais
| Item | Responsabilidade |
|---|---|
| `LIGHT` / `DARK` | Dicionários de cores por tema. |
| Constantes de card | `SOURCE_CARD_MIN_HEIGHT`, `BLUR_RADIUS_*`, `ANIMATION_DURATION_*`. |
| Gradientes | Gradientes usados pelos cards. |

**Sintoma-chave:** "tema não aplica" ou "card com tamanho errado" → aqui além de `main_window.py:_settings_page`.

### ui/components.py — Widgets reutilizáveis
| Classe/Função | Responsabilidade |
|---|---|
| `FlowLayout` | Layout de fluxo (empacotamento automático). |
| `AlchemistIconAtlas` | Atlas de ícones (hero icons). |
| `HorizontalScrollArea` | ScrollArea com barra que trata wheel como scroll lateral (usado em listas de cards de fontes). |
| `SourceCard` | Card de fonte no dashboard. |
| `CollapsibleSection` | Seção colapsável. |
| `SortableTreeItem` | Item de árvore ordenável. |
| `VisibilityBadgeDelegate` | Delegate de badge público/privado. |
| `ResponsiveOutputControls` | Controles de saída responsivos. |
| `GlowButton` / `animated_button` | Botões animados. |
| `card()` / `page_header()` / `button()` | Factories de widgets. |
| `repair_mojibake` / `repair_mojibake_text` | Correção de encoding quebrado em textos. |
| `timestamp_sort_value` | Valor de ordenação de timestamp. |

**Sintoma-chave:** "quebra visual genérica" → localize a classe aqui (`SourceCard`, `SortableTreeItem`, `VisibilityBadgeDelegate`).


### ui/mixins/ — Comportamentos da MainWindow (lógica de tela)
Os mixins são **métodos da `MainWindow`** separados por responsabilidade. A `MainWindow` herda de todos. Cada mixin é ~18–36KB e concentra a maior parte da lógica de UI — `main_window.py` (126.6 KB, 132 métodos) apenas orquestra e mantém estado.

| Mixin | Responsabilidade | Sintoma típico |
|---|---|---|
| `source_mixin.py` (~30KB) | Lista/edita/salva fontes; detecta plataforma via URL; teste de lookup de página; import/export de perfil. Métodos: `apply_source`, `add_source`, `duplicate_source`, `remove_selected_sources`, `_preview_detected_source`, `_commit_source_from_form`, `_lookup_page_details`. | "fonte não salva/detecta" → aqui + `source_detection.py` |
| `connection_mixin.py` (~18KB) | Autenticação por modo (`public`/`basic`/`bearer`/`browser`); `test_connection`; `start_browser_login`; `remove_session`; armazena runtime secret. | "connexion/login não funciona" → aqui + `auth.py` |
| `selection_mixin.py` (~36KB) | Árvore de seleção: carrega contêineres, expande, filtra, marca/desmarca, inverte, coleta leafs. Métodos: `_populate_selection_tree`, `_selection_tree_item_expanded`, `_leaf_items`, `_set_selection`, `_invert_selection`, `_selection_changed`, `_apply_selection_state`. | "não marca/expande/filtra" → aqui + `tree_mixin.py` |
| `tree_mixin.py` (~4,4KB) | Ponte entre árvore e dados: `_tree_pages`, `_tree_containers`, `_lazy_state`, `_lazy_method`, `_page_visibility`. Decide síncrono vs lazy. | "árvore não carrega/expande" → aqui + conector |

**Regra de ouro:** ao depurar um problema de UI, o mixin costuma ser o primeiro lugar a procurar — antes do `main_window.py`. O `main_window.py` principalmente conecta mixins a widgets, embora possa conter handlers locais.

### ui/pages/ — Construtores de tela (uma por rota)
Cada `build_*_page(window) -> QWidget` monta a UI da rota. Recebem `window` (= `MainWindow`) para acessar mixins e estado. Em geral são **majoritariamente visuais** — a maior parte da lógica de comportamento costuma ficar em mixins/controllers, mas builders podem conter lógica leve e handlers locais; verifique o builder específico antes de assumir.

| Página | Builder | Tela correspondente |
|---|---|---|
| `dashboard_page.py` | `build_dashboard_page` | Painel inicial |
| `sources_page.py` | `build_sources_page` | Lista de fontes (seção 2) |
| `connection_page.py` | `build_connection_page` | Autenticação (seção 3) |
| `selection_page.py` | `build_selection_page` | Árvore de páginas (seção 4) |
| `review_page.py` | `build_review_page` | Prévia/extração (seção 5) |
| `markdown_page.py` | `build_markdown_page` | Opções Markdown (seção 6) |
| `consolidation_page.py` | `build_consolidation_page` | Consolidação (seção 7) |
| `extraction_page.py` | `build_extraction_page` | Disparo de extração |
| `results_page.py` | `build_results_page` | Resultados (seção 8) |

**Sintoma-chave:** "widget não aparece" ou "layout quebrado de uma tela" → aqui. "comportamento errado" → mixin correspondente, não aqui.

### ui/main_window.py — Orquestrador da MainWindow (126.6 KB, 2733 linhas, 132 métodos)
A `MainWindow` herda dos mixins (grande parte da lógica de comportamento) e orquestra: mantém estado (`MainWindowState`), constrói páginas, conecta sinais e gerencia workers. **Comece investigando o mixin correspondente** antes de procurar lógica aqui — embora existam handlers locais, a maior parte do comportamento está nos mixins.

**Por categoria de responsabilidade:**

| Categoria | Métodos representativos | Sintoma típico |
|---|---|---|
| **Builders de página** | `_dashboard_page`, `_sources_page`, `_connection_page`, `_selection_page`/`_pages_page`, `_markdown_page`, `_consolidation_page` (e `_legacy`), `_review_page` (e `_legacy`), `_extraction_page`, `_results_page`/`_output_page`, `_settings_page` | "tela não aparece" — mas a lógica está no mixin |
| **Navegação** | `_show_page(key)`, `_page_go_back`, `_source_card_clicked` | "click não navega" |
| **Carregamento de árvore** | `load_tree`, `_load_tree_via_connector`, `_load_all_containers`, `_load_container_for_source`, `_populate_page_tree(_lazy)`, `_load_document_children`, `_load_expanded_document` | "árvore não carrega/expande" |
| **Workers** | `_start_worker(function,...)`, `_on_progress`, `_worker_failed`, `_worker_finished`, `_operation_done`, closures `work`/`done` (5×) | "extração/consolidação trava" → aqui ou no mixin |
| **Prévia Markdown** | `_schedule_preview`, `_update_preview`, `_render_preview_mode`, `_load_markdown_controls`, `_sync_markdown_controls` | "prévia não atualiza" |
| **Consolidação** | `preview_consolidation`, `run_consolidation`, `_sync_consolidation_ui`/`_controls`, `_update_consolidation_summary`, `_render_consolidation_preview`, `_mark_consolidation_preview_stale`, `_consolidation_example_paths` | "consolidação não pré-visualiza/roda" |
| **Output/Resultados** | `_update_output_preview`, `_render_consolidation_preview`, `_page_stat`, `_set_page_stat`, `_refresh_page_summary` | "resultados não aparecem" |
| **Estado/Projeto** | `save_project`, `save_project_as`, `_load_project_ui`, `_sync_project_ui(strict=...)`, `_update_load_context`, propriedades `last_result`/`selection_store`/`last_consolidation_preview`/`connection_states` | "projeto não salva/carrega" |
| **Colunas/ restore** | `_move_page_column`, `_send_page_column`, `_restore_table_columns` | "colunas não restauram" |
| **Cancelamento/loading** | `_set_tree_loading(loading)`, `_cancel_tree_operation` | "loading não some", "cancelar não funciona" |
| **Serviço browser** | `_lazy_discovery_page`, `_browser_cache_path`, `_browser_cache_scope`, `_lazy_state`, `_lazy_method`, `_page_render_key` | "cache/lazy do browser" |

**Regra de ouro:** ao depurar comportamento, comece pelo mixin correspondente antes de atribuir ao `main_window.py`. Esta classe conecta sinais e orquestra; pode haver handlers locais, mas a maior parte do comportamento vive nos mixins.

> _main_window.py tem 132 métodos distribuídos em 8 categorias acima. Embora grande, é majoritariamente orquestração (conexão de sinais, estado e workers); o comportamento de maior peso está espalhado pelos 4 mixins (~87 KB no total), mas handlers locais existem e devem ser verificados._

---

## ENTRY POINTS, CONFIGURAÇÃO E SCRIPTS
Arquivos de entrada, configuração e manutenção do projeto, organizados por responsabilidade.

| Arquivo | Responsabilidade |
|---|---|
| `tools/legacy/alquimista_core.py` | Facade de compatibilidade. Re-exporta `ConfluenceClient`, modelos, serviços, storage, erros. Mantém nomes históricos p/ scripts antigos. **Detalhe:** docstring diz "Studio 5" mas o projeto é "3.0" — inconsistência a corrigir. |
| `tools/legacy/alquimista_gui.py` | Entry point legado da UI PySide6. Importa e expõe `run_app` de `alquimista.ui`. |
| `alquimista/__main__.py` | Entry point oficial: `python -m alquimista` inicia o fluxo completo. |
| `tools/legacy/alquimista_studio_completo.py` | Launcher legado do fluxo completo, mantido fora da raiz. |
| `tools/legacy/alquimista_studio_extrator.py` | Launcher legado → agora chama `run_app("complete")`. |
| `tools/legacy/alquimista_studio_consolidador.py` | Launcher legado → agora chama `run_app("complete")`. |
| `packaging/ALQuimista Studio.spec` | Spec do PyInstaller; inclui assets e catálogos `.qm`. |
| `packaging/ALQuimista Studio.iss` | Instalador Windows com idiomas e atalhos. |
| `tools/build/gerar_distribuicoes.ps1` | Gera Portable Windows e chama o instalador Inno Setup. |
| `tools/build/gerar_portable_linux.sh` | Gera o pacote Portable Linux `.tar.gz`. |
| `tools/install/instalar_windows.bat` / `tools/install/instalar_linux.sh` | Dependências de desenvolvimento; Linux também suporta `--install`. |
| `tools/install/instalar_navegador.bat` | Instala browsers Playwright. |
| `tools/legacy/test_alquimista_studio.py` | Launcher legado de pytest (apenas delega para `pytest`). Os testes reais ficam em `tests/` (19 arquivos, ver seção abaixo). |
| `docs/examples/config.example.json` | Config de exemplo. |
| `projeto_alquimista.json` | Projeto de demonstração. |
| `docs/archive/REFACTORING_SUMMARY.md` | Documento histórico do refactoring recente. |
| `tests/` | Suíte de testes (19 arquivos `test_*.py` + `conftest.py`): `test_auth`, `test_browser_cache`, `test_client`, `test_confluence_url`, `test_connectors`, `test_lazy_confluence`, `test_markdown`, `test_models_storage`, `test_process_workers`, `test_services`, `test_session_store`, `test_source_detection`, `test_ui*`, `test_fixes_regression`, `test_build_documentation`. Marker `integration` p/ APIs reais. |
| `docs/` | `architecture.md` + `connectors/<plataforma>.md` + `manifest-index.md` + `screenshots/` (PNGs das 9 telas). |
| `tools/` | `capture_ui.py`, `normalize_utf8.py` e scripts de distribuição/instalação. |
| `alquimista/ui/i18n.py` | Idiomas PT-BR/EN/ES, preferência portable/instalada e troca em runtime. |
| `assets/icons/` | `alchemist_icon_atlas.png` usado por `components.py:AlchemistIconAtlas`. |
| `ALQuimista_Base/` | Diretório reservado (vazio por padrão). Excluído do ruff/mypy. |
| `config/pyproject.toml` | Configuração ruff (py312, line 120, F/I/B) + mypy. |
| `config/pytest.ini` | `qt_api=pyside6`, `testpaths=tests`, markers (`real_confluence`, `integration`, `build`, `slow`). |
| `config/constraints.txt` | Versões fixas validadas p/ Python 3.12/Windows (reprodutível). |
| `config/requirements*.txt` | `requirements.txt` (runtime) + `-browser` + `-dev` + `.freeze`. |
| `config/python-version.txt` | `Python 3.12` ( usado por gerenciadores de versão). |
| `abrir_completo.bat` | Atalho Windows p/ abrir o fluxo completo. |

**Regra:** código novo vai em `alquimista/`. Facades e launchers legados ficam em `tools/legacy/`.

## DUPLICAÇÕES E ARMADILHAS (ATALHO DE EDIÇÃO)
Alguns módulos definem a MESMA função duas vezes. A segunda definição sobrescreve a primeira, que fica órfã/morta no arquivo. **Antes de editar uma dessas funções, localize todas as definições com `rg -n "^def <nome>" <arquivo>` e edite apenas a última (a ativa).**

| Arquivo | Função | Estado |
|---|---|---|
| `ui/mixins/selection_mixin.py` | `_populate_selection_tree`, `_leaf_items`, `_set_selection`, `_invert_selection`, `_selection_changed`, `_apply_selection_state`, `_filter_selection` | 7 duplicações; a primeira ocorrência de cada é **morta**, a última é a ativa. |
| `ui/mixins/connection_mixin.py` | `_connection_source_changed`, `enter_confluence`, `_store_runtime_secret` | 3 duplicações; última ocorrência é a ativa. |
| `ui/execution_controller.py` | `validated_project_snapshot` | Definida duas vezes no arquivo; a **primeira** ocorrência é wrapper simples **morto**, a **segunda** é a implementação ativa com validação completa. |
| `auth.py` | `browser_login` | Definida duas vezes no arquivo; a **primeira** ocorrência é **morta**, a **segunda** é a ativa. |

### Sem referências estáticas encontradas
- `ui/page_registry.py` e `ui/process_workers.py` não aparecem em imports estáticos do pacote (`rg -n "page_registry|process_workers"`). Mantidos como código reserva; podem ser invocados dinamicamente ou reativados futuramente — se uma funcionalidade de roteamento/workers de processo for ativada, comece por aqui.


## COMO PEDIR PRA IA TRABALHAR — Fórmulas práticas

### Template básico
> "Problema na **<tela>**: <sintoma>. Comece investigando **<arquivo>**."

### Por sintoma (quando não souber a tela)
> "O programa está <sintoma>. Qual arquivo investigar?"

### Por arquivo (quando já souber)
> "Comece investigando `<arquivo>`, função `<função>`. Quero que <mudança>."

### Exemplos comuns
- "Na **seleção**, a árvore não carrega filhos ao expandir. Comece investigando `tree_mixin.py` e `confluence.py`."
- "Na **conexão**, o login pelo navegador não fecha. Comece investigando `auth.py`."
- "Na **markdown**, as tabelas saem quebradas. Comece investigando `markdown.py`."
- "Na **consolidação**, o índice do pacote está errado. Comece investigando `services.py`."
- "Na **fontes**, não detecta GitBook pela URL. Comece investigando `source_detection.py`."
- "Na **seleção**, páginas vêm fora de ordem. Comece investigando `tree_models.py`."
- "Na **extração**, não cancela. Comece investigando `runtime.py`."

### Quando o problema é visual/layout
> "Na **<tela>**, <elemento> está <visual errado>. Comece investigando `pages/<tela>.py` e `components.py`."

### Quando o problema é de autenticação
> "Na **conexão**, <erro de auth>. Comece investigando `connection_mixin.py`, `auth.py` e `connectors/<plataforma>.py`."

---

## OBSERVAÇÕES IMPORTANTES

1. **main_window.py é o orquestrador** (126.6 KB, 132 métodos). Se a tela não tiver arquivo em `pages/`, o comportamento está em `main_window.py`.
2. **Mixins** extraem comportamento da MainWindow: `selection_mixin.py` (seleção), `source_mixin.py` (CRUD fontes), `connection_mixin.py` (auth), `tree_mixin.py` (lazy loading).
3. **Conectores** seguem o ABC em `connectors/base.py`. O Confluence é o mais completo. Demais (GitBook/Notion/SharePoint/Zendesk) implementam as mesmas operações mas podem não ter lazy loading.
4. **Segredos nunca persistem**: `controllers.py:RuntimeSecrets` mantém em memória. `session_store.py` é efêmero.
5. **Atualização incremental** usa SHA-256 em `services.py` + `manifest_index.py`.
6. **Facades de compatibilidade** (`alquimista_*.py` na raiz): usar só p/ scripts antigos. Código novo vai em `alquimista/`.
7. **`.bat` e `.spec`** são setup Windows / PyInstaller. Raramente precisam alteração salvo mudar dependências ou ícone do exe.
