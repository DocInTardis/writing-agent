param([switch]$SkipInstall)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent

& (Join-Path $PSScriptRoot "build_frontend.ps1") -SkipInstall:$SkipInstall
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& (Join-Path $PSScriptRoot "build_sidecar.ps1") -SkipInstall:$SkipInstall
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Set-Location (Join-Path $repoRoot "desktop-tauri")
if (-not $SkipInstall) {
  & npm ci
  if ($LASTEXITCODE -ne 0) { throw "Tauri dependency installation failed." }
}
& npm run build -- --bundles nsis
exit $LASTEXITCODE
