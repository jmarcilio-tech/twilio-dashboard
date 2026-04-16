$ErrorActionPreference = "Stop"

$repo = "jmarcilio-tech/twilio-dashboard"
$workflowRef = "delivery-only.yml"
$maxLagMinutes = 12
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$logDir = Join-Path $repoRoot "logs"
if (-not (Test-Path $logDir)) {
  New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$logPath = Join-Path $logDir "dispatch-delivery-watchdog.log"
$now = Get-Date

function Write-Log($msg) {
  $stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
  Add-Content -Path $logPath -Value "$stamp | $msg"
}

function Invoke-DeliveryDispatch {
  & (Join-Path $scriptDir "dispatch-delivery.ps1")
}

try {
  $json = gh run list --repo $repo --workflow $workflowRef --limit 1 --json event,createdAt,status,displayTitle,databaseId 2>$null
  if (-not $json) {
    Invoke-DeliveryDispatch
    Write-Log "WARN | Nenhum run encontrado; dispatch enviado."
    exit 0
  }

  $runs = $json | ConvertFrom-Json
  if (-not $runs -or $runs.Count -eq 0) {
    Invoke-DeliveryDispatch
    Write-Log "WARN | Lista vazia de runs; dispatch enviado."
    exit 0
  }

  $last = $runs[0]
  $createdAt = [DateTime]::Parse($last.createdAt).ToUniversalTime()
  $lag = ($now.ToUniversalTime() - $createdAt).TotalMinutes

  if ($lag -gt $maxLagMinutes) {
    Invoke-DeliveryDispatch
    Write-Log "WARN | Último run id=$($last.databaseId) com atraso de $([Math]::Round($lag, 2)) min; dispatch enviado."
  }
  else {
    Write-Log "OK | Último run id=$($last.databaseId), status=$($last.status), lag=$([Math]::Round($lag, 2)) min; sem ação."
  }
}
catch {
  Write-Log "ERRO | $($_.Exception.Message)"
  throw
}
