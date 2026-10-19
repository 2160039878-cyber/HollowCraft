"""Validate live commit-failure rollback, safe return and per-room restoration."""
import argparse
import json
from pathlib import Path


def analyze(root):
    def read(name):
        return json.loads((root/(name+'.json')).read_text(encoding='utf-8-sig'))
    def cells(name):
        return {tuple(cell) for cell in read('live/'+name)['removed']}
    def blocks(name):
        return read('live/'+name)['blocks']
    def states(name):
        return {(b['x'],b['y'],b['z']):b['state'] for b in blocks(name)}

    assert read('lock-held')['sha256']==read('pointer-before-lock')['sha256']
    assert read('lock-released')['requested']
    failure=read('live/failed-restore-runtime')
    assert failure['checkpointError'] and not failure['checkpointSaving'] and not failure['recoveryBusy']
    assert failure['recoveryStatus']=='检查点未保存，地形保持原状。'
    assert failure['terrainCuts']>0 and cells('terrain-a')==cells('terrain-after-failed-restore')
    ammo={name:read('live/'+name)['arrows'] for name in ['status-a','status-mutated','status-after-failed-restore',
        'status-reloaded-a','status-restored-room','status-town-reloaded']}
    assert ammo==dict(zip(ammo,[64,63,63,64,64,64])),ammo
    assert blocks('blocks-a')==blocks('blocks-reloaded-a')
    assert cells('terrain-reloaded-a')==cells('terrain-a')
    for name in ['blocks-restored-room','blocks-town-reloaded']:
        assert states(name)==states('blocks-a')
        assert not any(b['dug'] for b in blocks(name))
    for name in ['terrain-restored-room','terrain-town-reloaded']:
        terrain=read('live/'+name)
        assert terrain['CutCount']==terrain['CutColliderCount']==terrain['Pending']==0 and not terrain['removed']
        assert any(ray['hits'] for ray in terrain['rays'] if ray['direction'][1])
    assert read('checkpoint-restored-room')['id']!=read('checkpoint-a')['id']
    assert read('checkpoint-local-reset')['id']!=read('checkpoint-two-rooms')['id']
    before,after=read('live/return-safe-before'),read('live/return-safe-after')
    flight=read('live/return-safe-flight')['samples']
    assert not flight[-1]['ground'] and flight[-1]['y']>before['heroY']+1
    assert after['recoveryStatus']=='已返回最近有效安全位置。'
    assert abs(after['heroX']-before['heroX'])<.1 and abs(after['heroY']-before['heroY'])<.1
    assert cells('second-room-crater') and cells('second-room-crater')==cells('second-room-after-town-reset')
    runtime=read('live/final-runtime')
    assert runtime['scene']=='Room_nailmaster' and runtime['ready'] and runtime['checkpointError'] is None
    assert runtime['PhysicsTimeouts']==0
    support={}
    for label,native in [('knight',True),('minecraft',False)]:
        result=read('live/support-'+label+'-drop');rows=result['samples']
        assert result.get('complete') and max(s['y'] for s in rows)>13.8 and rows[-1]['ground']
        state=read('live/support-'+label+'-runtime')
        assert state['native']==native and state['colliderMinY']>9.99 and state['terrainCuts']==0
        assert state['PhysicsTimeouts']==0
        support[label]=state['colliderMinY']
    observed=0
    for path in (root/'live').glob('*.json'):
        data=json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(data,dict):continue
        for row in data.get('samples',[]):
            assert row['HiddenWindow'] and row['visibleWindows']==0 and not row['ownsForegroundWindow'],path.name
            observed+=1
    assert observed>1000
    return dict(passed=True,commitFailureRetainedCheckpoint=True,liveUncommittedAmmo=63,reloadedCommittedAmmo=64,
                townRemovedCellsBeforeRestore=len(cells('terrain-a')),townRemovedCellsAfterRestore=0,
                otherRoomRemovedCellsPreserved=len(cells('second-room-crater')),buildingsPreserved=True,
                nativeAndMinecraftCollisionRestored=True,restoredSupportFeet=support,safeReturnFromAirPassed=True,hiddenSamples=observed,
                physicsTimeouts=0,limitations=[
                    'Commit-file contention was injected; disk-full and sudden-power-loss behavior were not simulated.',
                    'The second-room fixture initially crossed a native Ruins exit and was cancelled; the enclosed-room repeat supplies the isolation evidence.',
                    'Recovery actions invoke the same handlers as the UI; hardware mouse clicks are not covered.',
                    'The Town crater is shallow; this verifies restoration, not a new through-floor traversal claim.',
                    'This does not establish presentation FPS or complete the remaining full-goal requirements.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=analyze(args.evidence);text=json.dumps(result,indent=2)+'\n'
    if args.output:args.output.write_text(text,encoding='utf-8')
    print(text)
