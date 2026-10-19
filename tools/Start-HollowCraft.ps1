[CmdletBinding()]
param(
    [string]$Project = (Split-Path -Parent $PSScriptRoot),
    [Parameter(Mandatory=$true)][string]$Game
)
$ErrorActionPreference = 'Stop'
$hcProject = (Resolve-Path -LiteralPath $Project).Path
$hcGame = (Resolve-Path -LiteralPath $Game).Path
$hcExe = Join-Path $hcGame 'hollow_knight.exe'
$hcBackend = Join-Path $hcProject 'tools/Start-DevMinecraft.ps1'
foreach ($hcFile in @($hcExe, $hcBackend, (Join-Path $hcGame '.hollowcraft-managed'),
    (Join-Path $hcGame 'hollow_knight_Data/Managed/Mods/HollowCraft/HollowCraft.dll'))) {
    if (-not (Test-Path -LiteralPath $hcFile -PathType Leaf)) { throw "Missing HollowCraft file: $hcFile" }
}
$hcProcesses = @(Get-CimInstance Win32_Process -Filter "Name='hollow_knight.exe' OR Name='java.exe'")
if ($hcProcesses | Where-Object { $_.ExecutablePath -eq $hcExe }) {
    throw 'HollowCraft is already running.'
}
$hcExisting = @($hcProcesses | Where-Object { $_.Name -eq 'java.exe' -and $_.CommandLine -and
    $_.CommandLine.Contains($hcProject) -and $_.CommandLine.Contains('devlaunchinjector') })
if ($hcExisting.Count -gt 1) { throw 'More than one HollowCraft backend is running.' }
$hcShell = (Get-Command pwsh.exe -ErrorAction Stop).Source
$hcLogs = Join-Path (Split-Path -Parent $hcGame) 'logs'
[void][IO.Directory]::CreateDirectory($hcLogs)
$hcStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$env:HOLLOWCRAFT_TEST_MODE = '0'
Remove-Item Env:HOLLOWCRAFT_TEST_PROFILE -ErrorAction SilentlyContinue
if ($hcExisting.Count -eq 1) { $hcBackendPid = $hcExisting[0].ProcessId }
else {
    $hcChild = Start-Process -FilePath $hcShell -WindowStyle Hidden -WorkingDirectory $hcProject -PassThru `
        -ArgumentList @('-NoLogo', '-NoProfile', '-File', ('"' + $hcBackend + '"')) `
        -RedirectStandardOutput (Join-Path $hcLogs "minecraft-$hcStamp.log") `
        -RedirectStandardError (Join-Path $hcLogs "minecraft-$hcStamp.err.log")
    $hcBackendPid = $hcChild.Id
}
$hcHost = Start-Process -FilePath $hcExe -WorkingDirectory $hcGame -PassThru `
    -ArgumentList @('-logFile', ('"' + (Join-Path $hcLogs "host-$hcStamp.log") + '"'))
Write-Output "HollowCraft started: game PID $($hcHost.Id), backend PID $hcBackendPid. Logs: $hcLogs"
