"""Verify native Tier5 ending dispatch, outgoing hits and replacement actor visibility."""
import array
import json
import math
import statistics
import sys
from pathlib import Path

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def check(root):
    cases=[]
    for label,flower,movie,last_frame in [('d-04',False,'FinalD',1507),('e-05',True,'FinalE',1956)]:
        names=['intro','ascend','final-phase','sword','final-hit','transform','ending']
        probes={name:read(root/(name+'-'+label+'.json')) for name in names}
        story=[s for p in probes.values() for s in p['storySamples']]
        first=probes['intro']['storySamples'][-1]
        assert first['IsInSequence'] and (first['BossIndex'],first['BossCount'])==(52,53)
        assert first['givenGodseekerFlower']==flower and not first['bossRushMode'] and first['openedBlackEggDoor']
        audio=[]
        for name,data in probes.items():
            assert data.get('complete') or data.get('cancelled') and data['reason']=='scene or peer changed'
            assert data['samples'] and all(s['HiddenWindow'] and s['visibleWindows']==0 and not s['ownsForegroundWindow'] for s in data['samples'])
            if data.get('captureDirectory'):
                directory=Path(data['captureDirectory'])
                assert all((directory/f"{frame['index']:05}.png").is_file() for frame in data['captures'])
                track=data['audio'];assert not any(track[k] for k in ['error','overflow','channelsChanged'])
                assert track['sampleRate']==48000 and track['channels']==2 and abs(track['timingErrorSeconds'])<.1
                pcm=array.array('f');pcm.frombytes(Path(track['path']).read_bytes())
                assert len(pcm)==track['samples'] and all(math.isfinite(v) for v in pcm)
                rms=math.sqrt(sum(v*v for v in pcm)/len(pcm));assert rms>.0001
                audio.append(dict(probe=name,rms=rms,clockError=track['timingErrorSeconds']))
        arrows=[]
        for path in sorted(root.glob('bow-??-'+label+'.json')):
            data=read(path);assert data.get('complete'),path.name
            arrows.extend(h for h in data['hits'] if h['name']=='Absolute Radiance' and h['before']>h['after'])
        assert arrows and all(h['attackType']=='Generic' for h in arrows)
        bow_damage=sum(h['before']-h['after'] for h in arrows);assert bow_damage>280
        nails=[h for h in probes['final-hit']['hits'] if h['name']=='Absolute Radiance']
        assert sum(h['before']-h['after'] for h in nails)==21
        assert all(h['attackType']=='Nail' for h in nails)
        states={f['ActiveStateName'] for s in story for f in s['story'] if f['name']=='Absolute Radiance' and f['FsmName']=='Control'}
        assert {'Lord Appear','First Idle','Shade Slash','Kill Hit','Final Stream','Final Explode'}<=states
        hands=[a for s in story for a in s['actors'] if a['name']=='Shade Lord Hand' and a['active'] and a['visible']]
        assert {'Grab','Break'}<={a['clip'] for a in hands} and all(a['hidden'] for a in hands)
        parts=[p for s in story for lord in s['lords'] if lord['active'] for p in lord['parts'] if p['active'] and p['enabled']]
        bodies=[p for p in parts if p['name'] in ['head','arms','body'] or p['name'].startswith('tendril')]
        effects=[p for p in parts if p['name'] in ['white_fader','Death BG','Black Fader']]
        assert bodies and all(p['hidden'] for p in bodies) and effects and all(not p['hidden'] for p in effects)
        film=read(root/('film-'+label+'.json'))
        assert film['request']['Name']==movie and film['controller']=='CinematicPlayer' and not film['errors']
        assert film['endCallbacks']==1 and not film['skipSent'] and (film['firstReadyFrame'],film['endingFrame'])==(0,last_frame)
        assert film['beganInScene']=='Cinematic_Ending_'+movie[-1]
        assert film['separateAudio']['channels']==2 and max(s['audioRms'] for s in film['samples'])>.01
        offsets=[s['audioTime']-s['time'] for s in film['samples'] if s['isPlaying'] and s['audioPlaying']]
        assert offsets and abs(statistics.median(offsets))<.1
        credits=read(root/('credits-'+label+'.json'));assert credits['scene']=='End_Credits' and not credits['checkpointSaving']
        cases.append(dict(label=label,flower=flower,movie=movie,frames=[0,last_frame],bowHits=len(arrows),bowDamage=bow_damage,
            nativeNailDamage=21,handClips=sorted({a['clip'] for a in hands}),hiddenBodyPartSamples=len(bodies),
            preservedEffectSamples=len(effects),nativeStates=sorted(states),audio=audio,originalMovieAudio=film['separateAudio'],
            audioMedianOffset=statistics.median(offsets),physicsTimeouts=credits['PhysicsTimeouts']))
    short=read(root/'film-d-03.json')
    assert not short['errors'] and short['endCallbacks']==1 and not short['skipSent'] and 1020<=short['endingFrame']<1040
    return dict(passed=True,scope='Native ending and outgoing-hit correctness; not performance acceptance',cases=cases,
        nativeShortD=dict(openedBlackEggDoor=False,endingFrame=short['endingFrame'],elapsed=short['elapsed']),
        coldPhysicsTimeouts=[41.0597,40.0524],performanceAccepted=False,
        limitations=['Native Tier5 context begins at boss index52 and the fixture skips early combat, places the player on the final platform and enables temporary damage protection.',
            'The full pantheon and incoming combat damage are not covered by this fixture.',
            'Cold first-bow synchronization timed out twice in the initial run; warm repeats succeeded. Root cause remains unproven.',
            'Synchronous PNG capture is excluded from FPS acceptance; original HK listener audio is recorded, Minecraft process audio is not.',
            'The closed-Black-Egg E cutoff is confirmed by native metadata, not a separate live run; physical desktop skip keys were not sent.'])

if __name__=='__main__':
    root=Path(sys.argv[1]);result=check(root)
    (root/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=result['passed'],cases=[{k:c[k] for k in ['label','frames','bowHits','bowDamage','handClips','physicsTimeouts']} for c in result['cases']],performanceAccepted=False)))
