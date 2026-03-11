param(
    [string]$Source = 'D:\cloud_storage',
    [string]$WslTarget = '/home/chenrunsen/storage/ext4-cloud-storage',
    [string]$Distro = 'Ubuntu'
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $Source)) {
    throw "Source path not found: $Source"
}

Write-Host "[1/4] Ensuring WSL target exists: $WslTarget"
wsl -d $Distro -e bash -lc "mkdir -p '$WslTarget'"

Write-Host "[2/4] Copying data from Windows to WSL target"
wsl -d $Distro -e bash -lc "rsync -a --info=progress2 '/mnt/d/cloud_storage/' '$WslTarget/'"

Write-Host "[3/4] Generating file counts"
$srcCount = (Get-ChildItem $Source -Recurse -Force -File | Measure-Object).Count
$dstCountRaw = wsl -d $Distro -e bash -lc "find '$WslTarget' -type f | wc -l"
$dstCount = [int]($dstCountRaw | Select-Object -Last 1)

Write-Host "Source file count: $srcCount"
Write-Host "Target file count: $dstCount"

if ($srcCount -ne $dstCount) {
    Write-Warning 'File counts differ. Review before switching Home-Cloud to the new storage path.'
    exit 1
}

Write-Host "[4/4] Done. Next step is to point BASE_STORAGE_PATH to the mounted ext4 target and re-test."
