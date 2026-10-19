"""Validate scan, room-load memory and hidden rendering evidence without claiming a display FPS pass."""
import json
import math
import re
import statistics
import sys
from pathlib import Path


def check(root):
    def read(name):return json.loads((root/(name+'.json')).read_text(encoding='utf-8-sig'))
    def measure(name):
        data=read(name)
        assert data.get('complete') and not data['captures'],name
        assert data['renderContext']['width']==1920 and data['renderContext']['height']==1080
        assert data['renderContext']['targetFrameRate']==60
        assert data['samples'] and all(s['HiddenWindow'] and s['visibleWindows']==0
                                      and not s['ownsForegroundWindow'] for s in data['samples'])
        death=min((h['t'] for h in data['received'] if h['after']==0),default=math.inf)
        frames=[s for s in data['renderedFrames'] if s['step']>0 and s['t']<death]
        assert len(frames)>=500,name
        metrics={}
        for key in ('intervalMs','engineMs','renderMs','runtimeMs','replicaMs','probeMs','physicsMs'):
            values=[s[key] for s in frames]
            assert all(math.isfinite(v) and v>=0 for v in values)
            worst=sorted(values,reverse=True)[:math.ceil(len(values)/100)]
            metrics[key]=dict(meanMs=statistics.mean(values),maxMs=max(values),worst1MeanMs=statistics.mean(worst))
            if key in ('intervalMs','engineMs'):
                metrics[key].update(meanFps=1000/statistics.mean(values),low1Fps=1000/statistics.mean(worst))
        hits=[h for h in data['hits'] if h['before']>h['after']]
        return dict(source=name,frames=len(frames),metrics=metrics,effectiveHits=len(hits),
                    damage=sum(h['before']-h['after'] for h in hits),hitTypes=sorted({h['attackType'] for h in hits}),
                    hpStart=data['samples'][0]['hp'],hpEnd=data['samples'][-1]['hp'])

    idle=measure('render-idle')
    combat=[measure('final-render-'+name) for name in ('falseknight','hornet','mantis','mantis-bow')]
    assert {'Nail','Generic'}<=set(combat[0]['hitTypes']) and combat[1]['effectiveHits']>0
    assert combat[2]['hpEnd']<combat[2]['hpStart'],'Mantis encounter must include real incoming attacks'
    bow=read('final-render-mantis-bow')
    targets=[e for s in bow['combatSamples'] for e in s['targets']]
    canonical={e['id'] for e in targets if e['nativeResponder']}
    hits=[h for h in bow['hits'] if h['before']>h['after']]
    assert hits and all(h['id'] in canonical and h['attackType']=='Generic' for h in hits)
    shadows={e['id'] for e in targets if not e['nativeResponder']}
    assert shadows and all(len({e['hp'] for e in targets if e['id']==key})==1 for key in shadows)
    stress=measure('stress-final-measured')
    events=read('stress-final-events')
    built=events[0]
    assert built['event']=='built' and built['components']==256 and built['tntCount']==20
    assert max(e.get('powered',0) for e in events)==256
    assert len([e for e in events if e['event']=='exploded'])==20
    assert events[-1]['event']=='finished' and events[-1]['remaining']==0
    viewport=read('stress-view-prewarm')['renderContext']
    low=[(built['min'][0]-viewport['OffsetX'])/viewport['K'],built['min'][1]/viewport['K']]
    high=[(built['max'][0]-viewport['OffsetX'])/viewport['K'],built['max'][1]/viewport['K']]
    assert all(viewport['worldMin'][i]<=low[i]<high[i]<=viewport['worldMax'][i] for i in (0,1))
    for name in ('cold-room-runtime','final-runtime-falseknight','final-runtime-hornet','final-runtime-mantis','stress-final-runtime'):
        data=read(name)
        assert data['PhysicsTimeouts']==0 and not data['checkpointError'],name
    timeline=read('stress-final-status-timeline')
    assert all('error' not in t and t['ready'] and t['timeouts']==0 and t['statusWriteFailures']==0 for t in timeline)
    old=read('pre-memory-restart')['LastPhysicsTimeout']
    assert old['scopeMatches'] and old['lateScopeMatches'] and old['lateTick']<old['expectedTick'] and old['elapsed']>=40
    oldLog=(root/'minecraft-01.log').read_text(encoding='utf-8',errors='replace')
    newLog=(root/'minecraft-02.log').read_text(encoding='utf-8',errors='replace')
    stalls=lambda log:[float(v) for v in re.findall(r'Allocation Stall \(Render thread\) ([\d.]+)ms',log)]
    assert max(stalls(oldLog),default=0)>100 and max(stalls(newLog),default=0)<40
    flags=(root/'vm-flags-02.txt').read_text(encoding='utf-8-sig')
    assert '-XX:MaxHeapSize=6442450944' in flags and '-XX:SoftMaxHeapSize=3221225472' in flags
    sitting=read('sitting-scan-return');rising=read('rise-scan-return')
    actors=[a for d in (sitting,rising) for s in d['storySamples'] for a in s['actors']
            if a['name']=='Knight Sit' and a['active'] and a['visible']]
    assert {'Knight Sit','Knight Sit End'}<={a['clip'] for a in actors} and all(a['hidden'] for a in actors)
    npc=[a for s in sitting['storySamples'] for a in s['actors'] if a['name']=='NM Mato NPC' and a['active'] and a['visible']]
    assert npc and all(not a['hidden'] for a in npc) and max(s['rigs'] for s in sitting['storySamples'])>0
    film=read('film-scan-mato')
    assert (film['firstReadyFrame'],film['endingFrame'])==(0,129) and film['endCallbacks']==1 and not film['errors']
    assert max(s['audioRms'] for s in film['samples'])>.001
    gate=lambda item:item['metrics']['intervalMs']['meanFps']>=59.5 and item['metrics']['intervalMs']['low1Fps']>=50
    return dict(evidenceChecksPassed=True,renderedCombatGateMet=all(gate(c) for c in combat),
                stressNo100msStall=all(stress['metrics'][k]['maxMs']<=100 for k in ('intervalMs','engineMs')),
                displayPresentationMeasured=False,overallPerformanceAccepted=False,idle=idle,combat=combat,stress=stress,
                memory=dict(maxHeapBytes=6442450944,softMaxHeapBytes=3221225472,
                    priorRenderAllocationStallMs=max(stalls(oldLog)),newRenderAllocationStallMs=max(stalls(newLog),default=0),
                    newAllocationStalls=newLog.count('Allocation Stall'),priorPhysicsTimeout=old,
                    observedPreGcHeapMaxMiB=max((int(x) for x in re.findall(r'(\d+)M\(\d+%\)->',newLog)),default=0)),
                protagonist=dict(originalSeatedHidden=True,npcUnchanged=True,clips=['Knight Sit','Knight Sit End'],nativeMovieFrames=[0,129]),
                limitations=['Offscreen synchronous GPU completion is not display presentation; the full performance requirement remains unproven.',
                    'Final RenderOnly combat logs detail at2Hz while target discovery remains10Hz; every rendered frame and every native hit are retained.',
                    'The first Mantis sword window contains incoming attacks but no outgoing hits; it is not another full boss-victory acceptance.',
                    'Memory evidence covers one cold JVM and the recorded rooms/stress; it does not establish the cause of every older intermittent stall.',
                    'The learned Mato sitting interaction was checked after leaving and reentering the room; earlier incomplete dialogue attempts are preserved.'])


if __name__=='__main__':
    result=check(Path(sys.argv[1]))
    if len(sys.argv)>2:Path(sys.argv[2]).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('evidenceChecksPassed','renderedCombatGateMet','stressNo100msStall','overallPerformanceAccepted')}))
