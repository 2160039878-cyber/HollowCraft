[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Archive)
. (Join-Path $PSScriptRoot 'HollowCraft.Common.ps1')
$metadata = Read-HcInstallation $Archive -Archived
$lock = Enter-HcLock $metadata.id
try {
    Assert-HcPlainPath $metadata.root
    if (Test-Path -LiteralPath $metadata.root) { throw 'Original installation path is occupied; preserving both directories.' }
    if (Get-Item -LiteralPath $metadata.profileLink -Force -ErrorAction SilentlyContinue) { throw 'Profile path is occupied; preserving it.' }
    if (Get-Item -LiteralPath (Get-HcLaunchLink $metadata) -Force -ErrorAction SilentlyContinue) { throw 'Launch link is occupied; preserving it.' }
    $parent = [IO.Path]::GetDirectoryName($metadata.archivePath)
    Set-Location -LiteralPath $parent
    [Environment]::CurrentDirectory = $parent
    [IO.Directory]::Move($metadata.archivePath,$metadata.root)
    $profileCreated=$false
    try { New-HcProfileLink $metadata; $profileCreated=$true; New-HcLaunchLink $metadata }
    catch {
        if ($profileCreated) { Remove-HcProfileLink $metadata }
        [IO.Directory]::Move($metadata.root,$metadata.archivePath); throw
    }
    Write-Output "Restored: $($metadata.root)"
} finally { $lock.ReleaseMutex(); $lock.Dispose() }
