"""Check the recorded native terrain, control and checkpoint regression evidence."""
import argparse
import json
from pathlib import Path


def covers(renderer, point):
    vertices, triangles = renderer['vertices'], renderer['triangles']
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    for i in range(0, len(triangles), 3):
        a, b, c = (vertices[j] for j in triangles[i:i+3])
        if abs(cross(a, b, c)) < 1e-7:
            continue
        sides = cross(a, b, point), cross(b, c, point), cross(c, a, point)
        if min(sides) >= -1e-6 or max(sides) <= 1e-6:
            return True
    return False


def analyze(root):
    def read(name):
        return json.loads((root/(name+'.json')).read_text(encoding='utf-8-sig'))
    def completed(name):
        data = read(name)
        assert data.get('complete'), (name, data.get('reason', data.get('error')))
        assert data['samples']
        assert all(s['HiddenWindow'] and s['visibleWindows'] == 0 and not s['ownsForegroundWindow'] for s in data['samples']), name
        return data
    def clear_axis(data, axis):
        assert data['Pending'] == 0
        assert not any(r['hits'] for r in data['rays'] if r['direction'][axis]), data['rays']
    def cells(data):
        return {tuple(c) for c in data['removed']}

    before, after = read('wall-cutpoint-01'), read('fixed-after')
    chunk = 'TileMap Render Data/Scenemap/Chunk 2 1'
    original = next(r for r in before['renderers'] if r['path'] == chunk)
    cut = next(r for r in after['renderers'] if r['path'] == chunk)
    assert covers(original, before['point']) and not covers(cut, after['point'])
    assert len(cut['uv']) == len(cut['vertices']) and cut['materials'] == original['materials']
    wall = read('mesh-fixed-after-reset')
    clear_axis(wall, 0)
    assert cells(wall) == cells(read('mesh-fixed-before-reset'))
    for name, native in [('dash-cross', True), ('tool-jump-cross', False)]:
        rows = completed(name)['samples']
        assert rows[0]['x'] < 56 and max(s['x'] for s in rows) > 60, name
        assert any(s['native'] == native and s['x'] > 58 for s in rows), name

    ceiling = read('ceiling-under-after-2')
    clear_axis(ceiling, 1)
    for i in range(3):
        events = read('ceiling-under-events-'+str(i))
        assert [e['event'] for e in events] == ['built', 'lever-on', 'repeater-on', 'exploded', 'finished']
        assert [e['tick'] for e in events] == [0, 40, 44, 123, 180]
        assert events[3]['power'] == 4 and events[-1]['remaining'] == 0
    for name, native in [('ceiling-drop-native', True), ('ceiling-drop-tool-stable', False)]:
        rows = completed(name)['samples']
        assert max(s['y'] for s in rows) > 70 and min(s['y'] for s in rows) < 63, name
        assert all(s['native'] == native for s in rows if 63 < s['y'] < 70), name
    mask = next(f for f in read('ceiling-drop-native-visuals')['sceneFsms'] if f['path'] == 'Secret Mask')
    assert mask['ActiveStateName'] == 'Fade'
    for name, earlier, axis in [('wall-reloaded', wall, 0), ('ceiling-reloaded', ceiling, 1)]:
        restored = read(name)
        assert cells(restored) == cells(earlier), name
        clear_axis(restored, axis)

    before = read('gravity-before-fix')
    assert before['gravityScale'] == 0 and before['native'] and before['heroInput']
    recoil = completed('gravity-recoil-swap')
    assert len(recoil['damage']) == 1 and recoil['damage'][0]['before']-recoil['damage'][0]['after'] == 1
    rows = recoil['samples']
    assert any(s['recoiling'] for s in rows) and max(s['y'] for s in rows)-rows[-1]['y'] > 2
    assert rows[-1]['ground'] and rows[-1]['native'] and rows[-1]['gravityScale'] > 0
    rows = completed('gravity-bench')['samples']
    seated = [s for s in rows if s['step'] == 2]
    assert seated and all(s['atBench'] and s['gravityScale'] == 0 for s in seated)
    assert rows[-1]['ground'] and not rows[-1]['atBench'] and rows[-1]['gravityScale'] > 0
    runtime = read('terrain-final-runtime')
    assert runtime['ready'] and runtime['PhysicsTimeouts'] == 0 and not runtime['checkpointError']
    return dict(passed=True, wallCells=len(cells(wall)), ceilingCells=len(cells(ceiling)),
                wallAndCeilingTraversedInBothModes=True, checkpointReloadMatched=True,
                nativeSecretRevealPreserved=True, recoilAndBenchGravityPassed=True,
                backgroundOnly=True, finalProcessPhysicsTimeouts=0,
                earlierPhysicsTimeoutPreserved=read('gravity-before-fix')['PhysicsTimeouts'],
                limitations=['Geometry acceptance covers Ruins2_01, not every room.',
                             'The earlier 41.98ms Minecraft reply timeout remains unresolved.',
                             'Captured frames include readback overhead and do not establish presentation FPS.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = analyze(args.evidence)
    text = json.dumps(result, indent=2)+'\n'
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    print(text)
