"""Verify real TNT death, native respawn and committed building/inventory/cut replay."""
import json
import sys
from pathlib import Path


def check(root):
    def read(name):return json.loads((root/'live'/(name+'.json')).read_text(encoding='utf-8-sig'))
    def blocks(name):return {(b['x'],b['y'],b['z']):b for b in read(name)['blocks']}
    fatal=read('fatal-blast')
    deaths=[h for h in fatal['received'] if h['after']==0]
    assert len(deaths)==1 and deaths[0]['before']==4 and deaths[0]['amount']==8
    assert fatal.get('cancelled') and fatal['reason']=='scene or peer changed'
    respawn=read('respawn-wake')
    assert respawn.get('complete') and respawn['samples'][-1]['hp']==5 and respawn['samples'][-1]['acceptingInput']
    before,after,reloaded=blocks('before-blocks'),blocks('after-blocks'),blocks('reloaded-buildings')
    persistent={p:b['state'] for p,b in before.items() if b['state']!='Block{minecraft:air}'}
    assert len(persistent)>=2 and any('minecraft:lever' in state for state in persistent.values())
    assert all(after[p]['state']==state and reloaded[p]['state']==state for p,state in persistent.items())
    seed=next(e for e in read('seed-events') if e['event']=='exploded')['dugCellsAtPlane']
    final=next(e for e in read('fatal-events') if e['event']=='exploded')['dugCellsAtPlane']
    assert set(map(tuple,seed))<=set(map(tuple,final)) and len(final)>len(seed)
    observed=[tuple(p) for p in final if tuple(p) in after]
    assert len(observed)>=3 and all(after[p]['dug'] for p in observed)
    all_reloaded=blocks('reloaded-cuts')
    assert all(all_reloaded[tuple(p)]['dug'] for p in final)
    inventory=[read(name) for name in ('before-inventory','after-inventory','reloaded-inventory')]
    assert all(x['arrows']==64 and not x['creative'] and x['held']=='minecraft:diamond_pickaxe' for x in inventory)
    for name in ('runtime-after','reloaded-runtime'):
        state=read(name)
        assert state['ready'] and state['scene']=='Town' and state['PhysicsTimeouts']==0 and not state['checkpointError']
        assert state['terrainCuts']>0 and state['cutColliders']>0
    assert read('runtime-after')['epoch']>read('runtime-before')['epoch']
    assert read('checkpoint-before')['id']!=read('checkpoint-after')['id'], 'Death must commit the paired world state'
    assert read('checkpoint-restart')['id']==read('checkpoint-reloaded')['id']
    samples=fatal['samples']+respawn['samples']+read('reload-wake')['samples']
    assert all(s['HiddenWindow'] and s['visibleWindows']==0 and not s['ownsForegroundWindow'] for s in samples)
    return dict(passed=True,deathDamage=8,healthBeforeDeath=4,respawnHealth=5,
        seedRemovedCells=len(seed),fatalRemovedCells=len(final),cellsObservedImmediatelyAfterDeath=len(observed),
        allFatalCellsRestoredAfterRestart=True,preservedBuildingCells=len(persistent),arrows=64,
        nativeDeathCheckpointCommitted=True,reloadedCheckpoint=read('checkpoint-reloaded')['id'],
        physicsTimeouts=0,limitations=['The first post-death block sample covered only three of the five removed cells; the wider post-restart sample covers all five.',
            'This is an isolated Dirtmouth fixture with native TNT, death and bench respawn. It does not assert full-game progression or display FPS.'])


if __name__=='__main__':
    result=check(Path(sys.argv[1]))
    if len(sys.argv)>2:Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
