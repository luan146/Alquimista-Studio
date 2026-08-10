@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Execute instalar_windows.bat primeiro.
    pause
    exit /b 1
)
echo Instalando suporte opcional ao login pelo navegador...
".venv\Scripts\python.exe" -m pip install -c constraints.txt -r requirements-browser.txt
if errorlevel 1 goto :erro
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto :erro
echo Suporte ao navegador instalado.
exit /b 0
:erro
echo [ERRO] Nao foi possivel instalar o navegador.
exit /b 1
