param(
    [int]$Port = 5000
)

$ErrorActionPreference = 'SilentlyContinue'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $ProjectRoot 'home-cloud.pid'

$stopped = $false
if (Test-Path $PidFile) {
    $pid = Get-Content $PidFile | Select-Object -First 1
    if ($pid) {
        Stop-Process -Id ([int]$pid) -Force
        $stopped = $true
    }
    Remove-Item $PidFile -Force
}

Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object {
        Stop-Process -Id $_ -Force
        $stopped = $true
    }

if ($stopped) {
    Write-Host "Stopped Home-Cloud process(es) on port $Port."
} else {
    Write-Host "No running Home-Cloud process found on port $Port."
}
