"""Check mixed body/effect rendering, native seated flows and background recovery evidence."""
import json
import sys
from pathlib import Path


def check(root):
    def read(name):
        return json.loads((root / name).read_text(encoding='utf-8-sig'))

    fixture = read('static-fixture/result.json')
    assert fixture['passed'] and not fixture['errors'] and len(fixture['frames']) == 15
    mixed = [f for f in fixture['frames'] if f['label'].startswith('Mixed_Hit_')]
    assert len(mixed) == 6
    for frame in mixed:
        index = int(frame['label'].rsplit('_', 1)[1])
        body = index in (0, 2, 3, 4)
        assert frame['replaced'] == frame['originalHidden'] == body
        native = (root / 'static-fixture' / (frame['label'] + '-native.png')).read_bytes()
        replacement = (root / 'static-fixture' / (frame['label'] + '-steve.png')).read_bytes()
        assert (native != replacement) == body

    locked = read('probe-lock.json')
    result = read('live/lock-regression.json')
    assert locked['requestRetainedWhileLocked'] and result.get('complete') and 'error' not in result
    held = read('late-load-held.json')
    recovered = read('late-load-recovered.json')
    identity = read('late-load-identity.json')
    assert held['observed'] and held['elapsedSeconds'] >= 120
    assert held['snapshot']['checkpointError'] == 'Minecraft world load timed out; committed checkpoint retained'
    assert not held['snapshot']['checkpointReady']
    assert recovered['connected'] and recovered['ready'] and recovered['checkpointReady']
    assert recovered['checkpointError'] is None
    assert identity['selection']['id'] == identity['response']['id'] and identity['response']['status'] == 'ready'

    cases = []
    for place, scene in [('lake', 'Crossroads_50'), ('marissa', 'Ruins_Bathhouse')]:
        for item in ('sword', 'pickaxe'):
            label = place + '-' + item
            sit = read('live/' + label + '-sit.json')
            rise = read('live/' + label + '-rise.json')
            assert sit.get('complete') and rise.get('complete')
            samples = sit['samples'] + rise['samples']
            story = sit['storySamples'] + rise['storySamples']
            assert all(s['hp'] == 5 for s in samples)
            assert all(s['HiddenWindow'] and s['visibleWindows'] == 0 and not s['ownsForegroundWindow'] for s in samples)
            assert all(s['scene'] == scene for s in story)
            seated = [a for s in story for a in s['actors'] if a['name'] == 'Knight Sit' and a['active'] and a['visible']]
            assert {'Knight Sit', 'Knight Sit End'} <= {a['clip'] for a in seated}
            assert all(a['library'] == 'Quirrel' and a['hidden'] for a in seated)
            assert all(a['hidden'] for s in story for a in s['actors'] if a['name'] == 'Knight' and a['active'] and a['visible'])
            assert not sit['samples'][-1]['acceptingInput']
            final = rise['samples'][-1]
            assert final['acceptingInput'] and not final['controlReqlinquished']
            assert final['native'] == (item == 'sword')
            assert abs(final['x'] - rise['samples'][0]['x']) > .5
            foot_errors = []
            for sample in sit['storySamples']:
                actor = next((a for a in sample['actors'] if a['name'] == 'Knight Sit' and a['active'] and a['visible']), None)
                if actor and sample['rigBounds']:
                    rig = min(sample['rigBounds'], key=lambda r: abs(r['x'] - actor['x']))
                    foot_errors.append(abs(rig['minY'] - actor['minY']))
            assert len(foot_errors) > 5 and max(foot_errors) < .001
            if place == 'lake':
                npcs = [a for s in story for a in s['actors'] if a['name'] == 'Quirrel Lakeside' and a['active'] and a['visible']]
                assert npcs and all(not a['hidden'] for a in npcs)
            else:
                assert any(a['clip'] == 'Marissa Singing Loop' for s in sit['storySamples'] for a in s['sound'])
            peak = max(s['audioPeak'] for s in sit['storySamples'])
            assert peak > .001
            for data in (sit, rise):
                audio = data['audio']
                assert audio['channels'] == 2 and audio['sampleRate'] == 48000
                assert not audio['error'] and not audio['overflow'] and not audio['channelsChanged']
                assert abs(audio['timingErrorSeconds']) < .05
            cases.append(dict(label=label, scene=scene, clips=sorted({a['clip'] for a in seated}),
                nativeModeRestored=final['native'], maxFootError=max(foot_errors), audioPeak=peak,
                samples=len(samples), controlRestored=True, hp=5))

    runtime = read('live/runtime-final.json')
    assert runtime['PhysicsTimeouts'] == 0 and runtime['checkpointError'] is None and runtime['ready']
    monitor = read('background-monitor-ssd.json')
    assert monitor['passed'] and len(monitor['samples']) > 1000
    assert monitor['session']['hostPid'] == held['session']['hostPid']
    assert all(not s['owned'] for s in monitor['samples'])
    return dict(passed=True, staticSamples=15, bodyFramesReplaced=4, crystalFramesUnchanged=2,
        requestLockRetried=True, lateLoadErrorCleared=True, cases=cases,
        physicsTimeouts=0, maxPhysicsWaitMs=runtime['MaxPhysicsWaitMilliseconds'],
        foregroundSamples=len(monitor['samples']), limitations=[
            'Native scene entrances and quest flags were prepared in an isolated test profile.',
            'Input uses the native InControl test binding; hardware input latency is not measured.',
            'Marissa visuals were reviewed in captures; her Unity Animator is outside the tk2d actor telemetry.',
            'Synchronous frame capture is visual/audio evidence, not an FPS or frame-presentation test.',
            'The static fixture used the prior binary; subsequent changes only affect diagnostic request retry and checkpoint error status.',
            'The earlier USB terrain timeout and full performance gates remain open.'])


if __name__ == '__main__':
    print(json.dumps(check(Path(sys.argv[1])), indent=2))
