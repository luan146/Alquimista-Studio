<div align="center">

# 🧪 ALQuimista Studio

### Convierte bases de conocimiento en Markdown limpio y portátil, sin crear scripts ni depender del terminal.

Pega una URL, conecta la fuente, selecciona las páginas y exporta contenido estructurado para IA, RAG, NotebookLM, Obsidian, archivos sin conexión o cualquier flujo basado en Markdown.

[![ALQuimista quality](https://github.com/luan146/Alquimista-Studio/actions/workflows/quality.yml/badge.svg)](https://github.com/luan146/Alquimista-Studio/actions/workflows/quality.yml)
![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/UI-PySide6-41CD52?logo=qt&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-6E7781)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

</div>

> 🌐 **Lee este README en:** [English](README.md) · [Português (Brasil)](README.pt-BR.md) · [Español](README.es.md)

## ⬇️ Descargar

ALQuimista Studio se distribuye en formatos portátil e instalado. Los paquetes portátiles se pueden extraer y ejecutar sin instalación; el instalador de Windows crea accesos directos y mantiene las preferencias en el perfil del usuario. Ambos formatos incluyen Português (Brasil), English y Español.

Los paquetes portátiles se llaman ALQuimista-Studio-windows-portable.zip y ALQuimista-Studio-linux-portable.tar.gz. El instalador de Windows se llama ALQuimista-Studio-windows-installer-<version>.exe.

<p align="center">
  <img src="docs/screenshots/dashboard.png" alt="Panel de ALQuimista Studio" width="100%">
</p>

---

## ✨ ¿Qué es ALQuimista Studio?

ALQuimista Studio es una aplicación de escritorio para extraer, seleccionar, convertir y organizar contenido de plataformas de conocimiento mediante un flujo visual.

El objetivo es hacer que la extracción de conocimiento sea accesible incluso para quienes no quieren escribir scripts, recordar comandos o copiar cientos de páginas manualmente.

El flujo normal es:

~~~text
Pega una URL
    ↓
Conecta la fuente
    ↓
Elige espacios y páginas
    ↓
Personaliza el Markdown
    ↓
Extrae y consolida
    ↓
Usa el resultado donde quieras
~~~

El contenido exportado sigue siendo portátil y no queda bloqueado en una plataforma específica de IA.

---

## 🚀 ¿Por qué usarlo?

| | ALQuimista Studio |
|---|---|
| 🖥️ **Flujo visual** | El uso normal se realiza desde la interfaz de escritorio; no hacen falta comandos de extracción. |
| 🎯 **Extracción selectiva** | Elige exactamente los espacios, secciones, carpetas y páginas que necesitas. |
| 📝 **Markdown primero** | Convierte el conocimiento a un formato portátil y compatible con muchas herramientas. |
| 🧠 **Listo para IA** | Prepara contenido para asistentes de IA, pipelines RAG, NotebookLM y flujos basados en contexto. |
| 🗂️ **Orientado al conocimiento** | Usa el Markdown exportado en Obsidian o consérvalo como archivo sin conexión. |
| 🔎 **Salida trazable** | Conserva URLs originales, jerarquía, metadatos, fechas y hashes SHA-256. |
| 🔄 **Flujo incremental** | El seguimiento mediante hashes ayuda a detectar cambios y evitar trabajo innecesario. |
| 🔐 **Con seguridad en mente** | Los secretos de API no se guardan en los archivos del proyecto y las sesiones del navegador se gestionan por separado. |

---

## 🧭 Cómo funciona

### 1. 📚 Añade una fuente de conocimiento

Pega una URL y deja que ALQuimista identifique la plataforma y prepare la configuración de la fuente.

<p align="center">
  <img src="docs/screenshots/sources.png" alt="Añadir fuentes de conocimiento" width="95%">
</p>

### 2. 🔐 Elige cómo conectarte

Usa acceso público o configura la autenticación cuando la plataforma lo requiera.

<p align="center">
  <img src="docs/screenshots/connection.png" alt="Pantalla de conexión y autenticación" width="88%">
</p>

### 3. 🗃️ Explora espacios y selecciona lo importante

Navega por contenedores y páginas jerárquicas y marca exactamente el contenido que deseas extraer.

<p align="center">
  <img src="docs/screenshots/selection-section.png" alt="Selección de espacios" width="100%">
</p>

<p align="center">
  <img src="docs/screenshots/selection-pages.png" alt="Selección jerárquica de páginas" width="100%">
</p>

### 4. ✍️ Personaliza el Markdown

Elige qué conservar en los documentos generados: títulos, URLs originales, jerarquía, imágenes, enlaces, tablas, bloques de código, metadatos y mucho más.

<p align="center">
  <img src="docs/screenshots/markdown.png" alt="Personalización y vista previa de Markdown" width="100%">
</p>

### 5. 📦 Consolida para tu flujo de trabajo

Mantén un archivo Markdown por página o agrupa el contenido en paquetes más grandes. La consolidación es útil para NotebookLM, ingestión RAG, archivos y flujos donde sea más cómodo trabajar con menos archivos.

<p align="center">
  <img src="docs/screenshots/consolidation.png" alt="Opciones de consolidación Markdown" width="100%">
</p>

### 6. ⚗️ Revisa y ejecuta

Revisa la fuente seleccionada, el modo de acceso, la cantidad de páginas, el formato de salida, las reglas de consolidación y la carpeta de destino antes de iniciar la operación.

<p align="center">
  <img src="docs/screenshots/output.png" alt="Revisión final y pantalla de extracción" width="100%">
</p>

---

## 🔌 Plataformas compatibles

| Plataforma | Integración | Estado |
|---|---|---|
| **Confluence Server / Data Center** | API REST | 🟢 **Estable** |
| **GitBook** | API REST v1 | 🟡 **Disponible** |
| **Zendesk Guide** | Help Center API | 🟡 **Disponible** |
| **Notion** | API oficial | 🧪 **Experimental** |
| **SharePoint Online** | Microsoft Graph | 🚧 **En desarrollo** |
| **Sitios web genéricos** | HTTPS estático | 🧪 **Experimental** |

Las capacidades pueden variar según la plataforma. Algunos conectores ofrecen funciones como carga jerárquica lazy o búsqueda de forma más completa que otros.

---

## 🎯 ¿Qué puedo hacer con el contenido exportado?

ALQuimista no intenta ser otro chatbot ni encerrar tu conocimiento en un ecosistema. Su función es convertir conocimiento remoto en contenido que puedas conservar y reutilizar.

~~~text
Confluence ─┐
GitBook ────┤
Zendesk ────┤
Notion ─────┼──► ALQuimista ───► Markdown / Paquetes ───► IA y herramientas de conocimiento
SharePoint ─┘
~~~

Destinos habituales:

- 🧠 Asistentes de IA y flujos basados en contexto
- 🔍 Pipelines de ingestión RAG
- 📓 Paquetes de fuentes para NotebookLM
- 🪨 Bóvedas de Obsidian
- 🗄️ Archivos de documentación sin conexión
- 🔁 Migración y reutilización de documentación
- 🧰 Automatizaciones personalizadas basadas en archivos Markdown

---

## 📄 ¿Qué genera ALQuimista?

Según la configuración, una extracción puede producir:

~~~text
ALQuimista_Base/
├── arquivos_soltos/              # Documentos Markdown individuales
├── arquivos_consolidados/        # Paquetes consolidados
├── manifesto_alquimista.json     # Manifiesto y hashes de extracción
├── relatorio_execucao.json       # Informe de ejecución
└── ...
~~~

Un documento Markdown generado puede conservar información como:

~~~markdown
# Cómo configurar una venta

URL original: https://example.com/...
Módulo: POS
Ruta: Manual del producto > POS > Cómo configurar una venta
Última actualización: 2026-07-26 15:00
SHA-256: 88fe2b8c...

## Contenido técnico

El contenido original de la página se convierte aquí a Markdown.
~~~

Esto facilita rastrear el conocimiento exportado hasta su origen y procesarlo posteriormente.

---

## ⚡ Inicio rápido

### Windows

Clona el repositorio:

~~~powershell
git clone https://github.com/luan146/Alquimista-Studio.git
cd Alquimista-Studio
~~~

Instala las dependencias:

~~~bat
tools\install\instalar_windows.bat
~~~

Para habilitar la autenticación interactiva mediante navegador:

~~~bat
tools\install\instalar_windows.bat --with-browser
~~~

Inicia ALQuimista:

~~~bat
abrir_completo.bat
~~~

### Linux

~~~bash
git clone https://github.com/luan146/Alquimista-Studio.git
cd Alquimista-Studio
chmod +x tools/install/instalar_linux.sh
./tools/install/instalar_linux.sh
python -m alquimista
~~~

Para habilitar la autenticación mediante navegador:

~~~bash
./tools/install/instalar_linux.sh --with-browser
~~~

---

## 🔐 Seguridad y privacidad

ALQuimista está diseñado para evitar guardar datos sensibles de autenticación dentro de los archivos del proyecto.

- 🔑 Las contraseñas y tokens de API permanecen en memoria y no se serializan en el proyecto.
- 🌐 Las sesiones del navegador se guardan separadas de los archivos del proyecto.
- 🛡️ En Windows, las sesiones persistentes del navegador se protegen con Windows DPAPI.
- 🧹 La caché de discovery almacena solo metadatos, no contenido de documentos ni credenciales.
- 🚫 Se rechazan las URLs con credenciales embebidas.
- 📝 Los logs ocultan tokens, contraseñas, cookies y cabeceras de autorización.

Revisa siempre las políticas de acceso y los permisos de la API de la plataforma conectada.

---

## 🧱 Estructura del proyecto

~~~text
alquimista/
├── connectors/       # Integraciones con plataformas
├── browser/          # Discovery y caché de metadatos
├── ui/               # Interfaz de escritorio PySide6
├── models.py         # Contratos de datos
├── services.py       # Motor de extracción y consolidación
├── markdown.py       # Transformación HTML → Markdown
├── storage.py        # Persistencia atómica
├── auth.py           # Flujos de autenticación
├── reports.py        # Informes de ejecución
└── manifest_index.py # Índice incremental del manifiesto

tests/                # Suite de pruebas automatizadas
docs/                 # Arquitectura, conectores y capturas
assets/               # Recursos visuales e iconos
~~~

El flujo principal es:

~~~text
Dashboard → Fuentes → Conexión → Selección → Markdown → Consolidación → Revisión → Resultados
~~~

Para un mapa detallado del código, consulta [MAPA.md](MAPA.md) y el directorio [docs/](docs/).

---

## 🛠️ Desarrollo

Instala las dependencias de desarrollo en Windows:

~~~bat
.venv\Scripts\python.exe -m pip install -c config\constraints.txt -r config\requirements-dev.txt
~~~

Ejecuta las pruebas:

~~~bat
.venv\Scripts\python.exe -m pytest -c config\pytest.ini
~~~

Ejecuta Ruff:

~~~bat
.venv\Scripts\python.exe -m ruff check --config config\pyproject.toml alquimista tests
~~~

Ejecuta mypy:

~~~bat
.venv\Scripts\python.exe -m mypy --config-file config\pyproject.toml alquimista
~~~

Genera el ejecutable de Windows:

~~~bat
tools\build\gerar_executavel.bat
~~~

El ejecutable se crea en:

~~~text
dist/ALQuimista Studio.exe
~~~

---

## ✅ Integración continua

El repositorio incluye un workflow de GitHub Actions que ejecuta automáticamente:

- instalación de dependencias;
- verificaciones estáticas con Ruff;
- comprobación de tipos con mypy;
- compilación de los archivos Python;
- suite de pruebas con pytest;
- generación del ejecutable con PyInstaller.

Esto ayuda a detectar regresiones antes de incorporar cambios.

---

## 🤝 Contribuir

Las contribuciones, informes de errores, mejoras de conectores y correcciones de documentación son bienvenidos.

Antes de enviar un cambio:

1. Ejecuta las pruebas relevantes.
2. Ejecuta Ruff y mypy.
3. Comprueba que no se hayan añadido credenciales, sesiones, salidas locales o contenido privado al Git.
4. Mantén los cambios enfocados y documenta los cambios de comportamiento importantes.

---

## 📚 Documentación

Encontrarás más información técnica en el directorio [docs/](docs/), incluida la documentación de conectores, detalles del manifiesto y capturas de la interfaz.

Para navegar por el repositorio e investigar el código, consulta [MAPA.md](MAPA.md).

---

## 📜 Licencia

ALQuimista Studio se distribuye bajo la licencia MIT. Consulta [LICENSE](LICENSE).

---

## ⚠️ Aviso

ALQuimista Studio es un proyecto open source independiente y no está afiliado oficialmente a Atlassian, GitBook, Zendesk, Notion, Microsoft, Google, Obsidian ni a ninguna otra plataforma mencionada en este repositorio.

Los nombres de las plataformas y las marcas registradas pertenecen a sus respectivos propietarios.

---

<div align="center">

### 🧪 Transforma conocimiento. Mantenlo portátil.

Si ALQuimista te resulta útil, considera darle una ⭐ al repositorio.

</div>
