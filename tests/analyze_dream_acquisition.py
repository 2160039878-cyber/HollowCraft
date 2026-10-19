"""Check native Dream Nail acquisition, Dreamgate roundtrip and the facing regression."""
import array
import json
import math
import sys
from pathlib import Path
from PIL import Image


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def check(root):
    names=['memorial-story-01','memorial-story-02','nailworld-arrival-01','route-hop-02',
        'zone1-cross','zone2-cross','zone3-cross','nail-talk-02','nail-get-02','seer-first-arrival','seer-first-control',
        'back-warm-02','back-left-final','back-right-final','back-left-final-close','back-right-final-close',
        'gate-final-reward','gate-proof-set','gate-proof-away','gate-proof-warp','gate-proof-arrival','gate-proof-control']
    probes={name:read(root/(name+'.json')) for name in names}
    audio=[]
    for name,data in probes.items():
        assert data.get('complete') or data.get('cancelled') and data['reason']=='scene or peer changed',name
        assert data['samples'] and all(s['hp']==5 for s in data['samples']),name
        assert all(s['HiddenWindow'] and s['visibleWindows']==0 and not s['ownsForegroundWindow'] for s in data['samples'])
        if data.get('captureDirectory'):
            directory=Path(data['captureDirectory'])
            assert all((directory/f"{f['index']:05}.png").is_file() for f in data['captures'])
            track=data['audio'];assert not track['error'] and not track['overflow'] and not track['channelsChanged']
            assert abs(track['timingErrorSeconds'])<.1 and track['sampleRate']==48000 and track['channels']==2
            pcm=array.array('f');pcm.frombytes(Path(track['path']).read_bytes())
            assert len(pcm)==track['samples'] and all(math.isfinite(x) for x in pcm)
            rms=math.sqrt(sum(x*x for x in pcm)/len(pcm));assert rms>.0001
            audio.append(dict(probe=name,rms=rms,clockError=track['timingErrorSeconds']))
    arrival=probes['nailworld-arrival-01'];assert arrival['storySamples'][-1]['scene']=='Dream_Nailcollection'
    assert not arrival['storySamples'][-1]['hasDreamNail']
    hop=probes['route-hop-02']['samples'][-1];assert hop['ground'] and hop['mcGround'] and hop['y']>16
    for index in range(1,4):
        assert any(f['name']=='Witch Control' and f['ActiveStateName']=='Zone '+str(index)
            for s in probes[f'zone{index}-cross']['storySamples'] for f in s['story'])
    pickup=probes['nail-talk-02'];assert not pickup['storySamples'][0]['hasDreamNail'] and pickup['storySamples'][-1]['hasDreamNail']
    bodies=[a for s in pickup['storySamples'] for a in s['actors']
            if a['library']=='Knight Dream Custcene Anim' and a['active'] and a['clip'] in ['DN Get 1','DN Get 2','DN Get 3']]
    assert {a['clip'] for a in bodies}=={'DN Get 1','DN Get 2','DN Get 3'} and all(a['hidden'] for a in bodies)
    assert probes['nail-get-02'].get('cancelled')
    assert probes['seer-first-arrival']['storySamples'][-1]['scene']=='RestingGrounds_07'
    control=probes['seer-first-control'];assert control['samples'][-1]['x']-control['samples'][0]['x']>1
    assert control['samples'][-1]['acceptingInput'] and probes['back-warm-02']['storySamples'][-1]['hasDreamNail']
    # Fixed memorial camera: interior head patches distinguish the old visible face from the back of the head.
    skin_pixels={}
    for name,box in [('back-left-final',(889,901,904,917)),('back-right-final',(1019,901,1034,917)),('back-right-view',(1019,901,1034,917))]:
        data=read(root/(name+'.json'));assert data['samples'][-1]['animation']=='TurnToBG'
        frame=Path(data['captureDirectory'])/f"{data['captures'][-1]['index']:05}.png"
        pixels=Image.open(frame).convert('RGB').crop(box)
        count=sum(r>15 and r>g*1.2 for r,g,b in pixels.getdata());skin_pixels[name]=count
    assert skin_pixels['back-right-view']>20 and skin_pixels['back-left-final']<=2 and skin_pixels['back-right-final']<=2
    for name in ['back-left-final-close','back-right-final-close']:
        data=probes[name];assert 'TurnFromBG' in {s['animation'] for s in data['samples']}
        assert data['samples'][-1]['acceptingInput'] and data['samples'][-1]['animation']=='Idle'
    reward=probes['gate-final-reward']['storySamples'];assert not reward[0]['hasDreamGate'] and reward[-1]['hasDreamGate']
    assert any(f['name']=='Dream Moth' and f['ActiveStateName']=='Reward 5b' for s in reward for f in s['story'])
    point=probes['gate-proof-set']['storySamples'][-1];end=probes['gate-proof-arrival']['storySamples'][-1]
    assert probes['gate-proof-warp'].get('cancelled') and end['dreamOrbs']==point['dreamOrbs']-1
    before=probes['gate-proof-set']['samples'][-1];after=probes['gate-proof-arrival']['samples'][-1]
    assert all(abs(before[k]-after[k])<.001 for k in ['x','y','mcX','mcY'])
    proof=read(root/'gate-proof-summary.json');assert proof['passed'] and proof['movementAfterReturn'] < -1
    return dict(passed=True,firstAcquisition=True,nativeGetClips=sorted({a['clip'] for a in bodies}),
        abilityPersistedAfterRestart=True,dynamicPlatformHop=True,nativeZones=[1,2,3],gate=proof,backFacePixelCheck=skin_pixels,
        hp=5,backgroundOnly=True,audio=audio,
        limitations=['Fixture placement skips much of the dream-world platform route; one real platform hop and all3 native zone triggers were checked.',
            'The first-acquisition recordings precede the facing fix; final-build facing and Dreamgate checks are separate.',
            'Forced test exit reloads the last committed checkpoint; an unsaved Dreamgate point was not retained.',
            'Capture overhead excludes performance acceptance. Full-resolution visual review of every frame is not claimed.'])


if __name__=='__main__':
    root=Path(sys.argv[1]);result=check(root)
    (root/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='audio'}))
