"""Entry point oficial do ALQuimista Studio."""

from __future__ import annotations

import sys
from pathlib import Path

from .ui import run_app
from .ui.i18n import create_settings, normalize_language


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--set-language":
        language = normalize_language(sys.argv[2])
        if language is None:
            raise SystemExit("Idioma inválido. Use pt-BR, en ou es.")
        settings = create_settings()
        settings.setValue("preferences/language", language)
        settings.sync()
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--sync":
        from .headless import sync_project
        from .logging_utils import configure_logging, default_log_path

        logger = configure_logging(default_log_path())
        raise SystemExit(sync_project(Path(sys.argv[2]), logger.info))
    run_app("complete")


if __name__ == "__main__":
    main()
