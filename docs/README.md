# Documentação

Esta pasta reúne a documentação técnica e as referências visuais do ALQuimista Studio.

## Arquitetura

- [Visão geral da arquitetura](architecture.md): fluxo de dados, seleção, segredos, HTTP, relatórios e consolidação.
- [Índice do manifesto](manifest-index.md): manifesto JSON, índice SQLite e atualização atômica.

## Conectores

- [GitBook](connectors/gitbook.md): configuração, autenticação, endpoints e limitações.
- [Zendesk Guide](connectors/zendesk-guide.md): Help Center API, configuração e fluxo de leitura.
- [Notion](connectors/notion.md): status e escopo planejado.
- [SharePoint Online](connectors/sharepoint.md): status e escopo planejado.

## Referências visuais

O diretório [screenshots](screenshots/) contém capturas das telas principais:

- Dashboard;
- Fontes;
- Conexão;
- Seleção;
- Revisão;
- Markdown;
- Consolidação;
- Resultados;
- Saída.

As capturas são referências visuais de desenvolvimento e podem ser regeneradas pelos utilitários do diretório `tools/` quando a interface ou o tema forem atualizados.

## Recursos

Os ícones usados pela interface ficam em [assets/icons](../assets/icons/). Eles fazem parte do sistema visual da aplicação e são carregados pelos componentes PySide6.
