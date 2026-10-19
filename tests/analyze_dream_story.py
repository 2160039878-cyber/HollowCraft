"""Check a prepared Seer-upgrade fixture driven by native movement/dialogue input."""
import argparse
import array
import json
import math
from pathlib import Path
from PIL import Image, ImageStat


def analyze(path):
    d = json.loads(path.read_text(encoding='utf-8-sig'))
    assert d.get('complete') and not d.get('damage')
    rows, story = d['samples'], d['storySamples']
    assert len(story) > 100 and all(s['scene'] == 'RestingGrounds_07' for s in story)
    assert not story[0]['upgraded'] and story[-1]['upgraded']
    assert story[-1]['acceptingInput'] and not story[-1]['controlReqlinquished']
    assert all(s['HiddenWindow'] and s['visibleWindows'] == 0 and not s['ownsForegroundWindow'] for s in rows)
    assert min(s['hp'] for s in rows) == max(s['hp'] for s in rows)
    states = [f['ActiveStateName'] for s in story for f in s['story'] if f['FsmName'] == 'Conversation Control']
    needed = ['Reward 8', 'Get DN Upgrade', 'Nail Flash', 'Casting', 'Boom', 'Msg', 'DN End', 'Dn Got']
    positions = [states.index(name) for name in needed]
    assert positions == sorted(positions) and states[-1] == 'Idle'
    visible = [(s, a) for s in story for a in s['actors'] if a['name'] == 'Knight Dummy' and a['active'] and a['visible']]
    assert {'DN Get 2', 'DN Get 3', 'DN End'} <= {a['clip'] for _, a in visible}
    assert all(a['hidden'] and s['rigs'] >= 12 and s['controlReqlinquished'] for s, a in visible)
    assert all(not a['hidden'] for s in story for a in s['actors'] if a['name'] == 'Dream Moth')
    assert any(a['name'] == 'Knight Dummy' and not a['active'] and not a['hidden'] for a in story[-1]['actors'])
    assert [a['key'] for a in d['suppressedAchievements']] == ['AWAKENING']
    audio = d['audio']
    assert audio and not audio['error'] and not audio['overflow'] and not audio['channelsChanged']
    assert abs(audio['timingErrorSeconds']) < .1 and audio['duration'] > 20
    pcm = array.array('f'); pcm.frombytes(Path(audio['path']).read_bytes())
    assert len(pcm) == audio['samples'] and all(math.isfinite(v) for v in pcm)
    rms = math.sqrt(sum(v*v for v in pcm)/len(pcm)); assert rms > .001
    capture = Path(d['captureDirectory'])
    assert all((capture / f"{f['index']:05}.png").is_file() for f in d['captures'])
    first = visible[0][0]['t']
    frame = min(d['captures'], key=lambda f: abs(f['t'] - first))
    image = Image.open(capture / f"{frame['index']:05}.png").convert('RGB')
    assert image.size == (1920, 1080) and max(ImageStat.Stat(image).stddev) > 10
    summary = dict(passed=True, seconds=rows[-1]['t'], nativeStates=needed, visibleReplacementSamples=len(visible),
        captures=len(d['captures']), restoredNativeControl=True, originalNpcPreserved=True, health=rows[-1]['hp'],
        platformAchievementSuppressed='AWAKENING', audioRms=rms, audioTimingErrorSeconds=audio['timingErrorSeconds'],
        scope='Prepared1800essence isolated save; native Seer upgrade FSM, dialogue and input. Full game progression is not exercised.',
        limitations='Capture overhead excludes performance acceptance. Native HK audio only; normal world-traversal music transitions were not separately checked. First Dream Nail acquisition and other story flows remain unverified.')
    path.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('probe', type=Path)
    analyze(p.parse_args().probe)
