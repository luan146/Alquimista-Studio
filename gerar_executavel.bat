@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo [1/3] Verificando interpretador Python...
set "PYTHON_CMD="
if exist ".venv\Scripts\python.exe" set "PYTHON_CMD=.venv\Scripts\python.exe"
if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    echo [ERRO] Python nao foi encontrado. Execute instalar_windows.bat primeiro.
    goto :erro
)

echo [2/3] Verificando PyInstaller fixado...
%PYTHON_CMD% -m pip install -c constraints.txt pyinstaller
if errorlevel 1 goto :erro

echo [3/3] Gerando o executavel standalone ALQuimista Studio.exe...
%PYTHON_CMD% -m PyInstaller --noconfirm --clean "ALQuimista Studio.spec"
if errorlevel 1 goto :erro

echo.
echo =========================================================
echo [SUCESSO] Executavel criado em:
echo %~dp0dist\ALQuimista Studio.exe
echo =========================================================
pause
exit /b 0

:erro
echo [ERRO] Falha ao gerar o executavel. Verifique se o Python esta instalado no sistema.
pause
exit /b 1
