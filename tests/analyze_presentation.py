"""Check native-render timing and background isolation; do not infer physical display scanout."""
import json
import math
import statistics
import sys
from pathlib import Path


def check(root):
    def read(name):
        return json.loads((root/(name+'.json')).read_text(encoding='utf-8-sig'))

    def stats(values):
        assert values and all(math.isfinite(v) and v > 0 for v in values)
        worst = sorted(values, reverse=True)[:math.ceil(len(values)/100)]
        return dict(frames=len(values), meanFps=1000/statistics.mean(values),
                    low1Fps=1000/statistics.mean(worst), maxMs=max(values))

    def measure(name):
        data = read('live/'+name)
        assert data.get('complete') and not data['captures'] and not data['renderedFrames'], name
        context = data['renderContext']
        assert (context['width'], context['height']) == (1920, 1080)
        assert context['targetFrameRate'] == -1 and context['vSyncCount'] == 1
        assert context['cpuRecorderValid'] and context['gpuRecorderValid']
        assert 'RTX 4060' in context['graphicsDeviceName'] and 'i7-12700KF' in context['processorType']
        assert all(s['presentationMode'] and s['HiddenWindow'] and s['visibleWindows'] == 1
                   and not s['ownsForegroundWindow'] and s['screenWidth'] == 1920 and s['screenHeight'] == 1080
                   for s in data['samples'])
        death = min((h['t'] for h in data['received'] if h['after'] == 0), default=math.inf)
        frames = [f for f in data['nativeFrames'] if f['step'] > 0 and f['t'] < death]
        assert len(frames) >= 500, name
        assert abs(frames[-1]['cameraFrames']-frames[0]['cameraFrames']-len(frames)+1) <= 8
        timings = [f['timing'] for f in frames]
        assert all(b['frameStartTimestamp'] > a['frameStartTimestamp'] for a, b in zip(timings, timings[1:]))
        assert all(t['gpuFrameTime'] >= 0 and math.isfinite(t['gpuFrameTime']) for t in timings)
        gpu = [t['gpuFrameTime'] for t in timings if t['gpuFrameTime'] > 0]
        assert len(gpu) >= .95*len(timings), 'Insufficient GPU timing coverage'
        frequency = context['cpuTimerFrequency']
        assert frequency > 0
        intervals = [(b['cpuTimePresentCalled']-a['cpuTimePresentCalled'])*1000/frequency
                     for a, b in zip(timings, timings[1:])]
        result = dict(name=name, cpu=stats([t['cpuFrameTime'] for t in timings]), present=stats(intervals),
                      gpuMeanMs=statistics.mean(gpu), gpuMaxMs=max(gpu), gpuUnavailableFrames=len(timings)-len(gpu),
                      effectiveHits=sum(h['before'] > h['after'] for h in data['hits']),
                      receivedHits=sum(h['before'] > h['after'] for h in data['received']))
        state = read('live/'+name+'-runtime')
        assert state['PhysicsTimeouts'] == 0 and not state['checkpointError'] and state['statusWriteFailures'] == 0
        return result

    idle = measure('idle')
    combat = [measure(name) for name in ('falseknight', 'hornet', 'mantis', 'mantis-bow')]
    assert all(c['effectiveHits'] > 0 and c['receivedHits'] > 0 for c in combat)
    assert all(c['present']['meanFps'] >= 59.5 and c['present']['low1Fps'] >= 50 for c in combat)
    stress = measure('stress')
    assert stress['present']['maxMs'] < 100 and stress['cpu']['maxMs'] < 100
    events = read('live/stress-events')
    built = events[0]
    assert built['event'] == 'built' and built['components'] == 256 and built['tntCount'] == 20
    assert max(e.get('powered', 0) for e in events) == 256
    assert len([e for e in events if e['event'] == 'exploded']) == 20
    assert events[-1]['event'] == 'finished' and events[-1]['remaining'] == 0
    view = read('live/stress')['renderContext']
    low = [(built['min'][0]-view['OffsetX'])/view['K'], built['min'][1]/view['K']]
    high = [(built['max'][0]-view['OffsetX'])/view['K'], built['max'][1]/view['K']]
    assert all(view['worldMin'][i] <= low[i] < high[i] <= view['worldMax'][i] for i in (0, 1))
    terrain = read('terrain-summary')
    assert len(terrain['cases']) == 4 and terrain['afterCuts'] > terrain['beforeCuts']
    for case in terrain['cases']:
        name = case['name']
        assert read('live/'+name).get('complete')
        state = read('live/'+name+'-runtime')
        assert state['PhysicsTimeouts'] == 0 and not state['checkpointError']
        events = read('live/'+name+'-events')
        assert [e['tick'] for e in events if e['event'] == 'lever-on'] == [40]
        assert [e['tick'] for e in events if e['event'] == 'repeater-on'] == [44]
        assert len([e for e in events if e['event'] == 'exploded']) == 1
        assert events[-1]['event'] == 'finished' and events[-1]['remaining'] == 0
    aborted = read('live/'+terrain['abortedCase'])
    assert aborted.get('cancelled') and any(h['after'] == 0 for h in aborted['received'])
    assert read('live/'+terrain['abortedCase']+'-runtime')['PhysicsTimeouts'] == 0
    monitor = read('background-monitor')
    session = read('session')
    assert monitor['session']['hostPid'] == session['hostPid'] and monitor['passed']
    assert monitor['hostDesktop'] == session['backgroundDesktop'] != monitor['inputDesktop']
    assert len(monitor['samples']) > 1000 and not any(s['owned'] for s in monitor['samples'])
    return dict(passed=True, nativeRenderingGateMet=True, physicalDisplayScanoutMeasured=False,
                idle=idle, combat=combat, stress=stress, terrain=terrain,
                foregroundSamples=len(monitor['samples']), limitations=[
                    'Native Unity Present-call timestamps and GPU timings are measured on an inactive private desktop; physical display scanout and hardware input latency are not measured.',
                    'Unity returns zero for unavailable GPU timestamps. GPU summary statistics use available samples; every frame remains in the CPU and Present interval statistics.',
                    'Native graphics settings remain targetFrameRate=-1 and vSyncCount=1 on this 200Hz system. The separate forced-60FPS experiment did not meet the 1% submission-interval gate.',
                    'The historical USB terrain timeout is not reproduced in one wall blast and three ceiling blasts on the current NVMe build; its exact historical cause is not established.',
                    'One additional wall attempt was interrupted by native enemy death and scene change. The ceiling repeats used the upper platform; enemies remained active.',
                    'Warmup steps and scene loading are excluded; native hit-stop and damage during the measured windows are retained.',
                    'This phase does not repeat every earlier animation, cinematic, control and save acceptance case.'])


if __name__ == '__main__':
    result = check(Path(sys.argv[1]))
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result))
