[CmdletBinding()]
param(
    # Empty: read __version__ from alquimista/__init__.py (single source of the version).
    [string]$Version = "",
    # Tesseract installation copied next to the executable (reads text inside images).
    [string]$TesseractDir = $env:ALQ_TESSERACT_DIR,
    # Build without Tesseract: images keep only their description.
    [switch]$SemTesseract
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $root
if (-not $Version) {
    $Version = [regex]::Match((Get-Content -Raw (Join-Path $root "alquimista\__init__.py")), '__version__ = "([^"]+)"').Groups[1].Value
    if (-not $Version) { throw "__version__ não encontrado em alquimista/__init__.py." }
}
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = "python" }
$spec = Join-Path $root "packaging\ALQuimista Studio.spec"
$distRoot = Join-Path $root "dist\releases"
$buildId = Get-Date -Format "yyyyMMdd-HHmmss-fffffff"
$buildRoot = Join-Path $root (".tmp\pyinstaller-windows-" + $buildId)
$buildDist = Join-Path $buildRoot "dist"
$buildWork = Join-Path $buildRoot "work"
$portableRoot = Join-Path $root (".tmp\portable-staging-" + [guid]::NewGuid().ToString("N"))
$portableZip = Join-Path $distRoot "ALQuimista-Studio-windows-portable-$Version.zip"

& $python -m PyInstaller --noconfirm --clean --workpath $buildWork --distpath $buildDist $spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou." }

$builtExe = Join-Path $buildDist "ALQuimista Studio.exe"
if (-not (Test-Path -LiteralPath $builtExe)) { throw "PyInstaller terminou sem gerar um executável novo." }

# Only what OCR needs: the executable, its DLLs and the pt/en/es language data.
$tesseractStage = $null
if (-not $SemTesseract) {
    if (-not $TesseractDir) { $TesseractDir = Join-Path $env:ProgramFiles "Tesseract-OCR" }
    if (-not (Test-Path -LiteralPath (Join-Path $TesseractDir "tesseract.exe"))) {
        throw "Tesseract não encontrado em '$TesseractDir'. Instale (choco install tesseract), informe -TesseractDir ou gere com -SemTesseract."
    }
    $tesseractStage = Join-Path $buildRoot "tesseract"
    New-Item -ItemType Directory -Force -Path (Join-Path $tesseractStage "tessdata") | Out-Null
    Copy-Item -LiteralPath (Join-Path $TesseractDir "tesseract.exe") -Destination $tesseractStage
    Copy-Item -Path (Join-Path $TesseractDir "*.dll") -Destination $tesseractStage
    foreach ($language in "eng", "por", "spa", "osd") {
        $data = Join-Path $TesseractDir "tessdata\$language.traineddata"
        if (Test-Path -LiteralPath $data) { Copy-Item -LiteralPath $data -Destination (Join-Path $tesseractStage "tessdata") }
        elseif ($language -in "eng", "por") { throw "Falta $data (baixe de github.com/tesseract-ocr/tessdata_fast)." }
    }
    $configs = Join-Path $TesseractDir "tessdata\configs"
    if (Test-Path -LiteralPath $configs) { Copy-Item -LiteralPath $configs -Destination (Join-Path $tesseractStage "tessdata") -Recurse }
}

New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $portableRoot "data") | Out-Null
New-Item -ItemType File -Force -Path (Join-Path $portableRoot "data\.keep") | Out-Null
Copy-Item -LiteralPath $builtExe -Destination (Join-Path $portableRoot "ALQuimista Studio.exe")
New-Item -ItemType File -Force -Path (Join-Path $portableRoot "portable.flag") | Out-Null
Copy-Item -LiteralPath (Join-Path $root "distribuicao\LEIA-ME-PORTATIL.txt") -Destination (Join-Path $portableRoot "LEIA-ME-PORTATIL.txt")
if ($tesseractStage) { Copy-Item -LiteralPath $tesseractStage -Destination (Join-Path $portableRoot "tesseract") -Recurse }
if (Test-Path -LiteralPath $portableZip) { Remove-Item -LiteralPath $portableZip -Force }
Compress-Archive -Path (Join-Path $portableRoot "*") -DestinationPath $portableZip

$isccPath = $null
$isccCommand = Get-Command iscc.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if ($isccCommand) {
    $isccPath = [string]$isccCommand.Path
    if (-not $isccPath) { $isccPath = [string]$isccCommand.Source }
}
if (-not $isccPath) {
    $standardIscc = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if ($standardIscc) { $isccPath = [string]$standardIscc }
}
if ($isccPath) {
    $isccArguments = @("/DAppVersion=$Version", "/DAppExeSource=$builtExe")
    if ($tesseractStage) { $isccArguments += "/DTesseractDir=$tesseractStage" }
    & $isccPath @isccArguments (Join-Path $root "packaging\ALQuimista Studio.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup falhou." }
} else {
    Write-Warning "iscc.exe não encontrado; o pacote Portable foi gerado e o instalador pode ser criado com packaging/ALQuimista Studio.iss."
}

Remove-Item -LiteralPath $buildRoot, $portableRoot -Recurse -Force -ErrorAction SilentlyContinue
Write-Output "Portable: $portableZip"
