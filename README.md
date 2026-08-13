<div align="center">

# 🧪 ALQuimista Studio

### Turn knowledge bases into clean, portable Markdown — without building scripts or fighting the terminal.

Paste a source URL, connect, choose the pages you want, and export structured content ready for **AI, RAG, NotebookLM, Obsidian, offline archives, or any Markdown-based workflow**.

[![ALQuimista quality](https://github.com/luan146/Alquimista-Studio/actions/workflows/quality.yml/badge.svg)](https://github.com/luan146/Alquimista-Studio/actions/workflows/quality.yml)
![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/UI-PySide6-41CD52?logo=qt&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-6E7781)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

</div>

> 🌐 **Read this README in:** [English](README.md) · [Português (Brasil)](README.pt-BR.md) · [Español](README.es.md)

<p align="center">
  <img src="docs/screenshots/dashboard.png" alt="ALQuimista Studio dashboard" width="100%">
</p>

---

## ✨ What is ALQuimista Studio?

**ALQuimista Studio is a desktop application for extracting, selecting, converting, and organizing content from knowledge platforms through a visual workflow.**

The goal is simple: make knowledge extraction accessible even to people who do not want to write scripts, remember CLI commands, or manually copy hundreds of pages.

With ALQuimista, the normal workflow is:

```text
Paste a URL
    ↓
Connect to the source
    ↓
Choose spaces and pages
    ↓
Customize the Markdown
    ↓
Extract and consolidate
    ↓
Use the result anywhere
```

Your exported content remains portable instead of being locked to a specific AI platform.

---

## 🚀 Why use it?

| | ALQuimista Studio |
|---|---|
| 🖥️ **Visual workflow** | Normal usage happens through the desktop interface — no extraction commands required. |
| 🎯 **Selective extraction** | Choose exactly which spaces, sections, folders, and pages you want. |
| 📝 **Markdown-first** | Convert knowledge into a portable format that works across many tools. |
| 🧠 **AI-ready** | Prepare content for AI assistants, RAG pipelines, NotebookLM, and other context-based workflows. |
| 🗂️ **Knowledge-friendly** | Use exported Markdown in tools such as Obsidian or keep it as an offline archive. |
| 🔎 **Traceable output** | Preserve source URLs, hierarchy, metadata, timestamps, and SHA-256 hashes. |
| 🔄 **Incremental workflow** | Hash-based tracking helps identify content changes and avoid unnecessary work. |
| 🔐 **Security-aware** | API secrets are kept out of project files, and browser sessions are handled separately. |

---

## 🧭 How it works

### 1. 📚 Add a knowledge source

Paste a URL and let ALQuimista identify the platform and prepare the source configuration.

<p align="center">
  <img src="docs/screenshots/sources.png" alt="Adding knowledge sources in ALQuimista Studio" width="95%">
</p>

### 2. 🔐 Choose how to connect

Use public access or, when required by the platform, configure authentication for the source.

<p align="center">
  <img src="docs/screenshots/connection.png" alt="Connection and authentication screen" width="88%">
</p>

### 3. 🗃️ Browse spaces and select only what matters

Navigate through containers and hierarchical pages, then mark the exact content you want to extract.

<p align="center">
  <img src="docs/screenshots/selection-section.png" alt="Knowledge space selection" width="100%">
</p>

<p align="center">
  <img src="docs/screenshots/selection-pages.png" alt="Hierarchical page selection" width="100%">
</p>

### 4. ✍️ Customize the Markdown

Choose what should be preserved in the generated documents, including titles, original URLs, hierarchy, images, links, tables, code blocks, metadata, and more.

<p align="center">
  <img src="docs/screenshots/markdown.png" alt="Markdown customization and live preview" width="100%">
</p>

### 5. 📦 Consolidate for your workflow

Keep one Markdown file per page or group content into larger packages. Consolidation is useful for NotebookLM, RAG ingestion, archives, and other workflows where fewer files are easier to manage.

<p align="center">
  <img src="docs/screenshots/consolidation.png" alt="Markdown consolidation options" width="100%">
</p>

### 6. ⚗️ Review and run

Review the selected source, access mode, page count, output format, consolidation rules, and destination folder before starting the operation.

<p align="center">
  <img src="docs/screenshots/output.png" alt="Final review and extraction screen" width="100%">
</p>

---

## 🎯 What can I do with the exported content?

ALQuimista does **not** try to become another chatbot or lock your knowledge into one ecosystem. Its job is to turn remote knowledge into content you can keep and reuse.

```text
Confluence ─┐
GitBook ────┤
Zendesk ────┤
Notion ─────┼──► ALQuimista ───► Markdown / Packages ───► AI & knowledge tools
SharePoint ─┘
```

Typical destinations include:

- 🧠 AI assistants and context-based workflows
- 🔍 RAG ingestion pipelines
- 📓 NotebookLM source packages
- 🪨 Obsidian vaults
- 🗄️ Offline documentation archives
- 🔁 Documentation migration and reuse workflows
- 🧰 Custom automation built around Markdown files

---

## 🔌 Supported platforms

| Platform | Integration | Status |
|---|---|---|
| **Confluence Server / Data Center** | REST API | 🟢 **Stable** |
| **GitBook** | REST API v1 | 🟡 **Available** |
| **Zendesk Guide** | Help Center API | 🟡 **Available** |
| **Notion** | Official API | 🚧 **In development** |
| **SharePoint Online** | Microsoft Graph | 🚧 **In development** |
| **Generic websites** | — | 🗺️ **Planned** |

> Platform capabilities may differ. Some connectors support features such as hierarchical lazy loading or search more completely than others.

Integration status vocabulary: Estável, Disponível, Experimental, Parcial,
Em desenvolvimento and Planejado.

---

## 📄 What does ALQuimista generate?

Depending on your configuration, an extraction can produce:

```text
ALQuimista_Base/
├── arquivos_soltos/              # Individual Markdown documents
├── arquivos_consolidados/        # Consolidated packages
├── manifesto_alquimista.json     # Extraction manifest and hashes
├── relatorio_execucao.json       # Execution report
└── ...
```

A generated Markdown document can preserve information such as:

```markdown
# How to configure a sale

**Original URL:** https://example.com/...
**Module:** POS
**Path:** Product Manual > POS > How to configure a sale
**Last updated:** 2026-07-26 15:00
**SHA-256:** 88fe2b8c...

## Technical content

The original page content is converted to Markdown here.
```

This makes the exported knowledge easier to trace back to its original source and easier to process later.

---

## ⚡ Quick start

### Portable and installed distributions

ALQuimista Studio is distributed in portable and installed formats. The
portable packages can be extracted and launched without installation; the
Windows Installer creates shortcuts and keeps preferences in the user profile.
Both formats contain Portuguese (Brazil), English and Spanish.

The portable packages are named `ALQuimista-Studio-windows-portable.zip` and
`ALQuimista-Studio-linux-portable.tar.gz`. The Windows installer is named
`ALQuimista-Studio-windows-installer-<version>.exe`.

### Windows

Clone the repository:

```powershell
git clone https://github.com/luan146/Alquimista-Studio.git
cd Alquimista-Studio
```

Install the application dependencies:

```bat
tools\install\instalar_windows.bat
```

If you also want interactive browser authentication:

```bat
tools\install\instalar_windows.bat --with-browser
```

Then launch ALQuimista:

```bat
abrir_completo.bat
```

After setup, the normal extraction workflow is handled through the graphical interface.

### Linux

```bash
git clone https://github.com/luan146/Alquimista-Studio.git
cd Alquimista-Studio
chmod +x tools/install/instalar_linux.sh
./tools/install/instalar_linux.sh
python -m alquimista
```

For browser authentication support:

```bash
./tools/install/instalar_linux.sh --with-browser
```

---

## 🔐 Security and privacy

ALQuimista is designed to avoid storing sensitive authentication data inside project files.

- 🔑 API passwords and tokens remain in runtime memory and are not serialized into the project.
- 🌐 Browser sessions are stored separately from project files and can be deleted by the user.
- 🛡️ On Windows, persisted browser session data is protected with Windows DPAPI.
- 🧹 Discovery cache stores metadata only — not document content or credentials.
- 🚫 URLs containing embedded credentials are rejected.
- 📝 Logging includes secret redaction for sensitive values such as tokens, passwords, cookies, and authorization headers.

> Always review the access policies and API permissions of the knowledge platform you connect to.

---

## 🧱 Project structure

<details>
<summary><strong>Show technical architecture</strong></summary>

<br>

```text
alquimista/
├── connectors/       # Platform integrations
├── browser/          # Browser-assisted discovery and metadata cache
├── ui/               # PySide6 desktop interface
├── models.py         # Data contracts
├── services.py       # Extraction and consolidation engine
├── markdown.py       # HTML → Markdown transformation
├── storage.py        # Atomic persistence
├── auth.py           # Authentication workflows
├── reports.py        # Execution reports
└── manifest_index.py # Incremental manifest index

tests/                # Automated test suite
docs/                 # Architecture, connector docs and screenshots
assets/               # Visual assets and icons
```

Project configuration and maintenance tools are grouped separately:

```text
config/               # Ruff, pytest, Python version and dependencies
packaging/            # PyInstaller specification
tools/                # Installation, build and legacy compatibility scripts
```

The main application flow is:

```text
Dashboard → Sources → Connection → Selection → Markdown → Consolidation → Review → Results
```

For a deeper code map, see [`MAPA.md`](MAPA.md) and the [`docs/`](docs/) directory.

</details>

---

## 🛠️ Development

<details>
<summary><strong>Development commands</strong></summary>

<br>

Install development dependencies on Windows:

```bat
.venv\Scripts\python.exe -m pip install -c config\constraints.txt -r config\requirements-dev.txt
```

Run the test suite:

```bat
.venv\Scripts\python.exe -m pytest -c config\pytest.ini
```

Run Ruff:

```bat
.venv\Scripts\python.exe -m ruff check --config config\pyproject.toml alquimista tests
```

Run mypy:

```bat
.venv\Scripts\python.exe -m mypy --config-file config\pyproject.toml alquimista
```

Build the Windows executable:

```bat
tools\build\gerar_executavel.bat
```

The generated executable is written to:

```text
dist/ALQuimista Studio.exe
```

</details>

---

## ✅ Continuous integration

The repository includes a GitHub Actions workflow that automatically runs:

- dependency installation
- Ruff static checks
- mypy type checks
- Python compilation checks
- pytest
- PyInstaller executable build

This helps catch regressions before changes are merged.

---

## 🤝 Contributing

Contributions, bug reports, connector improvements, and documentation fixes are welcome.

Before submitting a change:

1. Run the relevant tests.
2. Run Ruff and mypy.
3. Make sure no credentials, sessions, local output, or private content were added to Git.
4. Keep changes focused and document behavior changes when necessary.

---

## 📚 Documentation

More technical information is available in the [`docs/`](docs/) directory, including architecture notes, connector documentation, manifest details, and interface screenshots.

For repository navigation and code investigation, see [`MAPA.md`](MAPA.md).

---

## 📜 License

ALQuimista Studio is released under the **MIT License**. See [`LICENSE`](LICENSE) for details.

---

## ⚠️ Disclaimer

ALQuimista Studio is an independent open-source project and is **not officially affiliated with Atlassian, GitBook, Zendesk, Notion, Microsoft, Google, Obsidian, or any other platform mentioned in this repository**.

Platform names and trademarks belong to their respective owners.

---

<div align="center">

### 🧪 Transform knowledge. Keep it portable.

If ALQuimista is useful to you, consider giving the repository a ⭐.

</div>
