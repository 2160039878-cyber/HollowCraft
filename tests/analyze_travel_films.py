"""Check native nailmaster rewards, seated-player replacement and stag round trip."""
import json
import statistics
import sys
from pathlib import Path


def check(root):
    def read(name):return json.loads((root/(name+'.json')).read_text(encoding='utf-8-sig'))
    cases=[]
    for label,movie,scene,skill,last_frame in [
        ('mato-clean','Nailsmith','Room_nailmaster','hasCyclone',129),
        ('sheo-01','NailsmithPaint','Room_nailmaster_02','hasDashSlash',315),
        ('oro-01','Nailsmith','Room_nailmaster_03','hasUpwardSlash',129),
    ]:
        film=read('film-'+label)
        assert not film['errors'] and film['endCallbacks']==1 and not film['skipSent']
        assert film['controller']=='CinematicPlayer' and film['beganInScene']==scene
        assert film['request']['Name']==movie and film['request']['ObserveNative']
        assert (film['firstReadyFrame'],film['endingFrame'])==(0,last_frame)
        assert film['separateAudio']['channels']==2 and film['separateAudio']['frequency']==44100
        offsets=[s['audioTime']-s['time'] for s in film['samples'] if s['isPlaying'] and s['audioPlaying']]
        offset=statistics.median(offsets)
        assert abs(offset)<.1 and max(s['audioRms'] for s in film['samples'])>.001
        assert not read('near-'+label)['storySamples'][-1][skill]
        returns=sorted(root.glob('return-*-'+label+'.json'),key=lambda p:int(p.name.split('-')[1]))
        final=json.loads(returns[-1].read_text(encoding='utf-8-sig'))
        last=final['storySamples'][-1]
        assert last[skill] and last['acceptingInput'] and not last['controlReqlinquished']
        story=[];samples=[]
        for path in root.glob('*-'+label+'.json'):
            data=json.loads(path.read_text(encoding='utf-8-sig'))
            if isinstance(data,dict) and 'storySamples' in data:
                story.extend(data['storySamples']);samples.extend(data['samples'])
        states={f['ActiveStateName'] for s in story for f in s['story'] if f['FsmName']=='Conversation Control' and f['name'].startswith('NM ')}
        assert {'Cinematic','Get Msg','Taught Msg'}<=states
        assert not last['fixtureInvincible']
        assert all(not s['fixtureInvincible'] or not s['acceptingInput'] for s in story)
        assert all(a['hidden'] for s in story for a in s['actors'] if a['name']=='Knight' and a['active'] and a['visible'])
        assert all(not a['hidden'] for s in story for a in s['actors'] if a['name'].startswith('NM ') and a['active'] and a['visible'])
        assert samples and all(s['HiddenWindow'] and s['visibleWindows']==0 and not s['ownsForegroundWindow'] for s in samples)
        cases.append(dict(label=label,scene=scene,movie=movie,frames=[0,last_frame],reward=skill,
            restoredControl=True,audioMedianOffsetSeconds=offset,states=sorted(states),geoAfter=last.get('geo')))

    sitting=read('sitting-mato-grounded');rising=read('rise-grounded')
    actors=[a for d in [sitting,rising] for s in d['storySamples'] for a in s['actors'] if a['name']=='Knight Sit' and a['active'] and a['visible']]
    assert {'Knight Sit','Knight Sit End'}<={a['clip'] for a in actors}
    assert all(a['library']=='Quirrel' and a['hidden'] for a in actors)
    assert any(s['rigs']>0 for s in sitting['storySamples'])
    floor_errors=[]
    for s in sitting['storySamples']:
        actor=next((a for a in s['actors'] if a['name']=='Knight Sit' and a['visible']),None)
        if actor and s['rigBounds']:
            rig=min(s['rigBounds'],key=lambda r:abs(r['x']-actor['x']))
            floor_errors.append(abs(rig['minY']-actor['minY']))
    assert len(floor_errors)>10 and max(floor_errors)<.001
    assert all(not a['hidden'] for s in sitting['storySamples'] for a in s['actors'] if a['name']=='NM Mato NPC')
    assert rising['samples'][-1]['acceptingInput'] and abs(rising['samples'][-1]['x']-rising['samples'][0]['x'])>1

    travel=[]
    for label,destination,skipped in [('stag-02','Crossroads_47',False),('stag-return','Room_Town_Stag_Station',True)]:
        film=read('film-'+label);arrival=read('arrive-'+label);runtime=read('runtime-'+label)
        assert not film['errors'] and film['endCallbacks']==1 and film['skipSent']==skipped
        assert film['controller']=='CinematicSequence' and film['beganInScene']=='Cinematic_Stag_travel'
        assert film['endedInScene']==destination and runtime['scene']==destination and runtime['ready']
        assert film['firstReadyFrame']==0 and film['separateAudio'] is None
        assert max(s['audioRms'] for s in film['samples'])>.001
        max_frame=max(s['frame'] for s in film['samples'])
        if skipped:
            assert film['skipModeAtRequest']=='SKIP_INSTANT' and 1.8<=film['skipVideoTime']<2
            assert max_frame<100
        else:assert max_frame>=100
        assert arrival.get('complete') and arrival['samples'][-1]['acceptingInput']
        windows=read('windows-'+label)
        assert len(windows)>200 and all(s['visible']==0 and not s['ownsForeground'] for s in windows)
        travel.append(dict(label=label,destination=destination,skipped=skipped,observedMaxFrame=max_frame,
            callbackFrame=film['endingFrame'],audioPeak=max(s['audioRms'] for s in film['samples']),windowSamples=len(windows)))

    for name in ['sheo-control-after','return-control-final']:
        samples=read(name)['samples']
        assert abs(samples[-1]['x']-samples[0]['x'])>1 and max(s['y'] for s in samples)>samples[0]['y']+.5
        assert samples[-1]['acceptingInput'] and all(s['hp']==5 for s in samples)
    final=read('runtime-final')
    assert final['PhysicsTimeouts']==0 and final['checkpointReady'] and not final['checkpointSaving'] and not final['checkpointError']
    return dict(passed=True,nailmasters=cases,seatedActor=dict(clips=sorted({a['clip'] for a in actors}),visibleSamples=len(actors),npcPreserved=True,maxFootAlignmentError=max(floor_errors)),
        travel=travel,physicsTimeouts=0,limitations=[
            'Prepared scene entrances; Oro was allocated800geo and the stag fixture pre-opened Dirtmouth/Crossroads.',
            'Stag ends after native scene loading; video.frame is already-1 in its end callback. Observed max frame is not claimed as the final decoded frame.',
            'Stag skip uses GameManager.SkipCutscene when the native mode permits; physical keyboard skip is not asserted.',
            'The initial captured Mato movie was slowed by synchronous PNG capture; audio timing acceptance uses the clean uncaptured runs.',
            'An initial Sheo helper checked the wrong legacy reward field; the native FSM grants hasDashSlash and that observed field is verified here.',
            'No1080p FPS/redstone/TNT stress or full-game progression acceptance is implied.'])


if __name__=='__main__':
    print(json.dumps(check(Path(sys.argv[1])),indent=2))
