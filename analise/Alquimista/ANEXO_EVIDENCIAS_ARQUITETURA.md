# Anexo de Evidências — Análise Arquitetural Definitiva

Este anexo registra a procedência, a validação e o status das alegações usadas em `ANALISE_ARQUITETURAL_DEFINITIVA.md`. O código do worktree é a fonte final de verdade; contagens documentais não substituem evidência de fluxo ativo.

## 1. Baseline reproduzível

### 1.1 Repositório

| Campo | Valor |
|---|---|
| Data da coleta | 12/08/2026 |
| Branch | `main` |
| Commit base | `028914d7b768dd22f877067de8caf56e3028c3f8` |
| Commit | `fix(i18n): retranslate dashboard content` |
| Baseline analisado | Worktree atual, incluindo alterações locais |
| Runtime local | Python 3.14.6 |
| Runtime alvo/CI | Python 3.12 |
| Pytest | 9.1.1 |
| Ruff | 0.16.0 |
| Mypy | 1.20.2 |

Arquivos de código modificados antes da análise:

- `alquimista/markdown.py`;
- `alquimista/ui/i18n.py`;
- `alquimista/ui/main_window.py`;
- `alquimista/ui/operation_controller.py`;
- novo `alquimista/ui/translation_fallbacks.py`.

As mudanças preexistentes são majoritariamente de internacionalização. Elas foram preservadas e consideradas ao citar o baseline.

### 1.2 Hashes do corpus

| Documento | SHA-256 |
|---|---|
| `analise_arquitetura1.md` | `88E197620B60AAA33357A2C47F30FF2E0F67F3CB830A701DA51CBA923F622CCF` |
| `Analise_Arquitetural2.md` | `3E133D802E240ECF352D71B8BE294F74B509CD580854073BBFE5FB654ADD7C6D` |
| `analise_arquitetural3.md` | `EC1E89848C48046BAF213FCB6359D2AC30AEAEECD6E34E7D3EB93AEF26A0AC2C` |
| `ANALISE_ARQUITETURa4.md` | `6461A8FEABBA57A8D3244E63FAFDEA9937D5C90BA518DFD54516E4ED68EA5374` |
| `ANALISE_ARQUITETURAL5.md` | `DAF281E1E8130989D1FD707B8867157CE74C653585B1D7533DD6B88D7150EF42` |
| `analise_arquitetural6.md` | `82F5AAF489B04E7B8D3A655F00FC570B68381E82863B46C8A523EBCA1A754EE6` |
| `ANALISE_ARQUITETURAL7.md` | `BA274B0758F453DBCD4C99772DB4658643718E56B27945256B1AC32A1AA1F48B` |
| `ANALISE_ARQUITETURAL_2026-08-12.md` | `C7C6FE35E9D6F039635FA5C6BD33B1D2DD7DB09A263BA7AF3A8D7BC81A01906E` |

### 1.3 Hierarquia de evidências aplicada

1. comportamento reproduzido;
2. fluxo ativo por callers, imports, registry, MRO e sinais;
3. código e contratos atuais;
4. testes e CI;
5. configuração/schema persistido;
6. documentação do projeto;
7. afirmações das análises.

`MAPA.md` foi usado como índice. Alegações de redefinições duplicadas e atividade de `TreeMixin` demonstraram por que ele não pode ser tratado como prova final.

## 2. Método multiagente

Quatro trilhas foram executadas:

- corpus 1–4, com leitura integral e decomposição em 27 grupos materiais;
- corpus 5–8, com leitura integral e decomposição em 26 grupos materiais;
- auditoria independente sem acesso às oito análises, focada em conectores, browser, autenticação, HTTP, testes e escala;
- auditoria principal de UI, controllers, services, models, Markdown, storage, manifest e consolidação.

Na segunda rodada, os agentes de corpus validaram suas divergências no código. A auditoria independente realizou revisão adversarial dos candidatos prioritários. Nenhum agente recebeu autorização para editar o repositório.

## 3. Matriz de consolidação documental

`X/Y` representa concordância entre os documentos que abordaram o tema; `Y/8` representa cobertura. Silêncio não é discordância.

| ID | Alegação consolidada | Concordância | Cobertura | Resultado final |
|---|---|---:|---:|---|
| CL-01 | Há uma fundação extensível aproveitável | 8/8 | 8/8 | Confirmada |
| CL-02 | Pipeline genérico e legado coexistem | 8/8 | 8/8 | Confirmada; somente o genérico é fluxo normal da UI |
| CL-03 | A coexistência dos dois pipelines é P0 por si só | 5/8 | 8/8 | Rebaixada para dívida P1; seus efeitos funcionais são priorizados separadamente |
| CL-04 | Há divergência de Markdown/normalização | 8/8 | 8/8 | Confirmada e elevada a P0 funcional |
| CL-05 | Faltam goldens completos | 8/8 | 8/8 | Confirmada; pré-requisito de aceitação do P0 funcional |
| CL-06 | Contract tests comportamentais são necessários | 8/8 | 8/8 | Confirmada; reutilizar testes existentes em harness parametrizado |
| CL-07 | `MainWindow` é hotspot | 8/8 | 8/8 | Confirmada; dívida P2 incremental |
| CL-08 | UI repete informação de plataforma | 8/8 | 8/8 | Confirmada; whitelist funcional é P1 |
| CL-09 | Parsing/discovery/paginação devem ser específicos por conector | 8/8 | 8/8 | Confirmada |
| CL-10 | Storage, manifesto, consolidação e runtime devem ser compartilhados | 8/8 | 8/8 | Confirmada com dívida lexical de schema |
| CL-11 | Novo modelo AST canônico é necessário | 1/4 | 4/8 | Não demonstrada; otimização prematura |
| CL-12 | Novo `DiscoveryService` é necessário | 2/4 | 4/8 | Refutada como necessidade imediata; serviço/adapter/cache já existem |
| CL-13 | Funções duplicadas citadas no `MAPA.md` ainda existem | 5/6 | 6/8 | Obsoleta; AST refutou no worktree atual |
| CL-14 | `TreeMixin` participa do fluxo ativo | 5/7 | 7/8 | Refutada; não faz parte da MRO da `MainWindow` |
| CL-15 | `process_workers.py` é risco operacional atual | 1/3 | 3/8 | Refutada; somente testes o importam |
| CL-16 | Existem duas pilhas HTTP | 8/8 | 8/8 | Confirmada; dívida P2, não migração imediata |
| CL-17 | Hierarquia de erros mistura plataforma/categoria | 5/5 | 5/8 | Confirmada, com mensagem incorreta possível na UI |
| CL-18 | Notion é bom segundo conector de prova | 8/8 | 8/8 | Confirmada como estratégia futura |
| CL-19 | Notion/SharePoint estão quase prontos | 5/7 | 7/8 | Refutada; ambos são abstratos e incompletos |
| CL-20 | Empacotar todos os conectores agora | 4/8 | 8/8 | Rejeitada; dividir somente por responsabilidade comprovada |
| CL-21 | Generic Web deve ser conector próprio | 8/8 | 8/8 | Confirmada, P3 |
| CL-22 | Lazy loading é necessário para escala | 8/8 | 8/8 | Confirmada como princípio; gargalos quantitativos não foram medidos |
| CL-23 | Manifesto/modelos têm alto blast radius | 8/8 | 8/8 | Confirmada; preservar compatibilidade |
| CL-24 | Observabilidade precisa de contexto uniforme | 7/7 | 7/8 | Melhoria P2 |
| CL-25 | Detector de URL precisa ser plugável agora | 0/3 | 3/8 | Prematura; manter simples até crescer |
| CL-26 | Reescrita/plugin framework devem ser evitados | 8/8 | 8/8 | Confirmada |
| CL-27 | `KnowledgeDocument.content` possui semântica explícita | 0/4 | 4/8 | Refutada; é Markdown de facto, mas somente `str` no contrato |
| CL-28 | Discovery da seleção é reutilizado na extração | 0/1 | 1/8 | Refutada por achado independente; runtime reinventa documentos |
| CL-29 | Capabilities possuem fonte única | 0/4 | 4/8 | Refutada; registry, métodos do conector e introspecção do adapter divergem |
| CL-30 | Projeto está pronto para 10–20 conectores | Divergente | 4/8 | Não verificável sem metas; arquitetura precisa concluir P0/P1 antes |

## 4. Evidências do fluxo ativo

### 4.1 Entry, UI e execução

| Proposição | Evidência |
|---|---|
| Entry oficial abre fluxo completo | `alquimista/__main__.py:main`; `alquimista/ui/__init__.py` |
| UI usa pipeline de conectores | `ui/execution_controller.py:prepare_runtimes` chama `RuntimeBuilder.build_connectors` |
| Builder legado não tem caller produtivo | `RuntimeBuilder.build()` aparece apenas em `tests/test_ui_controllers.py` |
| Dispatcher ainda mantém dois ramos | `services.py:ExtractionService._run` |
| `TreeMixin` não é ativo | MRO declarada em `ui/main_window.py:MainWindow` não o inclui |
| `page_registry.py` não compõe páginas | `_build()` mantém dicionário local; não há import/caller de `page_builders()` |
| Worker produtivo é threadpool Qt | `WorkerOperationController` + `ui/workers.py`; `process_workers.py` só é importado em testes |

### 4.2 Markdown e manifesto

| Proposição | Evidência |
|---|---|
| Preview usa legado | `MainWindow._update_preview()` instancia `MarkdownTransformer` |
| Produção usa renderer genérico | `_run_generic()` instancia `KnowledgeDocumentRenderer` |
| Parser genérico Confluence é simplificado | `ConfluenceRestConnector.normalize_document()` usa `BeautifulSoup`/`markdownify` |
| Parser legado interpreta semântica Atlassian | `MarkdownTransformer._replace_links`, `_replace_macros`, `technical_markdown` |
| Falha de fetch não é isolada no genérico | `connector.get_document()` ocorre antes do bloco que captura falha por documento |
| Atualização parcial é somente legado | única consulta a `partial_update_keys` na reconciliação de `_run_legacy()` |
| Manifesto é canônico + legado | `ManifestEntry` possui `container_id/document_id` e `space_key/confluence_version` |
| Consolidação não ramifica por plataforma | `ConsolidationService` opera sobre entries e caminhos Markdown |

### 4.3 Contrato e conectores

| Método | Confluence | GitBook | Zendesk | Notion | SharePoint | Uso produtivo |
|---|---|---|---|---|---|---|
| `validate_connection` | Concreto | Concreto | Concreto | Presente | Presente | Sim |
| `list_containers` | Concreto | Concreto | Concreto | Inválido/incompleto | Inválido/incompleto | Sim |
| `list_documents` | Concreto | Concreto | Concreto | Incompleto | Incompleto | Sim |
| roots/children lazy | Concreto | Base | Base | Base | Base | UI, somente Confluence |
| `get_document` | Concreto | Concreto | Concreto | Inválido/incompleto | Inválido/incompleto | Sim |
| `get_document_children` | Concreto | Concreto | Vazio | Ausente | Ausente | Não |
| `normalize_document` | Concreto | Concreto | Concreto | Ausente | Ausente | Apenas interno ao conector |
| `get_capabilities` | Override | Override | Override | Override | Override | Sem caller; duplicado no registry |

Introspecção confirmou:

- concretos: `ConfluenceRestConnector`, `GitBookConnector`, `ZendeskGuideConnector`;
- abstratos: `NotionConnector`, `SharePointConnector`, ambos sem `get_document_children` e `normalize_document`;
- registry: três disponíveis; Notion/SharePoint com `DEVELOPMENT` e `implemented=False`.

## 5. Achados independentes

Estes itens surgiram da auditoria `code-first`, antes do cotejo com os documentos.

| ID | Achado | Status | Natureza | Prioridade |
|---|---|---|---|---|
| CI-01 | Cache auth não isola identidade nem é purgado no logout | Confirmado | Problema de privacidade local | P1 |
| CI-02 | UI ignora `next_cursor` lazy | Confirmado | Problema de completude condicionado a cardinalidade | P1 alto |
| CI-03 | Runtime reinventa containers/documentos antes de filtrar | Confirmado | Dívida de escala | P1 |
| CI-04 | Zendesk corta em 5.000 sem aviso | Confirmado | Problema de completude condicionado a cardinalidade | P1 alto |
| CI-05 | URL absoluta pode reutilizar sessão auth fora da origem | Confirmado por fluxo; requer teste de segurança | Hardening de segurança | P2/P1 conforme política |
| CI-06 | Cache não limpa expirados automaticamente e faz N+1 reads | Confirmado | Dívida operacional | P2 |
| CI-07 | Falha de DPAPI degrada para Base64 + `chmod` | Confirmado | Risco de segurança local | P2; P1 em política enterprise |
| CI-08 | Recuperação de auth escolhe browser em vez de público | Confirmado | Bug funcional | P2 |
| CI-09 | Capabilities têm três fontes de verdade | Confirmado | Dívida contratual | P1/P2 |
| CI-10 | Notion/SharePoint são abstratos | Confirmado | Readiness contida | P2 antes de ativar |
| CI-11 | Blocos PowerShell da CI podem mascarar exit code anterior | Provável/fortemente sustentado | Confiabilidade CI | P1 |
| CI-12 | `get_document()` fora do isolamento por item aborta lote | Confirmado | Confiabilidade | P1 alto |
| CI-13 | `partial_update_keys` não é aplicado no genérico | Confirmado | Manifesto/retry | P1 alto |
| CI-14 | Retry de falhas não restringe seleção estruturada | Confirmado | Comportamento | P1 alto |

### 5.1 Evidência contrária e calibragem

- O cache remove chaves sensíveis e body; CI-01 refere-se a títulos, URLs, hierarquia e visibilidade, não a tokens armazenados no SQLite.
- `requests` pode remover `Authorization` em redirects entre hosts; CI-05 é uma nova requisição explícita via mesma sessão, portanto a proteção de redirect não basta. Um teste deve confirmar headers/cookies por modo.
- Redescoberta integral garante existência e metadados atualizados; CI-03 propõe separar validação pontual de varredura de remoções, não simplesmente confiar em cache indefinidamente.
- O limite lazy padrão é elevado; CI-02 permanece problema porque a omissão é silenciosa e configurável para valores menores, mas não é P0 sem base conhecida acima do budget.
- O fallback DPAPI tenta preservar operação em ambientes gerenciados; a crítica é a degradação silenciosa e a equivalência incorreta entre `chmod` e ACL Windows.

## 6. Itens refutados ou obsoletos

| Alegação | Verificação | Destino |
|---|---|---|
| Há 7/12 redefinições ativas em mixins/auth/controllers | AST encontrou apenas pares getter/setter legítimos | Remover do roadmap e corrigir `MAPA.md` |
| `TreeMixin` é a implementação da árvore | Não está na MRO | Classificar como código inativo |
| `process_workers.py` causa zumbis na UI atual | Não há caller produtivo | Classificar como código reserva testado |
| `_adapt_legacy_runtimes()` conecta os dois pipelines | Não possui caller | Código morto provável |
| `_download_compat()` é fallback ativo | Não possui caller | Código morto confirmado por busca estática |
| Pipeline genérico usa `MarkdownTransformer` | Usa `KnowledgeDocumentRenderer` | Refutada |
| Notion/SharePoint só precisam mudar `implemented=True` | São abstratos e constroem modelos inválidos | Refutada |
| Storage/consolidação precisam ser divididos por conector | Não ramificam por plataforma | Refutada |
| Nova AST é pré-requisito | Nenhuma perda impossível de representar foi demonstrada | Prematura |

## 7. Validações técnicas

### 7.1 Passaram

Executadas com `.venv`/Python 3.14.6:

| Verificação | Resultado |
|---|---|
| Ruff, config `config/pyproject.toml` | Passou |
| Mypy, 63 arquivos | Passou |
| `compileall` em `alquimista`, `tools/legacy`, `tests` | Passou |
| Core focado: services/connectors/Markdown/models-storage/cache/lazy Confluence | 80 passaram em 7,17 s |
| `test_ui_controllers.py` | 4 passaram |
| `test_ui_browser_cache_integration.py` | 1 passou |
| Validação focada do agente de UI/Markdown/serviços | 12 passaram |
| Registry/disponibilidade de conectores | 1 passou |

### 7.2 Inconclusivas

- Suíte completa: timeout de 120 s após 63 testes passarem, sem falha exibida.
- Grupo amplo focado com Qt: timeout após 80% e sem falha exibida.
- `test_ui_lazy_regressions.py`: primeiro teste passou; segundo não concluiu antes de 30 s no ambiente Python 3.14.6.

Timeout não foi classificado como regressão. A investigação mostrou que testes Qt individuais podem depender de comportamento do runtime local; a execução autoritativa deve ocorrer em Python 3.12 conforme CI.

### 7.3 Não executadas

- APIs reais e markers de integração, por ausência de autorização/credenciais;
- benchmark com milhares de documentos;
- build do instalador;
- comparação em Python 3.12 local, pois a `.venv` disponível é 3.14.6;
- PoCs de segurança com envio real de headers para host externo; a evidência permanece estática e deve virar teste local controlado.

## 8. Rastreabilidade roadmap → evidências

| Roadmap | Achados base | Testes de aceitação mínimos |
|---|---|---|
| P0.1 Baseline de paridade | CL-04, CL-05, CL-06 | payload→Markdown→manifest/hash e flags on/off |
| P0.2 Parser/renderer/preview únicos | R-01, R-02, CL-04 | macros, links, imagens, anexos, tabelas e igualdade preview/extração |
| P1.1 Isolamento por documento | CI-12 | uma falha não impede os demais documentos |
| P1.2 Retry parcial | CI-13, CI-14 | somente chaves falhas são buscadas; outras entries preservadas |
| P1.4 Continuação/limites | CI-02, CI-04 | mais que o budget/cap sem omissão silenciosa |
| P1.5 Snapshot selecionado | CI-03 | contagem de requests proporcional à seleção |
| P1.6 Cache por identidade | CI-01 | troca/logout não reutiliza metadata da identidade anterior |
| P1.7 CI fail-fast | CI-11 | cada comando falho encerra o job |
| P2.1 Catálogo/contrato mínimo | CL-08, CL-29, VB-02 | zero whitelist funcional e conformance kit dos conectores concretos |
| P2.2 Casos de uso | CL-07 | testes sem QApplication para lógica extraída |
| P2.3 Código inativo | seção 6 | zero callers e remoção protegida por testes |
| P2.5 Hardening | CI-05, CI-07 | same-origin/HTTPS e fallback DPAPI compatível com a política |
| P2.6 Notion | CL-18, CL-19 | classe concreta, paginação/blocos e goldens |

## 9. Critério para reavaliar itens adiados

- **AST canônica:** somente se Markdown não representar estrutura necessária sem perda comprovada em dois conectores.
- **Subpacotes:** quando um conector possuir responsabilidades coesas independentes ou mudanças frequentes com conflitos reais.
- **Plugin externo:** quando terceiros precisarem instalar conectores sem release do aplicativo.
- **Detector plugável:** quando regras sobrepostas/heurísticas tornarem a cadeia atual difícil de testar.
- **Otimização de UI/cache:** mediante benchmark com cardinalidade representativa e meta definida.
- **Generic Web:** após P0/P1, conformance kit e segundo conector difícil estável.

## 10. Veredito de evidência

A conclusão mais confiável não é a média das oito análises. É a interseção entre os consensos que sobreviveram ao código e os achados independentes reproduzíveis. Essa interseção mostra uma arquitetura em transição com boa infraestrutura, não um projeto sem arquitetura. O risco imediato está na divergência de comportamento e completude; a dívida estrutural deve ser resolvida depois, em mudanças pequenas e protegidas.
