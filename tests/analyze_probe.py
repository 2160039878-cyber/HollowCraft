"""Summarize observed runtime handoffs; never substitutes for damage or visual acceptance."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('input', type=Path)
parser.add_argument('output', type=Path)
parser.add_argument('--steps', type=Path)
args = parser.parse_args()
data = json.loads(args.input.read_text(encoding='utf-8-sig'))
assert data.get('complete'), data.get('error', 'Probe did not finish')
samples = data['samples']
assert samples
groups = {}
for sample in samples:
    groups.setdefault(sample['ControlSeq'], []).append(sample)
latencies = []
for generation, values in list(groups.items())[1:]:
    ack = next((s for s in values if s['ControlAck'] == generation), None)
    assert ack, f'Control generation {generation} never acknowledged'
    first = samples.index(values[0])
    latencies.append(ack['t'] - samples[max(0, first - 1)]['t'])
air_reset = [(a['t'], b['t']) for a, b in zip(samples, samples[1:])
             if not a['ground'] and not b['ground'] and a['AirJumpUsed'] and not b['AirJumpUsed']]
health_gains = [(b['t'], a['hp'], b['hp']) for a, b in zip(samples, samples[1:]) if b['hp'] > a['hp']]
immune_starts = []
last_damage = float('-inf')
for a, b in zip(samples, samples[1:]):
    if b['hp'] < a['hp']:
        last_damage = b['t']
    if not a.get('invulnerable', False) and b.get('invulnerable', False) and b['t'] - last_damage > 1:
        immune_starts.append(b['t'])
request_delays = []
if args.steps:
    commands = json.loads(args.steps.read_text(encoding='utf-8-sig'))
    for i, command in enumerate(commands):
        slot = command.get('Slot', 0)
        if slot not in (1, 2):
            continue
        indices = [n for n, s in enumerate(samples) if s['step'] == i]
        assert indices, f'No samples for input step {i}'
        ack = next((samples[n] for n in indices if samples[n]['native'] == (slot == 1)
                    and samples[n]['ControlAck'] == samples[n]['ControlSeq']), None)
        assert ack, f'Input step {i} did not reach its requested controller'
        request_delays.append(ack['t'] - samples[max(0, indices[0] - 1)]['t'])
result = {
    'source': args.input.name,
    'samples': len(samples),
    'durationSeconds': samples[-1]['t'],
    'observedControlTransfers': samples[-1]['ControlSeq'] - samples[0]['ControlSeq'],
    'maximumAckDelayUpperBoundMs': round(max(latencies, default=0) * 1000, 3),
    'maximumSamplingIntervalMs': round(max(b['t'] - a['t'] for a, b in zip(samples, samples[1:])) * 1000, 3),
    'horizontalSpanUnityUnits': max(s['x'] for s in samples) - min(s['x'] for s in samples),
    'verticalSpanUnityUnits': max(s['y'] for s in samples) - min(s['y'] for s in samples),
    'unexplainedAirJumpResets': air_reset,
    'unexpectedHealthGains': health_gains,
    'unexpectedAttacks': sum(bool(s.get('attacking', False)) for s in samples),
    'unexpectedInvulnerabilityStarts': immune_starts,
    'maximumRequestToControllerUpperBoundMs': round(max(request_delays) * 1000, 3) if request_delays else None,
    'passed': not air_reset and not health_gains and not immune_starts and max(latencies, default=0) <= .1
              and max(request_delays, default=0) <= .1 and not any(s.get('attacking', False) for s in samples),
    'limitations': ['Timing is sampled, not a hardware input latency measurement.',
                    'This probe does not establish combat, damage immunity, or visual acceptance.'],
}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2))
assert result['observedControlTransfers'] >= 1
assert result['maximumAckDelayUpperBoundMs'] <= 100
assert not air_reset, 'Air-jump budget reset while airborne'
assert not health_gains, 'Item switching unexpectedly healed the player'
assert not immune_starts, 'Item switching unexpectedly started damage immunity'
assert max(request_delays, default=0) <= .1, 'Controller handoff exceeded100ms'
assert result['unexpectedAttacks'] == 0, 'Item switching unexpectedly started an attack'
