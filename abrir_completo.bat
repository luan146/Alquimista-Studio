@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Primeira vez, ou bibliotecas novas no projeto: instala tudo sozinho em .venv.
fc /b "config\requirements.txt" ".venv\requirements-instaladas.txt" >nul 2>&1
if errorlevel 1 call "tools\install\instalar_windows.bat" --sem-pausa
if errorlevel 1 exit /b 1

echo [ALQuimista Studio] Iniciando aplicacao...
".venv\Scripts\python.exe" -m alquimista

if errorlevel 1 (
    echo.
    echo =========================================================
    echo [ERRO] Ocorreu uma falha ao executar o ALQuimista Studio.
    echo Veja a mensagem de erro acima.
    echo =========================================================
    pause
)
