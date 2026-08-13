[CmdletBinding()]
param(
    [string]$Version = "0.9"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $root
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

New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $portableRoot "data") | Out-Null
New-Item -ItemType File -Force -Path (Join-Path $portableRoot "data\.keep") | Out-Null
Copy-Item -LiteralPath $builtExe -Destination (Join-Path $portableRoot "ALQuimista Studio.exe")
New-Item -ItemType File -Force -Path (Join-Path $portableRoot "portable.flag") | Out-Null
Copy-Item -LiteralPath (Join-Path $root "distribuicao\LEIA-ME-PORTATIL.txt") -Destination (Join-Path $portableRoot "LEIA-ME-PORTATIL.txt")
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
    & $isccPath "/DAppVersion=$Version" "/DAppExeSource=$builtExe" (Join-Path $root "packaging\ALQuimista Studio.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup falhou." }
} else {
    Write-Warning "iscc.exe não encontrado; o pacote Portable foi gerado e o instalador pode ser criado com packaging/ALQuimista Studio.iss."
}

Remove-Item -LiteralPath $buildRoot, $portableRoot -Recurse -Force -ErrorAction SilentlyContinue
Write-Output "Portable: $portableZip"
