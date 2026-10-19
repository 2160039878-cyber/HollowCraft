"""Check recorded native background input, disconnect and checkpoint-replay evidence."""
import argparse
import json
from pathlib import Path


def analyze(root):
    def read(name):
        return json.loads((root / name).read_text(encoding='utf-8-sig'))
    first, second = read('input-result-01.json'), read('input-result-02.json')
    assert first.get('complete') and second.get('complete')
    a, b = first['samples'], second['samples']
    assert a and b and all(row['focused'] is False for row in a + b)
    assert all(row['hp'] == 5 for row in a + b), 'Unexpected player damage'
    assert any(row['step'] == 1 and not row['atBench'] for row in a), 'Bench did not release control'
    assert any(row['step'] == 3 and row['acceptingInput'] and not row['controlReqlinquished'] for row in a), 'Bench input was not restored'
    for steps, native in [({3, 4}, True), ({19, 20}, False)]:
        rows = [row for row in a if row['step'] in steps and row['native'] == native]
        assert rows and max(row['x'] for row in rows) - min(row['x'] for row in rows) > 2
    assert any(row['step'] == 8 and row['AirJumpUsed'] == 1 and row['animation'] == 'Double Jump' for row in a)
    assert any(row['step'] == 23 and row['AirJumpUsed'] == 1 and not row['native'] for row in a)
    assert 'SlashAlt' in {row['animation'] for row in a}
    assert any(row['step'] == 2 and row['animation'] == 'UpSlash' and not row['nearBench'] for row in b)
    assert any(row['step'] == 6 and row['animation'] == 'DownSlash' and not row['nearBench'] for row in b)
    bow = [row for row in b if row['step'] == 9]
    assert bow and all(not row['native'] and not row['attacking'] and row['heldFlags'] == 2 for row in bow)
    mc = read('minecraft-input-result-02.json')
    assert mc.get('complete') and len(mc['samples']) == 401
    use = [row for row in mc['samples'] if row['held'] == 'minecraft:bow']
    assert max(row['useTicks'] for row in use) >= 20
    arrows = {arrow['id'] for row in mc['samples'] for arrow in row['arrows']}
    assert len(arrows) == 1, 'Missing or duplicated arrow'
    for file in ('minecraft-input-result-01.json', 'minecraft-input-result-02.json'):
        assert all(row['hurtTime'] == 0 for row in read(file)['samples'])
    idle = read('idle-after-input.json')
    assert idle['ready'] and idle['connected'] and idle['pausedByBridge'] and idle['timeScale'] == 0
    assert not idle['BackgroundInput'] and not idle['focused']
    cancelled = read('cancelled-input-result.json')
    assert cancelled.get('cancelled') and cancelled['reason'] == 'Minecraft disconnected'
    loss, settled = read('disconnected-first.json'), read('disconnected-settled.json')
    for state in (loss, settled):
        assert not state['connected'] and not state['ready'] and not state['BackgroundInput']
        assert state['timeScale'] == 0 and state['pausedByBridge']
    assert (loss['heroX'], loss['heroY']) == (settled['heroX'], settled['heroY'])
    reconnect = read('reconnected-before-input.json')
    assert reconnect['ready'] and reconnect['connected'] and reconnect['epoch'] > loss['epoch']
    assert reconnect['timeScale'] == 0 and not reconnect['BackgroundInput']
    resumed = read('reconnect-input-result.json')
    rows = resumed['samples']
    assert resumed.get('complete') and rows[-1]['x'] < rows[0]['x'] - 1
    assert all(not row['attacking'] and not row['focused'] and row['hp'] == 5 for row in rows)
    replay = read('checkpoint-replay-fixed.json')
    assert replay['status'] == 'ready' and replay['snapshotFilesUnchanged'] and not replay['checkpointErrors']
    summary = dict(passed=True, nativeSamples=len(a) + len(b), reconnectSamples=len(rows),
        allSamplesUnfocused=True, healthUnchanged=5, nativeAndToolAirJumpObserved=True,
        nativeSlashUpDownObserved=True, bowChargeTicks=max(row['useTicks'] for row in use),
        arrowCount=len(arrows), idleFocusPauseRestored=True, disconnectCancelledInput=True,
        reconnectAcceptsNewInputOnly=True, completedCheckpointReplay='verified immutable snapshot reused',
        scope='Background input and recovery smoke test; does not establish bow target damage, 100 swaps, boss coverage or performance gates.',
        preliminarySetup='Sequence 1 used slot 8 (oak button) and aimed up beside a bench. Sequence 2 corrected slot 9 and moved clear of bench interaction.')
    (root / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    analyze(parser.parse_args().evidence)
