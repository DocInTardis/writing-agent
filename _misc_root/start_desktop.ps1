Param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8000,
  [string]$Model = "qwen2.5:3b",
  [string]$OllamaHost = "http://127.0.0.1:11434",
  [string]$IndexUrl = "",
  [switch]$SkipInstall,
  [switch]$SkipPull
)

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not $SkipInstall) {
  function Invoke-PipInstall([string]$Index) {
    if ($Index -and $Index.Trim().Length -gt 0) {
      .\\.venv\\Scripts\\pip install -r requirements.txt -i $Index
    } else {
      .\\.venv\\Scripts\\pip install -r requirements.txt
    }
    if ($LASTEXITCODE -ne 0) {
      throw "pip install failed with exit code $LASTEXITCODE"
    }
  }

  if (-not (Test-Path ".venv\\Scripts\\python.exe")) {
    python -m venv .venv
  }

  try {
    Invoke-PipInstall $IndexUrl
  } catch {
    if (-not ($IndexUrl -and $IndexUrl.Trim().Length -gt 0)) {
      Write-Host "pip install failed. Retrying with official index (https://pypi.org/simple) ..."
      Invoke-PipInstall "https://pypi.org/simple"
    } else {
      throw
    }
  }
}

$env:OLLAMA_HOST = $OllamaHost
$env:OLLAMA_MODEL = $Model

function Resolve-OllamaExe {
  $cmd = Get-Command ollama -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $candidates = @(
    Join-Path $env:LOCALAPPDATA "Programs\\Ollama\\ollama.exe",
    Join-Path $env:ProgramFiles "Ollama\\ollama.exe"
  )
  foreach ($c in $candidates) {
    if ($c -and (Test-Path $c)) { return $c }
  }
  return $null
}

$OllamaExe = Resolve-OllamaExe
if ($OllamaExe) {
  $ollamaDir = Split-Path $OllamaExe -Parent
  if ($env:PATH -notlike "*$ollamaDir*") { $env:PATH = "$ollamaDir;$env:PATH" }
} else {
  Write-Host "ollama not found. Continuing without Ollama (WRITING_AGENT_USE_OLLAMA=0)."
  $env:WRITING_AGENT_USE_OLLAMA = "0"
  $SkipPull = $true
}

function Test-OllamaPort {
  try {
    $uri = [Uri]$env:OLLAMA_HOST
    $host = $uri.Host
    $port = $uri.Port
    $client = New-Object System.Net.Sockets.TcpClient
    $iar = $client.BeginConnect($host, $port, $null, $null)
    $ok = $iar.AsyncWaitHandle.WaitOne(500)
    if ($ok -and $client.Connected) {
      $client.EndConnect($iar) | Out-Null
      $client.Close()
      return $true
    }
    try { $client.Close() } catch {}
    return $false
  } catch {
    return $false
  }
}

if (-not (Test-OllamaPort)) {
  if ($env:WRITING_AGENT_USE_OLLAMA -ne "0") {
    Write-Host "Starting Ollama service (ollama serve) ..."
    try {
      $exe = $OllamaExe
      if (-not $exe) { $exe = "ollama" }
      Start-Process -WindowStyle Hidden -FilePath $exe -ArgumentList "serve"
      Start-Sleep -Milliseconds 800
    } catch {
      Write-Host "Failed to start Ollama. Continuing without Ollama."
      $env:WRITING_AGENT_USE_OLLAMA = "0"
      $SkipPull = $true
    }
  }
}

if (-not $SkipPull) {
  $hasModel = $false
  try {
    $exe = $OllamaExe
    if (-not $exe) { $exe = "ollama" }
    $list = & $exe list 2>$null
    if ($list) {
      $hasModel = [bool]($list | Select-String -SimpleMatch $Model)
    }
  } catch {
    $hasModel = $false
  }

  if (-not $hasModel) {
    Write-Host "Ensuring model is available (ollama pull $Model) ..."
    $exe = $OllamaExe
    if (-not $exe) { $exe = "ollama" }
    & $exe pull $Model
  } else {
    Write-Host "Model already available: $Model"
  }
}

$env:WRITING_AGENT_HOST = $HostAddress
$env:WRITING_AGENT_PORT = "$Port"
if (-not $env:WRITING_AGENT_USE_OLLAMA) { $env:WRITING_AGENT_USE_OLLAMA = "1" }
if (-not $env:WRITING_AGENT_WORKERS) { $env:WRITING_AGENT_WORKERS = "2" }
if (-not $env:WRITING_AGENT_WORKER_MODELS) { $env:WRITING_AGENT_WORKER_MODELS = "qwen2.5:1.5b,qwen2.5:3b" }
if (-not $env:WRITING_AGENT_AGG_MODEL) { $env:WRITING_AGENT_AGG_MODEL = "qwen2.5:7b" }
if (-not $env:WRITING_AGENT_ANALYSIS_TIMEOUT_S) { $env:WRITING_AGENT_ANALYSIS_TIMEOUT_S = "45" }
if (-not $env:WRITING_AGENT_EXTRACT_TIMEOUT_S) { $env:WRITING_AGENT_EXTRACT_TIMEOUT_S = "20" }
if (-not $env:WRITING_AGENT_PLAN_TIMEOUT_S) { $env:WRITING_AGENT_PLAN_TIMEOUT_S = "45" }
if (-not $env:WRITING_AGENT_DRAFT_MAX_MODELS) { $env:WRITING_AGENT_DRAFT_MAX_MODELS = "2" }
if (-not $env:WRITING_AGENT_DRAFT_MAIN_MODEL) { $env:WRITING_AGENT_DRAFT_MAIN_MODEL = "qwen2.5:1.5b" }
if (-not $env:WRITING_AGENT_DRAFT_SUPPORT_MODEL) { $env:WRITING_AGENT_DRAFT_SUPPORT_MODEL = "qwen2.5:3b" }
if (-not $env:WRITING_AGENT_DRAFT_PARALLEL) { $env:WRITING_AGENT_DRAFT_PARALLEL = "0" }
if (-not $env:WRITING_AGENT_RAG_ENABLED) { $env:WRITING_AGENT_RAG_ENABLED = "1" }
if (-not $env:WRITING_AGENT_EMBED_MODEL) { $env:WRITING_AGENT_EMBED_MODEL = "bge-m3:latest" }
if (-not $env:WRITING_AGENT_RAG_MAX_CHARS) { $env:WRITING_AGENT_RAG_MAX_CHARS = "6000" }
if (-not $env:WRITING_AGENT_RAG_TOP_K) { $env:WRITING_AGENT_RAG_TOP_K = "8" }
if (-not $env:WRITING_AGENT_RAG_PER_PAPER) { $env:WRITING_AGENT_RAG_PER_PAPER = "3" }
if (-not $env:WRITING_AGENT_EVIDENCE_ENABLED) { $env:WRITING_AGENT_EVIDENCE_ENABLED = "0" }
if (-not $env:WRITING_AGENT_VALIDATE_PLAN) { $env:WRITING_AGENT_VALIDATE_PLAN = "0" }
if (-not $env:WRITING_AGENT_ENSURE_MIN_LENGTH) { $env:WRITING_AGENT_ENSURE_MIN_LENGTH = "1" }
if (-not $env:WRITING_AGENT_SECTION_CONTINUE_ROUNDS) { $env:WRITING_AGENT_SECTION_CONTINUE_ROUNDS = "0" }
if (-not $env:WRITING_AGENT_SECTION_RETRIES) { $env:WRITING_AGENT_SECTION_RETRIES = "2" }
if (-not $env:WRITING_AGENT_SECTION_TIMEOUT_S) { $env:WRITING_AGENT_SECTION_TIMEOUT_S = "60" }
if (-not $env:WRITING_AGENT_FAST_DRAFT) { $env:WRITING_AGENT_FAST_DRAFT = "0" }
if (-not $env:WRITING_AGENT_STRIP_FILLER) { $env:WRITING_AGENT_STRIP_FILLER = "1" }
if (-not $env:WRITING_AGENT_TARGET_TOTAL_CHARS) { $env:WRITING_AGENT_TARGET_TOTAL_CHARS = "8000" }
if (-not $env:WRITING_AGENT_MAX_TOKENS) { $env:WRITING_AGENT_MAX_TOKENS = "200" }
if (-not $env:WRITING_AGENT_OLLAMA_RETRIES) { $env:WRITING_AGENT_OLLAMA_RETRIES = "3" }
if (-not $env:WRITING_AGENT_OLLAMA_RETRY_BACKOFF_S) { $env:WRITING_AGENT_OLLAMA_RETRY_BACKOFF_S = "1.5" }

if (-not (Test-Path ".venv\\Scripts\\python.exe")) {
  throw "Virtualenv not found. Run without -SkipInstall first."
}

.\\.venv\\Scripts\\python -m writing_agent.desktop_app
