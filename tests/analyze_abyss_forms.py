"""Validate the native Abyss animation fixture and its retained NPC pixels."""
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops


def bounds(path):
    image=Image.open(path).convert('RGB')
    assert image.size==(1920,1080)
    difference=ImageChops.difference(image,Image.new('RGB',image.size,image.getpixel((0,0))))
    return difference.convert('L').point(lambda value:255 if value>8 else 0).getbbox()


def check(root):
    data=json.loads((root/'result.json').read_text(encoding='utf-8-sig'))
    assert data['passed'] and not data['errors'] and data['defaultAbyssReplaced']
    assert len(data['frames'])==159
    clips={'Knight Collapse':28,'Climb 1':6,'Climb 2':3,'Climb 3':25,'Climb 4':6,
           'Knight Grab':4,'Knight Falter':5,'Knight Fall':3}
    counts={name:0 for name in clips};preserved=0;cropped=[]
    standing=bounds(root/'abyss-Climb_3-24-steve.png')
    for frame in data['frames']:
        native=root/(frame['label']+'-native.png');steve=root/(frame['label']+'-steve.png')
        expected=frame['clip'] in clips
        assert frame['replaced']==frame['originalHidden']==expected
        assert (native.read_bytes()!=steve.read_bytes())==expected
        assert bounds(native) and bounds(steve)
        if not expected:preserved+=1
        elif not frame['mirrored'] and 'time-' not in frame['label']:counts[frame['clip']]+=1
        if expected and frame['clip'] in ['Climb 1','Climb 2','Climb 3']:
            bottom=bounds(steve)[3]
            assert bottom<=standing[3]+2,(frame['label'],bottom,standing)
            cropped.append(bottom)
    assert counts==clips and preserved==71
    loop=[frame for frame in data['frames'] if 'time-' in frame['label']]
    assert len(loop)==5 and {f['fps'] for f in loop}=={12,24}
    for frame in loop:
        start,length=(2,4) if frame['clip']=='Knight Grab' else (3,5)
        assert start/length<=frame['phase']<1
        assert abs(frame['phase']*length-frame['frame'])<.01
    return dict(passed=True,protagonistFrames=80,preservedNpcFrames=71,mirroredSamples=3,loopOverrunSamples=5,
                clippedSamples=len(cropped),standingPixelFloor=standing[3],clips=counts,
                limitation='Offscreen component test. Native story and camera occlusion require separate live evidence.')


if __name__=='__main__':
    root=Path(sys.argv[1]);result=check(root)
    (root/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
