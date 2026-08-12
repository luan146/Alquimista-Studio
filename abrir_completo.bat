@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo [ALQuimista Studio] Iniciando aplicacao...

set PYTHON_CMD=python
if exist ".venv\Scripts\python.exe" set PYTHON_CMD=.venv\Scripts\python.exe

%PYTHON_CMD% -m alquimista

if errorlevel 1 (
    echo.
    echo =========================================================
    echo [ERRO] Ocorreu uma falha ao executar o ALQuimista Studio.
    echo Veja a mensagem de erro acima.
    echo =========================================================
    pause
)
