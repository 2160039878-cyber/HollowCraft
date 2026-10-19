[CmdletBinding()]
param(
    [string]$Jdk = $env:JAVA_HOME,
    [string]$GradleCache = $env:GRADLE_USER_HOME,
    [switch]$TestMode,
    [switch]$Offline
)
$ErrorActionPreference = 'Stop'
$hcProject = Split-Path -Parent $PSScriptRoot
$hcMinecraft = Join-Path $hcProject 'minecraft'
if([string]::IsNullOrWhiteSpace($Jdk)){throw 'Set JAVA_HOME to JDK 25, or pass -Jdk.'}
foreach ($hcFile in @((Join-Path $Jdk 'bin/java.exe'), (Join-Path $hcMinecraft 'gradlew.bat'))) {
    if (-not (Test-Path -LiteralPath $hcFile)) { throw "Missing development dependency: $hcFile" }
}
$env:JAVA_HOME = $Jdk
if(![string]::IsNullOrWhiteSpace($GradleCache)) {
    [void][IO.Directory]::CreateDirectory($GradleCache)
    $env:GRADLE_USER_HOME = $GradleCache
}
$env:HOLLOWCRAFT_USERNAME = 'Steve'
$env:HOLLOWCRAFT_TEST_MODE = $(if ($TestMode) { '1' } else { '0' })
Push-Location -LiteralPath $hcMinecraft
try {
    $hcArguments=@('--no-daemon','runClient')
    if($Offline){$hcArguments=@('--offline')+$hcArguments}
    & './gradlew.bat' @hcArguments
    exit $LASTEXITCODE
}
finally { Pop-Location }
