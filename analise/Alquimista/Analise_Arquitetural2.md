# Análise Arquitetural — ALQuimista Studio

**Base da análise:** código real clonado de `https://github.com/luan146/Alquimista-Studio`
(commit `069e828`, branch principal, 12/08/2026), cruzado com o `MAPA.md` e `AGENTS.md`
do próprio repositório e com os arquivos que você enviou.

**Nota sobre os arquivos enviados:** o `MAPA.md` que você anexou não é o mapa de código do
projeto — é o prompt gigante de solicitação desta análise (32 seções, "atue como arquiteto
sênior..."). O `MAPA.md` real do repositório é outro documento, de 1035 linhas, bem mantido,
com uma tabela "quero mudar X → onde investigar" e um mapa arquitetural correto. Usei o real.
Também notei que o `README.md` que você enviou descreve uma reorganização de diretórios
(`tools/install/`, `config/`, `packaging/`) que **ainda não existe no repositório** — o repo
real ainda tem os scripts e configs na raiz (`instalar_windows.bat`, `constraints.txt`,
`pytest.ini` etc.), exatamente como o workflow de CI espera. Ou seja: aqui é a documentação
que está *à frente* do código, não atrasada — o inverso do que normalmente se vê. Vale
alinhar antes de continuar editando o README.

---

## 1. Resumo executivo

**Estado atual:** o projeto já passou por um refactor arquitetural real, não é um monólito
ingênuo. Existem um contrato ABC de conector (`connectors/base.py`), um modelo intermediário
independente de plataforma (`models.py`: `KnowledgeDocument`, `KnowledgeContainer`,
`KnowledgeSource`), um registry com factory (`connectors/registry.py`) e um pipeline de
extração genérico (`services.py::_run_generic`) que trata todos os conectores da mesma forma.
Isso é exatamente a arquitetura que a seção 6 do seu prompt perguntava se valia a pena
construir — **ela já existe**, em grande parte.

**Principal risco:** a migração para essa arquitetura está **incompleta e assimétrica**.
O Confluence — o conector "estável" — não usa a camada HTTP compartilhada
(`connectors/http.py::ApiHttpClient`) nem o renderizador de Markdown compartilhado
(`markdown.py::KnowledgeDocumentRenderer`). Ele mantém seu próprio cliente HTTP legado
(`client.py::ConfluenceClient`, 592 linhas) e seu próprio transformador de Markdown
(`markdown.py::MarkdownTransformer`), enquanto GitBook, Zendesk, Notion e SharePoint usam a
camada nova. Isso **isola acidentalmente** o Confluence de regressões vindas dos outros
conectores — o que é bom para o medo que você descreveu — mas ao custo de manter duas
implementações de retry/rate-limit/tratamento de erro HTTP, e dois formatadores de Markdown,
vivendo lado a lado sem um teste de regressão (golden sample) que garanta que ambos os
caminhos continuam produzindo o resultado esperado.

**Principal oportunidade:** formalizar essa fronteira em vez de tentar unificá-la às pressas.
O maior ganho de baixo risco não é "separar leitores por plataforma" (isso já está feito) nem
"criar um modelo intermediário" (já existe) — é **matar código morto que ainda é testado e
mantido** (um pipeline de extração legado inteiro, um builder de runtime legado, dois
arquivos de UI órfãos) e **substituir 4 ocorrências de uma lista mágica de strings dentro do
`main_window.py`** pela informação que já existe no registry.

**Recomendação arquitetural central:** não reescrever nada agora. Escrever testes de
regressão (golden samples) para o Confluence *antes* de tocar em `client.py` ou
`MarkdownTransformer`, remover os três blocos de código morto identificados, e só então
decidir se vale a pena migrar o Confluence para a camada HTTP/Markdown compartilhada.

---

## 2. Como o projeto funciona atualmente

### 2.1 Pipeline real (caminho de produção, via UI)

```
URL colada pelo usuário
        │
source_detection.py:detect_source_url()        ← detecta plataforma por padrão de host
        │
SourceConfig (models.py)                        ← persistido no projeto
        │
ui/mixins/connection_mixin.py + auth.py         ← autenticação (browser/basic/bearer)
        │
ui/main_window.py._load_tree() 
        │
        ├── source_type in {confluence_rest, gitbook_api, zendesk_guide}
        │        → connector_registry.create() → KnowledgeSourceConnector
        │        → connector.list_containers() / list_documents()
        │
        └── (fallback, mesmo arquivo) → ConfluenceClient direto  ← só ainda serve Confluence
        │
ui/mixins/selection_mixin.py + tree_models.py    ← árvore de seleção do usuário
        │
ui/execution_controller.py
        │
ui/controllers.py:RuntimeBuilder.build_connectors()   ← ÚNICO caminho usado em produção
        │
services.py:ExtractionService.run() → _run()
        │
        └── _run_generic()  (sempre, pois connector nunca é None neste caminho)
                │
                ├── connector.get_document()          ← específico por plataforma
                ├── connector.normalize_document()     ← específico por plataforma
                ├── markdown.py:KnowledgeDocumentRenderer.render()   ← genérico
                └── storage.py (persistência atômica) + manifest_index.py (incremental)
        │
services.py:ConsolidationService                 ← agrupamento/pacotes (genérico)
        │
reports.py:ExecutionReport                        ← relatório final
```

### 2.2 Pipeline "fantasma" (existe no código, não é usado pela UI)

```
ui/controllers.py:RuntimeBuilder.build()   ← usa ConfluenceClient direto, sem connector
        │
services.py:ExtractionService._run_legacy()
        │
markdown.py:MarkdownTransformer            ← parser de storage-format do Confluence
```

Este segundo caminho só é exercitado por `tests/test_ui_controllers.py`
(`RuntimeBuilder(...).build(...)`, linhas 41 e 72). Nenhum ponto do `main_window.py` ou dos
`mixins/` chama `RuntimeBuilder.build()` — apenas `build_connectors()`
(`ui/execution_controller.py:22`). **Fato observado, não hipótese**: `grep` por
`RuntimeBuilder(` e `.build(` no pacote `alquimista/` mostra exatamente duas ocorrências, ambas
em `controllers.py`, e nenhum chamador de `.build()` fora dos testes.

### 2.3 Divergência real entre Confluence e os demais conectores

| Camada | Confluence | GitBook / Zendesk / Notion / SharePoint |
|---|---|---|
| Cliente HTTP | `client.py::ConfluenceClient` (592 linhas, próprio) | `connectors/http.py::ApiHttpClient` (compartilhado) |
| Renderização Markdown | `markdown.py::MarkdownTransformer` (parser de `ac:*`/`ri:*` do storage format) | `markdown.py::KnowledgeDocumentRenderer` (genérico, baseado em `KnowledgeDocument`) |
| Contrato de conector | `connectors/confluence.py::ConfluenceRestConnector(KnowledgeSourceConnector)` | idem — todos implementam o mesmo ABC |
| Erros | `ConfluenceConnectionError`, `RateLimitError` (hierarquia própria) | `ApiConnectionError`, `ApiRateLimitError` (hierarquia própria) |

Isto é o achado central da análise: **o contrato de alto nível (o ABC) já é compartilhado por
todos os conectores**, mas **as engrenagens internas de HTTP e de renderização não são** — o
Confluence tem as suas próprias, paralelas às dos outros quatro conectores.

---

## 3. Mapa de responsabilidades (núcleo, sem UI)

| Arquivo | Linhas | Responsabilidade | Classificação |
|---|---:|---|---|
| `models.py` | 552 | Contratos de dados (Pydantic): `SourceConfig`, `KnowledgeDocument`, `ProjectConfig`, `ManifestEntry` etc. | CORE COMPARTILHADO |
| `connectors/base.py` | 122 | ABC `KnowledgeSourceConnector` — contrato mínimo entre core e conector | CORE COMPARTILHADO / CONTRATO |
| `connectors/registry.py` | 189 | Factory + descriptor de conectores, capacidades, status | CORE COMPARTILHADO / INFRAESTRUTURA |
| `connectors/http.py` | 253 | Cliente HTTP com retry, backoff, rate limit, mapeamento de erros | CORE COMPARTILHADO (usado por 4 de 5 conectores) |
| `connectors/confluence.py` | 722 | Conector Confluence (containers, páginas, lazy discovery, CQL, visibilidade) | CONNECTOR-SPECIFIC |
| `connectors/gitbook.py` | 350 | Conector GitBook | CONNECTOR-SPECIFIC |
| `connectors/zendesk.py` | 366 | Conector Zendesk Guide | CONNECTOR-SPECIFIC |
| `connectors/notion.py` | 221 | Conector Notion (stub, `implemented=False`) | CONNECTOR-SPECIFIC |
| `connectors/sharepoint.py` | 159 | Conector SharePoint (stub, `implemented=False`) | CONNECTOR-SPECIFIC |
| `client.py` | 592 | Cliente HTTP legado, exclusivo do Confluence | LEGADO — CONNECTOR-SPECIFIC (deveria estar dentro de `connectors/confluence.py` ou usar `http.py`) |
| `markdown.py` | 511 | Duas classes: `MarkdownTransformer` (legado, Confluence) e `KnowledgeDocumentRenderer` (genérico) | MISTO — ver seção 6 |
| `services.py` | 1234 | `ExtractionService` (extração incremental, hashing, manifest) e `ConsolidationService` (agrupamento de pacotes) | CORE COMPARTILHADO (com um ramal morto — `_run_legacy`) |
| `storage.py` | — | Persistência atômica de arquivos/projeto | CORE COMPARTILHADO / INFRAESTRUTURA |
| `manifest_index.py` | — | Índice para atualização incremental | CORE COMPARTILHADO |
| `browser/*.py` | ~1365 | Descoberta assistida por navegador (Playwright), cache SQLite de metadados | CORE COMPARTILHADO — **zero menções a nomes de plataforma**, bem isolado |
| `auth.py` | — | Login por browser/basic/bearer | CORE COMPARTILHADO — **zero menções a nomes de plataforma** |
| `source_detection.py` | 141 | Detecta plataforma pela URL | CORE COMPARTILHADO, mas cresce a cada conector (se/elif por host) |
| `errors.py` | 54 | Hierarquia de exceções | CORE COMPARTILHADO — mas com duas ramificações paralelas (ver §4) |

### 3.1 UI (PySide6)

| Arquivo | Linhas | Responsabilidade |
|---|---:|---|
| `ui/main_window.py` | 2942 | Orquestração geral, ainda concentra chamadas a conectores e ao `ConfluenceClient` legado |
| `ui/mixins/source_mixin.py` | 715 | CRUD de fontes |
| `ui/mixins/selection_mixin.py` | 632 | Árvore de seleção |
| `ui/mixins/connection_mixin.py` | 336 | Autenticação |
| `ui/mixins/tree_mixin.py` | 128 | Lazy loading da árvore (citado no `AGENTS.md` como "preparado para uso futuro" desde o `REFACTORING_SUMMARY.md` de 01/08) |
| `ui/execution_controller.py` | — | Prepara runtimes de extração (chama `build_connectors`) |
| `ui/controllers.py` | 201 | `RuntimeBuilder` (dois métodos: um morto, um vivo) e `RuntimeSecrets` |
| `ui/operation_controller.py` + `ui/workers.py` | — | Mecanismo real de workers em thread pool (ativo) |
| `ui/process_workers.py` | — | **Sem nenhum import em `alquimista/`** — órfão, mas com teste próprio (`tests/test_process_workers.py`) |
| `ui/page_registry.py` | — | **Sem nenhum import em `alquimista/`** — órfão |
| `ui/pages/*.py` | ~1400 | Uma tela por arquivo, delegam a mixins/controllers |

O `AGENTS.md` do próprio projeto já desconfiava disso: ele instrui explicitamente a "não
presumir que `ui/process_workers.py` ou `ui/page_registry.py` estão ativos apenas porque
existem". Confirmei com `grep` que, de fato, não há nenhum caller — a suspeita do time estava
certa.

---

## 4. Problemas encontrados (por severidade)

### P0 — Risco crítico

**P0-1. Pipeline de extração duplicado, um dos dois caminhos morto em produção mas vivo em testes.**
`services.py` tem `_run_generic()` (linhas 317–582, usado sempre em produção) e
`_run_legacy()` (linhas 600–882, ~280 linhas, só acionado se `runtime.connector is None`, o
que só acontece via `RuntimeBuilder.build()` — que só é chamado em
`tests/test_ui_controllers.py`). Isso não quebra nada hoje, mas é uma armadilha: qualquer
pessoa (ou IA) que "conserte um bug na extração" olhando só para `_run_legacy` está mexendo em
código morto sem saber, e qualquer um que rode `pytest` vê os testes passando e presume que o
caminho legado ainda importa. **Fato observado**, não hipótese — confirmado por grep cruzado
entre `services.py`, `controllers.py` e `execution_controller.py`.

**P0-2. Lista mágica de plataformas "implementadas" duplicada 4 vezes na UI.**
`ui/main_window.py` linhas ~1443, ~1509 (vizinha), ~1617 e ~1700 repetem literalmente
`source.source_type in {"confluence_rest", "gitbook_api", "zendesk_guide"}` para decidir se
usa o conector novo ou cai para o `ConfluenceClient` direto. Esse conjunto é **exatamente**
igual ao conjunto de conectores com `implemented=True` em `connectors/registry.py`. Hoje
funciona porque alguém manteve as duas listas sincronizadas manualmente. No dia em que Notion
ou SharePoint forem finalizados (`implemented=True` no registry), será fácil esquecer de
atualizar uma das 4 ocorrências em `main_window.py`, e a tela vai continuar chamando o
`ConfluenceClient` para uma fonte que não é Confluence, ou pior, silenciosamente não usar o
conector novo. **Este é exatamente o padrão `if connector == "confluence": ... elif ...` que
você queria eliminar — só que como `in {...}` em vez de `if/elif`.**

### P1 — Importante

**P1-1. Confluence não compartilha a camada HTTP nem a camada de renderização com os outros
4 conectores** (detalhado na seção 2.3). Duas implementações de retry/backoff/rate-limit
(`client.py` vs `connectors/http.py`) e duas de renderização de Markdown (`MarkdownTransformer`
vs `KnowledgeDocumentRenderer`) precisam ser mantidas e testadas separadamente. Correções de
segurança ou de comportamento (ex.: tratamento de `Retry-After`, redação de segredos em log)
feitas em uma não chegam automaticamente na outra.

**P1-2. Hierarquia de erros duplicada.** `errors.py` tem `ConfluenceConnectionError` (base
histórica, da qual herdam `RateLimitError` e `InvalidResponseError`) e, em paralelo,
`ApiConnectionError`/`ApiRateLimitError` (usados por `connectors/http.py`). Um `except
AlquimistaError` genérico captura ambos, então não quebra nada — mas um `except
ApiConnectionError` no código novo **não captura** um erro do caminho legado do Confluence, e
vice-versa. Se algum dia alguém adicionar tratamento específico de rate limit em um lugar,
pode esquecer o outro.

**P1-3. `markdown.py` mistura duas responsabilidades num único arquivo** — o parser de
storage-format do Confluence (`ac:link`, `ac:image`, `ac:structured-macro`, `ri:attachment`)
convive com o renderizador genérico. Não é urgente separar (ver §14), mas any novo
desenvolvedor abrindo este arquivo para mexer em "Markdown" (função genérica) pode acabar
lendo/editando lógica de parsing específica do Confluence sem perceber a fronteira.

### P2 — Melhoria desejável

**P2-1.** `connectors/http.py::_download_compat` — método completo (linhas 127–167),
comentado como "compatibility alias for older connector code", **sem nenhum chamador** no
repositório inteiro. Código morto duplicado byte a byte do método `download()` logo acima.

**P2-2.** `ui/process_workers.py` e `ui/page_registry.py` — confirmado sem callers. O primeiro
ainda tem suíte de teste própria (`tests/test_process_workers.py`), o que mascara o fato de
estar desconectado da aplicação.

**P2-3.** `main_window.py` com 2942 linhas. Já caiu de ~4046 (registrado no próprio
`REFACTORING_SUMMARY.md`, datado de 01/08) através da extração de `selection_mixin.py`,
`source_mixin.py` e `connection_mixin.py`. O documento já lista os próximos passos
(`worker_mixin.py`, `consolidation_controller.py`) como pendentes — a refatoração está em
andamento, não estagnada.

**P2-4.** Ausência de testes "golden sample" (comparação de Markdown final byte a byte) por
conector. Existem testes bons com fakes/mocks que verificam que GitBook e Zendesk "passam pelo
pipeline incremental comum" (`test_gitbook_runs_through_common_incremental_markdown_pipeline`,
`test_zendesk_guide_runs_through_incremental_markdown_pipeline`), o que já é uma proteção
razoável contra regressão estrutural — mas não há um arquivo de Markdown "esperado" salvo em
disco para detectar mudanças sutis de formatação.

### P3 — Futuro

**P3-1.** `source_detection.py` é uma cadeia de `if/elif` por host (uma por plataforma). Hoje,
com 5–6 plataformas, é perfeitamente legível e de baixo risco. Se o projeto chegar a 15–20
conectores (incluindo Generic Web, que precisa de heurísticas mais complexas que "olhar o
host"), vale considerar um registro de detectores plugável — não antes disso.

---

## 5. Hotspots e blast radius

| # | Hotspot | Arquivo/módulo | Blast radius | Prioridade |
|---|---|---|---|---|
| 1 | Pipeline duplicado (`_run_generic`/`_run_legacy`) | `services.py` | **ALTO** — qualquer fix aplicado só no ramo errado passa despercebido nos testes | P0 |
| 2 | Lista mágica de conectores implementados (4 ocorrências) | `ui/main_window.py` | **ALTO** — decide qual caminho de rede a UI usa; drift silencioso ao ativar novo conector | P0 |
| 3 | HTTP/retry duplicado (Confluence vs demais) | `client.py` + `connectors/http.py` | **MÉDIO-ALTO** — Confluence é o conector "estável"; qualquer correção de confiabilidade feita só em um lado não protege o outro | P1 |
| 4 | Duas hierarquias de erro | `errors.py` | **MÉDIO** — captura de exceção específica pode ficar incompleta | P1 |
| 5 | `MarkdownTransformer` + `KnowledgeDocumentRenderer` no mesmo arquivo | `markdown.py` | **MÉDIO** — risco de edição cruzada por engano | P1 |
| 6 | `ExtractionService` (1234 linhas, muitas responsabilidades: extração, hash, manifest, relatório) | `services.py` | **MÉDIO** — arquivo central, tocado por quase toda mudança de pipeline | P1/P2 |
| 7 | `_download_compat` morto | `connectors/http.py` | **BAIXO** — sem chamadores, mas confunde leitura | P2 |
| 8 | `ui/process_workers.py`, `ui/page_registry.py` órfãos | `ui/` | **BAIXO** (não são executados) mas **alto risco de confusão** para quem edita achando que estão ativos | P2 |
| 9 | `main_window.py` ainda com 2942 linhas | `ui/main_window.py` | **MÉDIO** — mistura orquestração de várias plataformas, embora já bem melhor que antes | P2 |
| 10 | `source_detection.py` como if/elif crescente | `source_detection.py` | **BAIXO hoje**, crescente com escala | P3 |

---

## 6. Shared Core vs Connector-Specific (o que já está certo)

| Componente | Classificação real hoje | Está correto? |
|---|---|---|
| Modelo de dados (`KnowledgeDocument` etc.) | CORE COMPARTILHADO | ✅ Sim — já é o "modelo intermediário" da seção 8 do seu prompt |
| Contrato de conector (ABC) | CONTRATO | ✅ Sim — já responde à pergunta da seção 7 |
| Descoberta/paginação de páginas | CONNECTOR-SPECIFIC (dentro do próprio arquivo de cada conector) | ✅ Sim — cada conector implementa `list_containers`/`list_documents`/lazy discovery à sua maneira; nenhum "page_reader.py" genérico tentando servir a todos |
| Parsing de conteúdo (HTML/storage-format → texto) | CONNECTOR-SPECIFIC (`normalize_document` de cada conector) + CORE (BeautifulSoup/markdownify como utilitário) | ✅ Sim |
| Renderização final do Markdown (frontmatter, cabeçalhos, hashing) | CORE COMPARTILHADO — mas só para 4 dos 5 conectores (`KnowledgeDocumentRenderer`) | ⚠️ Parcial — Confluence usa `MarkdownTransformer` à parte |
| HTTP/retry/rate limit | CORE COMPARTILHADO — mas só para 4 dos 5 conectores (`ApiHttpClient`) | ⚠️ Parcial — Confluence usa `ConfluenceClient` à parte |
| Consolidação de pacotes | CORE COMPARTILHADO (`ConsolidationService`) | ✅ Sim — nenhuma menção a nome de plataforma encontrada |
| Autenticação (browser/basic/bearer) | CORE COMPARTILHADO (`auth.py`) | ✅ Sim — zero acoplamento a plataforma |
| Cache/descoberta via browser | CORE COMPARTILHADO (`browser/*.py`) | ✅ Sim — zero acoplamento a plataforma |
| Detecção de fonte pela URL | CORE COMPARTILHADO, mas com um `if/elif` por plataforma | ✅ Aceitável na escala atual |
| Persistência/manifest/hash incremental | CORE COMPARTILHADO | ✅ Sim |
| Logging com redação de segredos | CORE COMPARTILHADO (`logging_utils.py`) | ✅ Sim |
| Registry/Factory de conectores | INFRAESTRUTURA | ✅ Sim, e é o ponto certo para expandir capacidades sem `if/elif` |

**Conclusão desta seção:** a divisão CORE vs CONNECTOR-SPECIFIC que você imaginava no seu
prompt já foi feita corretamente para descoberta, paginação, parsing, consolidação, auth e
persistência. O único ponto onde a "linha compartilhada" ainda não inclui todos os conectores
é justamente HTTP e renderização de Markdown — e só porque o Confluence ficou de fora, não
porque a ideia esteja errada.

---

## 7. Arquitetura recomendada

Não recomendo uma nova camada de arquitetura. Recomendo **terminar a que já existe**, com uma
ordem de operações que protege o Confluence. Diagrama do estado-alvo (mudanças em relação ao
estado atual estão marcadas com `*`):

```
                         ┌──────────────┐
                         │      UI      │  (main_window + mixins + pages)
                         └──────┬───────┘
                                │  *usa apenas connector_registry.implemented,
                                │   nunca mais uma lista literal de source_types
                         ┌──────▼───────┐
                         │ Application  │  RuntimeBuilder.build_connectors() [único caminho]
                         └──────┬───────┘   *build() legado removido após período de garantia
                                │
                         ┌──────▼───────┐
                         │   Pipeline   │  ExtractionService._run_generic() [único caminho]
                         └──────┬───────┘   *_run_legacy removido após golden samples no lugar
                                │
        ┌───────────────────────┼───────────────────────┬─────────────────┐
        ↓                       ↓                       ↓                 ↓
   Confluence               GitBook                 Zendesk        Notion/SharePoint
        │                       │                       │                 │
        └───────────────────────┼───────────────────────┴─────────────────┘
                                │
                    ┌───────────▼────────────┐
                    │      Shared Core        │
                    │  ApiHttpClient (http.py)│  *Confluence passa a usar este cliente
                    │  KnowledgeDocumentRend. │  *Confluence passa a usar este renderer
                    │  models / storage /     │   — SOMENTE depois de golden samples
                    │  manifest_index / auth  │
                    └─────────────────────────┘
```

Note que isso **não** é "separar leitores por plataforma em subpastas" — isso já está feito
(cada conector é um arquivo próprio, autocontido, implementando o mesmo ABC). A mudança
recomendada é a direção oposta: **puxar o Confluence para dentro do core compartilhado que os
outros quatro já usam**, e só depois disso considerar qualquer nova camada.

---

## 8. Estrutura de diretórios

A estrutura atual já é adequada para o tamanho do projeto. Não recomendo criar
`connectors/confluence/`, `connectors/notion/` etc. como subpacotes — com 5 conectores entre
150 e 720 linhas cada, um arquivo por conector é mais fácil de navegar do que uma árvore de
subpastas com 3-4 arquivos cada. Essa reorganização só se paga a partir de ~10 conectores, ou
quando um conector individual ultrapassar ~1000-1500 linhas (o Confluence, com 722 linhas, já
está perto — se crescer mais, aí sim vale dividir em
`connectors/confluence/{connector.py, discovery.py, visibility.py}`).

Duas mudanças pequenas e de baixo risco na estrutura:

```
alquimista/
├── client.py              # RENOMEAR/MOVER para connectors/confluence_client.py
│                           # (deixa explícito que é parte do conector Confluence,
│                           #  não um cliente genérico "solto" na raiz do pacote)
├── markdown.py             # DIVIDIR (ver seção 14) em:
│   ├── markdown.py         #   KnowledgeDocumentRenderer + normalize_markdown (genérico)
│   └── connectors/confluence_markup.py  # MarkdownTransformer (parser ac:*/ri:*)
```

Fora isso, a árvore atual (`connectors/`, `browser/`, `ui/mixins/`, `ui/pages/`) já reflete
bem as responsabilidades reais do código.

---

## 9. Contratos/interfaces recomendados

O contrato principal (`KnowledgeSourceConnector`) já está bom e não precisa mudar. A única
adição pequena que recomendo é formalizar, no próprio registry, a checagem que hoje está
espalhada como literal na UI:

```python
# connectors/registry.py — método já existe parcialmente (`operational`), só falta
# um atalho explícito para o caso de uso da UI:

class ConnectorRegistry:
    def uses_native_connector(self, source_type: str) -> bool:
        """True quando a UI deve usar o connector novo em vez do fallback legado."""
        try:
            return self.get(source_type).implemented
        except ValueError:
            return False
```

E em `main_window.py`, as 4 ocorrências de
`source.source_type in {"confluence_rest", "gitbook_api", "zendesk_guide"}` viram:

```python
if self.connector_registry.uses_native_connector(source.source_type):
    ...
```

Isso elimina a lista mágica sem tocar em nenhuma lógica de negócio — puramente uma
substituição de uma verdade duplicada por uma única fonte de verdade que já existe.

---

## 10. Estratégia contra regressões

O projeto já tem uma base de testes decente (21 arquivos, ~4660 linhas), incluindo testes que
verificam que GitBook e Zendesk passam pelo "pipeline incremental comum". O que falta é
proteção no nível de **saída final** (o Markdown gerado), que é o que mais importa para você
como usuário do produto.

**Antes de qualquer refatoração no Confluence** (mover para `ApiHttpClient` ou para
`KnowledgeDocumentRenderer`), proponho:

1. **Golden samples do Confluence.** Capturar 3-5 páginas reais (ou fixtures já usadas em
   `tests/test_connectors.py::FakeConfluenceClient`) e salvar o Markdown final esperado em
   `tests/fixtures/confluence/expected/*.md`. Um teste compara byte a byte (com normalização
   de campos voláteis: timestamps, hash, `collected_at`).
2. **Repetir para GitBook e Zendesk**, que já têm fakes prontos — é questão de salvar o
   resultado esperado em disco em vez de só afirmar propriedades no teste.
3. **Só então** avaliar migrar Confluence para `ApiHttpClient`/`KnowledgeDocumentRenderer`,
   rodando os golden samples a cada mudança.
4. **CI**: o workflow atual (`.github/workflows/quality.yml`) já roda ruff, mypy, pytest e
   build do executável a cada push — é uma boa base. Adicionar os golden samples como testes
   normais do pytest não exige mudança na esteira.

Não recomendo criar `tests/confluence/fixtures/`, `tests/notion/fixtures/` como diretórios
paralelos por conector agora — o padrão atual (um `test_connectors.py` com fakes por classe)
já funciona bem para 5 conectores. Vale reorganizar em pastas por conector só se
`test_connectors.py` continuar crescendo (hoje já tem quase 1000 linhas).

---

## 11. Estratégia para Generic Web

Hoje não há nenhum código de Generic Web — está corretamente listado no README como
"Planejado" e não há sequer um stub em `connectors/`. A boa notícia é que a arquitetura atual
já comporta isso sem mudança estrutural:

- **Onde entra:** um novo arquivo `connectors/web.py` com uma classe
  `GenericWebConnector(KnowledgeSourceConnector)`, registrado em `registry.py` como qualquer
  outro conector, com `implemented=False` até ficar pronto.
- **O que muda em relação aos conectores atuais:** Generic Web não tem uma API estruturada
  (containers/documentos com IDs estáveis) — ele vai precisar de crawling e de heurísticas de
  "isso é um link interno relevante ou não". Isso é diferente o bastante do resto para
  justificar um componente auxiliar próprio (ex.: `connectors/web_crawl.py` com lógica de
  sitemap/robots/canonical), mas ainda cabe atrás do mesmo `KnowledgeSourceConnector`:
  `discover()`/`list_containers()` fariam o crawling, `get_document()` buscaria uma página,
  `normalize_document()` faria a limpeza de HTML de site genérico (provavelmente reusando
  BeautifulSoup, já uma dependência do projeto).
- **JS/SPA:** o projeto já tem uma camada de browser embutido via Playwright
  (`browser/adapters.py`, `browser/service.py`) usada hoje para autenticação e discovery
  assistida. Ela já é plataforma-neutra — dá para reaproveitá-la para renderizar páginas
  JS-pesadas do Generic Web, em vez de criar um segundo motor de browser.
- **Rate limit/robots/retries:** usar `ApiHttpClient` (a camada compartilhada, a mesma que já
  serve GitBook/Zendesk/Notion/SharePoint) — mais um motivo para não deixar essa camada
  divergir do Confluence, ou o Generic Web herdaria a mesma inconsistência.

Não é necessário implementar nada disso agora — só evitar que o trabalho de destravar o
Confluence do `client.py` legado seja adiado indefinidamente, porque o Generic Web vai
precisar exatamente da camada HTTP compartilhada que hoje só 4 dos 5 conectores usam.

---

## 12. Plano incremental de refatoração

| Etapa | Objetivo | Arquivos afetados | Risco | Benefício | Pré-requisito | Como validar |
|---|---|---|---|---|---|---|
| **0** | Golden samples do Confluence, GitBook, Zendesk | `tests/fixtures/*/expected/*.md` (novos) | Baixo | Alto — rede de segurança para tudo que vem depois | Nenhum | `pytest` verde com os novos testes |
| **1** | Substituir a lista mágica de 4 ocorrências em `main_window.py` por `registry.uses_native_connector()` | `main_window.py`, `registry.py` | Baixo | Médio — elimina duplicação de verdade | Etapa 0 (para detectar qualquer efeito colateral) | Rodar app manualmente com Confluence e GitBook; testes de UI existentes |
| **2** | Remover `_run_legacy`, `RuntimeBuilder.build()`, `_adapt_legacy_runtimes` e seus testes dedicados | `services.py`, `controllers.py`, `tests/test_ui_controllers.py` | Baixo-Médio | Alto — reduz ~350 linhas de código morto e a confusão associada | Confirmar (via grep, já feito aqui) que não há caller em produção | `pytest`, `mypy`, `ruff` verdes; grep confirma ausência de novos usos |
| **3** | Remover ou reativar `ui/process_workers.py` e `ui/page_registry.py` | `ui/process_workers.py`, `ui/page_registry.py`, `tests/test_process_workers.py` | Baixo | Médio — remove ambiguidade sobre o que está "vivo" | Confirmar com o mantenedor se havia algum plano de uso futuro | Build + testes verdes após remoção |
| **4** | Unificar hierarquia de erros (`ApiConnectionError` como base única; `ConfluenceConnectionError` vira alias/subclasse) | `errors.py`, `client.py`, `connectors/http.py` | Médio | Médio — evita `except` incompletos | Etapa 0 | Testes de erro existentes + novos golden samples |
| **5** | Migrar `ConfluenceRestConnector` para usar `ApiHttpClient` em vez de `ConfluenceClient` | `client.py` → mesclado em `connectors/confluence.py` ou `connectors/confluence_client.py` | Médio-Alto | Alto — remove a última duplicação de HTTP/retry | Etapas 0 e 4, golden samples passando a cada commit intermediário | Golden samples do Confluence continuam batendo byte a byte |
| **6** | Migrar renderização do Confluence de `MarkdownTransformer` para `KnowledgeDocumentRenderer` | `markdown.py` | Alto | Alto — um único renderizador para todos os conectores | Etapa 5 concluída e estável | Golden samples do Confluence continuam batendo |
| **7** | Adicionar `connectors/web.py` (Generic Web), inicialmente `implemented=False` | `connectors/web.py`, `registry.py`, `source_detection.py` | Baixo (isolado, desligado) | Alto (prepara o roadmap) | Etapas 5 e 6 (para herdar a camada HTTP unificada) | Testes unitários do novo conector, sem integração com UI ainda |

As etapas 5 e 6 são as únicas de risco médio/alto — e só porque tocam no conector que hoje
"funciona bem", exatamente o que você pediu para proteger. Por isso elas vêm depois de todas
as redes de segurança (golden samples) estarem no lugar, e podem ser adiadas indefinidamente
sem prejuízo — as etapas 0 a 4 já entregam a maior parte do benefício (remoção de ambiguidade
e de código morto) com risco baixo.

---

## 13. Tabela de prioridades

| Prioridade | Mudança | Benefício | Risco | Esforço |
|---|---|---|---|---|
| P0 | Golden samples (Etapa 0) | Alto | Baixo | Baixo-Médio |
| P0 | Substituir lista mágica por `registry.uses_native_connector()` (Etapa 1) | Médio | Baixo | Baixo |
| P1 | Remover `_run_legacy`/`build()` legado (Etapa 2) | Alto | Baixo-Médio | Baixo |
| P1 | Remover UI órfã (`process_workers.py`, `page_registry.py`) (Etapa 3) | Médio | Baixo | Baixo |
| P1 | Unificar hierarquia de erros (Etapa 4) | Médio | Médio | Baixo-Médio |
| P2 | Migrar Confluence para `ApiHttpClient` (Etapa 5) | Alto | Médio-Alto | Médio |
| P2 | Migrar Confluence para `KnowledgeDocumentRenderer` (Etapa 6) | Alto | Alto | Médio-Alto |
| P2 | Continuar extração de mixins do `main_window.py` (worker_mixin, consolidation_controller — já planejado no `REFACTORING_SUMMARY.md`) | Médio | Baixo | Médio |
| P3 | `connectors/web.py` (Generic Web) | Alto (roadmap) | Baixo (isolado) | Alto |
| P3 | Dividir `source_detection.py` em detectores plugáveis | Baixo hoje | Baixo | Médio |

Destaque de **alto benefício + baixo/médio risco + baixo/médio esforço**: as quatro primeiras
linhas (P0/P1). É onde eu começaria.

---

## 14. O que NÃO modificar agora

- **`connectors/confluence.py` (lógica de negócio: CQL, lazy discovery, visibilidade
  pública/privada).** Funciona, é testado (`test_confluence_container_tree_uses_complete_descendant_inventory`,
  `test_confluence_container_tree_falls_back_to_hierarchy_after_cql_500`), e o
  `REFACTORING_SUMMARY.md` documenta uma correção de bug de visibilidade recente e delicada
  (linhas ~508-520). Não mexer sem necessidade concreta.
- **`browser/*.py` e `auth.py`.** Já são plataforma-neutros, bem isolados, sem nenhum
  acoplamento a nomes de conector. Não há problema a resolver aqui.
- **O ABC `KnowledgeSourceConnector` em si.** O contrato já é enxuto e cobre os 5 conectores
  reais sem forçar métodos irrelevantes (os métodos de discovery "lazy" são opcionais, com
  `NotImplementedError` explícito — um bom exemplo de "abstração só onde a variação já foi
  comprovada", exatamente o princípio que você pediu para seguir).
- **Estrutura de diretórios de `connectors/`.** Não vale dividir em subpastas por conector
  ainda (ver seção 8) — seria complexidade adicionada sem benefício no tamanho atual.
- **`client.py` e `markdown.py::MarkdownTransformer` isoladamente (sem golden samples
  prontos).** Não migrar o Confluence para a camada compartilhada às pressas — é exatamente o
  cenário que você descreveu no seu prompt como temor central. Primeiro a rede de segurança
  (Etapa 0), depois a migração (Etapas 5-6), nunca o contrário.

---

## 15. Teste de extensibilidade (os 4 cenários)

**Cenário A — adicionar Google Drive.**
Novo arquivo `connectors/google_drive.py` implementando `KnowledgeSourceConnector`, usando
`ApiHttpClient` para as chamadas HTTP, registrado em `registry.py` com `implemented=False`
até funcional. Ajuste em `source_detection.py` (mais um `if host == "drive.google.com"`).
**Nenhuma mudança em `services.py`, `markdown.py` (parte genérica), `storage.py` ou nos outros
4 conectores.** Única exceção: se a Etapa 1 (seção 12) não tiver sido feita, seria preciso
lembrar de adicionar `google_drive_rest` também às 4 listas mágicas em `main_window.py` — mais
um argumento a favor de fazer a Etapa 1 logo.

**Cenário B — adicionar Generic Website.**
Como descrito na seção 11: novo `connectors/web.py`, reaproveitando `browser/*` para
renderização JS quando necessário e `ApiHttpClient` para requisições simples. Não afeta os
conectores existentes. O ponto de atenção é que Generic Web provavelmente vai precisar de
métodos além do que o ABC atual expõe (ex.: sitemap discovery) — isso pode ser adicionado como
métodos opcionais no ABC (seguindo o padrão já usado por `list_root_documents`/
`search_documents`, que lançam `NotImplementedError` por padrão), sem quebrar os conectores
existentes.

**Cenário C — Notion exige paginação completamente diferente. Isso afeta o Confluence?**
**Não**, e isso já está comprovado pelo código, não é hipótese: `connectors/notion.py` não
importa nada de `connectors/confluence.py`, `client.py` ou `markdown.py::MarkdownTransformer`.
A única superfície compartilhada entre eles é o ABC (`base.py`) e, opcionalmente,
`ApiHttpClient`. Mudar a paginação do Notion não toca em nenhuma linha do Confluence.

**Cenário D — mudamos a geração de Markdown. Quais conectores são afetados?**
Depende de qual dos dois renderizadores muda:
- Mudar `KnowledgeDocumentRenderer` (`markdown.py`) → afeta GitBook, Zendesk, Notion,
  SharePoint (e qualquer conector futuro que siga o padrão novo). **Não afeta Confluence.**
- Mudar `MarkdownTransformer` (`markdown.py`) → afeta **somente** Confluence.

Isso responde diretamente à pergunta central do seu prompt: hoje, uma mudança na geração de
Markdown para atender Notion **não pode** quebrar o Confluence, porque eles não compartilham
o renderizador. O preço dessa segurança é a duplicação descrita na seção 4 (P1-1/P1-3).

---

## 16. Avaliação arquitetural

| Área | Nota atual | Justificativa | Nota projetada (após Etapas 0-4) |
|---|---:|---|---:|
| Modularidade | 7 | Conectores bem separados por arquivo, ABC claro | 8 |
| Separação de responsabilidades | 6 | Boa entre conectores; `main_window.py` e `services.py` ainda concentram demais | 7 |
| Extensibilidade | 7 | Registry+Factory já suporta novo conector sem tocar no core; ver Cenário A/B | 8 |
| Testabilidade | 6 | Boa cobertura com fakes; falta golden sample de saída final | 8 (após Etapa 0) |
| Proteção contra regressões | 5 | Isolamento Confluence/demais é acidental, não testado como contrato | 8 (após Etapa 0) |
| Acoplamento | 6 | Baixo entre conectores; alto entre `main_window.py` e tipos de conector (lista mágica) | 8 (após Etapa 1) |
| Coesão | 6 | `markdown.py` mistura dois propósitos; `services.py` grande mas coeso em "extração" | 7 |
| Observabilidade | 6 | Logging com redação de segredos já existe; falta prefixo por conector/etapa nos logs | 6 (fora do escopo desta rodada) |
| Manutenibilidade | 5 | Código morto testado (P0-1, P2-2) aumenta custo cognitivo real | 8 (após Etapas 2-3) |
| Preparação para novos conectores | 7 | Registry+ABC já provados com 5 conectores reais | 8 |

O projeto já está mais maduro do que o prompt original presumia — a maior parte da queda de
nota vem de **código morto testado** e **duplicação de verdade** (lista mágica), não de falta
de abstração.

---

## 17. Top 10 próximas ações (em ordem de execução)

1. Escrever golden samples de Markdown para Confluence, GitBook e Zendesk
   (`tests/fixtures/*/expected/`), com normalização de timestamps/hash/IDs voláteis.
2. Adicionar `ConnectorRegistry.uses_native_connector()` e trocar as 4 ocorrências da lista
   mágica em `main_window.py` (linhas ~1443, ~1509, ~1617, ~1700) por essa chamada.
3. Confirmar com `grep`/`git log` se há algum uso planejado de `ui/process_workers.py` e
   `ui/page_registry.py`; se não houver, remover ambos e o teste dedicado do primeiro.
4. Remover `ExtractionService._run_legacy`, `_adapt_legacy_runtimes` e
   `RuntimeBuilder.build()`, migrando `tests/test_ui_controllers.py` para usar
   `build_connectors()`.
5. Remover `connectors/http.py::_download_compat` (sem chamadores).
6. Unificar a hierarquia de erros: tornar `ApiConnectionError` a base única, com
   `ConfluenceConnectionError` como alias de compatibilidade temporário.
7. Continuar a extração de mixins do `main_window.py` já planejada no
   `REFACTORING_SUMMARY.md` (`worker_mixin.py`, `consolidation_controller.py`) — trabalho já
   mapeado pelo próprio time, só falta executar.
8. Com os golden samples da Etapa 1 protegendo, avaliar migrar
   `ConfluenceRestConnector` para `ApiHttpClient` em vez de `ConfluenceClient`.
9. Com a Etapa 8 estável, avaliar migrar a renderização do Confluence de
   `MarkdownTransformer` para `KnowledgeDocumentRenderer`.
10. Só então iniciar `connectors/web.py` (Generic Web), reaproveitando `browser/*` para
    conteúdo renderizado por JS e `ApiHttpClient` (já unificado) para o resto.

---

## Apêndice — respostas diretas às 20 perguntas do seu prompt (seção 23)

| # | Pergunta | Resposta curta |
|---|---|---|
| 1 | Escala para 5/10/20 conectores? | Para 5-8, sim, como está. Acima disso, revisitar `source_detection.py` e o tamanho de `connectors/confluence.py`. |
| 2 | Maiores acoplamentos hoje? | `main_window.py` → lista literal de source_types (§4, P0-2); `services.py` com dois pipelines (§4, P0-1). |
| 3 | O que deveria ser compartilhado? | HTTP, renderização final de Markdown, consolidação, auth, persistência, cache — já é, exceto Confluence em HTTP/Markdown (§6). |
| 4 | O que deveria ser isolado por conector? | Descoberta, paginação, parsing de conteúdo bruto — já é (§6). |
| 5 | Paginação específica por conector? | Sim, e já está assim. |
| 6 | Descoberta específica por conector? | Sim, e já está assim. |
| 7 | Parsing específico por conector? | Sim, e já está assim. |
| 8 | Markdown deve ser compartilhado? | Sim — e já é para 4 de 5 conectores; falta só o Confluence (§2.3, §12 Etapa 6). |
| 9 | Consolidação compartilhada? | Sim, já é, sem nenhuma menção a plataforma encontrada em `ConsolidationService`. |
| 10 | Precisa de modelo intermediário? | Já existe (`KnowledgeDocument` e família, `models.py`). |
| 11 | Precisa de interface/base para conectores? | Já existe (`connectors/base.py`). |
| 12 | Como impedir regressão entre conectores? | Golden samples (§10) + manter o isolamento Confluence/demais até haver rede de segurança. |
| 13 | Como testar cada integração isoladamente? | Já é feito via fakes por conector em `test_connectors.py`; adicionar golden samples de saída. |
| 14 | Novos conectores sem alterar o Core? | Já é possível hoje (Cenário A, §15) — só cuidado com a lista mágica (§4, P0-2) até a Etapa 1. |
| 15 | Preparar para URLs genéricas? | §11 — reaproveitar `browser/*` e `ApiHttpClient`; nenhum trabalho estrutural necessário agora. |
| 16 | Reduzir responsabilidades da UI? | Continuar plano já traçado no `REFACTORING_SUMMARY.md` (mixins pendentes). |
| 17 | Maior benefício com menor risco? | Etapas 0-2 do plano (§12): golden samples, eliminar lista mágica, remover pipeline morto. |
| 18 | O que alterar agora? | Etapas 0-4 (§12/§13, P0/P1). |
| 19 | O que deixar para depois? | Migração do Confluence para a camada compartilhada (Etapas 5-6) e Generic Web (Etapa 7). |
| 20 | O que não alterar? | §14 — lógica de negócio do conector Confluence, `browser/*`, `auth.py`, o ABC em si, estrutura de diretórios de `connectors/`. |

---

## Resposta em uma frase

> Se eu fosse o responsável técnico pelo Projeto Alquimista hoje, antes de desenvolver
> qualquer nova integração eu escreveria testes de "golden sample" (Markdown esperado salvo em
> disco) para Confluence, GitBook e Zendesk — porque hoje a única coisa que impede uma mudança
> no Notion de quebrar o Confluence é o fato de eles não compartilharem código, não um teste
> que garanta isso, e é exatamente essa garantia que falta antes de eu me sentir seguro para
> finalmente unificar o Confluence à camada compartilhada que os outros quatro conectores já
> usam.
