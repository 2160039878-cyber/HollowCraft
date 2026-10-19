"""Check captured native Dream_Abyss entry, ending, reward and return controls."""
import array
import json
import math
import sys
from pathlib import Path


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def check(root):
    names=['dream-hit-01','climb-01','end-start-03','end-text-01','return-01','return-wake-01','return-control-01']
    probes={name:read(root/(name+'.json')) for name in names}
    player_clips={'Knight Collapse','Climb 1','Climb 2','Climb 3','Climb 4','Knight Grab','Knight Falter','Knight Fall'}
    observed=set();preserved=set();audio=[]
    for name,data in probes.items():
        assert data.get('complete') or data.get('cancelled') and data['reason']=='scene or peer changed'
        assert data['samples'] and all(s['hp']==5 for s in data['samples'])
        assert all(s['HiddenWindow'] and s['visibleWindows']==0 and not s['ownsForegroundWindow'] for s in data['samples'])
        for sample in data['storySamples']:
            for actor in sample['actors']:
                if actor['library']!='Abyss Dream Anim' or not actor['active'] or not actor['visible']:continue
                if actor['clip'] in player_clips:
                    assert actor['hidden'];observed.add(actor['clip'])
                else:
                    assert not actor['hidden'];preserved.add((actor['name'],actor['clip']))
        directory=Path(data['captureDirectory'])
        assert data['captures'] and all((directory/f"{frame['index']:05}.png").is_file() for frame in data['captures'])
        track=data['audio'];assert track and not track['error'] and not track['overflow'] and not track['channelsChanged']
        assert track['sampleRate']==48000 and track['channels']==2 and abs(track['timingErrorSeconds'])<.1
        pcm=array.array('f');pcm.frombytes(Path(track['path']).read_bytes())
        assert len(pcm)==track['samples'] and all(math.isfinite(x) for x in pcm)
        rms=math.sqrt(sum(x*x for x in pcm)/len(pcm));assert rms>.0001
        audio.append(dict(probe=name,seconds=track['duration'],rms=rms,clockError=track['timingErrorSeconds']))
    assert observed==player_clips-{'Climb 4'},observed
    assert any(name=='King' for name,clip in preserved) and any(name=='Hollow Knight' for name,clip in preserved)
    assert any(clip=='Ground Shake' for name,clip in preserved) and any(clip and clip.startswith('Corpse Land') for name,clip in preserved)
    def states(data,owner):
        return list(dict.fromkeys(f['ActiveStateName'] for s in data['storySamples'] for f in s['story'] if f['name']==owner))
    entry=states(probes['climb-01'],'Entry Cutscene')
    required=['Start Pause','Intro Text','Fade Up','Corpse 1','Corpse 2','Corpse 3','Climb 1','Climb 2','Climb 3','End']
    assert [state for state in entry if state in required]==required
    assert probes['climb-01']['samples'][-1]['acceptingInput']
    ending=states(probes['end-start-03'],'End Cutscene')
    assert ending==['Idle','Start','King Look','King Leave','HK Step','Clamber1','Clamber Up','Look','HK Look End','Leave Pause','HK Leave','Falter','Shake','Fall','Black','Text 1']
    reward=probes['end-text-01']
    assert reward.get('cancelled') and 'Return' in states(reward,'End Cutscene')
    assert (reward['storySamples'][0]['royalCharm'],reward['storySamples'][0]['charmCost'],reward['storySamples'][0]['charmSlotsFilled'])==(3,5,5)
    assert any(s['royalCharm']==4 and s['charmCost']==0 and s['charmSlotsFilled']==0 for s in reward['storySamples'])
    assert any(a['key']=='VOID' for a in reward['suppressedAchievements'])
    control=probes['return-control-01'];last=control['samples'][-1]
    assert all(s['scene']=='Abyss_15' for s in control['storySamples'])
    assert last['acceptingInput'] and not last['controlReqlinquished'] and control['storySamples'][-1]['overlay']
    dx=last['x']-control['samples'][0]['x'];assert dx>1
    return dict(passed=True,entryStates=entry,endingStates=ending,observedPlayerClips=sorted(observed),
        preservedActors=sorted(preserved,key=str),voidHeartAwarded=True,achievementSuppressed=True,returnScene='Abyss_15',
        returnedMovementDistance=dx,hp=5,backgroundOnly=True,audio=audio,
        limitations=['Fixture prepares Kingsoul and Dream Nail and positions near entry/ending triggers; full platform traversal was not tested.',
            'Climb4 is present in the library and component-tested; these native controllers do not play it.',
            'Synchronous capture is excluded from performance acceptance; videos are separate probe segments.'])


if __name__=='__main__':
    root=Path(sys.argv[1]);result=check(root)
    (root/'story-summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['audio','preservedActors']}))
