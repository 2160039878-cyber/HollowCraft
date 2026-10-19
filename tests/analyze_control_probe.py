"""Validate recorded ground/air control transfers; latency bounds include sample uncertainty."""
import argparse
import json
from pathlib import Path


def analyze(root, kind):
    def read(name):
        return json.loads((root / name).read_text(encoding='utf-8-sig'))
    plan, result = read(kind + '-plan.json'), read(kind + '-result.json')
    rows = result['samples']
    assert result.get('complete') and rows[-1]['step'] == plan['lastStep']
    assert all(s['HiddenWindow'] and s['visibleWindows'] == 0 and not s['ownsForegroundWindow'] for s in rows)
    assert all(s['hp'] == 5 and not s['attacking'] and not s['invulnerable'] and not s['recoiling'] for s in rows)
    bounds = []
    for request in plan['switches']:
        previous = [s for s in rows if s['step'] < request['step']][-1]
        samples = [s for s in rows if s['step'] == request['step']]
        native = request['slot'] == 1
        if 'requests' in result:
            sent = [r for r in result['requests'] if r['step'] == request['step'] and r['slot'] == request['slot']]
            assert len(sent) == 1, 'Request timestamp missing or duplicated'
            started = sent[0]['t']
            completed = [s for s in result['transfers'] if s['step'] == request['step'] and s['t'] >= started
                and s['native'] == native and bool(s['HeldFlags'] & 1) == native
                and s['ControlSeq'] == previous['ControlSeq'] + 1 and s['ControlAck'] == s['ControlSeq']]
        else:
            started = previous['t']
            completed = [s for s in samples if s['native'] == native and bool(s['heldFlags'] & 1) == native
                and s['ControlSeq'] == previous['ControlSeq'] + 1 and s['ControlAck'] == s['ControlSeq']]
        assert completed, ('Transfer missing or duplicated', request)
        upper = (completed[0]['t'] - started) * 1000
        assert upper <= 100, ('Request-to-ack bound exceeds 100 ms', request, upper)
        bounds.append(upper)
    assert len(bounds) == 100
    continuity_excess = 0
    for a, b in zip(rows, rows[1:]):
        if 'scale' not in b:
            continue
        dt = max(0, b['fixedTime'] - a['fixedTime'])
        speed = max(abs(a['physicsVelocityY']), abs(b['physicsVelocityY']),
            abs(a['VelocityY']) / b['scale'], abs(b['VelocityY']) / b['scale'], b['JumpVelocity'] * 1.1 / b['scale'])
        excess = abs(b['physicsY'] - a['physicsY']) - speed * dt
        continuity_excess = max(continuity_excess, excess)
        assert excess < .04, ('Position advanced farther than the physics steps permit', b['t'], excess)
    flights = []
    for flight in plan['flights']:
        samples = [s for s in rows if flight['start'] <= s['step'] <= flight['end']]
        base = [s for s in samples if s['step'] == flight['start']][-1]
        assert base['ground'] and samples[-1]['ground'] and samples[-1]['AirJumpUsed'] == 0
        used = [s for s in samples if s['step'] >= flight['airStart'] and s['AirJumpUsed'] == 1]
        assert used, 'Second jump did not consume the shared budget'
        # Ground contact belongs to the active controller; the mirrored Unity body can arrive a step later.
        airborne = [s for s in samples if used[0]['t'] <= s['t'] and
            (not s['ground'] if s['native'] else not s['mcGround'])]
        assert airborne and all(s['AirJumpUsed'] == 1 for s in airborne), 'Air jump budget reset before landing'
        third = [s for s in samples if s['step'] == flight['third']]
        assert third and all(not s['ground'] and s['AirJumpUsed'] == 1 and not s['doubleJumping']
            and not ((s['MotionState'] | s['mcMotionState']) & (1 << 25)) for s in third), 'Third jump was accepted'
        flights.append(dict(slot=flight['slot'], height=max(s['physicsY'] for s in samples) - base['physicsY']))
    if kind == 'ground':
        assert all(s['AirJumpUsed'] == 0 for s in rows)
        assert max(s['physicsY'] for s in rows) - min(s['physicsY'] for s in rows) < .05
        assert max(s['x'] for s in rows) - min(s['x'] for s in rows) < .05
    summary = dict(passed=True, kind=kind, transfers=len(bounds), samples=len(rows),
        timing='request/ack events on the game thread' if 'requests' in result else 'sampled conservative bounds',
        maximumRequestToAcknowledgementUpperBoundMs=max(bounds),
        maximumSampleIntervalMs=max(b['t'] - a['t'] for a, b in zip(rows, rows[1:])) * 1000,
        maximumContinuityExcessUnityUnits=continuity_excess,
        hidden=True, hp=5, extraAttacks=0, invulnerabilityStarts=0, flights=flights,
        scope='Scripted native input; excludes hardware latency, active damage/invulnerability transitions and visual/performance acceptance.')
    (root / (kind + '-summary.json')).write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('kind', choices=['ground', 'air'])
    args = parser.parse_args()
    analyze(args.evidence, args.kind)
