param(
    [int]$Port = 5000,
    [string]$BindHost = '127.0.0.1'
)

$ErrorActionPreference = 'Continue'
$Url = "http://$BindHost`:$Port"

$listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listen) {
    Write-Host 'Listening:'
    $listen | Select-Object LocalAddress,LocalPort,OwningProcess,State | Format-Table -AutoSize
} else {
    Write-Host "Nothing is listening on port $Port"
}

try {
    $resp = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 8
    Write-Host "HTTP OK: $($resp.StatusCode) $Url"
} catch {
    Write-Host "HTTP check failed: $($_.Exception.Message)"
    exit 1
}
