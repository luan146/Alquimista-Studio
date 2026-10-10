# Análise Arquitetural, Modularização, Estabilidade e Expansão do ALQuimista Studio 3.0

**Data da análise:** 12 de agosto de 2026  
**Escopo:** código, testes, configuração e documentação presentes no worktree local  
**Natureza:** análise somente leitura; nenhuma alteração de código foi realizada

---

## 1. Resumo executivo

O ALQuimista Studio não é um sistema monolítico. O projeto já possui elementos arquiteturais importantes para crescer com segurança:

- registry de conectores;
- contrato comum de aquisição;
- modelos intermediários de fontes, contêineres e documentos;
- cliente HTTP compartilhado;
- descoberta lazy com cache de metadados;
- serviço de extração;
- renderer Markdown compartilhado;
- armazenamento transacional;
- manifest e índice incremental;
- consolidação independente de plataforma;
- estado de seleção separado dos widgets Qt;
- testes sintéticos para os conectores ativos.

O problema central é que essa arquitetura está em transição. O projeto possui um pipeline genérico funcional para Confluence, GitBook e Zendesk, mas ainda conserva caminhos legados e decisões de plataforma fora dos conectores. Isso cria mais de uma forma de descobrir, interpretar e renderizar o mesmo conteúdo.

Os principais riscos são:

1. Confluence possuir resultados diferentes entre preview, pipeline genérico e pipeline legado.
2. Novos conectores exigirem alterações em listas fechadas da UI.
3. Correções em `services.py`, `markdown.py`, `models.py` ou `main_window.py` terem blast radius elevado.
4. A descoberta lazy da UI não impedir uma redescoberta integral antes da extração.
5. Ausência de golden samples completos que congelem o comportamento conhecido do Confluence.

A recomendação arquitetural central é:

> Preservar o modelo intermediário e os serviços compartilhados, criar uma suíte de contratos e golden samples para o Confluence e fazer com que o registry e as capabilities governem o fluxo, removendo gradualmente decisões específicas de plataforma do Core e da UI.

Não é recomendada uma reescrita completa, um loader externo de plugins ou uma fragmentação imediata de todos os conectores em muitos arquivos.

### Resposta sobre escala

- **Até 5 conectores:** viável com o desenho atual, desde que os novos conectores sigam rigorosamente o pipeline genérico.
- **De 5 a 10 conectores:** o custo de manutenção da UI, registry, forms, detection e testes começará a crescer significativamente.
- **De 10 a 20 conectores:** não é recomendável manter listas fechadas, contratos amplos e dois pipelines paralelos.

---

## 2. Método, escopo e evidências

A análise confrontou:

- `MAPA.md`;
- `docs/architecture.md`;
- `README.md`;
- configuração em `config/`;
- módulos do Core;
- conectores;
- browser/discovery/cache;
- serviços de extração e consolidação;
- modelos e armazenamento;
- UI, controllers e mixins;
- testes existentes.

Foram usados imports, callers, contracts, modelos e testes como fonte de verdade. A documentação foi tratada apenas como índice.

### Validações realizadas

- 81 testes focados aprovados em 7,18 segundos.
- Ruff aprovado sem ocorrências.
- Mypy aprovado em 63 arquivos do pacote.
- A suíte completa executou ao menos 63 testes sem falha visível, mas excedeu 120 segundos; portanto o resultado integral é inconclusivo.
- A `.venv` local executa Python 3.14.6, enquanto a configuração declara Python 3.12. Os resultados são úteis como diagnóstico, mas não substituem uma validação na versão alvo.

### Estado do worktree

A análise considerou o worktree atual, incluindo alterações locais preexistentes. Nenhuma delas foi revertida ou sobrescrita.

---

## 3. Como o projeto funciona atualmente

### 3.1 Pipeline real

```text
Usuário
  ↓
UI / MainWindow
  ↓
detect_source_url + normalize_source_config
  ↓
SourceConfig no ProjectConfig
  ↓
RuntimeSecrets mantém token somente em memória
  ↓
ConnectorRegistry.create(source)
  ↓
validate_connection()
  ↓
MainWindow.load_tree()
  ├─ tipos ativos conhecidos → connector.list_containers()
  └─ fallback legado       → ConfluenceClient
  ↓
Seleção de contêiner/páginas
  ├─ Confluence pode usar LazyDiscoveryService + BrowserCache
  ├─ outros usam list_documents()
  └─ SelectionStore → ProjectConfig.selections
  ↓
execution_controller.prepare_runtimes()
  ↓
RuntimeBuilder.build_connectors()
  ├─ recria o conector
  ├─ lista contêineres novamente
  └─ chama list_documents() para cada contêiner selecionado
  ↓
SourceRuntime
  ↓
ExtractionService
  ├─ runtime com connector → _run_generic()
  └─ runtime sem connector → _run_legacy() exclusivo de Confluence
  ↓
connector.get_document()
  ↓
KnowledgeDocument
  ↓
knowledge_document_metadata()
  ↓
KnowledgeDocumentRenderer
  ↓
FileTransaction
  ├─ Markdown individual
  ├─ manifesto JSON
  ├─ índice SQLite
  ├─ falhas
  └─ ExecutionReport
  ↓
ConsolidationService
  ↓
Pacotes Markdown + índice de pacotes
  ↓
Tela de resultados
```

### 3.2 Divergência entre discovery e extração

A descoberta lazy usada pela UI não é reaproveitada integralmente pela preparação da extração. `RuntimeBuilder.build_connectors()` recria o conector e chama `list_documents()` para os contêineres selecionados.

Na prática:

```text
Seleção lazy de poucas páginas
  ↓
Usuário inicia extração
  ↓
RuntimeBuilder lista novamente todos os documentos do contêiner
  ↓
Somente então filtra as chaves selecionadas
```

Isso reduz o benefício do lazy loading e cria um futuro gargalo em bases grandes.

### 3.3 Estado dos conectores

| Conector | Registry | Classe concreta | Pipeline comum testado | Situação |
|---|---|---:|---:|---|
| Confluence | Disponível | Sim | Sim | Referência principal |
| GitBook | Disponível | Sim | Sim | Funcional com fixtures sintéticas |
| Zendesk Guide | Disponível | Sim | Sim | Funcional com fixtures sintéticas |
| Notion | Em desenvolvimento | Não; classe abstrata | Não | Protótipo incompleto |
| SharePoint | Em desenvolvimento | Não; classe abstrata | Não | Protótipo incompleto |

---

## 4. Mapa de responsabilidades

| Módulo | Responsabilidade atual | Classificação |
|---|---|---|
| `models.py` | Configuração, seleção, documentos intermediários e manifest | Core compartilhado |
| `connectors/base.py` | Contrato obrigatório dos conectores | Core/contrato |
| `connectors/registry.py` | Catálogo, status, capacidades e factory | Plugin/catalog |
| `connectors/<plataforma>.py` | Autenticação, paginação, descoberta e parsing | Connector-specific |
| `connectors/http.py` | HTTPS, proxy, rate limit, retry e download | Infraestrutura compartilhada |
| `browser/contracts.py` | Envelope de discovery lazy | Core compartilhado |
| `browser/service.py` | Orquestração cache-first | Infraestrutura compartilhada |
| `browser/cache.py` | Cache SQLite de metadados | Infraestrutura compartilhada |
| `services.py` | Extração, incremental, manifest, relatórios e consolidação | Application/Core |
| `markdown.py` | Parsing legado Confluence e renderer genérico | Core + legado misturados |
| `storage.py` | Escrita atômica, transações e manifest | Infraestrutura crítica |
| `runtime.py` | Cancelamento, rate limiting e callbacks | Infraestrutura |
| `selection.py` | Estado de seleção independente da UI | Core compartilhado |
| `ui/execution_controller.py` | Casos de uso de extração/consolidação | Application/UI adapter |
| `ui/controllers.py` | Runtime secrets e preparação de runtimes | Application/UI adapter |
| `ui/main_window.py` | Composição, navegação, árvore, previews, workers e resultados | UI/orquestrador excessivo |
| `ui/mixins/*` | CRUD de fontes, autenticação e seleção | UI/application misturados |

### 4.1 Dependências

O fan-in estático mostra os principais contratos compartilhados:

| Módulo | Quantidade aproximada de importadores internos |
|---|---:|
| `models.py` | 29 |
| `runtime.py` | 16 |
| `errors.py` | 13 |
| `ui/components.py` | 11 |
| `client.py` | 8 |
| `connectors/base.py` | 8 |

O maior fan-out pertence a `ui/main_window.py`, com dependência direta de aproximadamente 33 módulos.

### 4.2 Ciclo observado

```text
models.py → selection.py → models.py
```

O import de `SelectionStore` em `ProjectConfig.selected_keys_for()` é tardio, evitando falha de importação. Ainda assim, o ciclo indica que regras de identidade/seleção poderiam futuramente ser movidas para um módulo neutro.

Não é uma prioridade imediata.

---

## 5. Problemas encontrados

### 5.1 P0 — Dois pipelines de extração

**Fato observado no código**

`ExtractionService._run()` escolhe entre:

- `_run_generic()` quando todos os runtimes possuem connector;
- `_run_legacy()` quando os runtimes não possuem connector.

O pipeline legado é exclusivo de Confluence e usa diretamente `ConfluenceClient` e `MarkdownTransformer`.

**Consequência**

- correções precisam ser replicadas;
- resultados podem divergir;
- remoção futura do legado fica difícil;
- testes de um caminho não protegem automaticamente o outro.

**Recomendação**

Congelar primeiro o output atual do Confluence com goldens. Depois migrar todos os callers para o pipeline comum e manter o legado como adapter de entrada, não como algoritmo completo paralelo.

### 5.2 P0 — Dois comportamentos Markdown

**Fato observado no código**

`MarkdownTransformer`:

- conhece macros `ac:*`;
- reescreve links Confluence;
- processa attachments;
- trata imagens, painéis, expand e code;
- gera o documento final legado.

`ConfluenceRestConnector.normalize_document()` usa BeautifulSoup + `markdownify` de forma mais simples. Depois o conteúdo passa por `KnowledgeDocumentRenderer`.

A prévia da UI ainda usa `MarkdownTransformer`.

**Consequência**

Preview, extração legada e extração genérica podem produzir documentos diferentes para a mesma página.

**Recomendação**

O conector Confluence deve concentrar parsing de storage HTML e macros. O renderer compartilhado deve somente aplicar metadados, título e opções finais ao `KnowledgeDocument` já normalizado.

### 5.3 P0 — Ausência de golden samples completos

**Fato observado no código**

Existem testes sintéticos relevantes, mas payloads e expectativas ficam embutidos nos arquivos Python. Não existem diretórios versionados de fixtures e expected outputs por plataforma.

**Consequência**

Alterações sutis podem passar:

- ordem de seções;
- mudanças de cabeçalhos;
- frontmatter;
- links;
- macros;
- imagens;
- espaços em branco;
- campos omitidos;
- alterações involuntárias de hash.

**Recomendação**

Criar uma matriz de fixtures e outputs esperados, começando pelo Confluence.

### 5.4 P1 — Listas fechadas de plataformas na UI

**Fato observado no código**

`MainWindow.load_tree()` reconhece explicitamente:

```python
{"confluence_rest", "gitbook_api", "zendesk_guide"}
```

Tipos fora dessa lista seguem um fallback baseado em `ConfluenceClient`.

Além disso, a definição de uma integração está espalhada em:

- `connectors/registry.py`;
- `ui/connector_forms.py`;
- `source_detection.py`;
- `ui/pages/dashboard_page.py`;
- branches de `ui/main_window.py`;
- branches de `ui/mixins/source_mixin.py`.

**Consequência**

Adicionar um conector exige editar áreas que não deveriam conhecer a plataforma.

**Recomendação**

Criar um descriptor interno único, contendo factory, status, capabilities, form spec, aliases/detector e metadata de apresentação.

### 5.5 P1 — Contrato comum amplo e redundante

**Fato observado no código**

O ABC exige:

- `list_documents()`;
- `get_document()`;
- `get_document_children()`;
- `normalize_document()`;
- lifecycle;
- e oferece métodos opcionais de lazy discovery e busca.

Existem dois conceitos similares de filhos:

- `get_document_children(document_id)`;
- `list_document_children(container_id, parent_id, cursor=...)`.

Notion e SharePoint são abstratos porque não implementam `get_document_children` e `normalize_document`.

**Consequência**

Conectores sem hierarquia real precisam implementar métodos artificiais, e detalhes internos de normalização vazam para o contrato público.

**Recomendação**

Reduzir o contrato obrigatório e usar Protocols opcionais para hierarchy, lazy discovery e search.

### 5.6 P1 — Notion e SharePoint são protótipos, não conectores quase prontos

**Fato observado no código**

Além de serem classes abstratas:

- algumas construções de `KnowledgeSource` omitem `base_url`;
- algumas construções de `KnowledgeContainer` omitem `container_type` e `source_type`;
- algumas construções de `KnowledgeDocument` omitem `source_type`;
- Notion não percorre todos os `next_cursor`;
- a leitura de blocos Notion não percorre blocos filhos recursivamente;
- SharePoint não percorre `@odata.nextLink`;
- SharePoint decodifica downloads binários como UTF-8.

**Consequência**

Mudar apenas `implemented=True` no registry não ativaria conectores funcionais.

**Recomendação**

Tratá-los como esqueletos experimentais e escolher apenas um deles como próxima integração real. Notion é o melhor candidato para testar paginação e conteúdo estruturado muito diferentes de Confluence.

### 5.7 P1 — Hierarquia de erros contaminada pelo legado

**Fato observado no código**

`InvalidResponseError` herda de `ConfluenceConnectionError`, embora seja usado pelos conectores genéricos.

A UI ainda pode exibir “Confluence indisponível” para falhas de outros conectores.

**Consequência**

- classificação incorreta;
- mensagens incorretas;
- captura de exceções por tipo perde precisão;
- observabilidade mistura plataforma e categoria da falha.

**Recomendação**

Usar uma hierarquia neutra e manter aliases legados apenas por compatibilidade.

### 5.8 P1 — Descoberta integral antes da extração

**Fato observado no código**

O runtime filtra contêineres selecionados, mas lista todos os documentos do contêiner antes de resolver as chaves selecionadas.

**Consequência**

- custo proporcional ao total remoto, não à seleção;
- repetição de requisições;
- rate limit;
- perda do benefício do cache/lazy;
- piora ao crescer para milhares de páginas.

**Recomendação**

Transportar `DocumentRef` e metadados selecionados da etapa de seleção para o runtime. Quando necessário, oferecer `get_document_metadata(ref)` em vez de relistar o contêiner.

### 5.9 P1 — Responsabilidades excessivas na MainWindow

**Fatos quantitativos**

- 3.170 linhas;
- cerca de 150 métodos;
- 45 imports;
- aproximadamente 33 dependências internas.

**Responsabilidades encontradas**

- navegação;
- construção de telas;
- projeto;
- árvore;
- cache lazy;
- discovery remoto;
- preview Markdown;
- preview de consolidação;
- workers;
- resultados;
- filesystem;
- apresentação de erros.

**Recomendação**

Extrair casos de uso gradualmente para controllers sem Qt. A `MainWindow` deve continuar compondo telas e sinais, mas não executar decisões de plataforma ou aquisição.

### 5.10 P2 — TreeMixin inativo e lógica duplicada

**Fato observado no código**

`TreeMixin` implementa helpers de árvore, mas `MainWindow` não herda dele e possui implementações próprias equivalentes.

**Consequência**

Correções podem ser feitas no arquivo inativo e não afetar a aplicação.

**Recomendação**

Após cobertura dos testes de árvore, escolher uma única fonte de verdade. Não fazer essa limpeza junto de mudanças funcionais maiores.

### 5.11 P2 — MAPA.md parcialmente desatualizado

**Fato observado no código**

O mapa registra duplicações de funções em `selection_mixin.py`, `connection_mixin.py`, `execution_controller.py` e `auth.py`. No código atual existe uma única definição das funções citadas.

O tamanho e a quantidade de métodos da `MainWindow` também cresceram.

**Recomendação**

Atualizar o mapa depois que a arquitetura estabilizar. Ele deve continuar sendo índice, nunca fonte final da verdade.

### 5.12 P2 — Formato do conteúdo é implícito

**Fato observado no código**

`KnowledgeDocument.content` é `str`, mas o pipeline genérico pressupõe que o conector devolva Markdown normalizado.

**Consequência**

Não existe proteção de tipo contra um conector retornar HTML ou bytes decodificados incorretamente.

**Recomendação**

Evoluir de forma mínima para `content_markdown` ou adicionar `content_format`. Não criar um AST universal de conteúdo neste momento.

---

## 6. Hotspots e blast radius

### 6.1 Top 10 hotspots arquiteturais

| Hotspot | Arquivo/módulo | Problema | Consequência | Prioridade |
|---|---|---|---|---|
| Pipeline duplo | `services.py` | Genérico e legado Confluence | Correções duplicadas e divergência | P0 |
| Conversão dupla | `markdown.py` | Transformer Confluence e renderer comum | Preview/output inconsistentes | P0 |
| Ausência de goldens | `tests/` | Asserts parciais e fixtures inline | Regressões silenciosas | P0 |
| Orquestrador central | `ui/main_window.py` | 3.170 linhas e 33 dependências | Alto risco por alteração | P1 |
| Preparação do runtime | `ui/controllers.py` | Redescoberta integral e regra Confluence | Custo e acoplamento | P1 |
| Contrato | `connectors/base.py` | Interface ampla e redundante | Conectores artificiais/incompletos | P1 |
| Erros | `errors.py` | Erro genérico deriva de Confluence | Diagnóstico incorreto | P1 |
| Confluence | `connectors/confluence.py` + `client.py` | API e parsing distribuídos | Difícil determinar fonte de verdade | P1 |
| Onboarding | registry/forms/detection/dashboard | Metadata espalhada | Novo conector altera muitos módulos | P1 |
| Árvore | `main_window.py` + `tree_mixin.py` | Implementação duplicada/inativa | Correção no local errado | P2 |

### 6.2 Blast radius por módulo

| Módulo | Blast radius | O que pode quebrar |
|---|---|---|
| `models.py` | Crítico | Serialização, projeto, manifest, conectores, UI e hashes |
| `services.py` | Crítico | Extração, incremental, relatórios e consolidação |
| `markdown.py` | Crítico | Preview, arquivos individuais, hashes e pacotes |
| `storage.py` | Crítico | Integridade, rollback, manifest e arquivos finais |
| `ui/main_window.py` | Crítico | Navegação, seleção, discovery, workers e resultados |
| `connectors/base.py` | Alto | Todos os conectores e adapters |
| `connectors/http.py` | Alto | Todas as APIs oficiais |
| `connectors/confluence.py` | Alto | Fluxo de referência e maior integração ativa |
| `ui/controllers.py` | Alto | Preparação de todas as extrações |
| `selection.py` | Alto | Identidade de documentos e seleção persistida |
| `browser/cache.py` | Médio | Discovery/cache, sem afetar conteúdo extraído diretamente |
| `reports.py` | Médio | Diagnóstico e tela de resultados |

---

## 7. Shared Core vs Connector-Specific

| Componente | Classificação recomendada | Motivo |
|---|---|---|
| `KnowledgeDocument` e referências | Core compartilhado | Fronteira estável entre aquisição e processamento |
| Renderização final Markdown | Core compartilhado | Mesmas opções e metadata final |
| Parsing de HTML/blocos/API | Connector-specific | Semântica varia por plataforma |
| Normalização de whitespace/line endings | Utilitário | Comportamento universal |
| Macros Confluence | Connector-specific | Semântica exclusiva |
| Consolidação | Core compartilhado | Consome manifest e Markdown |
| Manifest e incremental | Core compartilhado | Rastreabilidade universal |
| Paginação | Connector-specific com envelope comum | Cursor e protocolo variam |
| Descoberta de hierarquia | Connector-specific | Estrutura remota varia |
| `DiscoveryPage` e `PageRequest` | Core compartilhado | Cursor opaco e resultado comum |
| HTTP básico | Infraestrutura | Transporte reutilizável |
| Interpretação de rate limit | Extensível por estratégia | Headers e políticas variam |
| Autenticação | Infraestrutura + connector-specific | Vault comum; fluxo remoto específico |
| Assets | Extensível por estratégia | Descoberta específica, gravação comum |
| Cache de metadados | Infraestrutura | Já é agnóstico de conteúdo |
| Logging/progresso/cancelamento | Infraestrutura | Transversal |
| Generic Web crawling | Plugin/connector-specific | Não pertence às APIs oficiais |
| Formulário/detecção/card | Metadata de plugin + UI | UI apresenta; plugin descreve |

### 7.1 Paginação deve ser específica por conector?

Sim.

O código atual já comprova mecanismos distintos:

- Confluence usa cursor e endpoints diferentes para roots/children/search;
- GitBook usa `next.page`;
- Zendesk usa URL absoluta em `links.next`;
- Notion usa `next_cursor` e `has_more`;
- Microsoft Graph usa `@odata.nextLink`.

O Core deve compartilhar apenas:

- `PageRequest`;
- `DiscoveryPage`;
- cancelamento;
- limite desejado;
- cursor opaco.

Ele não deve interpretar o cursor.

### 7.2 Descoberta deve ser específica?

Sim. Contêineres significam coisas diferentes:

- Confluence: espaços e páginas;
- GitBook: organizações, spaces e pages;
- Zendesk: categorias, seções e artigos;
- Notion: workspace, databases e pages;
- SharePoint: sites, drives, folders e files;
- Generic Web: hosts, scopes e URLs.

### 7.3 Parsing deve ser específico?

Sim. O Core não deve conhecer:

- storage format e macros Confluence;
- blocos Notion;
- payload Markdown GitBook;
- HTML Zendesk;
- DOCX/PDF/XLSX SharePoint;
- DOM e boilerplate de websites.

### 7.4 Markdown deve permanecer compartilhado?

O renderer final deve ser compartilhado. A conversão semântica da plataforma para conteúdo canônico deve ficar no conector.

### 7.5 Consolidação deve permanecer compartilhada?

Sim. Ela depende de manifest, paths, metadata e Markdown já gravado, não da plataforma remota.

---

## 8. Arquitetura recomendada

```text
                         ┌──────────────────────┐
                         │         UI           │
                         │ somente apresentação │
                         └──────────┬───────────┘
                                    │ comandos / view models
                         ┌──────────▼───────────┐
                         │ Application Services │
                         │ browse/extract/export│
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │ Connector Catalog    │
                         │ factory + metadata   │
                         └──────────┬───────────┘
                                    │
        ┌───────────────────────────┼──────────────────────────┐
        │                           │                          │
┌───────▼────────┐         ┌────────▼───────┐        ┌────────▼────────┐
│ Confluence     │         │ GitBook        │        │ Zendesk/Notion  │
│ discovery      │         │ discovery      │        │ discovery       │
│ fetch + parse  │         │ fetch + parse  │        │ fetch + parse   │
└───────┬────────┘         └────────┬───────┘        └────────┬────────┘
        └───────────────────────────┼──────────────────────────┘
                                    │
                         ┌──────────▼───────────┐
                         │ KnowledgeDocument   │
                         │ canonical Markdown  │
                         └──────────┬───────────┘
                                    │
                  ┌─────────────────┼──────────────────┐
                  │                 │                  │
          ┌───────▼──────┐  ┌───────▼───────┐  ┌──────▼───────┐
          │ Renderer     │  │ Manifest      │  │ Asset policy │
          │ compartilhado│  │ incremental   │  │ extensível   │
          └───────┬──────┘  └───────┬───────┘  └──────────────┘
                  └─────────────────┬┘
                                    │
                         ┌──────────▼───────────┐
                         │ Consolidation/Export │
                         └──────────────────────┘
```

### 8.1 Plugin architecture adequada ao projeto

O projeto já possui um registry. A evolução adequada é torná-lo um catálogo interno orientado a descriptors.

Não é necessário agora:

- entry points Python;
- instalação dinâmica de pacotes;
- sandbox de plugins externos;
- versionamento de SDK público.

Um `ConnectorPlugin` interno já pode centralizar:

- `source_type`;
- factory;
- status;
- capabilities;
- form spec;
- aliases/domínios detectáveis;
- auth modes;
- card/ícone;
- limitações;
- versão do contrato.

### 8.2 Composição vs herança

Preferir composição:

```text
NotionConnector
  ├─ ApiHttpClient
  ├─ NotionPaginator
  ├─ NotionBlockParser
  └─ Runtime logger/token
```

Evitar uma grande classe base com hooks para cada variação. Herança deve expressar somente o contrato essencial.

---

## 9. Estrutura de diretórios proposta

Esta é uma estrutura alvo, não uma recomendação para mover tudo agora:

```text
alquimista/
├── application/
│   ├── browse.py
│   ├── extraction.py
│   ├── consolidation.py
│   └── jobs.py
├── domain/
│   ├── documents.py
│   ├── projects.py
│   ├── manifests.py
│   └── errors.py
├── connectors/
│   ├── contracts.py
│   ├── catalog.py
│   ├── shared/
│   │   └── http.py
│   ├── confluence/
│   │   ├── connector.py
│   │   ├── client.py
│   │   ├── discovery.py
│   │   └── parser.py
│   ├── gitbook/
│   │   └── connector.py
│   ├── zendesk/
│   │   └── connector.py
│   ├── notion/
│   │   └── connector.py
│   ├── sharepoint/
│   │   ├── connector.py
│   │   └── document_extractors.py
│   └── web/
│       ├── connector.py
│       ├── crawler.py
│       ├── fetchers.py
│       └── content_extractor.py
├── rendering/
│   ├── markdown.py
│   └── assets.py
├── infrastructure/
│   ├── storage.py
│   ├── manifest_index.py
│   ├── logging.py
│   └── sessions.py
└── ui/
```

### 9.1 Sequência segura de adoção

1. Criar contratos nos caminhos atuais.
2. Criar testes.
3. Extrair código novo para a estrutura alvo.
4. Manter facades/reexports temporários.
5. Mover apenas Confluence quando seus goldens estiverem estáveis.
6. Evitar mover arquivos sem ganho funcional ou de testabilidade.

---

## 10. Contratos recomendados

### 10.1 Contrato mínimo

```python
@dataclass(frozen=True)
class DocumentRef:
    source_id: str
    container_id: str
    document_id: str


class SourceConnector(Protocol):
    source_type: str

    def validate_connection(self) -> ConnectionResult: ...

    def list_containers(self) -> list[KnowledgeContainer]: ...

    def list_documents(
        self,
        container_id: str,
        request: PageRequest,
    ) -> DiscoveryPage[KnowledgeDocumentMetadata]: ...

    def fetch_document(self, ref: DocumentRef) -> KnowledgeDocument: ...

    def close(self) -> None: ...
```

### 10.2 Capacidades opcionais

```python
class HierarchicalDiscovery(Protocol):
    def list_roots(...) -> DiscoveryPage[KnowledgeDocumentMetadata]: ...
    def list_children(...) -> DiscoveryPage[KnowledgeDocumentMetadata]: ...


class SearchableConnector(Protocol):
    def search(...) -> DiscoveryPage[KnowledgeDocumentMetadata]: ...
```

### 10.3 Decisões de contrato

- `normalize_document()` deixa de ser obrigação pública.
- `fetch_document()` sempre devolve o modelo canônico.
- hierarquia é capability opcional;
- busca é capability opcional;
- paginação usa cursor opaco;
- `close()` continua obrigatório;
- o Core não testa `source_type` para escolher algoritmo;
- o registry valida o contrato ao ativar um conector.

### 10.4 Modelo intermediário

O modelo atual é uma boa base e deve ser evoluído, não substituído.

Entidades suficientes:

- `KnowledgeSource`;
- `KnowledgeContainer`;
- `KnowledgeDocumentMetadata`;
- `DocumentRef`;
- `KnowledgeDocument`;
- `AssetRef`;
- `KnowledgeSelection`.

Campos essenciais do documento:

```text
source_type
source_id
container_id
document_id
parent_id
title
original_url
path
created_at
updated_at
etag/version
content_markdown
assets
metadata extensível
```

Um AST de `ContentNode` seria overengineering no estágio atual.

---

## 11. Estado, configuração e contexto de execução

### 11.1 Situação atual

O estado é distribuído entre:

- `ProjectConfig`;
- `MainWindowState`;
- `RuntimeSecrets`;
- `SourceRuntime`;
- `CancellationToken`;
- callbacks de log/progresso;
- paths construídos pelos services.

`SourceRuntime` também contém campos legados de Confluence e campos novos de conectores.

### 11.2 Contexto recomendado

Uma estrutura pequena pode reduzir passagem de argumentos:

```python
@dataclass(frozen=True)
class ExtractionJobContext:
    run_id: str
    project: ProjectConfig
    project_dir: Path
    output_dir: Path
    token: CancellationToken
    progress: ProgressCallback
    log: StructuredLogCallback
```

Separadamente:

```python
@dataclass
class ConnectorRuntime:
    source: SourceConfig
    connector: SourceConnector
    selected_documents: tuple[DocumentRef, ...]
    metadata: dict[str, KnowledgeDocumentMetadata]
```

Segredos não devem entrar no job context persistível. Eles devem ser usados somente durante a criação do conector.

---

## 12. Tratamento de erros

### 12.1 Hierarquia recomendada

```text
AlquimistaError
├── ConfigurationError
├── ConnectorError
│   ├── AuthenticationError
│   ├── PermissionDeniedError
│   ├── ResourceNotFoundError
│   ├── ConnectorTransportError
│   ├── ConnectorRateLimitError
│   ├── ConnectorPayloadError
│   └── ConnectorCapabilityError
├── DiscoveryError
├── FetchError
├── NormalizationError
├── RenderingError
├── ManifestError
├── StorageError
├── ConsolidationError
└── OperationCancelledError
```

### 12.2 Compatibilidade

Classes legadas podem continuar existindo como aliases/subclasses:

```python
class ConfluenceConnectionError(ConnectorTransportError):
    pass


class InvalidResponseError(ConnectorPayloadError):
    pass
```

### 12.3 UI

A UI deve mapear categoria para mensagem, sem procurar palavras em strings de exceção.

Exemplo:

```text
AuthenticationError → credencial inválida/expirada
PermissionDeniedError → acesso sem permissão
ConnectorRateLimitError → aguarde e tente novamente
ConnectorTransportError → serviço indisponível
ConnectorPayloadError → resposta incompatível
```

O nome do conector deve vir do contexto da operação, não estar fixo na mensagem.

---

## 13. Observabilidade e diagnóstico

### 13.1 Pontos positivos existentes

- logs JSONL;
- redação de segredos;
- console human-readable;
- progresso;
- cancelamento;
- `ExecutionReport` estruturado;
- relatório de falhas;
- manifest por documento.

### 13.2 Lacunas

Os logs ainda são predominantemente mensagens de texto. Faltam campos consistentes:

- `run_id`;
- `source_id`;
- `source_type`;
- `container_id`;
- `document_id`;
- `document_key`;
- `stage`;
- `attempt`;
- `duration_ms`;
- `from_cache`;
- `retry_delay`;
- `status`.

### 13.3 Estrutura sugerida

```json
{
  "run_id": "...",
  "component": "connector",
  "source_type": "notion_api",
  "source_id": "...",
  "stage": "fetch",
  "document_id": "...",
  "attempt": 2,
  "duration_ms": 481,
  "level": "INFO",
  "message": "Documento carregado"
}
```

Não é necessário substituir `logging`. Um `LoggerAdapter` ou callback estruturado é suficiente.

---

## 14. Estratégia contra regressões

### 14.1 Estrutura de testes sugerida

```text
tests/
├── contracts/
│   ├── test_connector_contract.py
│   └── test_pipeline_contract.py
├── golden/
│   ├── confluence/
│   │   ├── fixtures/
│   │   └── expected/
│   ├── gitbook/
│   ├── zendesk/
│   ├── notion/
│   └── sharepoint/
└── integration/
    ├── test_confluence_live.py
    └── ...
```

### 14.2 Camadas de teste

1. Unitários de parser/paginação por conector.
2. Contract tests para todo conector ativo.
3. Golden tests do documento final completo.
4. Pipeline genérico: incremental, manifest e relatórios.
5. Consolidação: pacotes, ordem e limites.
6. UI: wiring, estado e navegação.
7. Integração real opcional por marker/credencial.
8. E2E pequeno do Confluence antes de releases.

### 14.3 Golden samples

Fluxo:

```text
payload conhecido
  ↓
conector/parser
  ↓
KnowledgeDocument
  ↓
renderer compartilhado
  ↓
Markdown completo
  ↓
comparação com expected/*.md
```

Normalizar somente elementos instáveis:

- timestamp de coleta;
- ID de execução;
- diretório temporário;
- URL assinada/temporária;
- metadata explicitamente não ordenada;
- finais de linha.

Não normalizar:

- títulos;
- ordem do conteúdo;
- hierarquia;
- links canônicos;
- IDs de documentos;
- cabeçalhos;
- macros;
- estrutura Markdown;
- hashes de entradas estáveis.

Toda atualização de golden deve ser revisada em diff.

### 14.4 Casos Confluence prioritários

- página simples;
- árvore com vários níveis;
- macro code;
- painéis info/warning/note/tip;
- macro expand;
- link entre páginas;
- attachment;
- imagem local e remota;
- tabela;
- página vazia;
- caracteres UTF-8;
- restrição pública/privada;
- incremental sem mudança;
- mudança apenas de metadata;
- mudança de conteúdo;
- erro preservando versão anterior.

---

## 15. Estratégia para Generic Web

Generic Web deve ser um conector próprio, não um modo especial espalhado pelo Core.

```text
GenericWebConnector
  ├─ ScopePolicy
  │   ├─ same_host
  │   ├─ same_path_prefix
  │   └─ allow/deny patterns
  ├─ DiscoveryStrategy
  │   ├─ sitemap
  │   ├─ internal_links
  │   └─ single_page
  ├─ FetchStrategy
  │   ├─ requests/static
  │   └─ playwright/rendered
  ├─ ContentExtractor
  │   ├─ main/readability
  │   └─ site-specific hook
  └─ CanonicalizationPolicy
      ├─ canonical URL
      ├─ fragments/query
      └─ duplicate hash
```

### 15.1 Fase inicial recomendada

Suportar primeiro:

- página única;
- HTML estático;
- sitemap opcional;
- mesmo host;
- limite pequeno de páginas;
- extração do conteúdo principal;
- links absolutos;
- imagens referenciadas;
- deduplicação por canonical URL/hash.

### 15.2 Fase posterior

- SPAs;
- Playwright;
- autenticação interativa;
- downloads autorizados;
- políticas avançadas de assets;
- renderização por domínio;
- crawl incremental.

### 15.3 Proteções necessárias

- limite de profundidade;
- limite de URLs;
- timeout total;
- rate limit;
- allow/deny patterns;
- canonicalização antes da fila;
- bloqueio de loops;
- deduplicação;
- tratamento configurável de robots;
- isolamento de cookies/credenciais;
- cache sem body sensível.

---

## 16. Plano incremental de refatoração

### Etapa 0 — Baseline do Confluence

**Objetivo:** congelar o comportamento funcional conhecido.  
**Arquivos:** novos fixtures/goldens e testes.  
**Mudança:** capturar payloads representativos e Markdown esperado.  
**Risco:** baixo.  
**Benefício:** muito alto.  
**Pré-requisito:** escolher exemplos conhecidos e remover dados sensíveis.  
**Validação:** outputs atuais idênticos aos goldens.

### Etapa 1 — Conformance kit

**Objetivo:** garantir que todo conector ativo respeite o contrato.  
**Arquivos:** `connectors/base.py`, novos testes de contrato.  
**Mudança:** fixtures parametrizadas para lifecycle, IDs, metadata, close e erros.  
**Risco:** baixo.  
**Benefício:** alto.  
**Pré-requisito:** nenhuma mudança funcional.  
**Validação:** Confluence, GitBook e Zendesk aprovam a mesma suíte.

### Etapa 2 — Erros neutros

**Objetivo:** separar categoria da falha e plataforma.  
**Arquivos:** `errors.py`, `connectors/http.py`, `operation_controller.py`.  
**Mudança:** nova hierarquia com aliases legados.  
**Risco:** baixo.  
**Benefício:** alto.  
**Pré-requisito:** testes atuais de erros.  
**Validação:** 401, 403, 404, 429, timeout e payload inválido por conector.

### Etapa 3 — Catalog/descriptor único

**Objetivo:** centralizar metadata de integração.  
**Arquivos:** registry, connector forms, source detection e dashboard.  
**Mudança:** descriptor fornece capabilities e presentation metadata.  
**Risco:** médio.  
**Benefício:** alto.  
**Pré-requisito:** testes de UI e source detection.  
**Validação:** conector fake aparece sem branches adicionais na `MainWindow`.

### Etapa 4 — Remover listas fechadas da UI

**Objetivo:** UI não decidir por `source_type`.  
**Arquivos:** `ui/main_window.py`, controllers e registry.  
**Mudança:** decisões baseadas em capabilities/protocols.  
**Risco:** médio.  
**Benefício:** alto.  
**Pré-requisito:** descriptor único.  
**Validação:** testes de árvore com conector sintético.

### Etapa 5 — Unificar Markdown Confluence

**Objetivo:** preview e extração usarem a mesma normalização.  
**Arquivos:** `markdown.py`, `connectors/confluence.py`, `services.py`, UI preview.  
**Mudança:** parser Confluence específico + renderer único.  
**Risco:** médio/alto.  
**Benefício:** muito alto.  
**Pré-requisito:** goldens Confluence.  
**Validação:** nenhum golden muda sem decisão explícita.

### Etapa 6 — Unificar discovery e runtime

**Objetivo:** evitar redescoberta integral.  
**Arquivos:** `ui/controllers.py`, browser contracts e runtime.  
**Mudança:** transportar `DocumentRef` e metadata selecionada.  
**Risco:** médio.  
**Benefício:** alto.  
**Pré-requisito:** seleção estruturada estável.  
**Validação:** extrair poucas páginas sem chamar listagem integral novamente.

### Etapa 7 — Completar Notion

**Objetivo:** validar a abstração com conteúdo e paginação diferentes.  
**Arquivos:** `connectors/notion.py`, testes e fixtures.  
**Mudança:** cursor, blocos aninhados, assets, metadata e canonical Markdown.  
**Risco:** médio.  
**Benefício:** alto.  
**Pré-requisito:** contrato e pipeline únicos.  
**Validação:** contract tests, goldens e pipeline incremental.

### Etapa 8 — Remover o legado

**Objetivo:** manter um único algoritmo de extração.  
**Arquivos:** `services.py`, `client.py`, callers e facades.  
**Mudança:** adapter de compatibilidade sem pipeline paralelo.  
**Risco:** médio.  
**Benefício:** alto.  
**Pré-requisito:** callers identificados e Confluence protegido.  
**Validação:** projetos antigos, goldens e suíte completa.

### Etapa 9 — Generic Web inicial

**Objetivo:** suportar página única e documentação estática.  
**Arquivos:** novo package `connectors/web/`.  
**Mudança:** fetch estático, canonicalização e content extraction.  
**Risco:** médio.  
**Benefício:** alto.  
**Pré-requisito:** arquitetura baseada em descriptor e contrato.  
**Validação:** fixtures locais sem rede e sites controlados opcionais.

### Etapa 10 — Reorganização física

**Objetivo:** melhorar coesão somente onde comprovado.  
**Arquivos:** principalmente Confluence e application services.  
**Mudança:** packages menores e facades de compatibilidade.  
**Risco:** médio.  
**Benefício:** médio.  
**Pré-requisito:** comportamento estabilizado.  
**Validação:** imports, build e suíte completa.

---

## 17. Priorização benefício × risco × esforço

| Prioridade | Mudança | Benefício | Risco | Esforço |
|---|---|---|---|---|
| P0 | Golden baseline do Confluence | Alto | Baixo | Médio |
| P0 | Contract tests para conectores ativos | Alto | Baixo | Médio |
| P1 | Hierarquia de erros neutra | Alto | Baixo | Baixo |
| P1 | Registry controlar metadata e capabilities | Alto | Médio | Médio |
| P1 | Remover fallback Confluence da UI genérica | Alto | Médio | Médio |
| P1 | Unificar preview e pipeline real | Alto | Médio | Médio |
| P1 | Evitar redescoberta integral no runtime | Alto | Médio | Médio |
| P2 | Tornar formato de conteúdo explícito | Médio | Médio | Médio |
| P2 | Eliminar duplicação `TreeMixin`/MainWindow | Médio | Médio | Médio |
| P2 | Atualizar `MAPA.md` | Médio | Baixo | Baixo |
| P3 | Estrutura completa por conector | Médio | Médio | Alto |
| P3 | Plugins externos/dinâmicos | Baixo agora | Alto | Alto |
| P3 | AST universal de conteúdo | Baixo agora | Alto | Alto |

Melhor relação benefício/risco/esforço:

1. golden samples;
2. contract tests;
3. erros neutros;
4. descriptor único;
5. remoção de branches de plataforma da UI.

---

## 18. O que não modificar agora

- Não reescrever a aplicação.
- Não trocar PySide6, Pydantic, SQLite ou `FileTransaction`.
- Não alterar schema do manifest sem necessidade concreta.
- Não mudar o formato de `document_key`.
- Não alterar hashes antes dos goldens.
- Não remover o pipeline legado antes de identificar callers.
- Não ativar Notion ou SharePoint apenas mudando o registry.
- Não criar um AST universal de conteúdo.
- Não separar todo conector em vários arquivos por simetria.
- Não implementar plugins externos/dinâmicos.
- Não mover todos os módulos de uma vez.
- Não generalizar macros Confluence.
- Não substituir o HTTP compartilhado sem requisito comprovado.
- Não refatorar código funcional apenas por estética.
- Não misturar reorganização física com mudança funcional crítica.

---

## 19. Teste mental de extensibilidade

### Cenário A — Google Drive

Na arquitetura recomendada, criar:

- `GoogleDriveConnector`;
- parser/download para Google Docs e arquivos suportados;
- plugin descriptor;
- form spec e detector;
- fixtures e goldens.

Não alterar:

- `ExtractionService`;
- `KnowledgeDocumentRenderer`;
- `ConsolidationService`;
- `MainWindow`.

Na arquitetura atual, seria necessário alterar listas na UI, dashboard, forms, detection e registry.

### Cenário B — Generic Website

Criar:

- `GenericWebConnector`;
- crawler e scope policy;
- fetch estático/Playwright;
- canonicalização;
- parser de conteúdo principal;
- fixtures e goldens.

O Core continua recebendo `KnowledgeDocument`.

### Cenário C — Notion possui paginação completamente diferente

Somente `NotionConnector` e seus testes devem mudar. Ele interpreta `next_cursor`; o Core transporta o cursor como valor opaco.

Confluence não deve ser afetado.

### Cenário D — Mudança na geração de Markdown

Todos os conectores são afetados intencionalmente pelo renderer compartilhado. Parsing e paginação não mudam.

A matriz de goldens deve revelar exatamente quais outputs mudaram. Uma necessidade exclusiva de Confluence deve ser tratada no parser Confluence, antes do renderer comum.

---

## 20. Avaliação arquitetural quantitativa

Escala: 0 representa estado ruim; 10 representa estado excelente. Em “Acoplamento”, nota alta significa baixo acoplamento.

| Área | Atual | Projetada | Justificativa |
|---|---:|---:|---|
| Modularidade | 6,5 | 8,5 | Há módulos reais, mas pipelines e UI ainda se sobrepõem |
| Separação de responsabilidades | 5,5 | 8,5 | Services separados; MainWindow e Markdown ainda misturam papéis |
| Extensibilidade | 6,0 | 9,0 | Registry existe, mas onboarding toca vários arquivos |
| Testabilidade | 7,5 | 9,0 | Boa suíte sintética e componentes sem Qt |
| Proteção contra regressões | 5,5 | 9,0 | Bons testes pontuais, ausência de goldens completos |
| Acoplamento | 5,5 | 8,5 | Core importa Confluence e UI contém listas de plataformas |
| Coesão | 6,0 | 8,5 | Conectores ativos coesos; services/markdown misturam gerações |
| Observabilidade | 6,0 | 8,0 | JSON logs e reports existem; faltam campos estruturados |
| Manutenibilidade | 6,5 | 8,5 | Base boa, mas MainWindow e legado elevam custo |
| Preparação para novos conectores | 6,0 | 9,0 | Modelo intermediário existe; fronteira plugin/application incompleta |

---

## 21. Respostas diretas às questões críticas

1. **A arquitetura atual escala para 5, 10 ou 20 conectores?** Até 5, sim; 10 com custo crescente; 20 exige fechar as fronteiras propostas.
2. **Onde estão os maiores acoplamentos?** `MainWindow`, `services.py`, `markdown.py`, runtime builder e metadata de connector espalhada.
3. **O que deve ser compartilhado?** Modelo intermediário, renderer final, manifest, storage, consolidação, HTTP básico, cache, logging, progresso e cancelamento.
4. **O que deve ser isolado?** Paginação, discovery, parsing, autenticação específica e assets remotos.
5. **Paginação deve ser específica?** Sim.
6. **Descoberta deve ser específica?** Sim, com envelope comum.
7. **Parsing deve ser específico?** Sim.
8. **Markdown deve permanecer compartilhado?** O renderer final, sim; parsing de origem, não.
9. **Consolidação deve permanecer compartilhada?** Sim.
10. **Precisa de modelo intermediário?** Já existe e é adequado; precisa apenas evolução incremental.
11. **Precisa de interface/base?** Sim, menor que o ABC atual.
12. **Como impedir regressões?** Contract tests, goldens e pipeline único.
13. **Como testar cada integração?** Fixtures por conector, expected Markdown e matriz comum de contrato.
14. **Como adicionar conectores sem mudar o Core?** Descriptor + factory + contracts opcionais.
15. **Como preparar Generic Web?** Como connector/plugin próprio com strategies de discovery/fetch.
16. **Como reduzir responsabilidades da UI?** Mover casos de uso para controllers/application services sem Qt.
17. **Maior benefício com menor risco?** Baseline golden do Confluence.
18. **O que alterar agora?** Testes de regressão e contratos.
19. **O que deixar para depois?** Reorganização física, plugins externos e AST universal.
20. **O que definitivamente não alterar agora?** Schema, hashes, storage e comportamento Confluence sem goldens.

---

## 22. Top 10 próximas ações

1. Criar golden samples completos do Confluence antes de qualquer nova integração.
2. Criar um conformance kit executável para todo conector ativo.
3. Corrigir a hierarquia de erros para remover herança semântica de Confluence.
4. Centralizar no registry a metadata hoje espalhada entre forms, dashboard e capabilities.
5. Substituir listas fechadas da `MainWindow` por decisões baseadas em descriptor/capabilities.
6. Tornar preview e extração real usuários do mesmo pipeline Confluence.
7. Fazer o runtime consumir referências selecionadas sem redescobrir todo o contêiner.
8. Reduzir o contrato obrigatório, separando hierarchy e search em Protocols opcionais.
9. Usar Notion como teste real da abstração, incluindo paginação e blocos aninhados.
10. Somente depois iniciar Generic Web, começando por página única e sites estáticos.

---

## Conclusão

O ALQuimista já possui a maior parte das fundações corretas: modelos comuns, conectores, serviços, armazenamento seguro e testes. O principal trabalho não é inventar uma nova arquitetura, mas concluir a migração já iniciada, reduzir as exceções específicas de Confluence fora do conector e transformar o comportamento atualmente funcional em contratos verificáveis.

O equilíbrio recomendado é:

```text
isolamento da variação por conector
        +
modelo intermediário pequeno e estável
        +
renderer/manifest/consolidação compartilhados
        +
golden samples por plataforma
        +
migração incremental
```

> **Se eu fosse o responsável técnico pelo Projeto Alquimista hoje, a primeira mudança arquitetural seria criar uma suíte de contrato e golden samples que congelasse o pipeline e o Markdown atual do Confluence antes de desenvolver qualquer nova integração.**
