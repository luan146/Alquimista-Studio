# Conector Zendesk Guide

Status: **Disponível**, em modo somente leitura para a Help Center API oficial.

## Configuração

- informe o subdomínio da conta, sem `https://`;
- informe opcionalmente o locale, como `pt-br`;
- use um OAuth access token com escopo de leitura do Help Center (`hc:read`, ou
  equivalente concedido pela conta);
- a URL da API pode ficar vazia para usar
  `https://{subdomínio}.zendesk.com/api/v2`.

O ALQuimista envia o token como `Authorization: Bearer` e não implementa
senha comum nem API token legado como método recomendado. Refresh token e o
fluxo OAuth interativo ainda precisam de uma tela/redirect seguro e permanecem
pendentes; o método disponível nesta fase é o access token já emitido.

## Endpoints e fluxo

O conector utiliza a Help Center API oficial:

- `GET /api/v2/help_center/{locale}/categories.json`;
- `GET /api/v2/help_center/{locale}/categories/{category_id}/sections.json`;
- `GET /api/v2/help_center/{locale}/sections/{section_id}/articles.json`;
- `GET /api/v2/help_center/{locale}/articles/{article_id}.json`.

Categorias são contêineres; seções formam o caminho hierárquico; artigos são
documentos. O corpo HTML do artigo é convertido pelo pipeline existente para
Markdown. Comentários, tickets, usuários e conteúdo fora do Help Center não
são consultados.

O Help Center recomenda cursor pagination com `page[size]` e segue o link
`links.next`; o conector limita tentativas, trata 401/403/404/429/5xx,
`Retry-After` e cancelamento.

## Limitações

- artigos invisíveis para a identidade autenticada não aparecem;
- artigos em rascunho ou marcados como desatualizados são ignorados;
- o locale é único por configuração da fonte; traduções adicionais não são
  exportadas como documentos separados;
- refresh token/OAuth interativo e múltiplas marcas na mesma configuração ainda
  não estão implementados;
- os testes usam respostas sintéticas; nenhuma conta Zendesk real foi usada
  nesta validação.

Referências: [Help Center API](https://developer.zendesk.com/api-reference/help_center/help-center-api/introduction/),
[Articles](https://developer.zendesk.com/api-reference/help_center/help-center-api/articles/),
[OAuth tokens](https://developer.zendesk.com/api-reference/ticketing/oauth/oauth_tokens/).
