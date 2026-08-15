<div align="center">

# 🧪 ALQuimista Studio

### Transforme bases de conhecimento em Markdown limpo e portátil — sem criar scripts ou depender do terminal.

Cole a URL de uma fonte, conecte-se, escolha as páginas e exporte conteúdo estruturado para **IA, RAG, NotebookLM, Obsidian, arquivos offline ou qualquer fluxo baseado em Markdown**.

[![ALQuimista quality](https://github.com/luan146/Alquimista-Studio/actions/workflows/quality.yml/badge.svg)](https://github.com/luan146/Alquimista-Studio/actions/workflows/quality.yml)
[![Release](https://img.shields.io/github/v/release/luan146/Alquimista-Studio)](https://github.com/luan146/Alquimista-Studio/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/luan146/Alquimista-Studio/total)](https://github.com/luan146/Alquimista-Studio/releases)
![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/UI-PySide6-41CD52?logo=qt&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-6E7781)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

</div>

> 🌐 **Leia este README em:** [English](README.md) · [Português (Brasil)](README.pt-BR.md) · [Español](README.es.md)

➡️ [Baixar a última release](https://github.com/luan146/Alquimista-Studio/releases/latest) · [Ver todas as releases](https://github.com/luan146/Alquimista-Studio/releases)

**Release atual: `0.9.5`** · O Instalador do Windows e o ZIP portátil usam a mesma versão.

<p align="center">
  <img src="docs/screenshots/dashboard.png" alt="Painel do ALQuimista Studio" width="100%">
</p>

---

## ✨ O que é o ALQuimista Studio?

**O ALQuimista Studio é uma aplicação desktop para extrair, selecionar, converter e organizar conteúdo de plataformas de conhecimento por meio de um fluxo visual.**

O objetivo é simples: tornar a extração de conhecimento acessível também para quem não quer escrever scripts, memorizar comandos ou copiar centenas de páginas manualmente.

O fluxo normal do ALQuimista é:

```text
Cole uma URL
    ↓
Conecte-se à fonte
    ↓
Escolha espaços e páginas
    ↓
Personalize o Markdown
    ↓
Extraia e consolide
    ↓
Use o resultado onde quiser
```

O conteúdo exportado continua portátil, sem ficar preso a uma plataforma específica de IA.

---

## 🚀 Por que usar?

| | ALQuimista Studio |
|---|---|
| 🖥️ **Fluxo visual** | O uso normal acontece pela interface desktop — não é necessário executar comandos de extração. |
| 🎯 **Extração seletiva** | Escolha exatamente os espaços, seções, pastas e páginas desejados. |
| 📝 **Markdown em primeiro lugar** | Converta conhecimento para um formato portátil e compatível com várias ferramentas. |
| 🧠 **Pronto para IA** | Prepare conteúdo para assistentes de IA, pipelines RAG, NotebookLM e outros fluxos baseados em contexto. |
| 🗂️ **Adequado para conhecimento** | Use o Markdown exportado no Obsidian ou mantenha-o como arquivo offline. |
| 🔎 **Saída rastreável** | Preserve URLs de origem, hierarquia, metadados, datas e hashes SHA-256. |
| 🔄 **Sincronização incremental** | Compare fontes, detecte itens novos/alterados/removidos e baixe somente o que mudou. |
| 🔐 **Segurança em mente** | Segredos de API não são gravados nos arquivos de projeto, e sessões de navegador são tratadas separadamente. |

---

## 🧭 Como funciona

### 1. 📚 Adicione uma fonte de conhecimento

Cole uma URL e deixe o ALQuimista identificar a plataforma e preparar a configuração da fonte.

<p align="center">
  <img src="docs/screenshots/sources.png" alt="Adição de fontes no ALQuimista Studio" width="95%">
</p>

### 2. 🔐 Escolha como se conectar

Use acesso público ou, quando exigido pela plataforma, configure a autenticação da fonte.

<p align="center">
  <img src="docs/screenshots/connection.png" alt="Tela de conexão e autenticação" width="88%">
</p>

### 3. 🗃️ Navegue pelos espaços e selecione o que importa

Navegue pelos contêineres e páginas hierárquicas e marque exatamente o conteúdo que deseja extrair.

<p align="center">
  <img src="docs/screenshots/selection-section.png" alt="Seleção de espaços de conhecimento" width="100%">
</p>

<p align="center">
  <img src="docs/screenshots/selection-pages.png" alt="Seleção de páginas hierárquicas" width="100%">
</p>

### 4. ✍️ Personalize o Markdown

Escolha o que deve ser preservado nos documentos gerados, incluindo títulos, URLs originais, hierarquia, imagens, links, tabelas, blocos de código, metadados e muito mais.

<p align="center">
  <img src="docs/screenshots/markdown.png" alt="Personalização e prévia do Markdown" width="100%">
</p>

### 5. 📦 Consolide para o seu fluxo de trabalho

Mantenha um arquivo Markdown por página ou agrupe o conteúdo em pacotes maiores. A consolidação é útil para fontes do NotebookLM, ingestão em RAG, arquivos e outros fluxos nos quais menos arquivos facilitam o uso.

<p align="center">
  <img src="docs/screenshots/consolidation.png" alt="Opções de consolidação Markdown" width="100%">
</p>

### 6. ⚗️ Revise e execute

Revise a fonte selecionada, o modo de acesso, a quantidade de páginas, o formato de saída, as regras de consolidação e a pasta de destino antes de iniciar a operação.

<p align="center">
  <img src="docs/screenshots/output.png" alt="Revisão final e extração" width="100%">
</p>

---

## 🔌 Plataformas suportadas

O ALQuimista registra atualmente **28 conectores executáveis** por meio de um registry compartilhado. As capacidades e exigências de autenticação dependem da plataforma.

| Plataforma | Integração | Status |
|---|---|---|
| **Confluence** | API REST oficial | 🟢 Disponível |
| **Zendesk Guide** | Help Center API | 🟢 Disponível |
| **Notion** | API oficial | 🟢 Disponível |
| **SharePoint Online** | Microsoft Graph API | 🟢 Disponível |
| **GitBook** | API REST oficial | 🟢 Disponível |
| **Generic Web** | Páginas web públicas | 🟢 Disponível |
| **Generic Docs / Frameworks** | `llms.txt`, Sitemap, Docusaurus, MkDocs, Mintlify | 🟢 Disponível |
| **Arquivos e pastas locais** | Processador universal de documentos locais | 🟢 Disponível |
| **BookStack** | API REST oficial | 🟢 Disponível |
| **GitHub Docs / Wiki** | API oficial do GitHub | 🟢 Disponível |
| **GitLab Docs / Wiki** | API oficial do GitLab v4 | 🟢 Disponível |
| **Freshdesk** | Solutions API e tickets | 🟢 Disponível |
| **Intercom** | Help Center e Support API | 🟢 Disponível |
| **Salesforce** | Knowledge e Service Cloud API | 🟢 Disponível |
| **HubSpot** | Knowledge Base e Service Hub API | 🟢 Disponível |
| **Help Scout** | Docs API | 🟢 Disponível |
| **Document360** | REST API | 🟢 Disponível |
| **Outline** | Knowledge Base API | 🟢 Disponível |
| **Helpjuice** | Knowledge Base API | 🟢 Disponível |
| **Guru** | Knowledge Cards API | 🟢 Disponível |
| **Slite** | Channels e Notes API | 🟢 Disponível |
| **MediaWiki** | Action API (`api.php`) | 🟢 Disponível |
| **ReadMe** | Documentation API | 🟢 Disponível |
| **WordPress** | REST API v2 | 🟢 Disponível |
| **Ghost** | Content API | 🟢 Disponível |
| **Strapi** | Headless CMS API | 🟢 Disponível |
| **Contentful** | Content Delivery API | 🟢 Disponível |
| **Sanity** | GROQ Query API | 🟢 Disponível |

> “Disponível” significa que o conector está registrado, implementado e executável. Permissões da API, autenticação, rate limits, paginação, busca e descoberta hierárquica ainda variam por plataforma.

O vocabulário de status também contempla **Estável**, **Disponível**, **Experimental**, **Parcial**, **Em desenvolvimento** e **Planejado**; a matriz desta release apresenta os 28 conectores registrados como disponíveis.

As capacidades podem variar entre plataformas. Alguns conectores oferecem recursos como carregamento hierárquico lazy ou busca de forma mais completa que outros.

### 📁 Documentos locais para Markdown

O conector de Arquivos Locais percorre arquivos e pastas e envia cada arquivo compatível ao processador apropriado. O pipeline atual cobre:

- PDF, incluindo extração de texto, títulos por página, metadados e tabelas quando o backend do PDF as disponibiliza;
- planilhas convertidas em tabelas Markdown (`.xlsx`, `.xlsm`, `.csv`, `.tsv` e `.ods`);
- arquivos Word, PowerPoint, EPUB, HTML, imagens, texto simples e Markdown.

Arquivos grandes respeitam o limite do registry de processadores, e dependências opcionais de formato falham de forma explícita quando não estão disponíveis.

### 🔄 Sincronização incremental

O serviço de sincronização pode operar no escopo de seleção, fonte ou projeto. Ele cria um plano usando o inventário remoto e o manifesto existente e classifica os itens como **novos, alterados, sem alterações, removidos, com falha ou preservados após erro**. Somente documentos alterados são baixados, remoções remotas são tratadas com segurança, anexos podem ser comparados e a operação grava o relatório estruturado `sync_report.json`. A consolidação pode ser executada automaticamente após uma sincronização bem-sucedida.

---

## 🎯 O que posso fazer com o conteúdo exportado?

O ALQuimista **não tenta ser outro chatbot nem prender seu conhecimento a um ecossistema**. A função dele é transformar conhecimento remoto em conteúdo que você pode manter e reutilizar.

```text
Confluence ─┐
GitBook ────┤
Zendesk ────┤
Notion ─────┼──► ALQuimista ───► Markdown / Pacotes ───► IA e ferramentas de conhecimento
SharePoint ─┘
```

Destinos comuns incluem:

- 🧠 Assistentes de IA e fluxos baseados em contexto
- 🔍 Pipelines de ingestão RAG
- 📓 Pacotes de fontes para NotebookLM
- 🪨 Cofres do Obsidian
- 🗄️ Arquivos offline de documentação
- 🔁 Migração e reutilização de documentação
- 🧰 Automações personalizadas baseadas em arquivos Markdown

---

## 📄 O que o ALQuimista gera?

Dependendo da configuração, uma extração pode produzir:

```text
ALQuimista_Base/
├── arquivos_soltos/              # Documentos Markdown individuais
├── arquivos_consolidados/        # Pacotes consolidados
├── manifesto_alquimista.json     # Manifesto da extração e hashes
├── relatorio_execucao.json       # Relatório de execução
└── ...
```

Um documento Markdown gerado pode preservar informações como:

```markdown
# Como configurar uma venda

**URL original:** https://example.com/...
**Módulo:** POS
**Caminho:** Manual do produto > POS > Como configurar uma venda
**Última atualização:** 2026-07-26 15:00
**SHA-256:** 88fe2b8c...

## Conteúdo técnico

O conteúdo original da página é convertido para Markdown aqui.
```

Isso torna o conhecimento exportado mais fácil de rastrear até a origem e de processar posteriormente.

---

## ⚡ Início rápido

### 1. Para a maioria das pessoas: baixar e executar

Baixe → instale ou extraia → abra o ALQuimista Studio.

| Plataforma | Pacote |
|---|---|
| 🪟 Windows | [Instalador `0.9.5`](https://github.com/luan146/Alquimista-Studio/releases/latest/download/ALQuimista-Studio-windows-installer-0.9.5.exe) · [ZIP portátil `0.9.5`](https://github.com/luan146/Alquimista-Studio/releases/latest/download/ALQuimista-Studio-windows-portable-0.9.5.zip) |
| 🐧 Linux | [tar.gz portátil](https://github.com/luan146/Alquimista-Studio/releases/latest/download/ALQuimista-Studio-linux-portable-0.9.5.tar.gz) |

➡️ [Ver todas as releases](https://github.com/luan146/Alquimista-Studio/releases)

O instalador do Windows cria atalhos e mantém as preferências no perfil do
usuário. O pacote portátil pode ser extraído e executado sem instalação. No
Linux, extraia o tarball e execute o arquivo `ALQuimista Studio` incluído.

### 2. Para desenvolvedores: executar a partir do código

#### Windows

Clone o repositório:

```powershell
git clone https://github.com/luan146/Alquimista-Studio.git
cd Alquimista-Studio
```

Instale as dependências da aplicação:

```bat
tools\install\instalar_windows.bat
```

Se também quiser autenticação interativa pelo navegador:

```bat
tools\install\instalar_windows.bat --with-browser
```

Depois, inicie o ALQuimista:

```bat
abrir_completo.bat
```

Após a configuração, o fluxo normal de extração é executado pela interface gráfica.

#### Linux

```bash
git clone https://github.com/luan146/Alquimista-Studio.git
cd Alquimista-Studio
chmod +x tools/install/instalar_linux.sh
./tools/install/instalar_linux.sh
python -m alquimista
```

Para habilitar a autenticação pelo navegador:

```bash
./tools/install/instalar_linux.sh --with-browser
```

---

## 🔐 Segurança e privacidade

O ALQuimista foi projetado para evitar o armazenamento de dados sensíveis de autenticação dentro dos arquivos de projeto.

- 🔑 Senhas e tokens de API permanecem na memória e não são serializados no projeto.
- 🌐 Sessões de navegador são armazenadas separadamente dos arquivos de projeto e podem ser excluídas pelo usuário.
- 🛡️ No Windows, os dados persistidos de sessão do navegador são protegidos pelo Windows DPAPI.
- 🧹 O cache de discovery armazena apenas metadados — não conteúdo de documentos nem credenciais.
- 🚫 URLs com credenciais embutidas são recusadas.
- 📝 Os logs ocultam valores sensíveis, como tokens, senhas, cookies e cabeçalhos de autorização.

> Sempre revise as políticas de acesso e as permissões da API da plataforma de conhecimento conectada.

---

## 🧱 Estrutura do projeto

<details>
<summary><strong>Mostrar arquitetura técnica</strong></summary>

<br>

```text
alquimista/
├── connectors/          # Integrações e HTTP compartilhado
├── discovery/           # Descoberta web universal
├── document_processing/ # Processadores de PDF, planilhas e arquivos locais
├── browser/             # Discovery pelo navegador e cache de metadados
├── markdown/            # Transformação, metadados e renderização
├── services/            # Extração, sincronização e consolidação
├── ui/                  # Interface desktop PySide6
├── models.py            # Contratos de dados
├── storage.py           # Persistência atômica e manifestos
├── auth.py              # Fluxos de autenticação
└── runtime.py           # Cancelamento, progresso e estado de execução

tests/                # Suíte de testes automatizados
docs/                 # Arquitetura, documentação e screenshots
assets/               # Recursos visuais e ícones
```

O fluxo principal da aplicação é:

```text
Dashboard → Fontes → Conexão → Seleção → Markdown → Consolidação → Revisão → Resultados
```

Para um mapa mais detalhado do código, consulte [`MAPA.md`](MAPA.md) e o diretório [`docs/`](docs/).

</details>

---

## 🛠️ Desenvolvimento

<details>
<summary><strong>Comandos de desenvolvimento</strong></summary>

<br>

Instale as dependências de desenvolvimento no Windows:

```bat
.venv\Scripts\python.exe -m pip install -c config\constraints.txt -r config\requirements-dev.txt
```

Execute a suíte de testes:

```bat
.venv\Scripts\python.exe -m pytest -c config\pytest.ini
```

Execute o Ruff:

```bat
.venv\Scripts\python.exe -m ruff check --config config\pyproject.toml alquimista tests
```

Execute o mypy:

```bat
.venv\Scripts\python.exe -m mypy --config-file config\pyproject.toml alquimista
```

Gere o executável do Windows:

```bat
tools\build\gerar_executavel.bat
```

Gere o Portable e o instalador do Windows na versão `0.9.5`:

```powershell
.\tools\build\gerar_distribuicoes.ps1 -Version 0.9.5
```

O executável será criado em:

```text
dist/ALQuimista Studio.exe
```

Para criar um ZIP portátil para Windows 10/11 (64 bits), use:

```bat
tools\build\gerar_pacote_portatil.bat
```

O pacote será criado em `dist/releases/ALQuimista-Studio-windows-portable-0.9.5.zip`. Ele não exige Python no computador de destino. A autenticação assistida pelo navegador pode exigir o Google Chrome instalado; o Chromium não é incluído neste pacote portátil.

</details>

---

## ✅ Integração contínua

O repositório possui um workflow do GitHub Actions que executa automaticamente:

- instalação das dependências;
- verificações estáticas com Ruff;
- verificação de tipos com mypy;
- compilação dos arquivos Python;
- suíte de testes com pytest;
- geração do Portable e do instalador do Windows;
- geração e validação do pacote Portable Linux.

Isso ajuda a detectar regressões antes que as alterações sejam incorporadas.

---

## 🤝 Contribuição

Contribuições, relatos de bugs, melhorias de conectores e correções de documentação são bem-vindos.

Antes de enviar uma alteração:

1. execute os testes relevantes;
2. execute Ruff e mypy;
3. certifique-se de que nenhuma credencial, sessão, saída local ou conteúdo privado foi incluído no Git;
4. mantenha as alterações focadas e documente mudanças de comportamento quando necessário.

---

## 📚 Documentação

Mais informações técnicas estão disponíveis no diretório [`docs/`](docs/), incluindo notas de arquitetura, documentação dos conectores, detalhes do manifesto e screenshots da interface.

Para navegar pelo repositório e investigar o código, consulte [`MAPA.md`](MAPA.md).

---

## 📜 Licença

O ALQuimista Studio é distribuído sob a **licença MIT**. Consulte [`LICENSE`](LICENSE).

---

## ⚠️ Aviso

O ALQuimista Studio é um projeto open source independente e **não possui afiliação oficial com Atlassian, GitBook, Zendesk, Notion, Microsoft, Google, Obsidian ou qualquer outra plataforma mencionada neste repositório**.

Os nomes das plataformas e as marcas registradas pertencem aos seus respectivos proprietários.

---

<div align="center">

### 🧪 Transforme conhecimento. Mantenha-o portátil.

Se o ALQuimista for útil para você, considere dar uma ⭐ ao repositório.

</div>
