"""Compare native sword/tool jumps recorded by the hidden game probe."""
import argparse
import json
from pathlib import Path


def analyze(root, result_name):
    def read(name):
        return json.loads((root / name).read_text(encoding='utf-8-sig'))
    result, cases = read(result_name), read('v21-cases.json')
    assert result.get('complete'), 'Native probe did not complete'
    samples = result['samples']
    assert samples and all(s['HiddenWindow'] and s['visibleWindows'] == 0
        and not s['ownsForegroundWindow'] and s['hp'] == 5 for s in samples)
    measurements = {}
    for case in cases:
        rows = [s for s in samples if case['start'] <= s['step'] <= case['end']]
        base = [s for s in rows if s['step'] == case['start']][-1]
        active = [s for s in rows if s['step'] > case['start']]
        assert base['ground'] and rows[-1]['ground'] and not base['atBench']
        assert all(s['native'] == (case['slot'] == 1) and not s['recoiling'] for s in active)
        assert max(s['AirJumpUsed'] for s in active) == int(case['kind'] == 'double')
        assert rows[-1]['AirJumpUsed'] == 0, 'Landing did not restore the shared jump budget'
        key = (case['kind'], case['hold'])
        measurements.setdefault(key, {})[case['slot']] = dict(
            height=max(s['physicsY'] for s in rows) - base['physicsY'],
            pressTicks=rows[-1]['JumpReleaseTick'] - rows[-1]['JumpPressTick'],
            actualHold=rows[-1]['JumpHeldSeconds'])
    comparisons = []
    for (kind, hold), modes in measurements.items():
        native, tool = modes[1], modes[2]
        assert native['pressTicks'] == tool['pressTicks'], 'Input durations crossed different physics boundaries'
        difference = tool['height'] - native['height']
        # Native floor skin and sampled/interpolated positions are not exact mathematical points.
        assert abs(difference) < .06, (kind, hold, difference)
        comparisons.append(dict(kind=kind, requestedHold=hold, native=native, tool=tool, difference=difference))
    summary = dict(passed=True, source=result_name, samples=len(samples), allUnfocused=True,
        unityReportedFocusedSamples=sum(s['focused'] for s in samples),
        health=5, comparisons=comparisons, heightToleranceUnityUnits=.06,
        scope='Stationary single/double jumps on clear native ground; excludes midair item swaps, ceilings and performance.')
    (root / 'verified-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--result', default='v21d-result.json')
    args = parser.parse_args()
    analyze(args.evidence, args.result)
