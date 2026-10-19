"""Compare actual rendered mesh anchors with native interpolation and seated replicas."""
import json
import math
import statistics
import sys
from pathlib import Path


def check(root):
    def read(name):
        return json.loads((root/(name+'.json')).read_text(encoding='utf-8-sig'))

    motion={}
    for label in ('baseline','fixed'):
        data=read('live/'+label+'-motion')
        assert data.get('complete') and not data['captures']
        assert all(s['hp']==5 and not s['ownsForegroundWindow'] for s in data['samples'])
        modes={}
        for native in (True,False):
            frames=[f for f in data['visualFrames'] if f['native']==native]
            assert len(frames)>500 and all(f['interpolation']==1 for f in frames)
            assert max(f['bodyX'] for f in frames)-min(f['bodyX'] for f in frames)>2
            assert max(f['bodyY'] for f in frames)-min(f['bodyY'] for f in frames)>5
            error=max(max(abs(f['avatarX']-f['spriteX']),abs(f['avatarY']-(f['spriteY']-f['feetOffset']))) for f in frames)
            assert error<.0001 if label=='fixed' else error>.1
            modes['sword' if native else 'pickaxe']=dict(frames=len(frames),maxAnchorError=error)
        timings=[f['timing'] for f in data['nativeFrames']]
        frequency=data['renderContext']['cpuTimerFrequency']
        intervals=[(b['cpuTimePresentCalled']-a['cpuTimePresentCalled'])*1000/frequency for a,b in zip(timings,timings[1:])]
        assert all(v>0 for v in intervals)
        worst=sorted(intervals,reverse=True)[:math.ceil(len(intervals)/100)]
        motion[label]=dict(modes=modes,meanFps=1000/statistics.mean(intervals),low1Fps=1000/statistics.mean(worst),maxMs=max(intervals))
    assert motion['fixed']['low1Fps']>=50 and motion['fixed']['maxMs']<100

    seats=[]
    for item in ('sword','pickaxe'):
        sit=read('live/seat-'+item+'-sit');rise=read('live/seat-'+item+'-rise')
        assert sit.get('complete') and rise.get('complete')
        story=sit['storySamples']+rise['storySamples']
        actors=[a for s in story for a in s['actors'] if a['name']=='Knight Sit' and a['active'] and a['visible']]
        assert {'Knight Sit','Knight Sit End'} <= {a['clip'] for a in actors}
        assert all(a['hidden'] for a in actors)
        errors=[]
        for sample in sit['storySamples']:
            actor=next((a for a in sample['actors'] if a['name']=='Knight Sit' and a['active'] and a['visible']),None)
            if actor and sample['rigBounds']:
                rig=min(sample['rigBounds'],key=lambda r:abs(r['x']-actor['x']))
                errors.append(abs(rig['minY']-actor['minY']))
        assert len(errors)>5 and max(errors)<.001
        assert not sit['samples'][-1]['acceptingInput']
        final=rise['samples'][-1]
        assert final['acceptingInput'] and not final['controlReqlinquished'] and final['native']==(item=='sword')
        assert all(s['hp']==5 and not s['ownsForegroundWindow'] for s in sit['samples']+rise['samples'])
        seats.append(dict(item=item,maxFootError=max(errors),controlRestored=True,hp=5))
    state=read('fixed-seat-runtime')
    assert state['PhysicsTimeouts']==0 and not state['checkpointError']
    return dict(passed=True,motion=motion,seats=seats,physicsTimeouts=0,maxPhysicsWaitMs=state['MaxPhysicsWaitMilliseconds'])


if __name__=='__main__':
    print(json.dumps(check(Path(sys.argv[1])),indent=2))
