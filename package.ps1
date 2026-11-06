# Build omr-scanner-<date>.zip of this repository for a terminal without git access.
#   powershell -ExecutionPolicy Bypass -File .\package.ps1
$ErrorActionPreference = 'Stop'
$root  = $PSScriptRoot
$stage = Join-Path $env:TEMP 'omr-pkg\omr-scanner'
if (Test-Path (Split-Path $stage)) { Remove-Item (Split-Path $stage) -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
robocopy $root $stage /E /XD .git archive __pycache__ logs log /XF *.dmp *.zip scan_temp.bmp install.log /NFL /NDL /NJH /NJS | Out-Null
New-Item -ItemType Directory -Force -Path "$stage\service\logs", "$stage\sdk\log" | Out-Null
$zip = Join-Path $root ("omr-scanner-{0}.zip" -f (Get-Date -Format 'yyyyMMdd-HHmm'))
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path $stage -DestinationPath $zip
Write-Host "built $zip ($([int]((Get-Item $zip).Length / 1MB)) MB) - certs\ included if present"
