param([switch]$SkipInstall)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
$frontend = Join-Path $repoRoot "writing_agent\web\frontend_svelte"
$wasmOut = Join-Path $frontend "public\wasm"

Set-Location $repoRoot
& wasm-pack build "engine\bridge" --release --target web --out-dir $wasmOut
if ($LASTEXITCODE -ne 0) { throw "Rust WASM build failed." }

Set-Location $frontend
if (-not $SkipInstall) {
  & npm ci
  if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
}
& npm run check
if ($LASTEXITCODE -ne 0) { throw "Frontend type check failed." }
& npm run build
if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
