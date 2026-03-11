param(
    [int]$Port = 5000,
    [string]$BindHost = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot '.venv_win313\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    throw "Python venv not found: $Python"
}

$env:APP_CONFIG = 'production'
$env:USE_HTTPS = '0'
$env:SERVER_HOST = $BindHost
$env:SERVER_PORT = "$Port"

$Existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($Existing) {
    Write-Host "Port $Port already listening."
    $Existing | Select-Object LocalAddress,LocalPort,OwningProcess,State
    exit 0
}

$LogDir = Join-Path $ProjectRoot 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$StdOut = Join-Path $LogDir 'home-cloud.stdout.log'
$StdErr = Join-Path $LogDir 'home-cloud.stderr.log'
$PidFile = Join-Path $ProjectRoot 'home-cloud.pid'

$proc = Start-Process -FilePath $Python -ArgumentList 'main.py' -WorkingDirectory $ProjectRoot -RedirectStandardOutput $StdOut -RedirectStandardError $StdErr -PassThru -WindowStyle Hidden
$proc.Id | Set-Content -Path $PidFile -Encoding ascii

Start-Sleep -Seconds 3

try {
    $resp = Invoke-WebRequest -UseBasicParsing ("http://{0}:{1}" -f $BindHost, $Port) -TimeoutSec 8
    Write-Host "Started. PID=$($proc.Id) Status=$($resp.StatusCode) URL=http://$BindHost`:$Port"
} catch {
    Write-Warning "Process started with PID=$($proc.Id), but HTTP probe failed: $($_.Exception.Message)"
    Write-Host "Check logs: $StdOut and $StdErr"
    exit 1
}
