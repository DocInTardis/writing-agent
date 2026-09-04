param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8000,
  [string]$IndexUrl = "",
  [switch]$SkipInstall,
  [switch]$InstallDependencies
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $repoRoot
Remove-Item Env:PYTHON_HOME -ErrorAction SilentlyContinue

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if ($SkipInstall -and $InstallDependencies) {
  throw "Use either -SkipInstall or -InstallDependencies, not both."
}
$desktopReady = $false
if (Test-Path $python) {
  & $python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('PySide6') else 1)"
  $desktopReady = $LASTEXITCODE -eq 0
}
if (-not $SkipInstall -and ($InstallDependencies -or -not $desktopReady)) {
  if (-not (Test-Path $python)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
  }
  $pipArgs = @("-m", "pip", "install", "--no-cache-dir", "-e", ".[desktop]")
  if ($IndexUrl.Trim()) {
    $pipArgs += @("--index-url", $IndexUrl.Trim())
  }
  & $python @pipArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Desktop dependency installation failed."
  }
}

if (-not (Test-Path $python)) {
  throw "Virtual environment not found. Run this script without -SkipInstall first."
}

$env:WRITING_AGENT_HOST = $HostAddress
$env:WRITING_AGENT_PORT = [string]$Port
& $python -m writing_agent.desktop_app
