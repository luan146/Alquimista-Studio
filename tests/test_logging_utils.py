import logging

from alquimista.logging_utils import configure_logging


def test_configure_logging_emits_live_console_line(tmp_path, capsys) -> None:
    logger = configure_logging(tmp_path / "alquimista.jsonl")
    logger.info("Diagnóstico em tempo real token=segredo")

    output = capsys.readouterr().out
    assert "Diagnóstico em tempo real" in output
    assert "token=***" in output
    assert (tmp_path / "alquimista.jsonl").is_file()

    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
