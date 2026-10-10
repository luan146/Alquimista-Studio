# Análise Arquitetural Completa — ALQuimista Studio 3.0

Análise baseada no código real do repositório (`https://github.com/luan146/Alquimista-Studio`), confrontado com `MAPA.md` e `README.md`. Onde há divergência, **o código prevalece**.

---

## 1. Resumo executivo

**Estado atual:** O projeto já passou por uma transição importante: existe um contrato ABC (`KnowledgeSourceConnector`), um modelo intermediário (`KnowledgeDocument` / `KnowledgeDocumentMetadata`), um pipeline genérico de extração (`ExtractionService._run_generic`) e um renderizador de Markdown neutro (`KnowledgeDocumentRenderer`). Confluence, GitBook e Zendesk estão implementados e exercitados em testes; Notion e SharePoint existem mas são mais incompletos. A UI está parcialmente desacoplada via mixins e controllers.

**Principal risco:** Ainda coexistem **dois caminhos de extração** (legado Confluence via `MarkdownTransformer` + `ConfluenceClient` vs genérico via conector). Há `if source_type == ...` na UI e em serviços. O `MarkdownTransformer` é fortemente acoplado ao storage format do Confluence (`ac:`, `ri:`). Alterar o “core compartilhado” de Markdown/serviços para acomodar Notion/Web sem proteger o caminho Confluence pode regredir o que já funciona.

**Principal oportunidade:** O contrato e o modelo intermediário **já existem**. O caminho mais seguro não é reescrever, e sim **completar a migração** para o pipeline genérico, isolar a conversão específica de plataforma *dentro* de cada conector (já parcialmente feito), e blindar regressões com golden samples por conector.

**Recomendação central:** Tratar o conector como fronteira de aquisição + normalização (HTML/API → `KnowledgeDocument` com `content` já em Markdown técnico). Manter no core: orquestração, manifesto, incremental, consolidação, `KnowledgeDocumentRenderer`, storage atômico, cancelamento e erros tipados. Não espalhar `page_reader.py` genérico compartilhado; a variação de descoberta/paginação/parsing fica no conector (ou em submódulos por plataforma), atrás do ABC existente.

---

## 2. Como o projeto funciona atualmente

### Pipeline real (reconstruído do código)

```
Usuário (UI)
  │
  ├─ source_detection.detect_source_url()     → DetectedSource
  ├─ source_mixin / source_controller         → SourceConfig
  ├─ connection_mixin + auth + RuntimeSecrets → credenciais em memória
  ├─ registry.create(source)                  → KnowledgeSourceConnector
  │
  ├─ Descoberta / árvore
  │     connector.list_containers()
  │     connector.list_documents()  OU  list_root_documents / list_document_children (lazy)
  │     tree_models + selection_mixin + SelectionStore
  │
  ├─ execution_controller.prepare_runtimes()  → SourceRuntime[]
  │
  └─ ExtractionService.run()
        │
        ├─ se algum runtime.connector is None → _run_legacy (só Confluence)
        │     ConfluenceClient.fetch_page
        │     MarkdownTransformer (macros ac:/ri:)
        │     manifesto + hashes + FileTransaction
        │
        └─ senão → _run_generic
              connector.get_document() → KnowledgeDocument
                (content já Markdown: normalize_document no conector)
              knowledge_document_metadata()
              KnowledgeDocumentRenderer.render()  → frontmatter + metadados
              ManifestStore + SHA-256 incremental
              FileTransaction.commit()
              ManifestIndex.rebuild()

ConsolidationService
  ManifestStore → ordena/agrupa → demote_headings → pacote/arquivo/índice

reports.ExecutionReport → results_page
```

**Fato observado:** Em `services.py`, `_run()` escolhe legado vs genérico pela presença de `runtime.connector`. `_adapt_legacy_runtimes()` só aceita `source_type == "confluence_rest"` sem conector.

**Fato observado:** Conversão de conteúdo por plataforma *já ocorre no conector* no caminho genérico:

- **Confluence:** `normalize_document` → BeautifulSoup + `markdownify` (sem o tratamento fino de macros do `MarkdownTransformer`)
- **Zendesk:** HTML → markdownify no conector
- **GitBook:** API já devolve Markdown
- **Notion:** blocos → linhas de texto no conector
- **SharePoint:** download de bytes → texto

### Diagrama do pipeline recomendado

```
UI (pages + mixins)
        │
        ▼
Application (controllers, SelectionStore, RuntimeSecrets)
        │
        ▼
Pipeline (ExtractionService / ConsolidationService)
        │  contrato: KnowledgeDocument + ManifestEntry
        │
   ┌────┴────┬──────────┬──────────┬──────────┐
   ▼         ▼          ▼          ▼          ▼
Confluence Notion    GitBook   SharePoint  Web*
(discovery+ (blocks→  (md API)  (Graph)   (crawl)
 parse no    md)
 conector)
   │         │          │          │          │
   └─────────┴──────────┴──────────┴──────────┘
                        │
                        ▼
              Shared Core
        (KnowledgeDocumentRenderer,
         ManifestStore, FileTransaction,
         ConsolidationService, runtime,
         errors, logging)
```

\*Generic Web entra como mais um conector, não como segunda pipeline.

---

## 3. Mapa de responsabilidades

| Área | Arquivos principais | Responsabilidade real |
|------|---------------------|------------------------|
| Contrato de conector | `connectors/base.py` | ABC: containers, documents, get_document, normalize, lazy opcional, search opcional |
| Registry | `connectors/registry.py` | Catálogo + factory por `source_type` |
| HTTP comum | `connectors/http.py` | HTTPS, retry, rate limit, cancelamento, sem log de Authorization |
| Confluence | `connectors/confluence.py` + `client.py` | Espaços, CQL, lazy, restrições, normalize HTML→md |
| Outros conectores | `gitbook.py`, `zendesk.py`, `notion.py`, `sharepoint.py` | Implementações do ABC |
| Modelos | `models.py` | `SourceConfig`, `Knowledge*`, options, manifest, SCHEMA_VERSION=4 |
| Extração/consolidação | `services.py` (~1234 linhas) | Motor: genérico + legado, manifesto, consolidação |
| Markdown | `markdown.py` | `MarkdownTransformer` (Confluence legado) + `KnowledgeDocumentRenderer` (neutro) |
| Persistência | `storage.py` | Atomic write, FileTransaction, ManifestStore |
| Seleção | `selection.py` + mixins | Estado independente de Qt |
| Auth | `auth.py`, `session_store.py` | Browser/DPAPI; tokens só em RuntimeSecrets |
| UI | `main_window.py` (~2942 linhas) + mixins + pages | Orquestração; ainda com alguns `if source_type` |
| Browser discovery | `browser/*` | Cache de metadados, adapters |
| Erros | `errors.py` | Hierarquia tipada (ainda com ramo legado Confluence) |

---

## 4. Problemas encontrados (por severidade)

### P0 — Críticos para expansão segura

1. **Dois pipelines de extração** (`_run_legacy` vs `_run_generic`). Legado usa `MarkdownTransformer` com macros Confluence; genérico usa `normalize_document` do conector (markdownify simples). Comportamento de saída Confluence pode divergir conforme o caminho usado.

2. **`MarkdownTransformer` é específico de Confluence no núcleo** (`ac:link`, `ac:image`, `ac:structured-macro`). Qualquer “melhoria genérica” nesse arquivo afeta só o legado — ou, se alguém unificar mal, contamina o core.

3. **`if source_type in {...}` na UI e controllers** (`main_window.py` ~1443, 1509, 1617, 1700; `source_mixin.py` 419–451; `controllers.py` 141). Isso impede “novo conector sem tocar no core/UI”.

### P1 — Importantes

4. **`main_window.py` monólito** (~2942 linhas, dezenas de handlers). Mixins ajudam, mas handlers de árvore/extração ainda concentram conhecimento de plataformas.

5. **Duplicações mortas** (confirmadas no MAPA e arquitetura): funções definidas duas vezes em `selection_mixin`, `connection_mixin`, `execution_controller`, `auth.browser_login` — a última sobrescreve. Risco alto de editar a definição errada.

6. **Notion/SharePoint incompletos** em relação ao ABC (lazy, filhos, normalize completo). Pressão para “ajustar o core” em vez de completar o conector.

7. **Qualidade de Markdown Confluence no caminho genérico** inferior ao legado (macros não tratadas no `normalize_document` como no transformer).

### P2 — Desejáveis

8. Metadados ainda com vocabulário Confluence (`space_key`, `confluence_version`) no manifesto genérico (`knowledge_document_metadata`).

9. `page_registry` / `process_workers` com poucas referências estáticas (código reserva / possível dead path).

10. Observabilidade: logs existem, mas sem prefixo padronizado `[source_type][etapa][document_id]`.

### P3 — Futuro

11. Generic Web ainda não modelado.

12. Capacidades no registry às vezes “otimistas” vs implementação real.

---

## 5. Hotspots e blast radius

| # | Hotspot | Arquivo | Problema | Consequência | Prioridade |
|---|---------|---------|----------|--------------|------------|
| 1 | Extração dual | `services.py` | Legado + genérico | Regressão Confluence vs novos | P0 |
| 2 | Transformer Confluence | `markdown.py` MarkdownTransformer | Macros específicas no core | Confusão ao “generalizar Markdown” | P0 |
| 3 | MainWindow | `ui/main_window.py` | God-object + if source_type | Qualquer feature UI pode quebrar fluxos | P0 |
| 4 | Selection mixin | `selection_mixin.py` | ~632 linhas + duplicatas | Seleção some / árvore inconsistente | P1 |
| 5 | Confluence connector | `connectors/confluence.py` | Maior e mais completo | Base de referência; mudanças amplas | P1 |
| 6 | Client legado | `client.py` | HTTP Confluence legado | Afeta só Confluence, mas ainda no caminho | P1 |
| 7 | Models/manifest | `models.py` + storage | SCHEMA_VERSION / hashes | Invalidar manifestos de usuários | P1 |
| 8 | Registry | `registry.py` | Ponto único de factories | “Conector não aparece” | P2 |
| 9 | Tree models | `tree_models.py` | Ordenação/lazy | Páginas fora de ordem | P2 |
| 10 | Connection mixin | `connection_mixin.py` | Auth multi-modo + duplicatas | Login/test connection | P1 |

### Blast radius aproximado

| Módulo | Blast radius |
|--------|----------------|
| `services.py` | **CRÍTICO** |
| `markdown.py` (Transformer) | **ALTO** (legado) / médio (renderer) |
| `main_window.py` | **CRÍTICO** |
| `selection_mixin.py` | **ALTO** |
| `connectors/confluence.py` | **ALTO** (só Confluence se isolado) |
| `models.py` (campos serializados) | **ALTO** |
| `connectors/http.py` | **MÉDIO–ALTO** (todos os API connectors) |
| `KnowledgeDocumentRenderer` | **MÉDIO** (todos no genérico) |
| `registry.py` | **MÉDIO** |
| Novo arquivo em `connectors/X/` | **BAIXO** (ideal) |

---

## 6. Shared Core vs Connector-Specific

| Componente | Classificação | Motivo |
|------------|---------------|--------|
| Contrato ABC + capabilities | **CORE / contrato** | Já existe e é o ponto de extensão certo |
| `KnowledgeDocument*` | **CORE (modelo intermediário)** | Já existe; deve permanecer a língua franca |
| `ExtractionService` orquestração, manifesto, incremental | **CORE** | Independente de plataforma se content já vem normalizado |
| `ConsolidationService`, `demote_headings` | **CORE** | Opera sobre Markdown + manifesto |
| `KnowledgeDocumentRenderer` | **CORE** | Só metadados/frontmatter/opções |
| `MarkdownTransformer` (macros ac:) | **CONNECTOR-SPECIFIC** (hoje no core por legado) | Deve migrar para dentro de Confluence ou deixar de ser caminho ativo |
| Descoberta / paginação / lazy / CQL | **CONNECTOR-SPECIFIC** | Cada API pagina diferente |
| Parsing HTML/blocks → content | **CONNECTOR-SPECIFIC** | Confluence storage ≠ Notion blocks ≠ Zendesk HTML |
| `ApiHttpClient`, retries, rate limit | **INFRA / CORE** | Compartilhado com sucesso |
| Auth modes genéricos + RuntimeSecrets | **CORE + UI** | Browser/session específicos, tokens em memória |
| `session_store` DPAPI | **INFRA** | Só browser |
| SelectionStore, tree_models | **CORE UI/domínio** | Neutros se alimentados por metadados normalizados |
| Logging, FileTransaction, CancellationToken | **INFRA / CORE** | |
| `form_spec` por source_type | **EXTENSÍVEL (registry/UI)** | Já parcialmente feito |
| Generic Web crawl/sitemap | **CONNECTOR (ou pacote web)** | Não misturar no core de API |
| Consolidação | **CORE** | |
| Download de assets/imagens | **EXTENSÍVEL POR ESTRATÉGIA** | Opções no core; URL/resolução no conector |

### Resposta à pergunta: separar leitores/paginadores por plataforma?

**Não** crie um `page_reader.py` global compartilhado.

**Sim**, a descoberta/paginação/leitura devem ser específicas por conector — mas **atrás do ABC que já existe**, não necessariamente com a árvore de pastas `connectors/confluence/page_reader.py` desde o dia 1. Quando um arquivo de conector passar de ~400–700 linhas com responsabilidades claras (HTTP + normalize + lazy), aí sim extrair submódulos *dentro* do pacote da plataforma.

Organização superior ao “um reader genérico”:

```
connectors/
  base.py          # contrato
  http.py          # infra HTTP
  registry.py
  confluence.py    # ou confluence/ (connector, normalize, lazy) quando crescer
  notion.py
  ...
```

Composição + Protocol/ABC > herança profunda. Strategy só onde a variação já foi comprovada (ex.: lazy vs sync já modelado com métodos opcionais + `NotImplementedError`).

---

## 7. Arquitetura recomendada

Princípio: **conector entrega `KnowledgeDocument` pronto**; core não interpreta storage format de ninguém.

1. **Congelar o contrato** `KnowledgeSourceConnector` (já bom). Evitar novos métodos sem capability flag.
2. **Um único caminho de extração** (`_run_generic`). Legado só como adaptador temporário que instancia `ConfluenceRestConnector`.
3. **Melhorar `ConfluenceRestConnector.normalize_document`** para incorporar a lógica de macros hoje em `MarkdownTransformer` — assim o genérico não perde qualidade.
4. **Eliminar `if source_type`** na UI substituindo por capabilities + `form_spec` + registry.
5. **Testes por conector** com fixtures HTTP + golden Markdown.
6. **Generic Web** como `source_type=web_generic` implementando o mesmo ABC (discovery = crawl controlado; get_document = extract main content → md).

Não é plugin system completo agora: o registry + factory já é o plugin mínimo adequado para equipe pequena.

---

## 8. Estrutura de diretórios proposta (incremental)

**Não** mover tudo de uma vez. Evolução sugerida:

```
alquimista/
  models.py                 # permanece
  services.py               # pipeline (reduzir legado ao longo do tempo)
  markdown/
    __init__.py
    renderer.py             # KnowledgeDocumentRenderer (CORE)
    normalize.py            # normalize_markdown, hashes
    # confluence_macros.py  # só se ainda precisar fora do conector (preferir dentro)
  connectors/
    base.py
    http.py
    registry.py
    confluence/
      __init__.py           # exporta ConfluenceRestConnector
      connector.py
      normalize.py          # macros ac:/ri: + markdownify
      lazy.py               # opcional, quando extrair
    gitbook.py              # ok flat até crescer
    notion.py
    sharepoint.py
    zendesk.py
    web/                    # futuro
      connector.py
      extract.py
      discover.py
  ...
  ui/                       # pages + mixins; menos if source_type
tests/
  connectors/
    confluence/
      fixtures/
      expected/
    gitbook/
    zendesk/
    notion/
  pipeline/
  ui/
```

Migrar pasta só quando o arquivo único ficar difícil de manter — **não** por estética.

---

## 9. Contratos/interfaces recomendados

O ABC atual já é o contrato mínimo certo. Refinar apenas capabilities e documentação:

```python
class KnowledgeSourceConnector(Protocol):
    def get_source_type(self) -> str: ...
    def get_capabilities(self) -> ConnectorCapabilities: ...
    def validate_connection(self) -> dict[str, Any]: ...
    def list_containers(self) -> list[KnowledgeContainer]: ...
    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]: ...
    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument: ...
    # opcionais: list_root_documents, list_document_children, search_documents
    def close(self) -> None: ...
```

**Invariante do contrato:** `KnowledgeDocument.content` é Markdown técnico **já normalizado** (sem frontmatter). O core só aplica `KnowledgeDocumentRenderer`.

Capabilities devem dirigir a UI (lazy, search, bearer_only), não strings de `source_type`.

---

## 10. Estratégia contra regressões

**Fato:** Já há boa cobertura em `tests/test_connectors.py` (~1011 linhas), `test_services.py`, `test_lazy_confluence.py`, testes de UI. Falta organização por pasta e **golden files** estáveis de Markdown.

Proposta:

```
tests/
  connectors/confluence/fixtures/*.json
  connectors/confluence/expected/*.md
  connectors/gitbook/...
  connectors/zendesk/...
  pipeline/test_extraction_generic.py
  pipeline/test_consolidation.py
```

- **Contract tests:** cada conector registrado com `implemented=True` implementa os métodos obrigatórios e `get_document` retorna `KnowledgeDocument` com campos mínimos.
- **Golden samples:** HTML/JSON de entrada fixo → Markdown esperado (normalizar timestamps, etag, ordem se necessário).
- **Regression:** manter 1–2 fluxos Confluence “sagrados” (público + com macros) que devem continuar idênticos.
- **CI:** já existe quality workflow — adicionar job que falha se golden Confluence divergir.
- **Antes de refatorar:** capturar output atual do caminho genérico Confluence como baseline.

Golden samples são **adequados e prioritários** aqui, porque o risco principal é regressão silenciosa de formatação.

---

## 11. Estratégia para Generic Web

Tratar como **`WebGenericConnector`** (mesmo ABC), não como segunda pipeline.

| Aspecto | Abordagem |
|---------|-----------|
| Discovery | Sitemap se houver; senão BFS de links mesmos origin, limite de profundidade/páginas |
| Conteúdo | Readability/trafilatura ou heurística main-content → HTML limpo → markdownify |
| SPA/JS | Opcional via Playwright já existente no browser subsystem; capability `requires_browser` |
| Auth | public / browser_session (já no produto) |
| Rate limit | ApiHttpClient + politeness delay |
| Duplicatas | canonical URL + hash de conteúdo |
| Robots | respeitar robots.txt por padrão |

Core não precisa saber de sitemap: só chama `list_containers` / `list_documents` / `get_document` como nos outros.

---

## 12. Plano incremental de refatoração

### Etapa 0 — Baseline (fazer antes de qualquer integração nova)

- **Objetivo:** congelar comportamento Confluence genérico + legado.
- **Ação:** golden Markdown + fixtures HTTP; documentar diferença Transformer vs `normalize_document`.
- **Risco:** baixo. **Benefício:** alto.
- **Validar:** pytest nos goldens.

### Etapa 1 — Paridade Confluence no conector

- **Objetivo:** portar tratamento de macros de `MarkdownTransformer` para `ConfluenceRestConnector.normalize_document`.
- **Arquivos:** `connectors/confluence.py`, testes; não apagar Transformer ainda.
- **Risco:** médio. **Benefício:** alto (um só caminho com qualidade).

### Etapa 2 — Desligar legado na prática

- **Objetivo:** `prepare_runtimes` sempre injeta connector; `_run_legacy` só se alguém passar runtime antigo.
- **Arquivos:** `execution_controller`, `services._adapt_legacy_runtimes`.
- **Validar:** mesmos goldens; UI completa Confluence.

### Etapa 3 — Capabilities na UI

- **Objetivo:** substituir `if source_type in {confluence, gitbook, zendesk}` por flags do registry/capabilities.
- **Arquivos:** `main_window.py`, `source_mixin.py`, `controllers.py`.
- **Risco:** médio. **Benefício:** alto para novos conectores.

### Etapa 4 — Completar Notion (segundo conector “difícil”)

- **Objetivo:** validar que o ABC aguenta paginação/blocos diferentes **sem** mudar core.
- **Regra:** se Notion exigir mudança em `services.py`/`renderer`, reavaliar se a lógica não deveria estar no conector.

### Etapa 5 — Limpeza de mortos

- Remover definições duplicadas (editar só a ativa / deletar a morta com teste).
- Deprecar `MarkdownTransformer` quando legado não tiver callers.

### Etapa 6 — Generic Web

- Depois de 2+ conectores estáveis no genérico.

---

## 13. Tabela de prioridades

| Prioridade | Mudança | Benefício | Risco | Esforço |
|------------|---------|-----------|-------|---------|
| P0 | Goldens Confluence + baseline genérico | Alto | Baixo | Baixo–médio |
| P0 | Macros Confluence no `normalize_document` | Alto | Médio | Médio |
| P0 | UI por capabilities, não source_type | Alto | Médio | Médio |
| P1 | Runtimes sempre com connector | Alto | Médio | Baixo |
| P1 | Contract tests por conector no CI | Alto | Baixo | Médio |
| P1 | Completar Notion atrás do ABC | Alto | Médio | Alto |
| P2 | Extrair submódulos confluence/ se arquivo crescer | Médio | Baixo | Médio |
| P2 | Prefixos de log por etapa/conector | Médio | Baixo | Baixo |
| P2 | Vocabulário manifesto menos “space/confluence” | Médio | Médio | Médio |
| P3 | Generic Web connector | Alto (futuro) | Alto | Alto |
| P3 | Reorganizar pastas markdown/ | Baixo | Médio | Médio |

---

## 14. O que NÃO modificar agora

- **Não** reescrever `main_window.py` do zero.
- **Não** introduzir framework de plugins pesado.
- **Não** criar `page_reader` genérico compartilhado.
- **Não** alterar `SCHEMA_VERSION` / shape do manifesto sem migração e testes.
- **Não** generalizar `MarkdownTransformer` para “todas as plataformas”.
- **Não** fundir `client.py` e `ApiHttpClient` sem necessidade (blast alto no Confluence).
- **Não** mover Consolidation/Renderer para dentro de conectores.
- **Não** refatorar por estética arquivos estáveis cobertos por teste (ex.: `storage.FileTransaction`).

---

## 15. Teste de extensibilidade

### A — Google Drive

Criar `connectors/google_drive.py` (ou pasta), registrar no `registry`, `form_spec`, detector de URL se fizer sentido. Implementar listagem de pastas como containers e arquivos como documents; `get_document` exporta texto/md. **Core/UI:** só se faltar capability (ex.: OAuth) — preferir auth mode já existente ou estender auth sem `if drive` espalhado.

### B — Generic Website

`connectors/web/` implementando o ABC; opcionalmente reutilizar `browser/`. Core inalterado se o conector devolver `KnowledgeDocument`.

### C — Notion com paginação totalmente diferente

Só `notion.py` (+ testes Notion). **Não deve** alterar `services.py` nem Confluence, desde que o cursor continue no contrato lazy opcional já existente.

### D — Mudança na geração de Markdown (frontmatter/opções)

Afeta `KnowledgeDocumentRenderer` + todos os conectores no caminho genérico de forma uniforme — desejável. Não deve exigir mudança nos conectores se `content` já for md técnico.

---

## 16. Avaliação arquitetural (0–10)

| Área | Atual | Justificativa | Projetado pós-plano |
|------|-------|---------------|---------------------|
| Modularidade | 7 | Conectores e core separados; legado ainda acopla | 8–9 |
| Separação de responsabilidades | 6 | UI monólito; dual pipeline; Transformer no core | 8 |
| Extensibilidade | 7 | Registry + ABC bons; if source_type atrapalham | 9 |
| Testabilidade | 7 | Muitos testes unitários; poucos goldens organizados | 8–9 |
| Proteção contra regressões | 5 | Confluence coberto, mas dois caminhos e sem golden sistemático | 8 |
| Acoplamento | 6 | Bom no domínio; UI e legado puxam para baixo | 8 |
| Coesão | 7 | Conectores coesos; services/main_window menos | 8 |
| Observabilidade | 5 | Logs e redação; falta contexto estruturado | 7 |
| Manutenibilidade | 6 | MAPA ajuda; arquivos grandes e duplicatas | 8 |
| Preparação p/ novos conectores | 7 | Contrato existe; UI e parity Confluence limitam | 9 |

---

## 17. Top 10 próximas ações (ordem de execução)

1. **Capturar baseline:** fixtures + Markdown golden do Confluence no caminho **genérico** e no legado (documentar diferenças).
2. **Portar macros** `MarkdownTransformer` → `ConfluenceRestConnector.normalize_document` até goldens genéricos ≥ legado.
3. **Garantir** que a UI de extração sempre cria runtimes **com** `connector` (evitar `_run_legacy` no uso normal).
4. **Substituir** checagens `source_type in {...}` na UI por `capabilities` / `form_spec` / `descriptor.implemented`.
5. **Organizar** `tests/connectors/<plataforma>/` com contract test mínimo no CI.
6. **Remover ou marcar** definições mortas duplicadas (selection/connection/auth/execution) após `rg` das ocorrências ativas.
7. **Completar Notion** (`get_document` rico, containers, erros) **sem** alterar `ExtractionService` além de bugs genéricos.
8. **Padronizar logs** com source_type + etapa + document_id.
9. **Só então** avaliar extrair `connectors/confluence/normalize.py` se o arquivo continuar crescendo.
10. **Especificar** (design doc curto) `WebGenericConnector` — implementar depois de Notion estável no genérico.

---

## 18. Respostas objetivas às questões-chave

| Pergunta | Resposta |
|----------|----------|
| Escala para 10–20 conectores? | Sim **se** UI deixar de ramificar por `source_type` e o legado for desativado. |
| Maiores acoplamentos? | Dual pipeline; Transformer no core; `main_window` + ifs de plataforma. |
| Compartilhar? | Orquestração, manifesto, consolidação, renderer, HTTP, storage, runtime. |
| Isolar por conector? | Discovery, paginação, parse, normalize de conteúdo. |
| Paginação/discovery específicas? | **Sim.** |
| Parsing específico? | **Sim.** |
| Markdown compartilhado? | **Renderer sim**; conversão de origem **não**. |
| Consolidação compartilhada? | **Sim.** |
| Modelo intermediário? | **Já existe** (`KnowledgeDocument`); manter e enriquecer. |
| Interface base? | **Já existe**; não reinventar. |
| Impedir regressões? | Goldens + contract tests + um caminho de extração. |
| Novos conectores sem core? | Registry + ABC + capabilities na UI. |
| Generic Web? | Novo conector, mesmo pipeline. |
| Reduzir UI? | Capabilities + pages/mixins; extrair handlers de árvore aos poucos. |
| Maior benefício / menor risco? | Goldens + parity de normalize Confluence. |
| Alterar agora? | Baseline testes + parity normalize + capabilities UI. |
| Deixar para depois? | Web genérico, reorg grande de pastas, plugin framework. |
| Não alterar agora? | SCHEMA, Consolidation core, reescrita da MainWindow. |

---

## 19. Princípio central e decisão imediata

A arquitetura recomendada busca:

> Cada novo conector pode evoluir e apresentar particularidades próprias sem obrigar alterações perigosas no restante do sistema, enquanto funcionalidades realmente comuns permanecem centralizadas, testadas e reutilizáveis.

**Se o responsável técnico fosse decidir hoje:** a primeira mudança arquitetural antes de qualquer nova integração seria estabelecer golden samples do Confluence no pipeline genérico e igualar a qualidade de `normalize_document` à do `MarkdownTransformer`, para poder desligar o caminho legado sem medo e sem tocar no core a cada conector novo.

---

*Documento gerado a partir da análise do código-fonte do ALQuimista Studio 3.0.*
