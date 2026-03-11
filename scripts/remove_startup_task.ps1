param(
    [string]$TaskName = 'HomeCloudServer-Autostart'
)

$ErrorActionPreference = 'Continue'
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Scheduled task removed: $TaskName"
