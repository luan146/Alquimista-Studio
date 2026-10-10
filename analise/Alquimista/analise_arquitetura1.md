# Análise Arquitetural — Projeto ALQuimista

## Objetivo

Esta análise avalia como o Projeto ALQuimista pode continuar crescendo sem aumentar excessivamente o risco de regressões entre conectores e módulos compartilhados.

O foco principal é permitir que o sistema suporte novas fontes — como Notion, GitBook, SharePoint, Zendesk, sites genéricos e futuras integrações — sem que alterações específicas de uma plataforma quebrem funcionalidades já estáveis, especialmente o Confluence.

---

# 1. Diagnóstico geral

A arquitetura atual já possui uma boa base para modularização.

O projeto possui elementos importantes como:

- `connectors/base.py`;
- `ConnectorCapabilities`;
- `KnowledgeSourceConnector`;
- `KnowledgeDocument`;
- `KnowledgeContainer`;
- `ConnectorRegistry`;
- `DiscoveryPage`;
- `PageRequest`;
- `ExtractionService`;
- `ConsolidationService`;
- separação parcial entre UI, serviços, conectores e persistência.

Isso significa que não é necessário reescrever o ALQuimista.

O principal trabalho agora é fortalecer as fronteiras entre as camadas.

A regra arquitetural central recomendada é:

> O núcleo do ALQuimista não deve saber se está trabalhando com Confluence, Notion, GitBook, SharePoint, Zendesk ou qualquer outra plataforma.

O núcleo deve trabalhar apenas com contratos comuns.

---

# 2. Problema que precisa ser evitado

O maior risco futuro é o crescimento de condicionais específicas de plataforma em módulos compartilhados.

Exemplo do que deve ser evitado:

```python
if source_type == "confluence":
    ...
elif source_type == "notion":
    ...
elif source_type == "sharepoint":
    ...
```

especialmente dentro de módulos como:

```text
services.py
markdown.py
main_window.py
tree_models.py
selection_mixin.py
```

Quando isso começa a acontecer, a abstração entre o core e os conectores está vazando.

Uma correção feita para o Notion poderia acabar alterando comportamento do Confluence.

---

# 3. Modelo arquitetural recomendado

O fluxo ideal é:

```text
Confluence ─────┐
Notion ─────────┤
GitBook ────────┤
SharePoint ─────┤
Zendesk ────────┤
Web genérico ───┘
        │
        ▼
Conector específico
        │
        ▼
Normalização / Mapper
        │
        ▼
Contratos do ALQuimista
        │
        ▼
Discovery / Extraction
        │
        ▼
Markdown
        │
        ▼
Persistência
        │
        ▼
Consolidação
```

O núcleo recebe sempre estruturas conhecidas, por exemplo:

```text
KnowledgeSource
KnowledgeContainer
KnowledgeDocumentMetadata
KnowledgeDocument
DiscoveryPage
```

Cada conector fica responsável por traduzir a plataforma externa para esses contratos.

---

# 4. Paginação por conector

É recomendável separar a lógica de paginação específica de cada plataforma.

Porém, não é necessário criar uma implementação completamente independente de paginação no núcleo para cada conector.

A abordagem recomendada é usar um contrato comum:

```python
DiscoveryPage(
    items=[...],
    next_cursor="..."
)
```

O cursor deve ser considerado opaco pelo núcleo.

O ALQuimista não precisa saber se:

- Confluence usa offset;
- Notion usa `next_cursor`;
- SharePoint usa `@odata.nextLink`;
- GitBook usa página ou cursor;
- uma API usa `page=5`;
- outra API usa tokens internos.

Cada conector traduz seu mecanismo interno para:

```text
items
next_cursor
```

O núcleo apenas solicita a próxima página.

---

# 5. Evolução do subsistema de Discovery

O projeto já possui:

```text
browser/contracts.py
browser/service.py
browser/adapters.py
browser/cache.py
```

e contratos como:

```text
PageRequest
DiscoveryPage
DocumentMetadata
SpaceMetadata
DiscoveryAdapter
```

Esses conceitos já ultrapassam a responsabilidade exclusiva de um navegador.

Uma evolução futura recomendada seria:

```text
alquimista/
    discovery/
        contracts.py
        service.py
        cache.py
```

E deixar o navegador apenas como uma implementação:

```text
browser/
    playwright_adapter.py
```

Com isso:

```text
UI
 │
 ▼
DiscoveryController
 │
 ▼
DiscoveryService
 │
 ▼
Connector
```

A interface não precisa saber se a fonte é lazy, síncrona, paginada ou baseada em navegador.

---

# 6. Estrutura interna dos conectores

Atualmente conectores maiores, como o Confluence, acumulam várias responsabilidades.

Uma evolução possível seria:

```text
connectors/
    confluence/
        connector.py
        client.py
        discovery.py
        mapper.py

    notion/
        connector.py
        client.py
        discovery.py
        mapper.py

    sharepoint/
        connector.py
        client.py
        discovery.py
        mapper.py

    web/
        connector.py
        crawler.py
        discovery.py
        mapper.py
```

## `client.py`

Responsável exclusivamente pela comunicação externa:

```text
HTTP
API
retry
rate limit
auth
timeouts
```

## `discovery.py`

Responsável por:

```text
listar containers
listar documentos
listar filhos
paginação
hierarquia
cursor
```

## `mapper.py`

Responsável por transformar o formato externo para o formato do ALQuimista.

Exemplo:

```text
JSON Notion
    ↓
NotionMapper
    ↓
KnowledgeDocument
```

ou:

```text
Confluence Storage HTML
    ↓
ConfluenceMapper
    ↓
KnowledgeDocument
```

## `connector.py`

Funciona como camada de integração:

```text
client
+
discovery
+
mapper
```

---

# 7. Normalização antes do Markdown

Um dos pontos mais importantes da arquitetura atual é `markdown.py`.

Hoje existem comportamentos ligados diretamente ao Confluence, como:

```text
_replace_macros
_attachment_url
_replace_links
```

Isso era natural quando o Confluence era a principal fonte.

Com múltiplos conectores, a arquitetura deve caminhar para:

```text
Confluence
    ↓
ConfluenceContentNormalizer
    ↓
Documento normalizado
    ↓
MarkdownRenderer
```

Notion:

```text
Notion
    ↓
NotionContentNormalizer
    ↓
Documento normalizado
    ↓
MarkdownRenderer
```

SharePoint:

```text
SharePoint
    ↓
SharePointContentNormalizer
    ↓
Documento normalizado
    ↓
MarkdownRenderer
```

O renderer de Markdown deve conhecer o formato do ALQuimista, e não detalhes das plataformas externas.

---

# 8. Árvore de seleção

Hoje partes importantes da árvore ainda passam por:

```text
main_window.py
selection_mixin.py
tree_mixin.py
tree_models.py
```

O objetivo futuro deve ser:

```text
UI
 │
 ▼
DiscoveryController
 │
 ▼
DiscoveryService
 │
 ▼
Connector
```

A UI deveria solicitar operações como:

```python
children = discovery.list_children(node)
```

em vez de decidir internamente:

```text
é lazy?
é Confluence?
tem root_documents?
usa browser?
usa paginação?
```

Essas decisões devem ficar abaixo da camada de interface.

---

# 9. Relação com o problema de desempenho

Essa arquitetura também ajuda no cenário de fontes com centenas de containers e milhares de páginas.

A interface não deve carregar tudo antecipadamente.

Exemplo:

```text
Fonte

▶ Espaço A
▶ Espaço B
▶ Espaço C
▶ Espaço D
```

Quando o usuário expande:

```text
Espaço A
    ↓
DiscoveryService
    ↓
Connector
    ↓
50 documentos
    ↓
next_cursor
```

Ao precisar de mais itens:

```text
next_cursor
    ↓
mais documentos
```

A estratégia deve ser:

- lazy loading;
- paginação;
- carregamento sob demanda;
- cache apenas de metadados;
- conteúdo completo somente quando necessário.

Isso evita carregar milhares de páginas que o usuário talvez nunca selecione.

---

# 10. Suporte a URLs e sites genéricos

O objetivo futuro de permitir colar qualquer URL e transformar a página em Markdown é compatível com a arquitetura proposta.

Porém, um site comum nem sempre possui:

```text
container
space
section
```

Por isso, o modelo deve trabalhar com capacidades.

Exemplo:

```python
ConnectorCapabilities(
    containers=True,
    hierarchy=True,
    pagination=True,
    search=True,
    single_document=True,
)
```

Um conector web simples poderia usar:

```python
ConnectorCapabilities(
    containers=False,
    hierarchy=False,
    pagination=False,
    search=False,
    single_document=True,
)
```

No futuro, o `WebConnector` poderia suportar modos como:

```text
Single URL
Sitemap
Crawl
```

Fluxos:

```text
URL individual
    ↓
1 documento
```

```text
sitemap.xml
    ↓
250 documentos
```

```text
site
    ↓
crawler
    ↓
milhares de documentos
```

sem alterar Markdown, consolidação ou storage.

Para crawling, seria importante prever:

- limite de profundidade;
- limite máximo de páginas;
- domínio permitido;
- redirects controlados;
- bloqueio de hosts locais e internos;
- proteção contra SSRF;
- tratamento de loops;
- cancelamento;
- rate limit;
- respeito às regras e políticas aplicáveis ao site.

---

# 11. Pontos de risco atuais

## 11.1 `main_window.py`

Atualmente é um dos principais pontos de concentração:

```text
~2733 linhas
~132 métodos
```

Mesmo sendo principalmente um orquestrador, ainda contém várias operações relacionadas a:

- árvore;
- carregamento;
- workers;
- Markdown;
- consolidação;
- navegação;
- projeto;
- browser/discovery.

O tamanho sozinho não é necessariamente o problema.

O risco está no raio de impacto.

Quanto mais decisões de domínio forem tomadas dentro da `MainWindow`, maior a chance de uma alteração em uma funcionalidade atingir outras telas ou conectores.

## 11.2 `services.py`

O arquivo possui aproximadamente:

```text
~1145 linhas
```

e mantém duas arquiteturas:

```text
_run_generic()
_run_legacy()
```

além de:

```text
SourceRuntime.is_generic
```

Isso significa que ainda existem dois pipelines convivendo.

A recomendação é gradualmente levar o Confluence para o fluxo genérico.

Objetivo final:

```text
Confluence
Notion
GitBook
SharePoint
Zendesk
Web
     ↓
Connector Contract
     ↓
ExtractionService
```

sem um pipeline separado para Confluence.

---

# 12. Funções duplicadas

O `MAPA.md` registra funções duplicadas em:

```text
selection_mixin.py
connection_mixin.py
execution_controller.py
auth.py
```

Em Python, uma segunda definição com o mesmo nome sobrescreve a primeira.

Isso cria um risco real para manutenção por IA ou por desenvolvedor.

Exemplo:

```python
def _selection_changed(...):
    # implementação antiga
```

mais abaixo:

```python
def _selection_changed(...):
    # implementação realmente executada
```

Uma IA pode encontrar a primeira função, corrigir corretamente e ainda assim o programa continuar apresentando o problema.

Essa dívida técnica deveria ser eliminada antes de uma expansão forte do projeto.

---

# 13. Testes de contrato dos conectores

Uma das melhores proteções contra regressão seria criar testes que todos os conectores precisem passar.

Exemplo conceitual:

```python
def connector_contract(connector):
    connector.validate_connection()

    containers = connector.list_containers()

    documents = connector.list_documents(...)

    document = connector.get_document(...)

    assert document.id
    assert document.title
    assert document.source_url
```

Para conectores lazy:

```python
page1 = connector.list_children(...)

assert page1.items

if page1.next_cursor:
    page2 = connector.list_children(
        cursor=page1.next_cursor
    )
```

Então:

```text
ConfluenceConnector
        ↓
Connector Contract Tests
        ↓
OK
```

```text
NotionConnector
        ↓
Connector Contract Tests
        ↓
OK
```

```text
SharePointConnector
        ↓
Connector Contract Tests
        ↓
OK
```

Isso garante que conectores diferentes respeitem a mesma interface de domínio.

---

# 14. FakeConnector

É recomendável criar um conector artificial para testes.

Exemplo:

```text
tests/
    fake_connector.py
```

Ele não utiliza:

```text
Confluence
Notion
HTTP
Playwright
API externa
```

Retorna simplesmente:

```text
Fonte teste
 └── Espaço A
      ├── Página 1
      └── Página 2
```

Esse conector permite testar:

```text
FakeConnector
      ↓
Discovery
      ↓
Seleção
      ↓
Extração
      ↓
Markdown
      ↓
Manifest
      ↓
Consolidação
```

Se alguma parte do núcleo começar a exigir algo específico do Confluence, o `FakeConnector` tende a expor imediatamente o acoplamento indevido.

---

# 15. Golden Tests do Confluence

Como o Confluence já possui comportamento estável, é recomendável congelar exemplos conhecidos como testes de regressão.

Casos importantes:

```text
página simples
página com tabela
página com imagem
página com macro
página pai/filho
página restrita
página com link interno
```

Exemplo:

```text
fixture_confluence_table.json
        ↓
pipeline
        ↓
resultado gerado
```

comparado com:

```text
expected_confluence_table.md
```

Teste:

```python
assert generated == expected
```

Isso permite refatorações profundas sem depender apenas de testes funcionais superficiais.

Se o comportamento do Confluence mudar inesperadamente, o teste falha imediatamente.

---

# 16. Arquitetura de referência futura

Uma possível direção arquitetural:

```text
alquimista/

├── core/
│   ├── models.py
│   ├── capabilities.py
│   ├── errors.py
│   └── contracts/
│       ├── connector.py
│       ├── discovery.py
│       └── document.py
│
├── discovery/
│   ├── service.py
│   └── cache.py
│
├── extraction/
│   ├── service.py
│   └── manifest.py
│
├── rendering/
│   ├── markdown.py
│   └── consolidation.py
│
├── connectors/
│   ├── confluence/
│   │   ├── connector.py
│   │   ├── client.py
│   │   ├── discovery.py
│   │   └── mapper.py
│   │
│   ├── notion/
│   ├── gitbook/
│   ├── sharepoint/
│   ├── zendesk/
│   └── web/
│
└── ui/
    ├── controllers/
    ├── pages/
    ├── components/
    └── main_window.py
```

Essa estrutura deve ser entendida como direção arquitetural, e não como uma refatoração que precisa ser realizada de uma única vez.

---

# 17. O que NÃO fazer agora

Não é recomendável solicitar ao Codex algo como:

> reorganize o projeto inteiro seguindo essa arquitetura.

Isso produziria:

- milhares de linhas movidas;
- imports alterados;
- risco de regressão alto;
- conflitos;
- dificuldade de revisão;
- pouco benefício funcional imediato.

A melhor abordagem é refatorar por fronteiras.

---

# 18. Ordem recomendada de evolução

## Etapa 1 — Remover duplicações

Eliminar definições duplicadas existentes em:

```text
selection_mixin.py
connection_mixin.py
execution_controller.py
auth.py
```

Criar testes de regressão antes ou durante a limpeza.

## Etapa 2 — Congelar comportamento atual do Confluence

Criar Golden Tests para:

- Markdown;
- hierarquia;
- lazy loading;
- paginação;
- visibilidade;
- links;
- macros;
- imagens;
- tabelas.

## Etapa 3 — Consolidar o contrato de Discovery

Transformar conceitos como:

```text
DiscoveryPage
PageRequest
DocumentMetadata
```

em contratos centrais do ALQuimista.

## Etapa 4 — Criar DiscoveryService

Mover decisões sobre:

- lazy;
- paginação;
- cursor;
- cache;
- filhos;
- raízes;

para uma camada intermediária.

A UI deve consumir essa camada.

## Etapa 5 — Separar normalização de conteúdo

Mover comportamentos específicos de plataforma para normalizadores ou mappers.

Exemplo:

```text
ConfluenceContentNormalizer
NotionContentNormalizer
SharePointContentNormalizer
```

O renderer Markdown fica genérico.

## Etapa 6 — Migrar completamente o Confluence para o pipeline genérico

Eliminar progressivamente a necessidade de:

```text
_run_legacy
SourceRuntime.is_generic
```

Somente após testes comprovarem equivalência.

## Etapa 7 — Usar Notion como prova arquitetural

O Notion deve ser usado como teste da nova arquitetura.

Idealmente, adicionar ou corrigir Notion deveria exigir mudanças principalmente em:

```text
connectors/notion/
source_detection.py
connector_forms.py
registry.py
tests/
```

Se for necessário alterar amplamente:

```text
services.py
markdown.py
main_window.py
selection_mixin.py
storage.py
consolidation
```

isso indica que ainda existe acoplamento excessivo.

## Etapa 8 — Criar WebConnector

Depois que a arquitetura estiver validada com pelo menos dois conectores independentes, adicionar:

```text
WebConnector
```

com modos:

```text
Single URL
Sitemap
Crawl
```

---

# 19. Métrica de qualidade arquitetural

Uma métrica prática para avaliar a saúde da arquitetura é:

> Quantos arquivos compartilhados precisam ser modificados para adicionar um novo conector?

Exemplo ideal:

```text
connectors/mediawiki/
source_detection.py
connector_forms.py
registry.py
tests/
```

Exemplo preocupante:

```text
services.py
main_window.py
markdown.py
selection_mixin.py
tree_models.py
storage.py
consolidation.py
```

Quanto menor o raio de impacto, melhor está o isolamento entre o core e os conectores.

---

# 20. Regras recomendadas para AGENTS.md / Skills

Uma regra útil para orientar agentes de IA no projeto seria:

> Alterações específicas de um conector devem permanecer dentro do módulo desse conector sempre que possível. Antes de modificar módulos compartilhados (`services.py`, `markdown.py`, `storage.py`, `main_window.py`, `selection_mixin.py`, `tree_models.py`), o agente deve justificar por que a mudança não pode ser implementada através do contrato ou adaptador do conector. Toda mudança em módulo compartilhado deve executar os testes de regressão dos conectores existentes, especialmente Confluence.

Outra regra possível:

> Não adicionar condicionais por `source_type` ao núcleo sem avaliar primeiro a criação ou extensão de `ConnectorCapabilities`, contratos de discovery ou normalizadores específicos do conector.

---

# 21. Resultado esperado

Ao final dessa evolução, o ALQuimista deverá funcionar como uma plataforma de ingestão de conhecimento, e não apenas como um extrator de Confluence.

A arquitetura desejada é:

```text
Fontes externas
      ↓
Adaptadores específicos
      ↓
Modelo canônico ALQuimista
      ↓
Discovery
      ↓
Extração
      ↓
Renderização
      ↓
Persistência
      ↓
Consolidação
```

Com isso:

- corrigir Notion não deve quebrar Confluence;
- adicionar SharePoint não deve exigir alteração no Markdown;
- adicionar WebConnector não deve exigir alteração na consolidação;
- mudanças de UI não devem exigir mudanças nos clientes HTTP;
- paginação fica isolada por conector;
- o núcleo trabalha sempre com contratos estáveis;
- novos conectores passam por testes de contrato;
- o Confluence fica protegido por Golden Tests;
- o projeto consegue crescer com menor risco de regressões.

---

# Conclusão

O Projeto ALQuimista já possui várias peças corretas para uma arquitetura extensível.

O principal passo agora não é uma reescrita completa, mas uma evolução gradual para:

1. contratos mais fortes;
2. conectores mais isolados;
3. normalização antes do Markdown;
4. discovery centralizado;
5. eliminação do pipeline legado;
6. testes de contrato;
7. Golden Tests;
8. redução progressiva das responsabilidades da `MainWindow`.

A principal regra arquitetural deve ser:

> **Adicionar um novo conector deve significar adicionar código novo, e não modificar todo o sistema existente.**

Quando essa regra estiver sendo respeitada, o ALQuimista estará preparado para crescer para novas bases de conhecimento, APIs e sites genéricos sem colocar em risco as integrações que já funcionam.
