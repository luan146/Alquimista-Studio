# ALQuimista Studio

Aplicação desktop para adquirir, selecionar, converter e exportar conteúdo de plataformas de conhecimento por meio de APIs oficiais.

O ALQuimista permite configurar fontes, autenticar-se, navegar por espaços e páginas, selecionar o conteúdo desejado, converter documentos para Markdown e gerar arquivos individuais ou consolidados.

## Principais recursos

- Interface desktop em PySide6.
- Cadastro de múltiplas fontes e detecção de plataforma pela URL.
- Autenticação pública, Basic, Bearer e navegador.
- Navegação por contêineres e páginas hierárquicas.
- Carregamento lazy de páginas e documentos filhos.
- Seleção granular do conteúdo a extrair.
- Conversão de HTML para Markdown.
- Preservação de links, imagens, tabelas e metadados.
- Frontmatter e URL original no Markdown.
- SHA-256 e atualização incremental.
- Extração cancelável, retry e controle de taxa.
- Relatórios de execução e lista de falhas.
- Consolidação em arquivo único, pacote ou índice.
- Cache de discovery contendo apenas metadados.
- Sessões de navegador protegidas pelo sistema operacional.

## Fluxo de uso

```text
Dashboard → Fontes → Conexão → Seleção → Revisão → Markdown → Consolidação → Resultados
```

1. Crie ou abra um projeto.
2. Cadastre uma fonte e informe sua URL.
3. Escolha o método de autenticação.
4. Teste a conexão.
5. Carregue os espaços e páginas disponíveis.
6. Selecione o conteúdo desejado.
7. Revise as opções de Markdown e extração.
8. Execute a aquisição.
9. Gere arquivos individuais ou uma consolidação.

A aplicação não possui URLs, contas, credenciais ou páginas predefinidas.

## Plataformas

| Plataforma | Integração | Status |
| --- | --- | --- |
| Confluence Server/Data Center | REST API | Estável |
| GitBook | REST API v1 | Disponível |
| Zendesk Guide | Help Center API | Disponível |
| Notion | API oficial | Em desenvolvimento |
| SharePoint Online | Microsoft Graph | Em desenvolvimento |
| Sites genéricos | — | Planejado |

Os conectores seguem um contrato comum para validar conexão, listar contêineres, listar documentos, buscar conteúdo e consultar páginas filhas quando suportado.

Os estados da matriz significam: **Estável** é o caminho principal validado;
**Disponível** está implementado para uso conforme suas limitações;
**Experimental** pode mudar; **Parcial** cobre apenas parte do contrato;
**Em desenvolvimento** ainda não deve ser tratado como funcional; e
**Planejado** ainda não está implementado.

## Requisitos

- Python 3.12.
- Windows ou Linux.
- Acesso à API da plataforma utilizada.
- Credenciais temporárias quando a fonte exigir autenticação.

## Instalação no Windows

Execute:

```bat
instalar_windows.bat
```

Para instalar também o suporte ao login pelo navegador:

```bat
instalar_windows.bat --with-browser
```

Depois, inicie a aplicação com:

```bat
abrir_completo.bat
```

## Instalação no Linux

```bash
./instalar_linux.sh
```

Para instalar também o navegador usado na autenticação interativa:

```bash
./instalar_linux.sh --with-browser
```

## Execução manual

Após criar o ambiente virtual e instalar as dependências:

```bash
python alquimista_studio_completo.py
```

No Windows, também é possível executar:

```bat
.venv\Scripts\python.exe alquimista_studio_completo.py
```

## Configuração

O arquivo `config.example.json` contém uma configuração sintética para referência.

Comece criando ou abrindo um projeto pela interface e configure as fontes diretamente na aplicação.

Não coloque tokens, senhas, cookies ou arquivos de sessão dentro do repositório.

## Saída

O ALQuimista pode gerar:

- um arquivo Markdown por documento;
- um pacote organizado por fonte e contêiner;
- um arquivo Markdown consolidado;
- um índice de documentos;
- manifesto com hashes;
- relatório de execução;
- lista estruturada de falhas.

A estrutura de saída pode preservar a hierarquia original dos contêineres e documentos.

## Segurança e privacidade

- Senhas e tokens de API permanecem apenas em memória e não são serializados.
- Sessões de navegador podem ser persistidas localmente e são protegidas pelo sistema operacional no Windows.
- Arquivos de sessão permanecem fora da árvore do projeto e não são incluídos no repositório.
- Segredos não são serializados no projeto exportado.
- URLs com credenciais embutidas são recusadas.
- O cache do navegador armazena somente metadados de discovery.
- Conteúdo de documentos não é armazenado no cache de discovery.
- Sessões de navegador são mantidas fora da árvore do projeto.
- Arquivos locais, caches, saídas e credenciais permanecem ignorados pelo Git.

## Desenvolvimento

Instale as dependências de desenvolvimento:

```bat
.venv\Scripts\python.exe -m pip install -c constraints.txt -r requirements-dev.txt
```

Execute os testes:

```bat
.venv\Scripts\python.exe -m pytest
```

Execute o Ruff:

```bat
.venv\Scripts\python.exe -m ruff check alquimista tests
```

Execute o mypy:

```bat
.venv\Scripts\python.exe -m mypy alquimista
```

Os testes de integração e os testes que acessam APIs reais permanecem desabilitados por padrão.

## Geração do executável

No Windows, execute:

```bat
gerar_executavel.bat
```

O executável será gerado em:

```text
dist/ALQuimista Studio.exe
```

## Integração contínua

O projeto possui uma rotina no GitHub Actions que executa:

- instalação das dependências;
- Ruff;
- mypy;
- compilação;
- suíte de testes;
- geração do executável.

## Arquitetura

O projeto é organizado em camadas:

- `alquimista/`: núcleo da aplicação;
- `alquimista/connectors/`: conectores por plataforma;
- `alquimista/browser/`: discovery e cache de metadados;
- `alquimista/ui/`: interface PySide6;
- `tests/`: testes automatizados;
- `docs/`: arquitetura, conectores e referências visuais;
- `assets/`: ícones e recursos visuais.

O fluxo principal separa configuração de fontes, autenticação, seleção, extração, transformação Markdown, consolidação e resultados.

Consulte o [índice da documentação](docs/README.md) para detalhes técnicos.

## Limitações

Alguns recursos dependem das capacidades e políticas da plataforma conectada, incluindo:

- ambientes Cloud;
- SSO;
- proxies autenticados;
- anexos;
- macros;
- permissões específicas;
- limites de API;
- autenticação OAuth.

A disponibilidade de cada recurso pode variar conforme o conector utilizado.

## Licença

Este projeto é distribuído sob a licença MIT. Consulte o arquivo [LICENSE](LICENSE).

## Contribuição

Contribuições são bem-vindas. Antes de enviar alterações:

1. execute os testes;
2. execute Ruff e mypy;
3. verifique se nenhuma credencial ou saída local foi incluída;
4. mantenha as alterações específicas e documentadas.

Este é um projeto independente e não possui afiliação oficial com os fornecedores das plataformas suportadas.
