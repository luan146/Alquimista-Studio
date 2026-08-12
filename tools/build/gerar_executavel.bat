@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "ROOT_DIR=%%~fI"
cd /d "%ROOT_DIR%"

echo [1/3] Verificando interpretador Python...
set "PYTHON_CMD="
if exist "%ROOT_DIR%\.venv\Scripts\python.exe" set "PYTHON_CMD=%ROOT_DIR%\.venv\Scripts\python.exe"
if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    echo [ERRO] Python nao foi encontrado. Execute instalar_windows.bat primeiro.
    goto :erro
)

echo [2/3] Verificando PyInstaller fixado...
"%PYTHON_CMD%" -m pip install -c "%ROOT_DIR%\config\constraints.txt" pyinstaller
if errorlevel 1 goto :erro

echo [3/3] Gerando o executavel standalone ALQuimista Studio.exe...
rem Spec do build: "%ROOT_DIR%\packaging\ALQuimista Studio.spec"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$id=Get-Date -Format 'yyyyMMdd-HHmmss-fffffff'; $root='%ROOT_DIR%'; $buildRoot=Join-Path $root ('.tmp\pyinstaller-windows-'+$id); $dist=Join-Path $buildRoot 'dist'; $work=Join-Path $buildRoot 'work'; & '%PYTHON_CMD%' -m PyInstaller --noconfirm --clean --workpath $work --distpath $dist '%ROOT_DIR%\packaging\ALQuimista Studio.spec'; if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $dist 'ALQuimista Studio.exe'))) { exit 1 }"
if errorlevel 1 goto :erro

echo.
echo =========================================================
echo [SUCESSO] Executavel criado em:
echo O executavel foi gerado em um diretorio .tmp\pyinstaller-windows-* novo.
echo =========================================================
pause
exit /b 0

:erro
echo [ERRO] Falha ao gerar o executavel. Verifique se o Python esta instalado no sistema.
pause
exit /b 1
