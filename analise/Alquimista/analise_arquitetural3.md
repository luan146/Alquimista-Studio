# Análise Arquitetural, Modularização, Estabilidade e Expansão do Projeto Alquimista Studio 3.0

**Autor:** Análise de Arquitetura de Software Sênior  
**Data:** Agosto de 2026  
**Projeto:** Alquimista Studio 3.0  

---

## 1. Resumo Executivo

- **Estado Atual:** O Alquimista possui uma fundação sólida e funcional baseada no protocolo `KnowledgeSourceConnector` (`alquimista/connectors/base.py`). O conector de referência (`confluence.py`) funciona com alta qualidade, suportando *lazy loading*, navegação hierárquica e busca CQL. Contudo, componentes compartilhados do pipeline — especificamente `services.py` (`ExtractionService`), `markdown.py` (`MarkdownTransformer`) e a orquestração na `MainWindow` / mixins — possuem acoplamentos diretos e suposições específicas do Confluence.
- **Principal Risco:** *Regressão cruzada ("Blast Radius")*. Ajustar `ExtractionService`, `markdown.py` ou a estrutura da árvore de páginas para suprir divergências estruturais do Notion (ex: blocos vs páginas) ou SharePoint/GitBook pode quebrar silenciosamente a extração do Confluence, que hoje é estável.
- **Principal Oportunidade:** Isolar as etapas de *descoberta*, *leitura/paginação* e *extração bruta (HTML/JSON/Blocks)* dentro de cada conector, estabelecendo um **Modelo Intermediário Canônico** (`CanonicalDocument`). O *Shared Core* do Alquimista passará a manipular unicamente documentos canônicos para renderização em Markdown, aplicação de metadados, armazenamento atômico e consolidação.
- **Recomendação Arquitetural Central:** **Não reescreva o sistema**. Adote uma arquitetura orientada a **Contratos e Pipeline Strategy**. Mantenha o Confluence intacto encapsulando seu comportamento sob o contrato padronizado, e implemente o segundo conector (Notion) estritamente isolado para homologar a abstração antes de expandir para Web Genérica.

---

## 2. Como o Projeto Funciona Atualmente

### 2.1 Fluxo Real do Pipeline

1. **Entrada / Configuração:** O usuário cadastra/seleciona uma fonte (`SourceConfig`) via `source_mixin.py`.
2. **Detecção:** `source_detection.py` analisa a URL para classificar a plataforma (sem chamadas HTTP).
3. **Autenticação & Runtime:** `connection_mixin.py` / `auth.py` obtém credenciais que são salvas apenas em memória em `RuntimeSecrets`.
4. **Descoberta de Estrutura & Árvore:**
   - Contêineres: `connector.list_containers()` popula a raiz da árvore em `tree_models.py`.
   - Navegação: Ao expandir nós, `tree_mixin.py` decide síncrono vs. lazy, chamando `connector.list_root_documents()` ou `connector.list_document_children()`.
5. **Seleção de Conteúdo:** O usuário marca nós na UI; a lista de chaves marcadas é sincronizada no `SelectionStore`.
6. **Extração (`ExtractionService` em `services.py`):**
   - O serviço itera sobre os documentos selecionados.
   - Chama `connector.get_document(doc_meta)` que devolve um `KnowledgeDocument` com o payload cru (usualmente HTML no Confluence).
7. **Transformação (`markdown.py`):**
   - `KnowledgeDocumentRenderer` / `MarkdownTransformer` processa o HTML, trata macros de Confluence (`_replace_macros`), extrai anexos e gera o Markdown técnico + frontmatter.
8. **Persistência Atômica (`storage.py`):**
   - Escreve via `FileTransaction` em disco (`manifesto_alquimista.json` + `.md`) e atualiza o `ManifestIndex` (SQLite).
9. **Consolidação & Exportação (`ConsolidationService`):**
   - Rebaixa títulos (`demote_headings`), agrupa arquivos e gera pacotes ou arquivos únicos com base em `ConsolidationOptions`.

---

### 2.2 Diagrama Arquitetural do Pipeline Atual

```text
PIPELINE ATUAL (Com acoplamento implícito)

[Entrada do Usuário / URL]
           │
           ▼
[source_detection.py / connection_mixin.py]
           │
           ▼
[SelectionStore / UI Page Tree]
           │
           ▼
[ExtractionService (services.py)] ────► Chama connector.get_document()
           │
           ▼
[MarkdownTransformer (markdown.py)] ──► Regras de HTML Confluence, Macros, Assets
           │
           ▼
[FileTransaction (storage.py)] ──────► Escreve no disco + ManifestIndex (SQLite)
           │
           ▼
[ConsolidationService (services.py)] ─► Agrupa Markdown e gera saída final
```

---

### 2.3 Diagrama Arquitetural Recomendado

```text
PIPELINE RECOMENDADO (Orientado a Contratos e Modelo Intermediário)

┌────────────────────────────────────────────────────────────────────────┐
│ UI / Application Layer (MainWindow / ExecutionController)             │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Pipeline Manager (Extraction Pipeline Orchestrator)                   │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ Confluence      │       │ Notion          │       │ Generic Web     │
│ Connector       │       │ Connector       │       │ Connector       │
└────────┬────────┘       └────────┬────────┘       └────────┬────────┘
         │ (Extração crua)         │ (Extração crua)         │ (Crawler/Scrape)
         ▼                         ▼                         ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Engine de Normalização por Conector (Ex: NotionBlocksToCanonical)      │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼ (Output: CanonicalDocument AST)
┌────────────────────────────────────────────────────────────────────────┐
│ SHARED CORE PIPELINE                                                   │
│ 1. CanonicalToMarkdownRenderer (Conversor agnóstico de AST)             │
│ 2. Metadata & Link Normalizer                                          │
│ 3. Atomic Storage Manager (FileTransaction + ManifestIndex)            │
│ 4. Consolidation Service                                               │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Mapa de Responsabilidades dos Módulos Principais

- **`alquimista/models.py`:** Contrato de dados do Pydantic (`SourceConfig`, `KnowledgeDocument`, `MarkdownOptions`, `ManifestDocument`). *Gargalo de compatibilidade do manifesto.*
- **`alquimista/connectors/`:**
  - `base.py`: Classe abstrata base `KnowledgeSourceConnector`.
  - `confluence.py`: Implementação robusta do Confluence REST API.
  - `notion.py`, `gitbook.py`, `sharepoint.py`: Implementações preliminares ou incompletas.
  - `http.py`: Cliente `ApiHttpClient` seguro com retries, rate-limiting e redação de segredos.
- **`alquimista/services.py`:** Motor de execução do domínio. Concentra `ExtractionService` e `ConsolidationService`. Possui ramificação em modo genérico vs. legado.
- **`alquimista/markdown.py`:** Motor de conversão. O `MarkdownTransformer` possui código especializado em tratar macros do Confluence (`_replace_macros`, `_attachment_url`).
- **`alquimista/storage.py`:** Persistência atômica (`FileTransaction`), garantindo que falhas no meio da gravação não corrompam o workspace.
- **`alquimista/ui/`:** Orquestração de interface via PySide6. A `MainWindow` utiliza Mixins (`selection_mixin.py`, `source_mixin.py`, `connection_mixin.py`, `tree_mixin.py`) para modularizar o código.

---

## 4. Problemas Encontrados (Ordenados por Severidade)

1. **[SEV-0 / P0] Lógica Específica de Plataforma no Motor de Markdown (`markdown.py`)**
   - *Fato:* O `MarkdownTransformer` lida diretamente com estruturas exclusivas do Confluence (`_replace_macros` para códigos, avisos e painéis, e geração de URLs de anexos do Confluence).
   - *Consequência:* Adicionar tratamento de blocos do Notion ou tags do GitBook dentro desta mesma classe poluirá o motor compartilhado e causará quebras no Confluence.
2. **[SEV-1 / P0] Acoplamento do Formato HTML no Pipeline de Extração**
   - *Fato:* `ExtractionService` assume que o atributo `.body` de um documento retornado pelo conector é uma string em HTML pronta para ser passada ao `MarkdownTransformer` (usando BeautifulSoup).
   - *Consequência:* O Notion retorna uma árvore de blocos JSON; o SharePoint pode retornar arquivos de texto/DOCX/HTML; o GitBook usa AST/JSON próprio em certas versões.
3. **[SEV-2 / P1] Duplicação de Métodos nos Mixins da UI (Armadilha de Manutenção)**
   - *Fato:* Conforme registrado no `MAPA.md`, arquivos como `selection_mixin.py` e `connection_mixin.py` possuem funções redefinidas até 7 vezes no mesmo arquivo (onde apenas a última prevalece).
   - *Consequência:* Risco iminente de um desenvolvedor editar a versão morta do método e a alteração não surtir efeito, gerando confusão.
4. **[SEV-3 / P1] Falta de Abstração para Paginação/Descoberta em Conectores Distintos**
   - *Fato:* O `tree_mixin.py` trata o estado de lazy loading dependendo fortemente das capacidades e estruturas retornadas pelo Confluence (`list_document_children` com cursores de estilo REST/Confluence).
   - *Consequência:* Dificuldade em estender a árvore da UI para fontes sem estrutura pai/filho estrita.
5. **[SEV-4 / P2] Gerenciamento de Processos e Zumbis na UI**
   - *Fato:* Em `ui/operation_controller.py` e `ui/process_workers.py`, o gerenciamento de processos e threads via `QThreadPool` / `multiprocessing` precisa de limpeza rigorosa de ponteiros.
   - *Consequência:* Se um `Worker` é encerrado sem descartar corretamente a referência do `CancellationToken`, a UI pode congelar ou manter processos zumbis.

---

## 5. Hotspots e Blast Radius

### 5.1 Tabela de Hotspots Arquiteturais

| Hotspot | Arquivo / Módulo | Problema Concreto | Consequência no Sistema | Prioridade |
| :--- | :--- | :--- | :--- | :--- |
| **HS-01** | `alquimista/markdown.py` | Métodos `_replace_macros` e tratamento de links acoplados ao HTML Confluence. | Alterações para outras fontes quebram a formatação do Confluence. | **P0** |
| **HS-02** | `alquimista/services.py` | `ExtractionService` assume fluxo fixo `HTML -> MarkdownTransformer`. | Incompatível com conectores baseados em blocos JSON (Notion) ou AST. | **P0** |
| **HS-03** | `alquimista/ui/mixins/selection_mixin.py` | Métodos redefinidos e duplicados no mesmo arquivo. | Erros de manutenção e bugs silenciosos ao editar código órfão. | **P1** |
| **HS-04** | `alquimista/connectors/base.py` | O contrato `KnowledgeSourceConnector` é vago sobre o tipo interno do corpo do documento. | Cada conector injeta dados brutos heterogêneos no pipeline. | **P1** |
| **HS-05** | `alquimista/ui/main_window.py` | Orquestrador massivo (132 métodos) que manipula estados de conversão e UI diretamente. | Elevado risco de regressão ao adicionar novos fluxos de UI. | **P2** |

### 5.2 Classificação de Blast Radius (Raio de Impacto)

- **`alquimista/models.py` — CRÍTICO:** Alterações nas estruturas invalidam manifestos e projetos salvos (`.alquimista`).
- **`alquimista/services.py` — CRÍTICO:** Afeta diretamente a extração e a consolidação de todos os conectores.
- **`alquimista/markdown.py` — ALTO:** Afeta a qualidade da geração de saída de todos os conectores.
- **`alquimista/connectors/confluence.py` — MÉDIO:** Afeta exclusivamente a integração com o Confluence.
- **`alquimista/connectors/notion.py` — BAIXO:** Conector isolado.

---

## 6. Shared Core vs. Connector-Specific

| Componente | Classificação | Justificativa |
| :--- | :--- | :--- |
| **`FileTransaction` & `storage.py`** | **CORE COMPARTILHADO** | A escrita atômica em disco, controle de temporários e manifesto são independentes da origem dos dados. |
| **`ConsolidationService`** | **CORE COMPARTILHADO** | A junção de arquivos Markdown, rebaixamento de títulos e criação de índices opera sobre arquivos `.md` já gerados. |
| **`ManifestIndex` (SQLite)** | **CORE COMPARTILHADO** | O índice incremental depende apenas de hashes SHA-256 e chaves de documentos. |
| **Logging & Redação de Segredos** | **INFRAESTRUTURA** | A segurança e auditoria (`logging_utils.py`) devem ser globais e uniformes. |
| **Renderer de Markdown Canônico** | **CORE COMPARTILHADO** | Um renderizador central que transforma uma AST canônica em texto Markdown sem conhecer a API de origem. |
| **Descoberta e Paginação** | **CONNECTOR-SPECIFIC** | Cada plataforma possui regras de navegação próprias (CQL no Confluence, cursores/blocos no Notion, Graph API no SharePoint). |
| **Parsing e Extração Bruta** | **CONNECTOR-SPECIFIC** | Processar o payload bruto (HTML Confluence vs. JSON Notion vs. DOM Web) deve ser responsabilidade isolada de cada conector. |
| **Estratégia de Normalização** | **EXTENSÍVEL POR ESTRATÉGIA** | O conector transforma seu formato nativo em uma estrutura intermediária padronizada. |

---

## 7. Análise Crítica: Leitores e Paginadores por Plataforma

**Resposta:** **SIM, a paginação, a descoberta e a extração bruta de páginas DEVEM ser específicas por conector.**

Contudo, a estrutura **NÃO** deve duplicar o código da aplicação. Deve-se adotar o **Strategy Pattern** combinado com **Composição**.

### Justificativa Técnica baseada no Código Real
No Confluence, a navegação ocorre por Espaços (`list_containers`) e Hierarquia de Páginas Ancestrais (`list_document_children`). No Notion, a estrutura é baseada em Páginas-mãe que contêm Bancos de Dados e Subpáginas misturadas como blocos. No SharePoint, a navegação é orientada a *Document Libraries* e Pastas.

Tentar unir a lógica de descoberta e paginação em um `page_reader.py` genérico gerará um arquivo repleto de condicionais `if connector == "notion": ... elif connector == "confluence": ...`.

### Organização Recomendada para Conectores

```text
alquimista/connectors/
├── base.py                 # Protocol / Interfaces abstratas
├── registry.py             # Instanciação dinâmica
├── confluence/
│   ├── __init__.py
│   ├── connector.py        # Orquestrador da fonte
│   ├── discovery.py        # Paginação e descoberta REST/CQL
│   └── normalizer.py       # HTML Confluence -> Documento Canônico
├── notion/
│   ├── __init__.py
│   ├── connector.py
│   ├── discovery.py        # Navegação em árvore de blocos/páginas
│   └── normalizer.py       # Notion Blocks JSON -> Documento Canônico
```

---

## 8. Modelo Intermediário Comum (`CanonicalDocument`)

Para garantir que novos conectores não afetem o gerador de Markdown nem os motores de consolidação, é recomendado introduzir uma camada de representação intermediária.

```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum

class BlockType(Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    CODE = "code"
    TABLE = "table"
    CALLOUT = "callout"
    IMAGE = "image"

@dataclass
class CanonicalBlock:
    type: BlockType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    children: List['CanonicalBlock'] = field(default_factory=list)

@dataclass
class CanonicalDocument:
    id: str
    title: str
    source_url: str
    container_id: Optional[str]
    ancestors: List[str]
    updated_at: str
    blocks: List[CanonicalBlock]
    raw_assets: List[Dict[str, Any]] = field(default_factory=list)
```

**Fluxo:**  
`Confluence HTML` $ightarrow$ `ConfluenceNormalizer` $ightarrow$ `CanonicalDocument` $ightarrow$ `Core MarkdownRenderer` $ightarrow$ `.md`  
`Notion Blocks JSON` $ightarrow$ `NotionNormalizer` $ightarrow$ `CanonicalDocument` $ightarrow$ `Core MarkdownRenderer` $ightarrow$ `.md`

---

## 9. Estrutura de Diretórios Proposta

```text
alquimista/
├── application/             # Controladores de aplicação (ex-controllers da UI)
│   ├── execution.py
│   └── project.py
├── core/                    # Núcleo compartilhado puro
├── domain/                  # Entidades canônicas e contratos
│   ├── canonical.py         # CanonicalDocument e CanonicalBlock
│   └── interfaces.py        # Protocols dos conectores
├── connectors/              # Isolação completa por conector
│   ├── base.py
│   ├── registry.py
│   ├── confluence/
│   ├── notion/
│   ├── sharepoint/
│   └── web/                 # Futuro conector de sites genéricos
├── markdown/                # Renderizador de Markdown agnóstico
├── storage/                 # Persistência atômica e manifestos
└── ui/                     # Interface visual PySide6
```

---

## 10. Proteção Contra Regressões e "Golden Samples"

Para garantir a regra *"Ajustar Notion nunca quebra Confluence"*, a suíte de testes deve utilizar **Golden Samples (Snapshot Testing)** isolados por conector.

### Estrutura dos Testes de Regressão

```text
tests/
├── connectors/
│   ├── confluence/
│   │   ├── fixtures/
│   │   │   ├── raw_page_123.json       # Payload bruto retornado pela API
│   │   │   └── expected_page_123.md    # Markdown exato esperado
│   │   └── test_confluence_regression.py
│   ├── notion/
│   │   ├── fixtures/
│   │   │   ├── raw_blocks.json
│   │   │   └── expected_blocks.md
│   │   └── test_notion_regression.py
```

### Mecanismo do Teste Golden Sample
1. O teste injeta a *fixture* bruta (JSON/HTML) diretamente no `Normalizer` do conector.
2. O `CanonicalDocument` gerado é processado pelo `MarkdownRenderer` central.
3. O resultado em string é comparado diretamente com o arquivo `expected_*.md`.
4. **Normalização de Volatilidade:** O comparador de teste ignora ou substitui por *regex* campos dinâmicos como timestamps ISO atuais (`updated_at`) e hashes SHA-256 temporários.

---

## 11. Expansão Futura: Sites Genéricos (`GenericWebConnector`)

Para suportar URLs arbitrárias (`https://exemplo.com/documentacao`), a arquitetura proposta acomoda o módulo como um conector especializado:

1. **`GenericWebConnector`:** Implementa o contrato base `KnowledgeSourceConnector`.
2. **Componentes Internos do Conector Web:**
   - **Crawler:** Motor baseado em `Playwright` ou `httpx` + `BeautifulSoup` para navegar respeitando o mesmo domínio e `sitemap.xml`.
   - **Readability Parser:** Extrator tipo *Readability.py* para remover menus, footers, anúncios e preservar o artigo principal.
   - **WebNormalizer:** Transforma o HTML limpo da página diretamente na estrutura de `CanonicalDocument`.
3. **Isolamento:** Como o `GenericWebConnector` entrega um `CanonicalDocument` para o Core, o pipeline de geração de Markdown, salvamento e consolidação funciona instantaneamente sem modificar uma linha do Confluence ou Notion.

---

## 12. Plano de Migração Incremental (Sem Reescrita)

### Fase 0: Baseline & Testes de Proteção (Sem alterações de código produtivo)
- **Objetivo:** Travar o comportamento atual do Confluence com testes Snapshot.
- **Ações:** Criar `tests/connectors/confluence/fixtures` salvando HTML real e o Markdown esperado.
- **Risco:** Mínimo.
- **Validação:** Rodar `pytest` para confirmar passagem de 100% dos testes existentes.

### Fase 1: Limpeza de Mixins na UI
- **Objetivo:** Eliminar métodos duplicados/órfãos apontados no `MAPA.md`.
- **Ações:** Remover redefinições em `selection_mixin.py` e `connection_mixin.py`.
- **Risco:** Baixo.
- **Validação:** Verificação manual das telas e execução da suíte de testes de UI.

### Fase 2: Introdução do Modelo Canônico (`CanonicalDocument`) e Refatoração do Renderer
- **Objetivo:** Desacoplar `markdown.py` de especificidades do Confluence.
- **Ações:**
  - Extrair lógica de macros do Confluence de `markdown.py` e movê-la para um `ConfluenceHtmlNormalizer`.
  - Criar o renderizador agnóstico `CanonicalToMarkdownRenderer`.
- **Risco:** Médio.
- **Validação:** Execução dos testes Golden Sample do Confluence. O resultado do Markdown gerado deve ser idêntico byte a byte ao anterior.

### Fase 3: Homologação do Segundo Conector (Notion)
- **Objetivo:** Validar a nova arquitetura modular com uma plataforma baseada em blocos.
- **Ações:** Implementar `NotionNormalizer` que converte JSON do Notion em `CanonicalDocument`.
- **Risco:** Baixo (Notion isolado).
- **Validação:** Adicionar Golden Samples para o Notion sem impactar os testes do Confluence.

---

## 13. Tabela de Prioridades (Benefício × Risco × Esforço)

| Prioridade | Mudança Recomendada | Benefício | Risco | Esforço |
| :--- | :--- | :--- | :--- | :--- |
| **P0** | Travar o Confluence com Golden Samples de Regressão. | Alto | Muito Baixo | Baixo |
| **P0** | Desacoplar macros de Confluence de `markdown.py`. | Alto | Médio | Médio |
| **P1** | Corrigir duplicações de código nos Mixins da UI (`selection_mixin.py`). | Médio | Baixo | Baixo |
| **P1** | Introduzir a AST Canônica (`CanonicalDocument`). | Alto | Médio | Médio |
| **P2** | Isolar navegação e paginação dentro da pasta de cada conector. | Alto | Baixo | Médio |
| **P3** | Criar conector para sites genéricos (`GenericWebConnector`). | Médio | Baixo | Alto |

---

## 14. O Que NÃO Modificar Agora

1. **`alquimista/storage.py` (`FileTransaction` e persistência atômica):** O sistema de gravação atômica funciona perfeitamente e atende a todos os conectores sem necessidade de alterações.
2. **`alquimista/manifest_index.py` (Índice SQLite):** O mecanismo de hash SHA-256 e controle incremental é agnóstico à fonte.
3. **`alquimista/connectors/http.py` (`ApiHttpClient`):** A camada HTTP resiliente com retries e tratamento de segredos está madura e deve continuar sendo utilizada por todos os conectores.
4. **`alquimista/services.py` (`ConsolidationService`):** O motor de consolidação opera sobre Markdown estático e não deve ser alterado.

---

## 15. Teste de Extensibilidade (Cenários)

- **Cenário A: Adicionar Google Drive**
  - *Impacto:* Cria-se `alquimista/connectors/gdrive/`. O conector converte arquivos/docs para `CanonicalDocument`. **Zero linhas alteradas no Core ou no Confluence.**
- **Cenário B: Adicionar Website Genérico**
  - *Impacto:* Cria-se `alquimista/connectors/web/` com extração via Readability. O output gera `CanonicalDocument`. **Zero impacto em outros conectores.**
- **Cenário C: Notion altera completamente sua paginação/API**
  - *Impacto:* Altera-se apenas `alquimista/connectors/notion/discovery.py`. **O Confluence permanece 100% imune.**
- **Cenário D: Mudança nas regras globais de geração de Markdown (ex: formato de frontmatter)**
  - *Impacto:* Altera-se apenas o `CanonicalToMarkdownRenderer` no Core. Todos os conectores passam a gerar a nova formatação uniformemente sem mexer nas chamadas de API.

---

## 16. Avaliação Arquitetural Quantitativa

| Critério | Nota Atual | Nota Projetada | Justificativa da Evolução |
| :--- | :---: | :---: | :--- |
| **Modularidade** | 6.5 / 10 | 9.0 / 10 | Separação física clara das etapas por conector. |
| **Separação de Responsabilidades** | 6.0 / 10 | 8.5 / 10 | Fim do vazamento de HTML/macros do Confluence em `markdown.py`. |
| **Extensibilidade** | 5.5 / 10 | 9.0 / 10 | Inclusão de novas fontes via Modelo Canônico sem tocar no Core. |
| **Testabilidade** | 6.0 / 10 | 9.5 / 10 | Adoção de Golden Samples e testes isolados por fixture. |
| **Proteção contra Regressões** | 5.0 / 10 | 9.5 / 10 | Testes automatizados garantem estabilidade do Confluence. |
| **Acoplamento** | 5.5 / 10 | 8.5 / 10 | Desacoplam-se os formatos nativos de API do pipeline de escrita. |
| **Coesão** | 7.0 / 10 | 9.0 / 10 | Módulos concentrados em suas atribuições nativas. |
| **Observabilidade** | 7.5 / 10 | 8.5 / 10 | Mantido e expandido o padrão de logs JSON mascarados. |
| **Manutenibilidade** | 6.0 / 10 | 9.0 / 10 | Remoção de armadilhas como métodos duplicados em mixins. |
| **Preparação p/ Novos Conectores** | 5.0 / 10 | 9.0 / 10 | Processo de acoplamento de conectores padronizado por protocolo. |

---

## 17. Top 10 Próximas Ações (Em Ordem Exata de Execução)

1. **Criar suíte de teste Golden Sample para Confluence:** Gravar fixtures de requisições reais e Markdown de saída esperado em `tests/connectors/confluence/`.
2. **Remover duplicidades de código nos Mixins:** Corrigir os métodos duplicados listados em `MAPA.md` para `selection_mixin.py` e `connection_mixin.py`.
3. **Definir as Dataclasses Canônicas:** Implementar `CanonicalDocument` e `CanonicalBlock` em `alquimista/domain/canonical.py`.
4. **Extrair o Normalizador do Confluence:** Mover a lógica de conversão de HTML/Macros de `alquimista/markdown.py` para `alquimista/connectors/confluence/normalizer.py`.
5. **Implementar o Renderizador Canônico Agnóstico:** Criar em `alquimista/markdown/renderer.py` a conversão de `CanonicalDocument` para Markdown.
6. **Ajustar `ExtractionService`:** Fazer o serviço interagir com a interface canônica em vez de assumir HTML direto.
7. **Executar e Validar os Testes de Regressão:** Garantir que 100% das fixtures do Confluence continuem gerando o Markdown exatamente igual.
8. **Refatorar o Conector Notion:** Atualizar o conector do Notion para emitir `CanonicalDocument` usando a nova estrutura.
9. **Adicionar Golden Samples para Notion:** Criar testes de snapshot para validar a estabilidade do Notion isoladamente.
10. **Documentar os Contratos de Conector:** Atualizar o `MAPA.md` e `architecture.md` refletindo o novo fluxo de dados.

---

> **Frase de Encerramento (Decisão Técnica):**  
> *"Se eu fosse o responsável técnico pelo Projeto Alquimista hoje, a primeira mudança arquitetural que faria antes de desenvolver qualquer nova integração seria criar uma suíte de testes de regressão do tipo 'Golden Sample' (snapshot) para o Confluence, travando e garantindo o comportamento atual do sistema antes de qualquer refatoração no pipeline compartilhado."*
