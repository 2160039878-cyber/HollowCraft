"""Check live TNT rounding, attenuation, native recoil restoration and scoped native hits."""
import json
import math
import sys
from pathlib import Path


def check(root):
    def read(name):return json.loads((root/(name+'.json')).read_text(encoding='utf-8-sig'))
    vectors=read('live/native-explosion-vectors')['cases']
    assert len(vectors)==52
    assert 'PASS: 52 native explosion vectors' in (root/'native-vector-check.txt').read_text(encoding='utf-8-sig')
    cases=[]
    for name in ('far','near','safe-shield'):
        data=read('live/'+('safe-shield-blast' if name=='safe-shield' else name))
        state=read('live/'+('safe-shield-runtime' if name=='safe-shield' else name+'-runtime'))
        assert data.get('complete') and state['PhysicsTimeouts']==0 and not state['checkpointError']
        blast=state['playerExplosion']
        impact=(1-blast['distance']/8)*blast['exposure']
        expected=(impact*impact+impact)*28+1
        assert abs(blast['raw']-expected)<.00001 and abs(blast['impact']-impact)<.000001
        assert blast['masks']==math.ceil(blast['raw']/4)
        assert blast['before']-blast['after']==blast['masks'] and not blast['immune']
        damage=[h for h in data['received'] if h['before']>h['after']]
        assert len(damage)==1 and damage[0]['amount']==blast['masks']
        recoil=[s for s in data['samples'] if s['recoiling'] and not s['recoilFrozen']]
        assert len(recoil)>=2 and all(s['RECOIL_VELOCITY']==15 for s in data['samples'])
        speed=15*blast['impact']
        assert all(abs(abs(s['physicsVelocityX'])-speed)<.001 and abs(s['physicsVelocityY']-speed*.5)<.001 for s in recoil)
        assert all(s['HiddenWindow'] and s['visibleWindows']==0 and not s['ownsForegroundWindow'] for s in data['samples'])
        cases.append(dict(name=name,rawDamage=blast['raw'],masks=blast['masks'],impact=blast['impact'],recoilSamples=len(recoil),horizontalSpeed=speed))
    assert cases[1]['horizontalSpeed']>cases[0]['horizontalSpeed']>0
    assert cases[2]['rawDamage']==1 and cases[2]['horizontalSpeed']==0
    standing=read('live/safe-standing')
    assert standing['colliderMinY']+standing['colliderHeight']<65
    shield=read('live/safe-shield-blast')
    feet_offset=standing['heroY']-standing['colliderMinY']
    position_error=max(abs(s['y']-feet_offset-s['mcY']/s['scale']) for s in shield['samples'])
    assert position_error<.05, 'Valid terrain support must remain aligned after the blast'
    normal=read('live/safe-normal-after-blast')
    assert normal.get('complete') and normal['damage'][0]['before']-normal['damage'][0]['after']==1
    assert all(s['RECOIL_VELOCITY']==15 for s in normal['samples'])
    assert any(s['recoiling'] and abs(abs(s['physicsVelocityX'])-15)<.001 and abs(s['physicsVelocityY']-7.5)<.001 for s in normal['samples'])
    boss=read('live/blast-boss-targeted')
    assert boss.get('complete')
    hits=[h for h in boss['hits'] if h['source']=='HollowCraft TNT blast']
    assert len(hits)==1 and hits[0]['name']=='False Knight New'
    hit=hits[0]
    assert not hit['IgnoreInvulnerable'] and not hit['invincible'] and hit['before']-hit['after']==hit['DamageDealt']>0
    assert 0<hit['MagnitudeMultiplier']<1.5
    impact=hit['MagnitudeMultiplier']/1.5
    assert hit['DamageDealt']==round(((impact*impact+impact)*28+1)*3)
    for label in ('safe-shield','blast-boss-targeted'):
        events=read('live/'+label+'-events')
        assert events[-1]['event']=='finished' and sum(e['event']=='exploded' for e in events)==1
    state=read('live/blast-boss-targeted-runtime')
    assert state['PhysicsTimeouts']==0 and not state['checkpointError']
    return dict(passed=True,nativeComparisonCases=52,playerCases=cases,ordinaryRecoilRestored=True,
        maximumFootPositionError=position_error,bossHit=hit,physicsTimeouts=0,
        limitations=['The first roof test teleported inside an uncut terrain tile and is excluded from locomotion acceptance.',
            'The first boss blast missed; only the targeted hit establishes enemy damage.',
            'The initial session ended across a system restart; the later sessions and profile restoration are recorded separately.',
            'This check covers the explosion rules change, not a repetition of the full game acceptance.'])


if __name__=='__main__':
    result=check(Path(sys.argv[1]))
    if len(sys.argv)>2:Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
