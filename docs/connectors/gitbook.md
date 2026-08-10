# Conector GitBook

Status: **Disponível**, para a API REST oficial v1.

## Requisitos

- uma organização GitBook acessível pela conta do token;
- o ID da organização;
- um Personal Access Token criado nas configurações de desenvolvedor do GitBook;
- acesso HTTPS à API `https://api.gitbook.com/v1`.

O GitBook documenta que os PATs são enviados como `Authorization: Bearer` e
que o token tem as permissões da conta que o criou:
<https://gitbook.com/docs/developers/gitbook-api/authentication>.

## Configuração no ALQuimista

1. Adicione uma fonte e escolha **GitBook — API REST oficial**.
2. Informe o **ID da organização GitBook**.
3. Deixe a URL da API vazia para usar a base oficial padrão, ou informe uma
   base HTTPS compatível terminada em `/v1`.
4. Em Conexão, use **Token de acesso pessoal** e informe o PAT no campo
   mascarado.
5. Teste a conexão, carregue os espaços e marque as páginas desejadas.

O token não é salvo no projeto, no JSON de perfil, no SQLite, no manifesto,
nos logs ou no Markdown. Ele é mantido apenas no cofre runtime da sessão e é
limpo ao fechar o conector.

## API utilizada

- `GET /v1/orgs/{organizationId}` para validar a organização e o token;
- `GET /v1/orgs/{organizationId}/spaces` para descobrir espaços, usando
  `page`, `limit` e `next.page`;
- `GET /v1/spaces/{spaceId}/content/pages` para listar a estrutura de páginas;
- `GET /v1/spaces/{spaceId}/content/page/{pageId}?format=markdown` para
  recuperar o conteúdo Markdown real.

Referências oficiais: [Spaces](https://gitbook.com/docs/developers/gitbook-api/api-reference/spaces),
[Space content](https://gitbook.com/docs/developers/gitbook-api/api-reference/spaces/space-content),
[rate limiting](https://gitbook.com/docs/developers/gitbook-api/rate-limiting) e
[errors](https://gitbook.com/docs/developers/gitbook-api/errors).

## Limitações conhecidas

- a API exige token mesmo quando o espaço publicado é público;
- o conector importa Markdown nativo e não baixa arquivos/anexos;
- páginas especiais ou conteúdo computado sem Markdown são preservados como
  documento vazio e podem ser ignorados pelo pipeline conforme as opções;
- o endpoint de páginas não expõe uma paginação documentada como a de espaços;
  a resposta é processada integralmente e a hierarquia aninhada é reconstruída;
- a integração real depende de uma organização/token do usuário e não é
  afirmada pelos testes unitários sintéticos.

## Erros e limites

HTTP 401 e 403 são apresentados como falha de autenticação/permissão, 404 como
recurso ausente, e 429/5xx/timeouts usam retry finito, backoff, jitter,
`Retry-After` e `X-RateLimit-Reset`. O cancelamento interrompe a espera.
