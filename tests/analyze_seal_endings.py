"""Verify native final-hit, absorption and FinalA/B movie dispatch evidence."""
import json
import statistics
import sys
from pathlib import Path


def check(root):
    def read(name):return json.loads((root/(name+'.json')).read_text(encoding='utf-8-sig'))
    results=[]
    for label,movie,last_frame,damage in [('a','FinalA',968,252),('b','FinalB',1143,360)]:
        fight=[read(p.stem) for p in root.glob('fight-*-'+label+'.json') if p.name.split('-')[1].isdigit()]
        hits=[h for d in fight for h in d['hits'] if h['name']=='Hollow Knight Boss' and h['before']>h['after']]
        assert hits and all(h['attackType']=='Nail' and h['DamageDealt']==21 for h in hits)
        assert sum(h['before']-h['after'] for h in hits)==damage
        assert {h['before']-h['after'] for h in hits}==({21} if label=='a' else {1,21})
        absorption=[read('absorb-'+label)]+([read('absorb-end-a')] if label=='a' else [])
        assert absorption[-1].get('cancelled') and absorption[-1]['reason']=='scene or peer changed'
        story=[s for d in absorption for s in d['storySamples']]
        assert all(s['gotShadeCharm']==(label=='b') for s in story)
        states={f['ActiveStateName'] for s in story for f in s['story'] if f['name']=='Boss Corpse' and f['FsmName']=='Corpse'}
        assert {'Sucking','Suck Flashing','Ramp Up','Chain Break','Final Suck','Stop Shake'}<=states
        hero=[a for s in story for a in s['actors'] if a['name']=='Knight' and a['active'] and a['visible']]
        assert hero and all(a['hidden'] for a in hero) and 'Focus' in {a['clip'] for a in hero}
        npc=[a for s in story for a in s['actors'] if a['name']=='Boss Corpse' and a['active'] and a['visible']]
        assert npc and all(not a['hidden'] for a in npc)
        hornet=[a for d in fight for s in d['storySamples'] for a in s['actors'] if a['name'].startswith('Hornet') and a['active'] and a['visible']]
        assert all(not a['hidden'] for a in hornet)
        if label=='b':assert {'Hornet Hold','Hornet Thread','Hornet Wound'}<={a['clip'] for a in hornet}
        else:assert not hornet
        for data in fight+absorption:
            assert all(s['HiddenWindow'] and s['visibleWindows']==0 and not s['ownsForegroundWindow'] for s in data['samples'])
            assert all(s['hp']==5 for s in data['samples'])
        film=read('film-'+label)
        assert film['request']['Name']==movie and film['request']['ObserveNative'] and film['controller']=='CinematicPlayer'
        assert not film['errors'] and film['endCallbacks']==1 and not film['skipSent']
        assert (film['firstReadyFrame'],film['endingFrame'])==(0,last_frame)
        assert film['beganInScene']=='Cinematic_Ending_'+label.upper()
        assert film['separateAudio']['channels']==2 and film['separateAudio']['frequency']==44100
        offsets=[s['audioTime']-s['time'] for s in film['samples'] if s['audioPlaying'] and s['isPlaying']]
        median=statistics.median(offsets)
        assert abs(median)<.1 and max(s['audioRms'] for s in film['samples'])>.001
        credits=read('credits-'+label)
        assert credits['scene']=='End_Credits' and credits['PhysicsTimeouts']==0 and not credits['checkpointSaving'] and not credits['checkpointError']
        results.append(dict(label=label,movie=movie,frames=[0,last_frame],nativeNailHits=len(hits),hpDamage=damage,
            nativeDamageAmounts=sorted({h['before']-h['after'] for h in hits}),hornetClips=sorted({a['clip'] or '' for a in hornet}),
            absorptionStates=sorted(states),audioMedianOffsetSeconds=median,endCallbacks=1,credits=True))
    return dict(passed=True,cases=results,scope='Native ending flow, outgoing sword damage and protagonist/NPC rendering; not a full boss-fight or performance acceptance.',
        limitations=['Prepared core-room entry and teleports between chain anchors; chains were broken by native sword input.',
            'SealFinish enters the native250HP final phase and temporarily protects the player; early combat phases are bypassed.',
            'Hornet intervention/cancellation and native1HP scripted hits are retained in branch B.',
            'No physical keyboard skip or full frame-by-frame visual review is claimed; recordings use synchronous PNG capture and cannot establish FPS.'])


if __name__=='__main__':
    print(json.dumps(check(Path(sys.argv[1])),indent=2))
