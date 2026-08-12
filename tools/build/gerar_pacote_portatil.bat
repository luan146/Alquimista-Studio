@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "ROOT_DIR=%%~fI"
cd /d "%ROOT_DIR%"

echo [1/2] Gerando Portable Windows com os tres idiomas...
set "PYTHON_CMD=%ROOT_DIR%\.venv\Scripts\python.exe"
if not exist "%PYTHON_CMD%" (
    echo [ERRO] Ambiente virtual nao encontrado. Execute instalar_windows.bat primeiro.
    goto :erro
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\tools\build\gerar_distribuicoes.ps1"
if errorlevel 1 goto :erro

echo.
echo =========================================================
echo [SUCESSO] Arquivos criados:
echo %ROOT_DIR%\dist\releases\ALQuimista-Studio-windows-portable-5.0.0.zip
echo =========================================================
exit /b 0

:erro
echo.
echo [ERRO] Falha ao gerar o pacote portatil.
exit /b 1
