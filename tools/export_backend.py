"""Export the already-resolved Fabric development runtime; no Gradle or network is needed to launch it."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def digest(path, algorithm='sha256'):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def export(project, jdk, assets, output):
    project, jdk, assets, output = (p.resolve() for p in (project, jdk, assets, output))
    assert not output.exists(), 'Runtime destination must be new'
    assert all(not output.is_relative_to(p) for p in (project, jdk, assets)), 'Nested output is unsafe'
    lines = (project/'minecraft/build/loom-cache/argFiles/runClient').read_text(encoding='utf-8-sig').splitlines()
    assert len(lines) == 2 and lines[0] == '-classpath', 'Unexpected Loom argument format'
    classpath = [Path(p) for p in lines[1].split(';')]
    assert all(p.exists() for p in classpath), 'A resolved runtime dependency is missing'
    libraries = [p for p in classpath if p.is_file()]
    assert len({p.name.lower() for p in libraries}) == len(libraries), 'Ambiguous library filenames'
    settings = (project/'minecraft/.gradle/loom-cache/launch.cfg').read_text(encoding='utf-8-sig')
    config = {}; section = None; client_args = []
    for line in settings.splitlines():
        if not line.startswith('\t'):
            section = line
        elif section == 'clientArgs':
            client_args.append(line.strip())
        else:
            key, value = line.strip().split('=', 1)
            config[key] = value
    assert client_args[0] == '--assetIndex' and client_args[2] == '--assetsDir' and len(client_args) == 4
    assert config['fabric.development'] == 'true'
    expected = {'fabric.development', 'log4j.configurationFile', 'log4j2.formatMsgNoLookups',
                'fabric.defaultModDistributionNamespace', 'fabric.defaultMixinRemapType',
                'fabric.gameJarPath', 'fabric.classPathGroups', 'fabric.gameJarPath.client'}
    assert set(config) == expected, 'Review new Loom settings before exporting'
    index = client_args[1]
    asset_index = assets/'indexes'/(index+'.json')
    asset_data = json.loads(asset_index.read_text(encoding='utf-8'))
    mod = project/'minecraft/build/libs/hollowcraft-0.1.1.jar'
    assert mod.is_file() and (jdk/'bin/java.exe').is_file()
    java_release = (jdk/'release').read_text(encoding='utf-8')
    assert 'JAVA_VERSION="25.' in java_release
    output.mkdir(parents=True)
    shutil.copytree(jdk, output/'java')
    destination = output/'minecraft'
    (destination/'libraries').mkdir(parents=True)
    copied = []
    for path in libraries + [mod]:
        target = destination/'libraries'/path.name
        assert not target.exists()
        shutil.copy2(path, target)
        copied.append(str(target.relative_to(output)).replace('\\', '/'))
    (destination/'assets/indexes').mkdir(parents=True)
    shutil.copy2(asset_index, destination/'assets/indexes'/asset_index.name)
    objects = {v['hash']:v['size'] for v in asset_data['objects'].values()}
    for key, size in objects.items():
        source = assets/'objects'/key[:2]/key
        assert source.stat().st_size == size and digest(source, 'sha1') == key, 'Invalid asset '+key
        target = destination/'assets/objects'/key[:2]/key
        target.parent.mkdir(exist_ok=True, parents=True)
        shutil.copy2(source, target)
    shutil.copy2(Path(config['log4j.configurationFile']), destination/'log4j.xml')
    metadata = dict(schema=1, minecraft='26.3', loader='0.19.5', assetIndex=index,
                    mainClass='net.fabricmc.devlaunchinjector.Main', classpath=copied,
                    commonJar='minecraft/libraries/'+Path(config['fabric.gameJarPath']).name,
                    clientJar='minecraft/libraries/'+Path(config['fabric.gameJarPath.client']).name,
                    modJar='minecraft/libraries/'+mod.name, modSha256=digest(mod),
                    properties={k:config[k] for k in ('fabric.development','log4j2.formatMsgNoLookups',
                                'fabric.defaultModDistributionNamespace','fabric.defaultMixinRemapType')},
                    maxHeapMiB=6144, softHeapMiB=3072)
    (output/'runtime.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    files = {str(p.relative_to(output)).replace('\\','/'):dict(bytes=p.stat().st_size,sha256=digest(p))
             for p in output.rglob('*') if p.is_file()}
    (output/'manifest.json').write_text(json.dumps(files,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(path=str(output),files=len(files),bytes=sum(v['bytes'] for v in files.values()),
                         libraries=len(libraries),assets=len(objects),modSha256=metadata['modSha256'])))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    for name in ('project','jdk','assets','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args()
    export(args.project,args.jdk,args.assets,args.output)
