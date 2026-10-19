[CmdletBinding()]
param(
    [string]$PackageRoot,
    [string]$GameSource,
    [string]$Destination = 'D:\HollowCraft\Standalone'
)
if (!$PackageRoot) { $PackageRoot = Split-Path -Parent $PSScriptRoot }
. (Join-Path $PSScriptRoot 'HollowCraft.Common.ps1')
$PackageRoot = Get-HcLocalPath $PackageRoot
$Destination = Get-HcLocalPath $Destination
Assert-HcPlainPath $PackageRoot
Assert-HcPlainPath $Destination
$package = Read-HcJson (Get-HcChild $PackageRoot 'package.json')
if ($package.schema -ne 1 -or $package.gameVersion -ne '1.5.12620' -or $package.protocol -ne 24) { throw 'Unsupported installation package.' }
if (!$GameSource) { $GameSource = $package.defaultGameSource }
$GameSource = Get-HcLocalPath $GameSource
Assert-HcPlainPath $GameSource
if (Get-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue) { throw 'Destination already exists; use a new directory.' }
foreach ($path in @($GameSource,$PackageRoot)) {
    if (($Destination+'\').StartsWith($path+'\',[StringComparison]::OrdinalIgnoreCase) -or
        ($path+'\').StartsWith($Destination+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Source, package and destination must be separate.' }
}
$basePath = Get-HcChild $PackageRoot 'base-game.json'
if ((Get-FileHash -LiteralPath $basePath -Algorithm SHA256).Hash -ine $package.baseManifestSha256) { throw 'Base manifest checksum mismatch.' }
$baseGame = Read-HcJson $basePath
$requiredBytes = [long]$package.payloadBytes + [long]$baseGame.bytes + 2147483648
$drive = New-Object IO.DriveInfo([IO.Path]::GetPathRoot($Destination))
if ($drive.AvailableFreeSpace -lt $requiredBytes) { throw 'Insufficient free space for the independent copy.' }
$id = [Guid]::NewGuid().ToString('N')
$link = Get-HcProfileLink $id
if (Get-Item -LiteralPath $link -Force -ErrorAction SilentlyContinue) { throw 'Profile identity already exists; retry the installation.' }
$staging = $Destination+'.installing-'+$id
Assert-HcPlainPath $staging
if (Test-Path -LiteralPath $staging) { throw 'Staging path already exists.' }
[void][IO.Directory]::CreateDirectory($staging)
$owned = @{}
$copied = 0
foreach ($entry in $baseGame.files.PSObject.Properties) {
    $relative = 'game/'+$entry.Name
    Copy-HcFile (Get-HcChild $GameSource $entry.Name) (Get-HcChild $staging $relative) $entry.Value.sha256
    $owned[$relative] = $entry.Value.sha256
    $copied++
    if ($copied % 250 -eq 0) { Write-Output "Base files copied: $copied" }
}
$copied = 0
foreach ($entry in $package.files.PSObject.Properties) {
    Copy-HcFile (Get-HcChild $PackageRoot ('payload/'+$entry.Name)) (Get-HcChild $staging $entry.Name) $entry.Value.sha256
    $owned[$entry.Name] = $entry.Value.sha256
    $copied++
    if ($copied % 1000 -eq 0) { Write-Output "Package files copied: $copied" }
}
$globalRelative = 'game/hollow_knight_Data/globalgamemanagers'
$globalFile = Get-HcChild $staging $globalRelative
$patch = $package.profilePatch
if ((Get-FileHash -LiteralPath $globalFile -Algorithm SHA256).Hash -ine $patch.sourceSha256) { throw 'Unsupported Unity profile layout.' }
$bytes = [IO.File]::ReadAllBytes($globalFile)
foreach ($replacement in @(
    @{offset=$patch.companyOffset;before='Team Cherry';after=('HC-'+$id.Substring(0,8))},
    @{offset=$patch.productOffset;before='Hollow Knight';after='HollowCraftHK'}
)) {
    $offset = [int]$replacement.offset
    $old = [Text.Encoding]::UTF8.GetBytes($replacement.before)
    $new = [Text.Encoding]::UTF8.GetBytes($replacement.after)
    if ($offset -lt 4 -or $offset+$old.Length -gt $bytes.Length -or $old.Length -ne $new.Length -or
        [BitConverter]::ToInt32($bytes,$offset-4) -ne $old.Length -or
        [Text.Encoding]::UTF8.GetString($bytes,$offset,$old.Length) -cne $replacement.before) { throw 'Unity identity bytes do not match.' }
    [Array]::Copy($new,0,$bytes,$offset,$new.Length)
}
[IO.File]::SetAttributes($globalFile,([IO.File]::GetAttributes($globalFile) -band (-bnot [IO.FileAttributes]::ReadOnly)))
[IO.File]::WriteAllBytes($globalFile,$bytes)
$owned[$globalRelative] = (Get-FileHash -LiteralPath $globalFile -Algorithm SHA256).Hash.ToLowerInvariant()
foreach ($relative in @('data/profile','data/minecraft','data/temp','run','logs')) { [void][IO.Directory]::CreateDirectory((Get-HcChild $staging $relative)) }
$critical = @{}
foreach ($name in $package.criticalFiles) {
    if (!$owned.ContainsKey($name)) { throw "Missing critical file: $name" }
    $critical[$name] = $owned[$name]
}
$metadata = [ordered]@{schema=1;id=$id;status='ready';root=$Destination;archivePath=$null;
    profileLink=$link;company=('HC-'+$id.Substring(0,8));product='HollowCraftHK';
    created=[DateTime]::UtcNow.ToString('o');gameVersion=$package.gameVersion;protocol=$package.protocol;
    packageSha256=(Get-FileHash -LiteralPath (Get-HcChild $PackageRoot 'package.json') -Algorithm SHA256).Hash.ToLowerInvariant();
    criticalFiles=$critical;ownedFiles=$owned}
Write-HcJson (Get-HcChild $staging '.hollowcraft-install.json') $metadata
if (Test-Path -LiteralPath $Destination) { throw 'Destination became occupied; staged files are preserved.' }
[IO.Directory]::Move($staging,$Destination)
$profileCreated=$false
try { New-HcProfileLink $metadata; $profileCreated=$true; New-HcLaunchLink $metadata }
catch {
    if ($profileCreated) { Remove-HcProfileLink $metadata }
    [IO.Directory]::Move($Destination,$staging); throw
}
Write-Output "Installed: $Destination"
Write-Output "Start: $(Join-Path $Destination 'Start-HollowCraft.cmd')"
