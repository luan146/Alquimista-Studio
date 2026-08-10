@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    echo [ERRO] Python nao foi encontrado.
    echo Instale Python 3.12 em https://www.python.org/downloads/
    pause
    exit /b 1
)

%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,12) else 1)"
if errorlevel 1 (
    echo [ERRO] Use Python 3.12.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente virtual...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :erro
)

echo Instalando o ALQuimista Studio...
".venv\Scripts\python.exe" -m pip install -c constraints.txt -r requirements.txt
if errorlevel 1 goto :erro

if /I "%~1"=="--with-browser" call instalar_navegador.bat
if errorlevel 1 goto :erro

echo.
echo Instalacao concluida.
echo Use abrir_completo.bat para iniciar o ALQuimista diretamente pelo Python.
echo Para login pelo navegador, execute instalar_navegador.bat.
pause
exit /b 0

:erro
echo.
echo [ERRO] A instalacao nao foi concluida. Revise a mensagem acima.
pause
exit /b 1
