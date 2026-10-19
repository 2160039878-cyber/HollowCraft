"""Check the actual ending fixture, fragment regression and native FinalC playback."""
import array
import json
import math
import statistics
import sys
from pathlib import Path

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def check(root):
    names=['arrival-03-v6','challenge-03-v6','ascend-fixture-03-v6','final-hit-03-v6','transform-06','ending-06']
    probes={name:read(root/(name+'.json')) for name in names}
    audio=[]
    for name,data in probes.items():
        assert data.get('complete') or data.get('cancelled') and data['reason']=='scene or peer changed',name
        assert data['samples'] and all(s['hp']==5 for s in data['samples']),name
        assert all(s['HiddenWindow'] and s['visibleWindows']==0 and not s['ownsForegroundWindow'] for s in data['samples']),name
        if data.get('captureDirectory'):
            directory=Path(data['captureDirectory'])
            assert all((directory/f"{frame['index']:05}.png").is_file() for frame in data['captures'])
            track=data['audio'];assert not any(track[k] for k in ['error','overflow','channelsChanged'])
            assert track['sampleRate']==48000 and track['channels']==2 and abs(track['timingErrorSeconds'])<.1
            pcm=array.array('f');pcm.frombytes(Path(track['path']).read_bytes())
            assert len(pcm)==track['samples'] and all(math.isfinite(v) for v in pcm)
            rms=math.sqrt(sum(v*v for v in pcm)/len(pcm));assert rms>.0001
            audio.append(dict(probe=name,rms=rms,clockError=track['timingErrorSeconds']))
    hit=probes['final-hit-03-v6'];matches=[h for h in hit['hits'] if h['name']=='Radiance' and h['DamageDealt']==21]
    assert len(matches)==1 and matches[0]['before']-matches[0]['after']==21 and matches[0]['attackType']=='Nail'
    assert not hit['samples'][-1]['acceptingInput']
    assert probes['ascend-fixture-03-v6']['storySamples'][-1]['fixtureInvincible']
    story=[s for p in probes.values() for s in p['storySamples']]
    states={f['ActiveStateName'] for s in story for f in s['story'] if f['name']=='Radiance' and f['FsmName']=='Control'}
    assert {'First Idle','Antic','Kill Hit','Yank Down','Drag','Final Black'}<=states
    required={'Knight Hang','Knight Split Antic','Knight Split','Knight Form','Knight Idle',
        'Slash1 Antic','Slash1','Slash2 Antic','Slash2','Knight Unform'}
    bodies=[a for s in story for a in s['actors'] if a['active'] and a['visible'] and a['clip'] in required]
    assert required<={a['clip'] for a in bodies} and all(a['hidden'] for a in bodies)
    fragments=[f for s in story for f in s['fragments'] if f['active'] and f['enabled']]
    assert len(fragments)>20 and all(f['hidden'] for f in fragments)
    assert {f['sprite'] for f in fragments}=={'hollow_knight_skull_left','hollow_knight_skull_right'}
    glow=[a for s in story for a in s['actors'] if a['active'] and a['visible'] and a['name']=='Death Glow']
    assert glow and all(not a['hidden'] for a in glow),'Light effect was replaced by a character'
    radiance=[a for s in story for a in s['actors'] if a['active'] and a['visible'] and a['name']=='Radiance']
    assert radiance and all(not a['hidden'] for a in radiance)
    movie=read(root/'film-full-06.json')
    assert movie['request']['ObserveNative'] and movie['controller']=='CinematicPlayer'
    assert not movie['errors'] and movie['endCallbacks']==1 and not movie['skipSent']
    assert movie['firstReadyFrame']==0 and movie['endingFrame']==2531 and movie['beganInScene']=='Cinematic_Ending_C'
    assert movie['separateAudio']['name']=='Final_Cutscene_C_v01 AUDIO' and movie['separateAudio']['channels']==2
    assert max(s['audioRms'] for s in movie['samples'])>.01
    offsets=[s['audioTime']-s['time'] for s in movie['samples'] if s['isPlaying'] and s['audioPlaying']]
    assert offsets and abs(statistics.median(offsets))<.1
    assert read(root/'credits-runtime-06.json')['scene']=='End_Credits'
    policy=read(root/'film-skip-policy-05.json')
    assert policy['request']['SkipAt']==2.5 and not policy['skipSent'] and policy['endCallbacks']==1 and not policy['errors']
    return dict(passed=True,observedClips=sorted(required),nativeStates=sorted(states),nativeNailDamage=21,
        hiddenFragmentSamples=len(fragments),preservedGlowSamples=len(glow),preservedRadianceSamples=len(radiance),
        originalFilmAudio=movie['separateAudio'],movieFrames=[movie['firstReadyFrame'],movie['endingFrame']],
        movieAudioMedianOffset=statistics.median(offsets),nativeNotSkippableRespected=True,backgroundOnly=True,audio=audio,
        limitations=['Ending-only fixture bypasses earlier Radiance phases and enables temporary player damage protection; not a complete boss-combat test.',
            'Placement skips platform traversal. Full-resolution review of every frame is not claimed.',
            'Native FinalC is NOT_SKIPPABLE; physical desktop skip keys were not sent.',
            'Synchronous capture overhead excludes performance acceptance; recordings contain native HK listener audio only.',
            'GG_Radiance shares the fragment assets but its actual ending flow still requires a separate check.'])

if __name__=='__main__':
    root=Path(sys.argv[1]);result=check(root)
    (root/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='audio'}))
