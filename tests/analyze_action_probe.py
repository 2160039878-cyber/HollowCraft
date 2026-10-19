"""Validate native attack/recoil ownership, modal pause and cancelled bow use."""
import argparse
import json
from pathlib import Path


def analyze(root):
    def read(name):
        return json.loads((root / name).read_text(encoding='utf-8-sig'))
    result, plan = read('final-result.json'), read('plan.json')
    rows = result['samples']
    assert result.get('complete') and rows[-1]['step'] == plan[-1]['end']
    assert all(s['HiddenWindow'] and not s['ownsForegroundWindow'] and s['visibleWindows'] == 0 for s in rows)
    damage = result['damage']
    assert [(d['before'], d['after']) for d in damage] == [(5, 4), (4, 3), (3, 3), (3, 2)]
    findings = {}
    for case in plan:
        samples = [s for s in rows if case['start'] <= s['step'] <= case['end']]
        assert samples
        for s in samples:
            if (s['attacking'] or s['recoiling'] or s['recoilFrozen']) and not s['native']:
                # Damage is injected after Frame publishes its tick. An unchanged acknowledgement means no later MC step ran.
                assert s['mcPhysicsTick'] <= s['PhysicsTick'], ('Busy action lost native physics ownership', case['name'], s['t'])
        if case['name'] == 'sword_attack_swap':
            active = [s for s in samples if s['attacking']]
            assert active and all(s['native'] for s in active) and not samples[-1]['native']
            starts = sum(b['attacking'] and not a['attacking'] for a, b in zip(samples, samples[1:]))
            assert starts == 1, 'Sword swing repeated'
            findings['swordSwingStarts'] = starts
        if 'inventory' in case['name']:
            menu = [s for s in samples if s['mcScreenOpen']]
            assert len(menu) >= 5 and all(s['timeScale'] == 0 for s in menu)
            stable = [s for s in menu if s['t'] > menu[0]['t'] + .2]
            assert stable and not samples[-1]['mcScreenOpen'] and samples[-1]['timeScale'] > 0
            for field in ('physicsX', 'physicsY', 'mcX', 'mcY', 'unityTime'):
                assert max(s[field] for s in stable) - min(s[field] for s in stable) < .01, ('Movement during modal pause', field)
            assert not any(s['isPaused'] for s in samples), 'Minecraft inventory also opened the native pause menu'
            if case['name'] == 'air_inventory_resume':
                assert menu[0]['physicsY'] > samples[0]['physicsY'] + 1 and samples[-1]['ground']
            findings[case['name']] = dict(pausedSamples=len(menu), resumed=True)
        if case['name'] == 'tool_recoil_and_immunity':
            immune = [s for s in samples if s['invulnerable']]
            assert immune and any(s['recoiling'] for s in samples)
            assert all(b['invulnerableDuration'] <= a['invulnerableDuration'] + .001 for a, b in zip(immune, immune[1:]))
            assert not samples[-1]['native'] and not samples[-1]['invulnerable']
            findings['invulnerabilityRefreshed'] = False
    mc = read('minecraft-final-result.json')
    assert mc.get('complete') and len(mc['samples']) >= 401
    bow = [s for s in mc['samples'] if s['held'] == 'minecraft:bow']
    assert bow and max(s['useTicks'] for s in bow) >= 5
    assert all(not s['arrows'] for s in mc['samples']), 'Damage interruption released a stale arrow'
    status = read('final-idle.json')
    assert status['ready'] and status['PhysicsTimeouts'] == 0 and status['timeScale'] == 0
    native_menu = read('native-menu-result.json')
    menu_rows = native_menu['samples']
    paused = [s for s in menu_rows if s['isPaused'] and s['timeScale'] == 0]
    assert native_menu.get('complete') and paused and not any(s['mcScreenOpen'] for s in menu_rows)
    stable = [s for s in paused if s['t'] > paused[0]['t'] + .2]
    assert stable
    for field in ('physicsX', 'physicsY', 'mcX', 'mcY'):
        assert max(s[field] for s in stable) - min(s[field] for s in stable) < .01
    assert menu_rows[-1]['timeScale'] > 0 and not menu_rows[-1]['isPaused']
    assert menu_rows[-1]['x'] < menu_rows[0]['x'] - 2 and all(s['hp'] == 2 for s in menu_rows)
    findings['nativePause'] = dict(pausedSamples=len(paused), resumed=True)
    summary = dict(passed=True, nativeSamples=len(rows), minecraftSamples=len(mc['samples']),
        damage=damage, checks=findings, bowChargeTicks=max(s['useTicks'] for s in bow), arrows=0,
        physicsTimeouts=0, scope='Controlled native TakeDamage calls and real inventory/input handlers; excludes actual enemy/Boss attacks and visual acceptance.')
    (root / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    analyze(parser.parse_args().evidence)
