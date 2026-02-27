$target = "TASKS_CN.md"
$text = Get-Clipboard -Raw
if ([string]::IsNullOrWhiteSpace($text)) {
  Write-Host "Clipboard is empty. Copy the Chinese content first."
  exit 1
}
$enc = New-Object System.Text.UTF8Encoding($true)
[System.IO.File]::WriteAllText($target, $text, $enc)
Write-Host "Wrote $target"
# self-delete
$me = $PSCommandPath
Start-Sleep -Milliseconds 200
Remove-Item -LiteralPath $me -Force
