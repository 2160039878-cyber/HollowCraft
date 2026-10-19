#Requires -Version 7.4
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$HollowCraftDll,
    [Parameter(Mandatory=$true)][string]$MinecraftClientJar
)
$ErrorActionPreference='Stop'
$destination=Join-Path (Split-Path -Parent $PSScriptRoot) 'assets/steve'
$dll=(Resolve-Path -LiteralPath $HollowCraftDll).Path
$jar=(Resolve-Path -LiteralPath $MinecraftClientJar).Path
function Write-LocalTexture([string]$Name,[byte[]]$Bytes) {
    if($Name -notmatch '^(steve|diamond_sword|void-hand-0[6-9]|void-hand-10)\.png$'){throw 'Unexpected texture name'}
    if($Bytes.Length -lt 8 -or [Convert]::ToHexString($Bytes[0..7]) -ne '89504E470D0A1A0A'){throw ('Invalid PNG: '+$Name)}
    $path=Join-Path $destination $Name
    $hash=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes))
    if(Test-Path -LiteralPath $path) {
        if((Get-FileHash -LiteralPath $path).Hash -ne $hash){throw ('Refusing to overwrite a different texture: '+$path)}
        return
    }
    [IO.File]::WriteAllBytes($path,$Bytes)
}
# Read embedded resources only; no game types are instantiated and no game process is launched.
$assembly=[Reflection.Assembly]::LoadFile($dll)
foreach($name in @('steve.png','void-hand-06.png','void-hand-07.png','void-hand-08.png','void-hand-09.png','void-hand-10.png')) {
    $stream=$assembly.GetManifestResourceStream('HollowCraft.Steve.'+$name)
    if($null -eq $stream){throw ('Missing local resource '+$name+'; use the matching HollowCraft build.')}
    $buffer=[IO.MemoryStream]::new()
    try {$stream.CopyTo($buffer); Write-LocalTexture $name $buffer.ToArray()}
    finally {$stream.Dispose();$buffer.Dispose()}
}
$archive=[IO.Compression.ZipFile]::OpenRead($jar)
try {
    $entry=$archive.GetEntry('assets/minecraft/textures/item/diamond_sword.png')
    if($null -eq $entry){throw 'This JAR does not contain the Minecraft client textures.'}
    $stream=$entry.Open();$buffer=[IO.MemoryStream]::new()
    try {$stream.CopyTo($buffer);Write-LocalTexture 'diamond_sword.png' $buffer.ToArray()}
    finally {$stream.Dispose();$buffer.Dispose()}
} finally {$archive.Dispose()}
Write-Output 'Imported seven local textures. They remain ignored by Git.'
