# Gera o executável (dist\MediaLoader\) e o instalador (dist\MediaLoader-Setup.exe).
# Uso, na pasta python\:   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
# Requisitos: python -m pip install pyinstaller   |   winget install JRSoftware.InnoSetup
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==> Testes" -ForegroundColor Cyan
python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Os testes falharam; build cancelado." }

Write-Host "==> Ícone" -ForegroundColor Cyan
python packaging\make_icon.py
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o ícone." }

Write-Host "==> PyInstaller" -ForegroundColor Cyan
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\medialoader.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou." }

Write-Host "==> Inno Setup" -ForegroundColor Cyan
$candidates = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Write-Warning "Inno Setup não encontrado (winget install JRSoftware.InnoSetup). O app portátil está em dist\MediaLoader."
    exit 0
}
& $iscc "packaging\installer.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup falhou." }
Write-Host "Pronto: dist\MediaLoader-Setup.exe" -ForegroundColor Green
