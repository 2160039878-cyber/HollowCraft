"""Check the native actor fixture and Dream Nail geometry; visual review remains separate."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def analyze(root, geometry_path):
    result=json.loads((root/'result.json').read_text(encoding='utf-8-sig'))
    assert result['passed'] and result['errors']==[] and result['scene']=='Menu_Title'
    assert result['defaultDreamReplaced'] and result['resolution']==[1920,1080]
    expected={'Warp In':26,'DN Item':3,'DN Get 1':4,'DN Get 2':6,'DN Get 3':8,'DN End':2}
    seen=set();preserved=replaced=0
    for frame in result['frames']:
        clip,index=frame['clip'],frame['frame']
        assert clip in expected and 0<=index<expected[clip] and (clip,index) not in seen
        seen.add((clip,index))
        change=clip!='DN Item' and not (clip=='Warp In' and index<2)
        assert frame['replaced']==change and frame['originalHidden']==change
        prefix=f"dream-{clip.replace(' ','_')}-{index:02d}"
        digests=[hashlib.sha256((root/f'{prefix}-{kind}.png').read_bytes()).digest() for kind in ('native','steve')]
        assert (digests[0]!=digests[1])==change
        replaced+=change;preserved+=not change
    assert len(seen)==sum(expected.values())==49 and replaced==44 and preserved==5
    sprites=json.loads(geometry_path.read_text(encoding='utf-8-sig'))['sprites']
    assert len(sprites)==40 and sum(s['replace'] for s in sprites.values())==35
    for name,sprite in sprites.items():
        for polygon in sprite['keep']:
            assert len(polygon)>=3
            for point in polygon:
                assert len(point)==5 and all(math.isfinite(v) and -1e-7<=v<=1+1e-7 for v in point)
            if sprite['cleanLeft'] is not None:
                assert (max(p[3] for p in polygon)<=sprite['cleanLeft']+1e-7
                        or min(p[3] for p in polygon)>=sprite['bodyRight']-1e-7
                        or (max(p[3] for p in polygon)<=sprite['cleanTop'][0]+1e-7 and max(p[4] for p in polygon)<=sprite['cleanTop'][1]+1e-7))
        if name.startswith('dream_nail_object'): assert not sprite['replace'] and not sprite['keep']
    summary=dict(passed=True,nativeFrames=49,replacedFrames=44,preservedFrames=5,
                 preserved='Three DN Item frames and two pure-light arrival frames are byte-identical.',
                 limitations='Actor-only offscreen fixture; excludes actual story FSM, dialogue, audio and gameplay performance.')
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('probe',type=Path);parser.add_argument('geometry',type=Path)
    args=parser.parse_args();analyze(args.probe,args.geometry)
