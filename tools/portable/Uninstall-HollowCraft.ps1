[CmdletBinding()]
param([string]$Root)
if (!$Root) { $Root = Split-Path -Parent $PSScriptRoot }
. (Join-Path $PSScriptRoot 'HollowCraft.Common.ps1')
$metadata = Read-HcInstallation $Root
$lock = Enter-HcLock $metadata.id
try {
    Assert-HcStopped $metadata
    Assert-HcProfileLink $metadata
    Assert-HcLaunchLink $metadata
    $parent = [IO.Path]::GetDirectoryName($metadata.root)
    Set-Location -LiteralPath $parent
    [Environment]::CurrentDirectory = $parent
    $archive = $metadata.root+'.removed-'+(Get-Date -Format 'yyyyMMdd-HHmmssfff')
    Assert-HcPlainPath $archive
    if (Test-Path -LiteralPath $archive) { throw 'Archive already exists; preserving it.' }
    if ([IO.Path]::GetDirectoryName($archive) -ine [IO.Path]::GetDirectoryName($metadata.root)) { throw 'Archive must stay beside the installation.' }
    $profileRemoved=$false; $launchRemoved=$false
    try {
        Remove-HcLaunchLink $metadata; $launchRemoved=$true
        Remove-HcProfileLink $metadata; $profileRemoved=$true
        [IO.Directory]::Move($metadata.root,$archive)
    } catch {
        if ($profileRemoved) { New-HcProfileLink $metadata }
        if ($launchRemoved) { New-HcLaunchLink $metadata }
        throw
    }
    Write-Output "Uninstalled. Files and saves retained in: $archive"
} finally { $lock.ReleaseMutex(); $lock.Dispose() }
