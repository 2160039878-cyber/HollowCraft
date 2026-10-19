[CmdletBinding()]
param(
    [string]$Root,
    [switch]$Background,
    [ValidateRange(0,4)][int]$TestProfile = 0
)
if (!$Root) { $Root = Split-Path -Parent $PSScriptRoot }
. (Join-Path $PSScriptRoot 'HollowCraft.Common.ps1')
if ($TestProfile -and !$Background) { throw 'TestProfile requires Background mode.' }
$metadata = Read-HcInstallation $Root
$Root = $metadata.root
$lock = Enter-HcLock $metadata.id
$backend = $null; $gameProcess = $null; $outputFile = $null; $errorFile = $null; $backgroundHost = $null
try {
    Assert-HcStopped $metadata
    Assert-HcProfileLink $metadata
    Assert-HcLaunchLink $metadata
    foreach ($entry in $metadata.criticalFiles.PSObject.Properties) {
        $file = Get-HcChild $Root $entry.Name
        Assert-HcPlainPath $file
        if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ine $entry.Value) { throw "Installed file changed: $($entry.Name)" }
    }
    if ($Background) {
        # A fresh profile otherwise waits for language confirmation before the mod can initialize.
        $preferences=[Microsoft.Win32.Registry]::CurrentUser.CreateSubKey(('Software\HC-'+$metadata.id.Substring(0,8)+'\HollowCraftHK'))
        try {
            if ($null -eq $preferences.GetValue('GameLangSet_h1172976845',$null)) {
                $preferences.SetValue('GameLangSet_h1172976845',1,[Microsoft.Win32.RegistryValueKind]::DWord)
            }
        } finally { $preferences.Dispose() }
    }
    $runtimeRoot = Get-HcChild $Root 'runtime'
    $runtime = Read-HcJson (Get-HcChild $runtimeRoot 'runtime.json')
    if ($runtime.schema -ne 1 -or $runtime.mainClass -ne 'net.fabricmc.devlaunchinjector.Main') { throw 'Unsupported runtime metadata.' }
    $run = Get-HcChild $Root 'run'
    $logs = Get-HcChild $Root 'logs'
    $gameDirectory = Get-HcChild $Root 'data/minecraft'
    $temporary = Get-HcChild $Root 'data/temp'
    foreach ($directory in @($run,$logs,$gameDirectory,$temporary)) { Assert-HcPlainPath $directory; [void][IO.Directory]::CreateDirectory($directory) }
    $link = 'Local\HollowCraft_'+$metadata.id
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmssfff'
    $config = New-Object 'System.Collections.Generic.List[string]'
    $config.Add('commonProperties')
    foreach ($entry in $runtime.properties.PSObject.Properties) { $config.Add("`t$($entry.Name)=$($entry.Value)") }
    $config.Add("`tlog4j.configurationFile="+(Get-HcChild $runtimeRoot 'minecraft/log4j.xml'))
    $config.Add("`tfabric.gameJarPath="+(Get-HcChild $runtimeRoot $runtime.commonJar))
    $config.Add("`tfabric.classPathGroups="+(Get-HcChild $runtimeRoot $runtime.modJar))
    $config.Add('clientArgs'); $config.Add("`t--assetIndex"); $config.Add("`t"+$runtime.assetIndex)
    $config.Add("`t--assetsDir"); $config.Add("`t"+(Get-HcChild $runtimeRoot 'minecraft/assets'))
    $config.Add('clientProperties'); $config.Add("`tfabric.gameJarPath.client="+(Get-HcChild $runtimeRoot $runtime.clientJar))
    $configPath = Join-Path $run 'launch.cfg'
    [IO.File]::WriteAllLines($configPath,$config,$script:HcUtf8)
    $classpath = @($runtime.classpath | ForEach-Object { Get-HcChild $runtimeRoot $_ }) -join ';'
    $javaArguments = @('-Xmx6G','-XX:+UseZGC','-XX:SoftMaxHeapSize=3G','-XX:StackShadowPages=32',
        '--sun-misc-unsafe-memory-access=allow','--enable-native-access=ALL-UNNAMED',
        '-Dhollowcraft.startHidden=true','-Dhollowcraft.quitWithHost=true',('-Dhollowcraft.link='+$link),
        ('-Dhollowcraft.profile='+(Get-HcChild $Root 'data/profile')),('-Djava.io.tmpdir='+$temporary),
        ('-Dfabric.dli.config='+$configPath),'-Dfabric.dli.env=client','-Dfabric.dli.main=net.fabricmc.loader.impl.launch.knot.KnotClient',
        '-Xlog:gc:file=hollowcraft-gc.log:time,uptime:filecount=3,filesize=10M')
    if ($Background) { $javaArguments += '-Dhollowcraft.testMode=true' }
    $javaArguments += @('-classpath',$classpath,$runtime.mainClass,'--username','Steve','--gameDir',$gameDirectory)
    $quoted = @($javaArguments | ForEach-Object {
        if ($_ -match '["\r\n\x00]' -or $_.EndsWith('\')) { throw 'Invalid Java argument.' }
        '"'+$_+'"'
    })
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = Get-HcChild $runtimeRoot 'java/bin/java.exe'
    $start.WorkingDirectory = $gameDirectory
    # CreateProcessW preserves Unicode paths; the Windows Java argfile parser uses the native code page.
    $start.Arguments = $quoted -join ' '
    if ($start.Arguments.Length+$start.FileName.Length+4 -ge 32767) { throw 'Installation path is too long for the Windows Java command line.' }
    $start.UseShellExecute = $false; $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true; $start.RedirectStandardError = $true
    foreach ($name in @('JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS','CLASSPATH')) { $start.EnvironmentVariables.Remove($name) }
    $backend = [Diagnostics.Process]::Start($start)
    $outputFile = [IO.File]::Open((Join-Path $logs "minecraft-$stamp.log"),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    $errorFile = [IO.File]::Open((Join-Path $logs "minecraft-$stamp.err.log"),[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    $outputCopy = $backend.StandardOutput.BaseStream.CopyToAsync($outputFile)
    $errorCopy = $backend.StandardError.BaseStream.CopyToAsync($errorFile)
    $hostStart = New-Object Diagnostics.ProcessStartInfo
    $hostStart.FileName = Get-HcChild (Get-HcLaunchLink $metadata) 'hollow_knight.exe'
    $hostStart.WorkingDirectory = Get-HcLaunchLink $metadata
    $hostStart.UseShellExecute = $false; $hostStart.CreateNoWindow = $true
    $hostStart.EnvironmentVariables['HOLLOWCRAFT_LINK'] = $link
    $hostStart.EnvironmentVariables.Remove('HOLLOWCRAFT_TEST_PROFILE')
    $hostArguments = @('-logFile',(Join-Path $logs "host-$stamp.log"))
    if ($Background) {
        $hostStart.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
        $hostArguments += @('-batchmode','-screen-fullscreen','0','-screen-width','1920','-screen-height','1080','-hollowcraft-test','-hollowcraft-background')
        if ($TestProfile) { $hostStart.EnvironmentVariables['HOLLOWCRAFT_TEST_PROFILE'] = [string]$TestProfile }
    }
    $hostStart.Arguments = (@($hostArguments | ForEach-Object { '"'+$_+'"' }) -join ' ')
    if ($Background) {
        $backgroundHost = Start-HcBackgroundProcess $hostStart $temporary
        $gameProcess = $backgroundHost.Process
    } else { $gameProcess = [Diagnostics.Process]::Start($hostStart) }
    $session = [ordered]@{installId=$metadata.id;started=[DateTime]::UtcNow.ToString('o');launcherPid=$PID;
        hostPid=$gameProcess.Id;backendPid=$backend.Id;status='running';background=[bool]$Background;
        backgroundDesktop=if ($backgroundHost) { $backgroundHost.DesktopName } else { $null };
        hostThreadId=if ($backgroundHost) { $backgroundHost.ThreadId } else { $null };
        hostExitCode=$null;backendExitCode=$null;forcedBackendStop=$false}
    Write-HcJson (Join-Path $run 'session.json') $session
    $reportedBackend = $false
    while (!$gameProcess.HasExited) {
        if (!$reportedBackend -and $backend.HasExited) {
            $reportedBackend = $true; $session.status='backend-exited'; $session.backendExitCode=$backend.ExitCode
            Write-HcJson (Join-Path $run 'session.json') $session
        }
        [void]$gameProcess.WaitForExit(1000)
    }
    if (!$backend.WaitForExit(15000)) { $session.forcedBackendStop=$true; $backend.Kill(); $backend.WaitForExit() }
    [Threading.Tasks.Task]::WaitAll(@($outputCopy,$errorCopy))
    $session.status='stopped'; $session.hostExitCode=$gameProcess.ExitCode; $session.backendExitCode=$backend.ExitCode
    Write-HcJson (Join-Path $run 'session.json') $session
} finally {
    if ($backend -and !$gameProcess -and !$backend.HasExited) { $backend.Kill(); $backend.WaitForExit() }
    if ($outputFile) { $outputFile.Dispose() }; if ($errorFile) { $errorFile.Dispose() }
    if ($backgroundHost) { $backgroundHost.Dispose() }
    $lock.ReleaseMutex(); $lock.Dispose()
}
