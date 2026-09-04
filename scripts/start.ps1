param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8000,
  [string]$IndexUrl = "",
  [switch]$SkipInstall,
  [switch]$InstallDependencies,
  [switch]$NoWeb
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $repoRoot
$env:PYTHONDONTWRITEBYTECODE = "1"

# A stale custom PYTHON_HOME can make venv/pip use a removed interpreter.
Remove-Item Env:PYTHON_HOME -ErrorAction SilentlyContinue

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if ($SkipInstall -and $InstallDependencies) {
  throw "Use either -SkipInstall or -InstallDependencies, not both."
}
if (-not $SkipInstall -and ($InstallDependencies -or -not (Test-Path $python))) {
  if (-not (Test-Path $python)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed." }
  }

  $pipArgs = @("-m", "pip", "install", "--no-cache-dir", "-r", "requirements.txt")
  if ($IndexUrl.Trim()) {
    $pipArgs += @("--index-url", $IndexUrl.Trim())
  }
  & $python @pipArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed. Recreate .venv if its base Python was removed."
  }
}

if (-not (Test-Path $python)) {
  throw "Virtual environment not found. Run this script without -SkipInstall first."
}

& $python -B -c "import writing_agent.launch"
if ($LASTEXITCODE -ne 0) {
  throw "Runtime dependencies are unavailable. Run scripts/start.ps1 -InstallDependencies to repair them."
}

$env:WRITING_AGENT_HOST = $HostAddress
$env:WRITING_AGENT_PORT = [string]$Port
if ($NoWeb) {
  Write-Host "Environment is ready."
  exit 0
}

& $python -B -m writing_agent.launch
