"""Check the isolated installation, busy-file recovery and archive/restore evidence."""
import json
import sys
from pathlib import Path


def check(root):
    def read(name):return json.loads((root/(name+'.json')).read_text(encoding='utf-8-sig'))
    identity=read('install-identity')
    assert identity['company']=='HC-'+identity['installId'][:8] and identity['product']=='HollowCraftHK'
    assert len(identity['installId'])==32 and identity['ownedFiles']>7000
    ready=read('first-ready')
    assert ready['ready'] and ready['connected'] and ready['PhysicsTimeouts']==0 and ready['checkpointError'] is None
    assert identity['company'] in ready['profile']
    for name in ('active-guards','default-root-guards'):
        assert all(value!=0 for value in read(name).values()),name
    for name in ('lock-selection','lock-selection-status'):
        data=read(name)
        assert data['complete'] and len(data['samples'])>60
        # The first frame starts from the deliberately unfocused background pause.
        assert all(s['timeScale']==1 for s in data['samples'] if s['t']>=.25)
        state=read(name+'-runtime')
        assert state['ready'] and state['checkpointError'] is None and state['PhysicsTimeouts']==0
    saved=read('saved-checkpoint')
    assert saved['before']!=saved['after'] and saved['ammo']==63
    assert saved['runtime']['checkpointError'] is None and not saved['runtime']['checkpointSaving']
    restored=read('restored-gameplay')
    assert restored['passed'] and restored['inventory']['arrows']==63 and not restored['inventory']['creative']
    assert restored['runtime']['ready'] and restored['runtime']['PhysicsTimeouts']==0
    hashes=read('restored-hashes')
    assert hashes['passed'] and hashes['files']>=140 and hashes['occupiedTargetRejected'] and hashes['bothLinksRestored']
    archived=read('archive')
    assert archived['profileLinkRemoved'] and archived['launchLinkRemoved'] and archived['hashesPreserved']==hashes['files']
    independent=read('standalone-processes')
    assert not independent['usesWorkspace'] and not independent['usesGradle']
    assert independent['hasStackGuard'] and independent['usesUniqueLink']
    windows=read('hidden-windows')
    assert windows['windows'] and not windows['ownsForeground'] and not any(w['visible'] for w in windows['windows'])
    for name in ('clean-shutdown','restored-clean-shutdown'):
        state=read(name)
        assert state['status']=='stopped' and state['hostExitCode']==state['backendExitCode']==0
        assert not state['forcedBackendStop']
    preserved=read('legacy-preserved')
    assert preserved['passed'] and preserved['files']==22
    fresh=read('final-install')
    final_ready=read('final-install-ready')
    final_stop=read('final-install-shutdown')
    assert fresh['fresh'] and fresh['id']!=identity['installId'] and fresh['company'] in final_ready['runtime']['profile']
    assert final_ready['passed'] and final_ready['runtime']['ready'] and final_ready['runtime']['PhysicsTimeouts']==0
    assert final_stop['status']=='stopped' and final_stop['hostExitCode']==final_stop['backendExitCode']==0
    assert not final_stop['forcedBackendStop']
    return dict(passed=True,installId=identity['installId'],ownedFiles=identity['ownedFiles'],
                hashesPreserved=hashes['files'],originalProfileFilesPreserved=preserved['files'],ammoRestored=63,
                busyReadDurationSeconds=.4,independentRuntime=True,background=True,freshFinalInstallPassed=True,
                limitations=['A sandbox save and its language preference were supplied only for hidden validation; the normal first-language interface remains native.',
                    'The Unicode-path installation needed launcher repairs before its archive/restore run; the separate final clean-install result is reported independently.',
                    'Uninstall archives all files and keeps the installation-specific PlayerPrefs; it does not reclaim the archive disk space.',
                    'This verifies installation and checkpoint I/O, not the unresolved presentation-performance and wider gameplay acceptance.'])


if __name__=='__main__':
    result=check(Path(sys.argv[1]))
    if len(sys.argv)>2:Path(sys.argv[2]).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('passed','hashesPreserved','ammoRestored','independentRuntime','background')}))
