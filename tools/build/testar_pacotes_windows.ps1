# CI check: Tesseract inside the portable ZIP reads text, the program opens and the installer installs.
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot "..\.."))
# Logs need a GitHub login; annotations are public, so the failure is readable there.
function Fail([string]$Message) { Write-Output "::error::$Message"; exit 1 }

$work = Join-Path $env:RUNNER_TEMP "portatil"
Expand-Archive -Path (Get-Item "dist\releases\*-portable-*.zip").FullName -DestinationPath $work -Force
$image = Join-Path $work "texto.png"
python -c "from PIL import Image, ImageDraw, ImageFont; i = Image.new('RGB', (900, 160), 'white'); ImageDraw.Draw(i).text((20, 40), 'ALQUIMISTA 2026', fill='black', font=ImageFont.load_default(size=64)); import sys; i.save(sys.argv[1])" $image

$env:TESSDATA_PREFIX = Join-Path $work "tesseract\tessdata"
$text = & (Join-Path $work "tesseract\tesseract.exe") $image stdout -l por
if ("$text" -notmatch "ALQUIMISTA") { Fail "O Tesseract do portátil não leu o texto: $text" }

$exe = Join-Path $work "ALQuimista Studio.exe"
# A startup error opens a dialog that never closes, so a quick command must finish with code 0.
$command = Start-Process -FilePath $exe -ArgumentList "--set-language", "pt-BR" -PassThru
if (-not $command.WaitForExit(90000)) {
    taskkill /T /F /PID $command.Id | Out-Null
    Fail "O programa portátil travou ao iniciar (provável janela de erro)."
}
if ($command.ExitCode -ne 0) { Fail "O programa portátil terminou com erro (código $($command.ExitCode))." }

$app = Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds 20
if ($app.HasExited) { Fail "O programa portátil fechou sozinho (código $($app.ExitCode))." }
taskkill /T /F /PID $app.Id | Out-Null

$installed = Join-Path $env:RUNNER_TEMP "instalado"
$installer = (Get-Item "dist\releases\*-installer-*.exe").FullName
Start-Process -FilePath $installer -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/DIR=$installed" -Wait
foreach ($file in "ALQuimista Studio.exe", "tesseract\tesseract.exe", "tesseract\tessdata\por.traineddata") {
    if (-not (Test-Path -LiteralPath (Join-Path $installed $file))) { Fail "O instalador não colocou $file." }
}
Write-Output "Pacotes do Windows conferidos."
