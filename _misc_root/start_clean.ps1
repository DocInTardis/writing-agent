Param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8000,
  [int]$PortTries = 10,
  [switch]$SkipInstall,
  [switch]$SkipPull
)

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

function Stop-ListeningProcess {
  param([int]$Port)
  $lines = netstat -aon | Select-String -Pattern ":$Port\s+LISTENING"
  foreach ($line in $lines) {
    $parts = $line -split "\s+"
    $pid = $parts[-1]
    if ($pid -match "^\d+$") {
      try {
        Stop-Process -Id $pid -Force -ErrorAction Stop
        Write-Host "Stopped PID $pid listening on port $Port"
      } catch {
        Write-Host "Failed to stop PID $pid on port $Port"
      }
    }
  }
}

# Stop listeners on target ports (8000..)
for ($i = 0; $i -lt $PortTries; $i++) {
  Stop-ListeningProcess -Port ($Port + $i)
}

# Stop stale python/uvicorn that mention writing_agent
Get-Process | Where-Object { $_.ProcessName -in @("python","uvicorn") } | ForEach-Object {
  try {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
    if ($cmd -and ($cmd -like "*writing_agent*")) {
      Stop-Process -Id $_.Id -Force -ErrorAction Stop
      Write-Host "Stopped PID $($_.Id) ($($_.ProcessName))"
    }
  } catch {}
}

# Start normally
$argList = @("-HostAddress", $HostAddress, "-Port", $Port)
if ($SkipInstall) { $argList += "-SkipInstall" }
if ($SkipPull) { $argList += "-SkipPull" }

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot\start.ps1" @argList
