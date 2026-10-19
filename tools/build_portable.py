"""Assemble the local installation kit from verified runtime and game assets."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def build(args):
    project,backend,game,api,cinematics,output=(getattr(args,n).resolve() for n in
        ('project','backend','game_source','api','cinematics','output'))
    assert all(not output.is_relative_to(p) for p in (project,backend,game,api,cinematics))
    origin=dict(schema=1,project=str(project),backendManifest=sha(backend/'manifest.json'),baseManifest=sha(args.base_manifest))
    marker=output/'.hollowcraft-package-build.json'
    if output.exists():assert marker.is_file() and read(marker)==origin,'Refusing to refresh an unknown directory'
    else:output.mkdir(parents=True);write(marker,origin)
    payload=output/'payload';payload.mkdir(exist_ok=True)
    if not (payload/'runtime').exists():shutil.copytree(backend,payload/'runtime')
    runtime=read(payload/'runtime/runtime.json')
    mod=project/'minecraft/build/libs'/Path(runtime['modJar']).name
    shutil.copy2(mod,payload/'runtime'/runtime['modJar'])
    runtime['modSha256']=sha(mod);write(payload/'runtime/runtime.json',runtime)
    runtime_manifest=read(backend/'manifest.json')
    for name in (runtime['modJar'],'runtime.json'):
        p=payload/'runtime'/name;runtime_manifest[name]=dict(bytes=p.stat().st_size,sha256=sha(p))
    write(payload/'runtime/manifest.json',runtime_manifest)
    managed=payload/'game/hollow_knight_Data/Managed';managed.mkdir(parents=True,exist_ok=True)
    for path in api.glob('*.dll'):shutil.copy2(path,managed/path.name)
    (managed/'Mods/HollowCraft').mkdir(parents=True,exist_ok=True)
    shutil.copy2(project/'host/bin/Release/netstandard2.1/HollowCraft.dll',managed/'Mods/HollowCraft/HollowCraft.dll')
    films={}
    for clip in read(args.ledger)['clips']:
        if clip['treatment']!='replace protagonist':continue
        name=clip['clip']+'.mp4';path=cinematics/name
        assert sha(path)==clip['installedSha256'].lower(),name
        target=payload/'game/hollow_knight_Data/StreamingAssets'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,target);films[name]=sha(path)
    assert len(films)==9
    scripts=project/'tools/portable'
    for directory in (payload/'scripts',output/'scripts'):directory.mkdir(exist_ok=True)
    for path in scripts.glob('*.ps1'):
        # Windows PowerShell5.1 needs a BOM for UTF-8 script text.
        text=path.read_text(encoding='utf-8-sig')
        if path.name in ('Install-HollowCraft.ps1','HollowCraft.Common.ps1'):
            (output/'scripts'/path.name).write_text(text,encoding='utf-8-sig')
        if path.name!='Install-HollowCraft.ps1':(payload/'scripts'/path.name).write_text(text,encoding='utf-8-sig')
    shell='"%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"'
    (payload/'Start-HollowCraft.cmd').write_text('@echo off\nstart "" '+shell+' -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0scripts\\Start-HollowCraft.ps1" %*\n',encoding='ascii')
    for action in ('Uninstall','Restore'):
        argument=' -Archive "%~dp0."' if action=='Restore' else ''
        # The launcher exits from the parent directory before the installation is renamed.
        text='@echo off\ncd /d "%~dp0.."\nstart "" '+shell+' -NoProfile -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\\'+action+'-HollowCraft.ps1"'+argument+' %*\n'
        (payload/(action+'-HollowCraft.cmd')).write_text(text,encoding='ascii')
    (output/'Install-HollowCraft.cmd').write_text('@echo off\n'+shell+' -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\\Install-HollowCraft.ps1" %*\npause\n',encoding='ascii')
    shutil.copytree(project/'licenses',payload/'licenses',dirs_exist_ok=True)
    shutil.copy2(project/'LICENSE',payload/'LICENSE');shutil.copy2(project/'THIRD-PARTY-NOTICES.md',payload/'THIRD-PARTY-NOTICES.md')
    base=read(args.base_manifest)
    assert base['version']=='1.5.12620'
    base['bytes']=sum(v['bytes'] for v in base['files'].values());write(output/'base-game.json',base)
    original=game/'hollow_knight_Data/globalgamemanagers';data=original.read_bytes()
    assert sha(original)==base['files']['hollow_knight_Data/globalgamemanagers']['sha256']
    # The supported1.5.12620 PlayerSettings stores these consecutive, length-prefixed UTF-8 strings.
    assert data[1560:1571]==b'Team Cherry' and data[1576:1589]==b'Hollow Knight'
    assert int.from_bytes(data[1556:1560],'little')==11 and int.from_bytes(data[1572:1576],'little')==13
    files={p.relative_to(payload).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in payload.rglob('*') if p.is_file()}
    package=dict(schema=1,protocol=25,gameVersion='1.5.12620',defaultGameSource=str(game),
        baseManifestSha256=sha(output/'base-game.json'),payloadBytes=sum(v['bytes'] for v in files.values()),files=files,
        profilePatch=dict(sourceSha256=sha(original),companyOffset=1560,productOffset=1576),filmSha256=films,
        criticalFiles=['game/hollow_knight.exe','game/UnityPlayer.dll','game/hollow_knight_Data/globalgamemanagers',
            'game/hollow_knight_Data/Managed/Assembly-CSharp.dll','game/hollow_knight_Data/Managed/Mods/HollowCraft/HollowCraft.dll',
            'runtime/java/bin/java.exe','runtime/java/bin/server/jvm.dll','runtime/runtime.json','runtime/'+runtime['modJar'],
            'scripts/HollowCraft.Common.ps1','scripts/Start-HollowCraft.ps1'])
    write(output/'package.json',package)
    print(json.dumps(dict(output=str(output),payloadFiles=len(files),payloadBytes=package['payloadBytes'],
                         baseBytes=base['bytes'],filmCount=len(films),modSha256=runtime['modSha256'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('project','backend','game-source','api','cinematics','base-manifest','ledger','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    build(parser.parse_args())
