"""Checks explicit background Abyss mirror/entry traces; not a performance test."""
import json
import sys
from pathlib import Path

from PIL import Image


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def check(root):
    mirror=read(root/'mirror-final.json')
    collapse=read(root/'collapse-final.json')
    arrival=read(root/'dream-arrival-final.json')
    assert mirror.get('complete')
    assert collapse.get('cancelled') and collapse['reason']=='scene or peer changed'
    assert arrival.get('complete')
    assert {s['scene'] for s in arrival['storySamples']}=={'Dream_Abyss'}
    assert all(s['hp']==5 for d in (mirror,collapse,arrival) for s in d['samples'])
    assert all(s['HiddenWindow'] and s['visibleWindows']==0 and not s['ownsForegroundWindow']
               for d in (mirror,collapse,arrival) for s in d['samples'])
    samples=mirror['storySamples']+collapse['storySamples']
    for sample in samples:
        assert sample['scene']=='Abyss_15'
        siblings=[a for a in sample['actors'] if a['library']=='Sibling Anim']
        assert len(siblings)==16 and all(a['visible'] and not a['hidden'] for a in siblings)
        assert all(a['hidden'] for a in sample['actors'] if a['library']=='Knight')
    assert any(s['overlay'] for s in mirror['storySamples'])
    assert all(m['mask']==512 for s in mirror['storySamples'] for m in s['mirrors'])
    assert any(s['mirrors'] and s['mirrors'][0]['texture'] for s in mirror['storySamples'])
    assert any(s['native'] for s in mirror['samples']) and any(not s['native'] for s in mirror['samples'])
    directory=Path(mirror['captureDirectory'])
    reflections=sorted(directory.glob('*.reflection-*.png'))
    # The native mirror creates its texture only when the camera first sees the surface.
    indices=[int(p.name.split('.')[0]) for p in reflections]
    assert len(reflections)>10 and indices==list(range(indices[0],len(mirror['captures'])))
    reflected_body=0
    for path in reflections:
        image=Image.open(path).convert('RGB')
        assert image.size==(1024,1024)
        teal=sum(g>45 and b>45 and g>r*1.4 and b>r*1.4 for r,g,b in image.getdata())
        reflected_body+=teal>20
    assert reflected_body>10
    states=list(dict.fromkeys(f['ActiveStateName'] for s in collapse['storySamples']
        for f in s['story'] if f['name']=='Dream Enter Abyss'))
    assert states==['Idle','Impact','Wait','Black','Change Scene'],states
    bodies=[(s,a) for s in collapse['storySamples'] for a in s['actors']
            if a['library']=='Abyss Dream Anim' and a['active']]
    assert len(bodies)>10
    assert all(a['clip']=='Knight Collapse' and a['hidden'] and a['visible'] and a['layer']==19 for s,a in bodies)
    assert all(s['rigs']>=12 and not s['overlay'] for s,a in bodies[1:])
    assert min(a['frame'] for s,a in bodies)==0 and max(a['frame'] for s,a in bodies)>=27
    audio=collapse['audio']
    assert audio and audio['channels']==2 and audio['sampleRate']==48000
    assert not audio['error'] and not audio['overflow'] and abs(audio['timingErrorSeconds'])<.1
    assert Path(audio['path']).stat().st_size==audio['samples']*4
    return dict(passed=True,siblingsPreserved=16,reflections=len(reflections),reflectionsWithBody=reflected_body,
        collapseSamples=len(bodies),nativeStates=states,destination='Dream_Abyss',hp=5,
        backgroundOnly=True,overlayHiddenDuringStory=True,audioClockErrorSeconds=audio['timingErrorSeconds'],
        limitations='Frame capture is synchronous and excluded from performance acceptance. Dream_Abyss climb/ending clips remain unfinished.')


if __name__=='__main__':
    root=Path(sys.argv[1])
    result=check(root)
    (root/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
