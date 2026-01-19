Param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8000,
  [string]$Model = "qwen:7b",
  [string]$OllamaHost = "http://127.0.0.1:11434",
  [string]$IndexUrl = "",
  [switch]$SkipInstall,
  [switch]$SkipPull,
  [switch]$NoWeb
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

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
  throw "ollama not found. Please install Ollama and add it to PATH."
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
  Write-Host "Starting Ollama service (ollama serve) ..."
  Start-Process -WindowStyle Hidden -FilePath "ollama" -ArgumentList "serve"
  Start-Sleep -Milliseconds 800
}

if (-not $SkipPull) {
  $hasModel = $false
  try {
    $list = & ollama list 2>$null
    if ($list) {
      $hasModel = [bool]($list | Select-String -SimpleMatch $Model)
    }
  } catch {
    $hasModel = $false
  }

  if (-not $hasModel) {
    Write-Host "Ensuring model is available (ollama pull $Model) ..."
    & ollama pull $Model
  } else {
    Write-Host "Model already available: $Model"
  }
}

$env:WRITING_AGENT_HOST = $HostAddress
$env:WRITING_AGENT_PORT = "$Port"
$env:WRITING_AGENT_USE_OLLAMA = "1"
if (-not $env:WRITING_AGENT_WORKERS) { $env:WRITING_AGENT_WORKERS = "4" }

if ($NoWeb) {
  Write-Host "Setup complete. (NoWeb set; not starting the app.)"
  exit 0
}

if (-not (Test-Path ".venv\\Scripts\\python.exe")) {
  throw "Virtualenv not found. Run without -SkipInstall first."
}

.\\.venv\\Scripts\\python -m writing_agent.launch
