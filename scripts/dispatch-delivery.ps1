$ErrorActionPreference = "Stop"

$repo = "jmarcilio-tech/twilio-dashboard"
$eventType = "delivery_tick"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$logDir = Join-Path $repoRoot "logs"
if (-not (Test-Path $logDir)) {
  New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$logPath = Join-Path $logDir "dispatch-delivery.log"
$now = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")

function Send-Dispatch {
  $dispatchSecret = $env:TWILIO_REPO_DISPATCH_SECRET
  if ($dispatchSecret) {
    $bodyObj = @{
      event_type      = $eventType
      client_payload  = @{ token = $dispatchSecret }
    }
    $jsonBody = $bodyObj | ConvertTo-Json -Compress -Depth 5
    $jsonBody | gh api "repos/$repo/dispatches" --method POST --input -
  }
  else {
    gh api "repos/$repo/dispatches" -X POST -f "event_type=$eventType" | Out-Null
  }
}

try {
  Send-Dispatch
  Add-Content -Path $logPath -Value "$now | OK | repository_dispatch ($eventType)"
}
catch {
  Add-Content -Path $logPath -Value "$now | ERRO | $($_.Exception.Message)"
  throw
}
