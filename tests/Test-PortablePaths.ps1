[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Work)
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'tools/portable/HollowCraft.Common.ps1')
$Work = Get-HcLocalPath $Work
if (Test-Path -LiteralPath $Work) { throw 'Test directory must be new.' }
[void][IO.Directory]::CreateDirectory($Work)
$blocked = 0
foreach ($relative in @('../outside','x/../../outside','C:\outside','a:stream','.. /outside','x./file','NUL.txt','CON','a\..\b')) {
    $rejected=$false
    try { [void](Get-HcChild $Work $relative) } catch { $rejected=$true }
    if (!$rejected) { throw "Unsafe path accepted: $relative" }; $blocked++
}
foreach ($path in @('C:','\relative','\\server\share\folder','C:\')) {
    $rejected=$false
    try { [void](Get-HcLocalPath $path) } catch { $rejected=$true }
    if (!$rejected) { throw "Unsafe root accepted: $path" }; $blocked++
}
$id=[Guid]::NewGuid().ToString('N')
$metadata=[pscustomobject]@{id=$id;root=$Work;profileLink=(Get-HcProfileLink $id)}
$data=Get-HcChild $Work 'data/profile'
[void][IO.Directory]::CreateDirectory($data)
$sentinel=Join-Path $data 'sentinel.txt'
[IO.File]::WriteAllText($sentinel,'preserved')
$game=Get-HcChild $Work 'game';[void][IO.Directory]::CreateDirectory($game)
[IO.File]::WriteAllText((Join-Path $game 'sentinel.txt'),'preserved')
New-HcLaunchLink $metadata
Assert-HcLaunchLink $metadata
Remove-HcLaunchLink $metadata
if ([IO.File]::ReadAllText((Join-Path $game 'sentinel.txt')) -ne 'preserved') { throw 'Removing launch link touched the game.' }
New-HcProfileLink $metadata
Assert-HcProfileLink $metadata
Remove-HcProfileLink $metadata
if (![IO.File]::Exists($sentinel) -or [IO.File]::ReadAllText($sentinel) -ne 'preserved') { throw 'Removing the junction touched its target.' }
$other=Get-HcChild $Work 'other';[void][IO.Directory]::CreateDirectory($other)
[void](New-Item -ItemType Junction -Path $metadata.profileLink -Target $other)
$rejected=$false
try { Remove-HcProfileLink $metadata } catch { $rejected=$true }
if (!$rejected) { throw 'A substituted profile link was removed.' }
$item=Get-Item -LiteralPath $metadata.profileLink -Force
$targets=@($item.Target)
if ($item.LinkType -ne 'Junction' -or (Get-HcLocalPath $targets[0]) -ine $other) { throw 'Unexpected fixture link; preserve it.' }
[IO.Directory]::Delete($metadata.profileLink)
[IO.Directory]::Delete([IO.Path]::GetDirectoryName($metadata.profileLink))
$report=[ordered]@{passed=$true;blockedPaths=$blocked;junctionTargetPreserved=$true;substitutedLinkRejected=$true;powerShell=$PSVersionTable.PSVersion.ToString()}
Write-HcJson (Join-Path $Work 'result.json') $report
Write-HcJson (Join-Path $Work 'result.json') $report
if (!(Read-HcJson (Join-Path $Work 'result.json')).passed) { throw 'Atomic metadata replacement failed.' }
$report | ConvertTo-Json
