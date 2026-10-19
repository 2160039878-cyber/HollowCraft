"""Check hidden 1080p rendering evidence; report failed FPS gates without relabeling them."""
import json
import math
import statistics
import sys
from pathlib import Path


def check(root):
    def read(name):
        return json.loads((root / (name + '.json')).read_text(encoding='utf-8-sig'))

    def distribution(values):
        assert values and all(math.isfinite(v) and v >= 0 for v in values)
        worst = sorted(values, reverse=True)[:math.ceil(len(values) / 100)]
        return dict(meanMs=statistics.mean(values), maxMs=max(values),
                    worst1MeanMs=statistics.mean(worst), over100Ms=sum(v > 100 for v in values))

    def measured(name, steps=None):
        data = read(name)
        assert data.get('complete') and not data.get('cancelled'), name
        assert not data['captures'], 'PNG encoding must stay outside measured frames'
        context = data['renderContext']
        assert (context['width'], context['height'], context['targetFrameRate']) == (1920, 1080, 60)
        assert 'ReadPixels' in context['completion'] and not context['avatarTextureDiagnostics']
        assert data['samples'] and all(s['HiddenWindow'] and s['visibleWindows'] == 0
                                      and not s['ownsForegroundWindow'] for s in data['samples'])
        death = min((h['t'] for h in data['received'] if h['after'] == 0), default=math.inf)
        frames = [f for f in data['renderedFrames'] if f['step'] > 0 and f['t'] < death
                  and (steps is None or f['step'] in steps)]
        assert len(frames) >= 500 and all(f['cameras'] >= 4 for f in frames), name
        metrics = {k: distribution([f[k] for f in frames]) for k in
                   ('engineMs', 'intervalMs', 'renderMs', 'statusMs', 'physicsMs')}
        for key in ('runtimeMs', 'probeMs', 'drainMs', 'replicaMs'):
            if key in frames[0]:
                metrics[key] = distribution([f[key] for f in frames])
        for key in ('engineMs', 'intervalMs'):
            metrics[key]['meanFps'] = 1000 / metrics[key]['meanMs']
            metrics[key]['low1Fps'] = 1000 / metrics[key]['worst1MeanMs']
        hits = [h for h in data['hits'] if h['before'] > h['after']]
        return dict(source=name, frames=len(frames), backgroundSamples=len(data['samples']),
                    measuredSeconds=sum(f['intervalMs'] for f in frames) / 1000,
                    deathExcludedAt=None if math.isinf(death) else death,
                    effectiveHits=len(hits), hpDamage=sum(h['before'] - h['after'] for h in hits),
                    metrics=metrics)

    stress = measured('stress-prewarm-measured')
    assert stress['frames'] >= 1700
    events = read('stress-prewarm-events')
    built = events[0]
    assert built['event'] == 'built' and built['components'] == 256 and built['tntCount'] == 20
    assert events[-1]['event'] == 'finished' and events[-1]['remaining'] == 0
    assert max(e.get('powered', 0) for e in events) == 256
    explosions = [e for e in events if e['event'] == 'exploded']
    assert len(explosions) == 20 and all(e['power'] == 4 for e in explosions)
    assert any(e['dugCellsAtPlane'] for e in explosions)
    view = read('stress-view-prewarm')['renderContext']
    low = [(built['min'][0] - view['OffsetX']) / view['K'], built['min'][1] / view['K']]
    high = [(built['max'][0] - view['OffsetX']) / view['K'], built['max'][1] / view['K']]
    assert all(view['worldMin'][i] <= low[i] < high[i] <= view['worldMax'][i] for i in (0, 1))
    runtime = read('stress-prewarm-runtime')
    assert runtime['PhysicsTimeouts'] == 0 and runtime['statusWriteFailures'] == 0
    timeline = read('stress-prewarm-status-timeline')
    assert len(timeline) > 250 and all('error' not in t and t['ready'] and t['timeouts'] == 0
                                     and t['statusWriteFailures'] == 0 for t in timeline)
    freshness = max(t['unix'] - t['mtime'] for t in timeline)
    assert freshness < 2
    log = (root / 'minecraft-07.log').read_text(encoding='utf-8', errors='replace')
    atlas = log.index('sent texture minecraft:textures/atlas/particles.png')
    assert atlas < log.index('Redstone probe armed at tick 0')
    prior = read('stress-final-measured')
    assert prior.get('cancelled') and prior['reason'] == 'Minecraft physics timed out'
    prior_timeout = read('stress-final-runtime')['LastPhysicsTimeout']
    assert prior_timeout['replyTick'] < prior_timeout['expectedTick'] and prior_timeout['elapsed'] >= 40
    sword = measured('render-combat-hornet')
    bow = measured('render-combat-bow')
    assert sword['effectiveHits'] > 0 and bow['effectiveHits'] == 13 and bow['hpDamage'] == 255
    assert {h['attackType'] for h in read('render-combat-hornet')['hits']} == {'Nail'}
    assert all(s['heldFlags'] == 2 for s in read('render-combat-bow')['samples'])
    assert read('combat-runtime-before-quit')['PhysicsTimeouts'] == 0
    idle = measured('profile-components-idle')
    mixed = measured('profile-combat-mixed')
    assert mixed['effectiveHits'] > 0
    gate = lambda x: 59.5 <= x['metrics']['intervalMs']['meanFps'] <= 60.5 and x['metrics']['intervalMs']['low1Fps'] >= 50
    return dict(evidenceChecksPassed=True, stressNo100msStall=all(stress['metrics'][k]['maxMs'] <= 100 for k in ('engineMs', 'intervalMs')),
                regularCombatFpsPassed=all(gate(x) for x in (sword, bow, mixed)),
                displayPresentationMeasured=False, overallPerformanceAccepted=False,
                stress=stress, sword=sword, bow=bow, instrumentedIdle=idle, instrumentedMixedCombat=mixed,
                fixture=dict(components=256, powered=256, tntExplosions=20, remainingTnt=0,
                             nativeBounds=[low, high], viewport=[view['worldMin'], view['worldMax']],
                             scope='Full fixture inside viewport; HUD and native chains can occlude parts.'),
                statusFreshnessMaxSeconds=freshness, previousTimeout=prior_timeout,
                limitations=['Offscreen synchronous GPU completion is measured, not display presentation.',
                             'Warmup step 0 and frames after player death are excluded; native hit-stop remains included.',
                             'One percent low is 1000 divided by the mean of the slowest ceil(N/100) intervals.',
                             'Mean target uses 60 +/- 0.5 FPS; the independent 50 FPS low-frame gate is not relaxed.',
                             'The stress fixture measures redstone/TNT load with the player away from the blast; damage and traversability use separate acceptance evidence.',
                             'The prewarm change passed one cold-JVM stress run; it does not establish the cause of older intermittent bow stalls.'])


if __name__ == '__main__':
    result = check(Path(sys.argv[1]))
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(text, encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('evidenceChecksPassed', 'stressNo100msStall',
                                          'regularCombatFpsPassed', 'displayPresentationMeasured',
                                          'overallPerformanceAccepted')}))
