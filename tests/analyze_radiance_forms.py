"""Verify native protagonist replacement, preserved clips, mirroring and asset scope."""
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path


def analyze(root,geometry_path):
    result=json.loads((root/'result.json').read_text(encoding='utf-8-sig'))
    assert result['passed'] and result['defaultRadianceReplaced'] and result['errors']==[]
    assert result['scene']=='Menu_Title' and result['resolution']==[1920,1080]
    player={'Knight Ball':4,'Knight Form':15,'Knight Idle':8,'Slash1 Antic':3,'Slash1':2,
            'Slash2 Antic':3,'Slash2':2,'Knight Unform':10,'Knight Pull':1,'Knight Hang':8,
            'Knight Split Antic':4,'Knight Split':4}
    preserved={'HollowShade Rise':1,'HollowShade 1':6,'HollowShade 2':12,'HollowShade 3':8,
               'HollowShade 4':3,'BG Shade 1':6,'BG Shade 2':6,'BG Shade 3':6,'BG Shade 4':6,'Eye Struggle':3}
    seen=set();counts={'protagonist':0,'preserved':0,'mirrored':0}
    for f in result['frames']:
        clip,index,mirror=f['clip'],f['frame'],f['mirrored']
        assert clip in player or clip in preserved
        assert 0<=index<(player|preserved)[clip] and (clip,index,mirror) not in seen
        seen.add((clip,index,mirror));change=clip in player
        assert f['replaced']==change and f['originalHidden']==change
        if mirror:assert clip in ('Knight Idle','Slash1','Knight Hang') and index==0
        prefix=f"radiance-{'mirror-' if mirror else ''}{clip.replace(' ','_')}-{index:02d}"
        images=[(root/f'{prefix}-{name}.png').read_bytes() for name in ('native','steve')]
        assert all(data[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('!II',data[16:24])==(1920,1080) for data in images)
        assert (hashlib.sha256(images[0]).digest()!=hashlib.sha256(images[1]).digest())==change
        counts['mirrored' if mirror else 'protagonist' if change else 'preserved']+=1
    assert counts=={'protagonist':64,'preserved':57,'mirrored':3}
    geometry=json.loads(geometry_path.read_text(encoding='utf-8-sig'))
    assert set(geometry['clips'])==set(player) and len(geometry['sprites'])==53
    assert all(len(geometry['clips'][name]['frames'])==count for name,count in player.items())
    for sprite in geometry['sprites'].values():
        assert sprite['kind'] in ('ball','void','skin') and .1<sprite['scale']<4
        assert all(math.isfinite(v) for v in sprite['anchor'])
        if sprite['beam']:
            assert len(sprite['beam'])==2 and len(sprite['beamStyle'])==3
            assert all(math.isfinite(v) for point in sprite['beam'] for v in point)
    summary=dict(passed=True,**counts,staticDefaultReplaced=True,
                 limitations='Native component fixture only; not actual Dream_Final_Boss/GG_Radiance scene flow, audio or performance acceptance.')
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('probe',type=Path);parser.add_argument('geometry',type=Path)
    args=parser.parse_args();analyze(args.probe,args.geometry)
