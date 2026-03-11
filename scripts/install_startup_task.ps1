param(
    [string]$TaskName = 'HomeCloudServer-Autostart',
    [string]$ProjectRoot = 'C:\Users\96152\My-Project\Website_Project\Home-Cloud-Server'
)

$ErrorActionPreference = 'Stop'
$StartScript = Join-Path $ProjectRoot 'scripts\start_local.ps1'
if (-not (Test-Path $StartScript)) {
    throw "Start script not found: $StartScript"
}

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description 'Auto start Home-Cloud local server at logon' -Force | Out-Null
Write-Host "Scheduled task installed: $TaskName"
