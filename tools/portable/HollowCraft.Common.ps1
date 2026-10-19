Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:HcUtf8 = New-Object System.Text.UTF8Encoding($false)
if ($PSVersionTable.PSEdition -eq 'Desktop') { $env:PSModulePath = Join-Path $PSHOME 'Modules' }
[Console]::OutputEncoding = $script:HcUtf8

function Get-HcLocalPath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path -notmatch '^[A-Za-z]:[\\/]') { throw 'An absolute local path is required.' }
    $value = [IO.Path]::GetFullPath($Path).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $drive = [IO.Path]::GetPathRoot($value)
    if ($value.StartsWith('\\') -or $value.Length -le $drive.Length) { throw 'A local subdirectory is required.' }
    if ($value -match '[. ]([\\/]|$)') { throw 'Ambiguous Windows path.' }
    if ((New-Object IO.DriveInfo($drive)).DriveType -notin @([IO.DriveType]::Fixed,[IO.DriveType]::Removable)) { throw 'Network locations are not supported.' }
    return $value
}

function Assert-HcPlainPath([string]$Path) {
    $cursor = Get-HcLocalPath $Path
    while ($cursor -and $cursor.Length -gt [IO.Path]::GetPathRoot($cursor).Length) {
        $item = Get-Item -LiteralPath $cursor -Force -ErrorAction SilentlyContinue
        if ($item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Unexpected link in installation path: $cursor" }
        $cursor = [IO.Path]::GetDirectoryName($cursor)
    }
}

function Get-HcChild([string]$Root, [string]$Relative) {
    if ([string]::IsNullOrEmpty($Relative) -or [IO.Path]::IsPathRooted($Relative) -or $Relative.Contains(':') -or
        $Relative -match '(^|[\\/])\.{1,2}([\\/]|$)' -or $Relative -match '[*?<>|"]') { throw 'Invalid manifest path.' }
    foreach ($part in ($Relative -split '[\\/]')) {
        if (!$part -or $part -match '[. ]$' -or $part -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])($|\.)') { throw 'Ambiguous Windows filename.' }
    }
    $base = (Get-HcLocalPath $Root) + '\'
    $value = [IO.Path]::GetFullPath([IO.Path]::Combine($base,$Relative.Replace('/','\')))
    if (!$value.StartsWith($base,[StringComparison]::OrdinalIgnoreCase)) { throw 'Manifest path escapes its root.' }
    return $value
}

function Read-HcJson([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Length -gt 16777216 -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Invalid metadata file.' }
    return ([IO.File]::ReadAllText($Path,[Text.Encoding]::UTF8) | ConvertFrom-Json)
}

function Write-HcJson([string]$Path, $Value) {
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path))
    $temporary = $Path + '.tmp'
    [IO.File]::WriteAllText($temporary,($Value | ConvertTo-Json -Depth 16),$script:HcUtf8)
    if ([IO.File]::Exists($Path)) { [IO.File]::Replace($temporary,$Path,[NullString]::Value) }
    else { [IO.File]::Move($temporary,$Path) }
}

function Copy-HcFile([string]$Source,[string]$Target,[string]$Sha256) {
    $item = Get-Item -LiteralPath $Source -Force
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Expected a regular source file.' }
    if ((Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash -ine $Sha256) { throw "Source checksum mismatch: $Source" }
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Target))
    if ([IO.File]::Exists($Target)) {
        [IO.File]::SetAttributes($Target,([IO.File]::GetAttributes($Target) -band (-bnot [IO.FileAttributes]::ReadOnly)))
    }
    [IO.File]::Copy($Source,$Target,$true)
    if ((Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash -ine $Sha256) { throw "Copied checksum mismatch: $Target" }
}

function Get-HcProfileLink([string]$Id) {
    if ($Id -cnotmatch '^[a-f0-9]{32}$') { throw 'Invalid installation identity.' }
    return Join-Path ([Environment]::GetFolderPath('UserProfile')) ('AppData\LocalLow\HC-'+$Id.Substring(0,8)+'\HollowCraftHK')
}

function Assert-HcJunction([string]$Path,[string]$Target) {
    $item = Get-Item -LiteralPath $Path -Force
    $targets = @($item.Target)
    if ($item.LinkType -ne 'Junction' -or $targets.Count -ne 1 -or (Get-HcLocalPath $targets[0]) -ine $Target) {
        throw 'Managed link has changed; preserving it.'
    }
}

function Assert-HcProfileLink($Metadata) {
    $path = Get-HcProfileLink $Metadata.id
    if ($path -ine $Metadata.profileLink) { throw 'Profile identity mismatch.' }
    Assert-HcJunction $path (Get-HcChild $Metadata.root 'data/profile')
}

function Get-HcLaunchLink($Metadata) {
    return Join-Path ([IO.Path]::GetPathRoot((Get-HcLocalPath $Metadata.root))) ('HollowCraftRuntime\'+$Metadata.id)
}

function Assert-HcLaunchLink($Metadata) {
    Assert-HcJunction (Get-HcLaunchLink $Metadata) (Get-HcChild $Metadata.root 'game')
}

function New-HcLaunchLink($Metadata) {
    $path = Get-HcLaunchLink $Metadata
    Assert-HcPlainPath ([IO.Path]::GetDirectoryName($path))
    if (Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue) { throw 'Launch link already exists; preserving it.' }
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path))
    [void](New-Item -ItemType Junction -Path $path -Target (Get-HcChild $Metadata.root 'game'))
    Assert-HcLaunchLink $Metadata
}

function Remove-HcLaunchLink($Metadata) {
    Assert-HcLaunchLink $Metadata
    [IO.Directory]::Delete((Get-HcLaunchLink $Metadata))
}

function New-HcProfileLink($Metadata) {
    $path = Get-HcProfileLink $Metadata.id
    Assert-HcPlainPath ([IO.Path]::GetDirectoryName($path))
    if (Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue) { throw 'Profile path already exists; preserving it.' }
    $target = Get-HcChild $Metadata.root 'data/profile'
    Assert-HcPlainPath $target
    [void][IO.Directory]::CreateDirectory($target)
    [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path))
    [void](New-Item -ItemType Junction -Path $path -Target $target)
    Assert-HcProfileLink $Metadata
}

function Remove-HcProfileLink($Metadata) {
    Assert-HcProfileLink $Metadata
    # Nonrecursive deletion removes only the verified junction, never its target data.
    [IO.Directory]::Delete($Metadata.profileLink)
}

function Read-HcInstallation([string]$Root,[switch]$Archived) {
    $resolved = Get-HcLocalPath $Root
    Assert-HcPlainPath $resolved
    $data = Read-HcJson (Get-HcChild $resolved '.hollowcraft-install.json')
    if ($data.schema -ne 1 -or $data.id -cnotmatch '^[a-f0-9]{32}$' -or
        $data.profileLink -ine (Get-HcProfileLink $data.id)) { throw 'Invalid installation marker.' }
    $original = Get-HcLocalPath $data.root
    if ($Archived) {
        if ($data.status -ne 'ready' -or
            !$resolved.StartsWith($original+'.removed-',[StringComparison]::OrdinalIgnoreCase) -or
            [IO.Path]::GetDirectoryName($original) -ine [IO.Path]::GetDirectoryName($resolved)) { throw 'Invalid archived installation.' }
        $data.archivePath = $resolved
    } elseif ($data.status -ne 'ready' -or $original -ine $resolved) { throw 'Installation is incomplete or moved.' }
    return $data
}

function Enter-HcLock([string]$Id) {
    $mutex = New-Object Threading.Mutex($false,('Local\HollowCraftLauncher_'+$Id))
    try { $acquired = $mutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $acquired = $true }
    if (!$acquired) { $mutex.Dispose(); throw 'This HollowCraft installation is already in use.' }
    return $mutex
}

function Start-HcBackgroundProcess([Diagnostics.ProcessStartInfo]$Info, [string]$TemporaryDirectory) {
    if (!('HollowCraftBackgroundProcess' -as [type])) {
        $previousTemp = $env:TEMP; $previousTmp = $env:TMP
        try {
            $env:TEMP = $TemporaryDirectory; $env:TMP = $TemporaryDirectory
            Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
public sealed class HollowCraftBackgroundProcess : IDisposable {
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    private struct Startup {
        public uint size; public string reserved, desktop, title;
        public uint x,y,width,height,xChars,yChars,fill,flags;
        public ushort show,reservedSize; public IntPtr reservedPointer,input,output,error;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct Started { public IntPtr process,thread; public uint processId,threadId; }
    [DllImport("user32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
    private static extern IntPtr CreateDesktopW(string name,IntPtr device,IntPtr mode,uint flags,uint access,IntPtr security);
    [DllImport("user32.dll",SetLastError=true)] private static extern bool CloseDesktop(IntPtr desktop);
    [DllImport("user32.dll")] private static extern IntPtr GetThreadDesktop(uint thread);
    [DllImport("user32.dll",SetLastError=true)] private static extern bool SetThreadDesktop(IntPtr desktop);
    [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
    private static extern bool CreateProcessW(string file,StringBuilder command,IntPtr processSecurity,IntPtr threadSecurity,
        bool inherit,uint flags,IntPtr environment,string directory,ref Startup startup,out Started result);
    [DllImport("kernel32.dll")] private static extern bool CloseHandle(IntPtr handle);
    private IntPtr desktop;
    public Process Process { get; private set; }
    public string DesktopName { get; private set; }
    public uint ThreadId { get; private set; }
    public static HollowCraftBackgroundProcess Start(ProcessStartInfo info) {
        var result=new HollowCraftBackgroundProcess();
        var originalDesktop=GetThreadDesktop(GetCurrentThreadId());
        result.DesktopName="HollowCraft-"+Guid.NewGuid().ToString("N");
        result.desktop=CreateDesktopW(result.DesktopName,IntPtr.Zero,IntPtr.Zero,0,0x01ff,IntPtr.Zero);
        if(result.desktop==IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
        IntPtr environment=IntPtr.Zero;
        Started started=new Started();
        try {
            if(GetThreadDesktop(GetCurrentThreadId())!=originalDesktop && !SetThreadDesktop(originalDesktop))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            var keys=new string[info.EnvironmentVariables.Count];info.EnvironmentVariables.Keys.CopyTo(keys,0);
            Array.Sort(keys,StringComparer.OrdinalIgnoreCase);
            var values=new StringBuilder();
            foreach(var key in keys) values.Append(key).Append('=').Append(info.EnvironmentVariables[key]).Append('\0');
            values.Append('\0'); environment=Marshal.StringToHGlobalUni(values.ToString());
            var startup=new Startup {size=(uint)Marshal.SizeOf(typeof(Startup)),desktop=result.DesktopName,flags=0x81,show=0};
            var command=new StringBuilder("\""+info.FileName+"\" "+info.Arguments);
            if(!CreateProcessW(info.FileName,command,IntPtr.Zero,IntPtr.Zero,false,0x400,environment,info.WorkingDirectory,ref startup,out started))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            result.Process=Process.GetProcessById((int)started.processId);
            // Open the managed handle before releasing CreateProcess's handles, so ExitCode remains available.
            var managedHandle=result.Process.Handle;
            result.ThreadId=started.threadId;
            return result;
        } catch { result.Dispose(); throw; }
        finally {
            if(environment!=IntPtr.Zero) Marshal.FreeHGlobal(environment);
            if(started.thread!=IntPtr.Zero) CloseHandle(started.thread);
            if(started.process!=IntPtr.Zero) CloseHandle(started.process);
        }
    }
    public void Dispose() {
        if(Process!=null) { Process.Dispose(); Process=null; }
        if(desktop!=IntPtr.Zero) {
            if(!CloseDesktop(desktop)) throw new Win32Exception(Marshal.GetLastWin32Error());
            desktop=IntPtr.Zero;
        }
    }
}
'@
        } finally { $env:TEMP = $previousTemp; $env:TMP = $previousTmp }
    }
    return [HollowCraftBackgroundProcess]::Start($Info)
}

function Assert-HcStopped($Metadata) {
    $executables = @((Get-HcChild $Metadata.root 'game/hollow_knight.exe'),
        (Get-HcChild (Get-HcLaunchLink $Metadata) 'hollow_knight.exe'),
        (Get-HcChild $Metadata.root 'runtime/java/bin/java.exe'),(Get-HcChild $Metadata.root 'runtime/java/bin/javaw.exe'))
    $running = @(Get-CimInstance Win32_Process -Filter "Name='hollow_knight.exe' OR Name='java.exe' OR Name='javaw.exe'" |
        Where-Object { $_.ExecutablePath -and $executables -icontains $_.ExecutablePath })
    if ($running.Count) { throw 'Close this installation before continuing.' }
}
