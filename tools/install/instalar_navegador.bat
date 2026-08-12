@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "ROOT_DIR=%%~fI"
cd /d "%ROOT_DIR%"
if not exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
    echo [ERRO] Execute tools\install\instalar_windows.bat primeiro.
    pause
    exit /b 1
)
echo Instalando suporte opcional ao login pelo navegador...
"%ROOT_DIR%\.venv\Scripts\python.exe" -m pip install -c "%ROOT_DIR%\config\constraints.txt" -r "%ROOT_DIR%\config\requirements-browser.txt"
if errorlevel 1 goto :erro
"%ROOT_DIR%\.venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto :erro
echo Suporte ao navegador instalado.
exit /b 0
:erro
echo [ERRO] Nao foi possivel instalar o navegador.
exit /b 1
