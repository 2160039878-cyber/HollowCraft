"""Check measured publication latency and the real cold-inventory regression."""
import argparse
import datetime
import json
from pathlib import Path


def analyze(root):
    def read(name):
        return json.loads((root/(name+'.json')).read_text(encoding='utf-8-sig'))
    def complete(name):
        result=read('live/'+name)
        assert result.get('complete'), (name,result.get('reason',result.get('error')))
        assert result['samples'] and all(s['HiddenWindow'] and s['visibleWindows']==0 and not s['ownsForegroundWindow'] for s in result['samples'])
        return result
    def stats(values):
        values=sorted(values)
        assert values
        return dict(count=len(values),meanMs=sum(values)/len(values),p99Ms=values[int((len(values)-1)*.99)],maxMs=values[-1])

    timing={}
    for label in ('baseline','early'):
        # These are diagnostic references from before desktop isolation, not no-foreground acceptance runs.
        reference=read('live/'+label+'-tool-idle')
        assert reference.get('complete')
        rows=[s for s in reference['samples'] if s['step']>0]
        low,high=min(s['PhysicsTick'] for s in rows),max(s['PhysicsTick'] for s in rows)
        frames=[e['values'] for e in read(label+'-frames')['recording']['events']]
        frames=[f for f in frames if f['world']==1 and not f['menu'] and not f['nativeControl'] and low<=f['hostTick']<=high]
        assert high-low>=900 and len(frames)>=1500
        assert all(f['hostTick']==f['replyTick'] for f in frames)
        timing[label]=stats(f['beforePublicationMs'] for f in frames)
        timing[label]['foregroundOwnedSamples']=sum(s['ownsForegroundWindow'] for s in rows)
    assert timing['early']['meanMs']<timing['baseline']['meanMs']*.25
    assert timing['early']['p99Ms']<timing['baseline']['p99Ms']*.25

    failure=read('live/early-modal-bow')
    timeout=read('live/early-modal-timeout-runtime')['LastPhysicsTimeout']
    assert failure.get('cancelled') and failure['reason']=='Minecraft physics timed out'
    assert failure['samples'][-1]['step']==2 and not failure['samples'][-1]['mcScreenOpen']
    assert timeout['expectedTick']==timeout['replyTick']+1 and timeout['elapsed']>=40
    end=timeout['utcMilliseconds'];start=end-timeout['elapsed']
    covering=[]
    for event in read('early-modal-events')['recording']['events']:
        if event['type']!='hollowcraft.Frame':continue
        value=event['values'];time=datetime.datetime.fromisoformat(value['startTime']).timestamp()*1000
        duration=float(value['duration'][2:-1])*1000
        if time<=start and time+duration>=end:covering.append(duration)
    assert covering and max(covering)>=90

    modal=complete('desktop-modal-bow')['samples']
    paused=[s for s in modal if s['mcScreenOpen']]
    assert len(paused)>=20 and all(s['timeScale']==0 for s in paused)
    assert not any(s['isPaused'] for s in modal)
    spans={key:max(s[key] for s in paused)-min(s[key] for s in paused)
           for key in ('physicsX','physicsY','mcX','mcY','unityTime')}
    assert all(value<.001 for value in spans.values()),spans
    assert modal[-1]['ground'] and not modal[-1]['mcScreenOpen'] and modal[-1]['timeScale']>0
    assert all(s['hp']==5 for s in modal)
    assert any(s['step']==9 and s['attackInput'] and not s['native'] for s in modal)
    before,after=read('live/desktop-ammo-before'),read('live/desktop-ammo-after')
    assert before['arrows']-after['arrows']==1 and not before['creative'] and not after['creative']

    controls={kind:read('live/desktop-controls/'+kind+'-summary') for kind in ('ground','air')}
    for summary in controls.values():
        assert summary['passed'] and summary['transfers']==100
        assert summary['maximumRequestToAcknowledgementUpperBoundMs']<=100
    complete('desktop-chain-distant')
    chain=read('live/desktop-chain-distant-events')
    assert chain[0]['event']=='built' and chain[0]['tntCount']==20
    assert len([e for e in chain if e['event']=='exploded'])==20
    assert chain[-1]['event']=='finished' and chain[-1]['remaining']==0
    runtime=read('live/desktop-final-runtime')
    assert runtime['ready'] and runtime['PhysicsTimeouts']==0 and runtime['LastPhysicsTimeout'] is None
    monitor=read('background-monitor')
    assert monitor['passed'] and monitor['hostDesktop']==monitor['session']['backgroundDesktop']
    assert monitor['hostDesktop']!=monitor['inputDesktop'] and monitor['hostWindows']>0
    assert len(monitor['samples'])>=1000 and not any(s['owned'] for s in monitor['samples'])
    focus=read('foreground-failure')
    assert focus['foregroundPid']==focus['session']['hostPid'] and not focus['visible']
    complete('desktop-render')
    return dict(passed=True,publication=timing,coldInventoryFailure=dict(waitMs=timeout['elapsed'],blockingFrameMs=max(covering)),
                menuPositionSpans=spans,modalSamples=len(paused),arrowCountBefore=before['arrows'],arrowCountAfter=after['arrows'],
                controlTransfers=controls,chainExplosions=20,finalProcessTimeouts=0,
                privateDesktop=dict(name=monitor['hostDesktop'],inputDesktop=monitor['inputDesktop'],samples=len(monitor['samples']),foregroundOwnershipSamples=0),
                maximumPhysicsWaitMs=runtime['MaxPhysicsWaitMilliseconds'],
                limitations=['Publication A/B precedes the two final menu fixes; final functional checks use the final JAR.',
                             'The publication reference runs predate desktop isolation and include foreground ownership; they are diagnostic timings, not background or presentation acceptance.',
                             'The original terrain-room41.98ms timeout remains unproven; the captured inventory timeout has a separate confirmed cause.',
                             'JFR client timing and hidden probes do not establish display presentation FPS.',
                             'The first final-JAR run failed the no-foreground requirement despite having no visible windows; private-desktop reruns replace that acceptance.',
                             'The earlier close-range chain killed the player and cancelled the probe; its evidence is retained.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=analyze(args.evidence);text=json.dumps(result,indent=2)+'\n'
    if args.output:args.output.write_text(text,encoding='utf-8')
    print(text)
