"""Author the shared Steve action curves used by Minecraft, Unity replicas and Blender."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets' / 'steve'
POSES = {}


def pose(name, tracks=None, *, hide=False, duration=1):
    POSES[name] = {'duration': duration, 'hideHeld': hide, 'tracks': tracks or {}}


def keys(*values):
    return [[i / (len(values) - 1), value] for i, value in enumerate(values)]


def still(value):
    return [[0, value], [1, value]]


def cycle(amplitude, phase=0, repeats=1):
    return [[i / (8 * repeats), round(amplitude * math.cos(i * math.pi / 4 + phase), 4)] for i in range(8 * repeats + 1)]


pose('idle', {'right_arm.rx': still(-12), 'right_arm.rz': still(3), 'left_arm.rz': still(-3)})
for name, amplitude, repeats in [('walk', 28, 1), ('run', 56, 2)]:
    pose(name, {'right_leg.rx': cycle(amplitude, repeats=repeats), 'left_leg.rx': cycle(amplitude, math.pi, repeats),
                'right_arm.rx': cycle(amplitude * .65, math.pi, repeats), 'left_arm.rx': cycle(amplitude * .8, repeats=repeats),
                'body.rx': still(7), 'head.rx': still(-5)})
pose('air', {'right_arm.rx': still(-20), 'left_arm.rx': still(22), 'right_leg.rx': still(12), 'left_leg.rx': still(-14)})
pose('double_jump', {'root.roll': keys(0, 70, 220, 360), 'right_arm.rz': keys(4, 65, 30, 4),
                     'left_arm.rz': keys(-4, -65, -30, -4), 'right_leg.rx': keys(0, -65, -30, 0), 'left_leg.rx': keys(0, 50, 20, 0)})
pose('land', {'root.dy': keys(-.03, -.015, 0), 'body.rx': keys(20, 10, 0), 'head.rx': keys(-12, -6, 0),
              'right_leg.rx': keys(-18, -8, 0), 'left_leg.rx': keys(18, 8, 0)}, duration=.3)
pose('hard_land', {'root.dy': keys(-.23, -.15, 0), 'body.rx': keys(42, 30, 0), 'head.rx': keys(-20, -12, 0),
                   'right_leg.rx': keys(-50, -40, 0), 'left_leg.rx': keys(50, 40, 0)}, duration=.7)
pose('dash', {'root.roll': keys(-12, -18, -12), 'body.rx': still(18), 'right_arm.rx': still(40), 'left_arm.rx': still(65),
              'right_leg.rx': still(-35), 'left_leg.rx': still(32), 'head.rx': still(-18)}, duration=.35)
pose('dash_down', {'right_arm.rx': still(30), 'left_arm.rx': still(30), 'right_leg.rz': still(6), 'left_leg.rz': still(-6)}, duration=.4)
pose('wall_slide', {'right_arm.rx': still(-115), 'left_arm.rx': still(-80), 'right_leg.rx': still(-35), 'left_leg.rx': still(-12), 'head.rx': still(-8)})
pose('wall_jump', {'right_arm.rx': keys(-100, -30, 0), 'left_arm.rx': keys(-80, 40, 0),
                   'right_leg.rx': keys(-70, 10, 0), 'left_leg.rx': keys(-20, -35, 0), 'root.roll': keys(15, 5, 0)}, duration=.45)
pose('slash', {'right_arm.rx': [[0,-25],[.12,-145],[.28,-55],[.42,30],[1,-12]],
               'right_arm.ry': keys(-25, 10, 0), 'body.ry': keys(-18, 18, 0), 'left_arm.rx': keys(10, 40, 0)}, duration=.75)
pose('slash_alt', {'right_arm.rx': [[0,20],[.15,40],[.32,-140],[.48,-80],[1,-12]], 'body.ry': keys(18,-18,0)}, duration=.75)
pose('up_slash', {'right_arm.rx': [[0,-50],[.12,-95],[.4,-95],[1,-12]], 'head.rx': keys(-10,-40,0), 'left_arm.rx': keys(10,35,0)}, duration=.75)
pose('down_slash', {'right_arm.rx': [[0,-20],[.12,90],[.4,100],[1,-12]], 'body.rx': keys(10,30,0),
                    'head.rx': keys(20,50,0), 'right_leg.rx': keys(5,-25,0), 'left_leg.rx': keys(-5,25,0)}, duration=.75)
pose('charge', {'right_arm.rx': still(-100), 'right_arm.ry': still(-35), 'left_arm.rx': still(-40), 'body.rx': still(12)})
pose('big_slash', {'right_arm.rx': [[0,-170],[.2,-160],[.4,35],[1,-12]], 'body.ry': keys(-40,45,0), 'root.roll': keys(8,-12,0)}, duration=.9)
pose('cyclone', {'root.yaw': keys(0,360,720), 'right_arm.rx': still(-90), 'left_arm.rx': still(-90),
                 'right_arm.rz': still(70), 'left_arm.rz': still(-70), 'right_leg.rz': still(8), 'left_leg.rz': still(-8)})
pose('cast', {'right_arm.rx': keys(-30,-100,-105,-12), 'left_arm.rx': keys(-10,-70,-75,0), 'body.rx': keys(0,15,15,0)}, duration=.7)
pose('scream', {'head.rx': keys(0,-50,-55,0), 'right_arm.rz': keys(3,70,70,3), 'left_arm.rz': keys(-3,-70,-70,-3),
                'root.dy': keys(0,.15,.15,0)}, hide=True, duration=1.2)
pose('quake_antic', {'right_arm.rx': keys(0,-160,-170), 'left_arm.rx': keys(0,-160,-170), 'right_leg.rx': keys(0,-25,-45),
                     'left_leg.rx': keys(0,25,45)}, hide=True, duration=.45)
pose('quake', {'right_arm.rx': still(15), 'left_arm.rx': still(15), 'head.rx': still(30), 'body.rx': still(15)}, hide=True)
pose('heal', {'right_arm.rx': still(-70), 'left_arm.rx': still(-70), 'right_arm.ry': still(-25), 'left_arm.ry': still(25),
              'head.rx': still(25), 'body.rx': still(8), 'root.dy': keys(0,.025,0)}, hide=True)
pose('hurt', {'root.roll': keys(0,22,12,0), 'right_arm.rx': keys(0,-70,-20,0), 'left_arm.rx': keys(0,-45,-10,0),
              'head.rx': keys(0,-25,-10,0)}, duration=.6)
pose('die', {'root.roll': [[0,0],[.15,15],[.65,80],[1,90]], 'root.dy': [[0,0],[.15,.03],[.65,-.52],[1,-.675]],
             'right_arm.rx': keys(0,-35,15,15), 'left_arm.rx': keys(0,40,15,15)}, hide=True, duration=1.3)
pose('sit', {'root.dy': still(-.15), 'right_leg.rx': still(-90), 'left_leg.rx': still(-90),
             'right_arm.rx': still(-35), 'left_arm.rx': still(-35), 'head.rx': still(6)}, hide=True)
pose('sleep', {'root.dy': still(-.15), 'right_leg.rx': still(-90), 'left_leg.rx': still(-90), 'body.rx': still(14),
               'head.rx': keys(30,34,30), 'right_arm.rx': still(-35), 'left_arm.rx': still(-35)}, hide=True)
pose('rise', {'root.dy': keys(-.4,-.2,0), 'body.rx': keys(35,20,0), 'head.rx': keys(15,5,0),
              'right_leg.rx': keys(-75,-30,0), 'left_leg.rx': keys(-75,-30,0)}, hide=True)
pose('bench_enter', {'root.dy': keys(-.28,-.15,-.15), 'right_leg.rx': keys(0,-65,-90), 'left_leg.rx': keys(0,-65,-90),
                      'right_arm.rx': keys(-12,-25,-35), 'left_arm.rx': keys(0,-25,-35), 'head.rx': keys(0,6,6)}, hide=True)
pose('bench_exit', {'root.dy': [[0,-.15],[.25,.13],[1,0]], 'right_leg.rx': keys(-90,-45,0), 'left_leg.rx': keys(-90,-45,0),
                     'body.rx': keys(0,18,0), 'head.rx': keys(6,12,0), 'right_arm.rx': keys(-35,-25,-12), 'left_arm.rx': keys(-35,-25,0)}, hide=True)
pose('bench_sleep', {'root.dy': still(-.15), 'right_leg.rx': still(-90), 'left_leg.rx': still(-90),
                      'body.rx': keys(0,14), 'head.rx': keys(6,30), 'right_arm.rx': still(-35), 'left_arm.rx': still(-35)}, hide=True)
pose('bench_wake', {'root.dy': still(-.15), 'right_leg.rx': still(-90), 'left_leg.rx': still(-90),
                     'body.rx': keys(14,0), 'head.rx': keys(30,6), 'right_arm.rx': still(-35), 'left_arm.rx': still(-35)}, hide=True)
pose('prone', {'root.roll': still(90), 'root.dy': still(-.68), 'right_arm.rx': still(-15), 'left_arm.rx': still(-15)}, hide=True)
pose('collect', {'right_arm.rx': keys(-15,-125,-135,-20), 'left_arm.rx': keys(-15,-125,-135,-20),
                 'head.rx': keys(10,-25,-25,0), 'root.dy': keys(0,.1,.1,0)}, hide=True, duration=1.2)
pose('look_up', {'head.rx': keys(0,-35,-35), 'right_arm.rx': still(-12)})
pose('look_down', {'head.rx': keys(0,35,35), 'right_arm.rx': still(-12)})
pose('map', {'head.rx': still(28), 'right_arm.rx': still(-65), 'left_arm.rx': still(-65),
             'right_arm.ry': still(-20), 'left_arm.ry': still(20)}, hide=True)
pose('swim', {'root.roll': still(-75), 'right_arm.rx': cycle(65), 'left_arm.rx': cycle(65,math.pi),
              'right_leg.rx': cycle(20,math.pi), 'left_leg.rx': cycle(20)}, hide=True)
pose('teleport_charge', {'right_arm.rx': keys(-30,-90,-90), 'left_arm.rx': keys(-30,-90,-90), 'head.rx': still(20)}, hide=True)
pose('teleport', {'root.sy': keys(1,.5,.05), 'root.dy': keys(0,.1,.2)}, hide=True, duration=.5)
pose('appear', {'root.sy': keys(.05,.6,1), 'root.dy': keys(.2,.1,0)}, hide=True, duration=.5)
pose('slug', {'root.sy': still(.4), 'root.dy': still(-.54), 'body.rx': still(28), 'head.rx': still(-25),
              'right_arm.rx': cycle(20), 'left_arm.rx': cycle(20,math.pi), 'right_leg.rx': cycle(35,math.pi), 'left_leg.rx': cycle(35)}, hide=True)
pose('challenge', {'right_arm.rx': keys(-12,-110,-110,-12), 'head.rx': keys(0,15,-10,0), 'body.rx': keys(0,10,0,0)}, duration=1.2)
pose('turn', {'head.ry': keys(-20,10,0), 'right_arm.rx': still(-12)}, duration=.4)
pose('turn_to_bg', {'root.yawSide':[[0,0],[1/3,45],[2/3,90],[1,90]]},hide=True,duration=3/12)
pose('turn_from_bg', {'root.yawSide':[[0,90],[.5,0],[1,0]]},hide=True,duration=2/12)
pose('dream_warp', {
    'root.dy': [[0,.75],[2/26,.6],[4/26,0],[1,0]],
    'root.yaw': [[0,-90],[10/26,-90],[12/26,-20],[1,-20]],
    'root.roll': [[0,0],[10/26,0],[12/26,-38],[20/26,-38],[23/26,-5],[25/26,0],[1,0]],
    'right_arm.rz': [[0,30],[10/26,30],[12/26,3],[1,3]],
    'left_arm.rz': [[0,-30],[10/26,-30],[12/26,-3],[1,-3]],
    'head.rx': [[0,0],[10/26,0],[12/26,20],[21/26,20],[25/26,0],[1,0]],
    'flash': [[0,1],[2/26,1],[3/26,.55],[4/26,.12],[5/26,0],[1,0]]}, hide=True, duration=26/12)
pose('dream_get_1', {'right_arm.rx': [[0,-12],[.75,-65],[1,-65]], 'head.rx': keys(0,15,15),
                     'left_arm.rx': still(-5)}, hide=True, duration=4/12)
pose('dream_get_2', {'head.rx': [[0,15],[.5,-20],[1,-20]], 'right_arm.rx': keys(-65,-110,-125),
                     'left_arm.rx': still(-5)}, hide=True, duration=6/12)
pose('dream_get_3', {'head.rx': still(-20), 'right_arm.rx': still(-125), 'left_arm.rx': still(-5),
                     'flash': [[0,1],[1/8,.55],[2/8,.15],[3/8,0],[1,0]]}, hide=True, duration=8/12)
pose('dream_end', {'head.rx': [[0,-20],[.5,15],[1,15]], 'right_arm.rx': [[0,-110],[.5,-65],[1,-65]],
                   'left_arm.rx': still(-5)}, hide=True, duration=2/12)
for name in ('dream_get_1','dream_get_2','dream_get_3','dream_end'):
    POSES[name]['tracks']['root.yaw'] = still(-20)
pose('radiance_ball', {'root.yaw':still(70)}, hide=True, duration=4/12)
POSES['radiance_ball']['headOnly']=True
void_base={'root.yaw':still(70),'root.roll':still(-25),'head.rx':still(-8),
           'right_arm.rx':still(-35),'left_arm.rx':still(25),'right_leg.rx':still(12),'left_leg.rx':still(-16)}
pose('radiance_form', {**void_base,'root.roll':[[0,80],[.2,35],[.4,-25],[1,-25]],
                       'left_arm.rz':keys(-60,-25,-8)}, hide=True, duration=15/12)
pose('radiance_idle', {**void_base,'left_arm.rx':cycle(8),'right_leg.rx':cycle(8),
                       'left_leg.rx':cycle(8,math.pi)}, hide=True, duration=8/12)
pose('radiance_unform', {**void_base,'root.roll':[[0,-25],[.35,35],[1,80]]}, hide=True, duration=10/12)
for n,roll in ((1,-10),(2,-40)):
    pose(f'radiance_swing_{n}_antic',{**void_base,'root.roll':keys(-25,roll,roll),
                                   'left_arm.rx':keys(-35,-125,-90)},hide=True,duration=3/18)
    pose(f'radiance_swing_{n}',{**void_base,'root.roll':keys(roll,-25),
                              'left_arm.rx':keys(-90,-35)},hide=True,duration=2/18)
for name in ('radiance_form','radiance_idle','radiance_unform','radiance_swing_1_antic','radiance_swing_1','radiance_swing_2_antic','radiance_swing_2'):
    POSES[name]['voidEyes']=True
pose('radiance_pull',{'root.yaw':still(70),'root.roll':still(35),'head.rx':still(25),
                     'left_arm.rx':still(10),'right_arm.rx':still(10)},hide=True,duration=1/30)
pose('radiance_hang',{'root.yaw':still(70),'root.roll':[[0,35],[.125,10],[.25,0],[1,0]],
                     'head.rx':still(28),'right_leg.rx':still(5),'left_leg.rx':still(-5)},hide=True,duration=8/12)
pose('radiance_split_antic',{'root.yaw':still(70),'root.roll':[[0,0],[.25,0],[.5,-10],[.75,-20],[1,-20]],
                            'head.rx':keys(28,28,0),'flash':[[0,0],[.5,0],[.75,1],[1,1]]},hide=True,duration=4/12)
pose('radiance_split',{'root.yaw':still(70),'root.roll':keys(-20,0,15,20),'root.sy':keys(1,.9,.5,.2),
                      'head.rx':keys(0,20,35,35),'right_arm.rx':keys(-40,-90,-120,-120),
                      'left_arm.rx':keys(40,90,120,120),'flash':keys(1,.6,.1,0)},hide=True,duration=4/15)
for name in POSES:
    if name.startswith('radiance_'):POSES[name]['nativeFacingRight']=True

# Native Knight Collapse holds its recoil pose for 19 of its 28 frames.
pose('abyss_collapse', {
    'root.roll': [[0,15],[19/28,15],[20/28,0],[23/28,-90],[1,-90]],
    'root.dy': [[0,0],[20/28,0],[23/28,-.66],[24/28,-.675],[1,-.675]],
    'right_arm.rx': [[0,-8],[19/28,-8],[21/28,-30],[24/28,0],[1,0]],
    'left_arm.rx': [[0,-8],[19/28,-8],[21/28,-30],[24/28,0],[1,0]],
},hide=True,duration=1.75)
pose('abyss_climb_1', {
    'root.dy': [[0,-1.72],[1/6,-1.55],[2/6,-1.32],[3/6,-1.2],[4/6,-1],[5/6,-1.06],[1,-1.06]],
    'root.roll': [[0,0],[2/6,5],[4/6,-5],[1,-5]],
    'right_arm.rx': still(0),'left_arm.rx': still(-5),'head.rx': still(12),
},hide=True,duration=6/12)
pose('abyss_climb_2', {
    'root.dy': [[0,-.98],[1/3,-.92],[2/3,-.86],[1,-.86]],
    'root.roll': [[0,-5],[1,-20]],'right_arm.rx': still(-25),'left_arm.rx': still(-15),'head.rx': still(12),
},hide=True,duration=3/12)
pose('abyss_climb_3', {
    'root.dy': [[0,-.86],[4/25,-.58],[18/25,-.58],[20/25,-.05],[22/25,0],[1,0]],
    'root.roll': [[0,-20],[4/25,-45],[18/25,-45],[20/25,-10],[22/25,0],[1,0]],
    'right_arm.rx': [[0,-25],[4/25,-70],[18/25,-70],[22/25,-12],[1,-12]],
    'left_arm.rx': [[0,-15],[4/25,-40],[18/25,-40],[22/25,0],[1,0]],
    'head.rx': [[0,12],[18/25,12],[22/25,0],[1,0]],
},hide=True,duration=25/12)
pose('abyss_climb_4', {
    'root.dy': [[0,-.58],[1/6,-.05],[3/6,0],[1,0]],
    'root.roll': [[0,-30],[1/6,-10],[3/6,0],[1,0]],
    'right_arm.rx': [[0,-70],[3/6,-12],[1,-12]],'left_arm.rx': [[0,-40],[3/6,0],[1,0]],
    'head.rx': [[0,12],[3/6,0],[1,0]],
},hide=True,duration=6/12)
pose('abyss_grab', {
    'root.dy': [[0,.62],[1/4,.81],[3/4,.78],[1,.78]],
    'right_arm.rx': still(-90),'left_arm.rx': still(-90),
    'right_leg.rx': still(-15),'left_leg.rx': still(20),'head.rx': still(-5),
},hide=True,duration=4/12)
pose('abyss_falter', {
    'root.dy': [[0,.81],[1/5,.62],[2/5,.24],[1,.24]],
    'root.roll': [[0,0],[1/5,0],[2/5,25],[1,25]],
    'right_arm.rx': still(-125),'left_arm.rx': [[0,-100],[2/5,-35],[1,-35]],
    'right_leg.rx': keys(-15,10,10),'left_leg.rx': keys(20,-20,-20),'head.rx': still(-5),
},hide=True,duration=5/12)
pose('abyss_fall', {
    'root.dy': still(.15),'root.roll': keys(65,70,65),
    'right_arm.rx': keys(-125,-110,-125),'left_arm.rx': keys(-90,-105,-90),
    'right_leg.rx': keys(-30,-40,-30),'left_leg.rx': keys(15,25,15),
},hide=True,duration=3/12)


def classify(name):
    if not name: return None
    if name=='TurnToBG': return 'turn_to_bg'
    if name=='TurnFromBG': return 'turn_from_bg'
    if any(token in name for token in ('Effect', 'Fx', ' FX', 'Trail', 'Puff', 'Wings', 'Death Head', 'Hit Crack', 'SD Crys')) or name in ('Shadow Recharge','Shadow Dash Burst'): return None
    if name.startswith('Slug'): return 'slug'
    if name.startswith('UpSlash'): return 'up_slash'
    if name.startswith('DownSlash'): return 'down_slash'
    if name == 'SlashAlt': return 'slash_alt'
    if name in ('Slash', 'Wall Slash', 'DN Slash', 'NA Dash Slash'): return 'slash'
    if name == 'NA Big Slash': return 'big_slash'
    if name.startswith('NA Cyclone'): return 'cyclone'
    if name in ('NA Charge', 'DN Charge', 'DN Start', 'DN Slash Antic', 'SD Charge Ground', 'SD Wall Charge'): return 'charge'
    if name in ('SD Charge Ground End', 'DN Cancel'): return 'idle'
    if name.startswith('DG '): return 'appear' if name.endswith('In') else 'idle' if name.endswith('Cancel') else 'teleport' if name == 'DG Warp' else 'teleport_charge'
    if name in ('Wall Slide', 'Walljump'): return 'wall_slide' if name == 'Wall Slide' else 'wall_jump'
    if name == 'Double Jump': return 'double_jump'
    if 'Death' in name: return 'die'
    if name == 'Hazard Respawn': return 'appear'
    if name in ('HardLand','Super Hard Land','Dash Down Land','Quake Land','Quake Land 2'): return 'hard_land'
    if name in ('Land','Collect Magical Land','Dreamer Land','DJ Get Land','SD Hit Wall','SD Air Brake','SD Break'): return 'land'
    if name == 'Quake Antic': return 'quake_antic'
    if name.startswith('Quake Fall'): return 'quake'
    if name.startswith('Scream'): return 'scream'
    if name.startswith('Fireball'): return 'cast'
    if name.startswith('Focus'): return 'heal'
    if name in ('Recoil','Stun','Roar Lock','Idle Hurt','Thorn Attack'): return 'hurt'
    if name in ('Airborne','Fall','Collect Magical Fall'): return 'air'
    if name in ('Dash Down','Shadow Dash Down','Shadow Dash Down Sharp'): return 'dash_down'
    if name in ('Dash','Shadow Dash','Shadow Dash Sharp','SD Dash'): return 'dash'
    if name == 'Dash To Idle': return 'land'
    if name.startswith('Surface'): return 'swim'
    if name == 'Sit': return 'bench_enter'
    if name == 'Get Off': return 'bench_exit'
    if name == 'Sit Fall Asleep': return 'bench_sleep'
    if name == 'Wake To Sit': return 'bench_wake'
    if 'Asleep' in name: return 'sleep'
    if name.startswith('Sit'): return 'sit'
    if name in ('Wake','Wake Up Ground','Respawn Wake','GetUpToIdle','Prostrate Rise'): return 'rise'
    if name in ('Prostrate','ToProne'): return 'prone'
    if name.startswith('LookUp') or name in ('Look At King',): return 'look_up'
    if name.startswith('LookDown'): return 'look_down'
    if name.startswith('Map'): return 'map'
    if name in ('Run','Lantern Run','Sprint'): return 'run'
    if name in ('Walk','Enter','Exit','Exit Door To Idle'): return 'walk'
    if name in ('Idle','Idle Wind','Lantern Idle','Run To Idle','Collect StandToIdle'): return 'idle'
    if 'Turn' in name: return 'turn'
    if name.startswith('Collect') or name == 'Dreamer Lift': return 'collect'
    if name.startswith('Challenge'): return 'challenge'
    raise ValueError('Unmapped native clip: ' + name)


def evaluate(track, t):
    if t <= track[0][0]: return track[0][1]
    for (a, v0), (b, v1) in zip(track, track[1:]):
        if t <= b:
            u = (t - a) / (b - a)
            return v0 + (v1 - v0) * u * u * (3 - 2 * u)
    return track[-1][1]


def main():
    clips = json.loads((ASSETS / 'hk-clips.json').read_text(encoding='utf-8-sig'))
    aliases, effects = {}, []
    for clip in clips:
        name = clip['name']
        motion = classify(name)
        if motion: aliases[name] = motion
        else: effects.append(name)
    for motion in POSES.values():
        for track in motion['tracks'].values():
            assert track[0][0] == 0 and track[-1][0] == 1
            assert all(a[0] < b[0] for a,b in zip(track,track[1:]))
            assert all(math.isfinite(v) for key in track for v in key)
    assert evaluate([[0,10],[1,30]], .5) == 20
    output = {'schema':1, 'rotationUnit':'degrees', 'rootTranslationUnit':'Minecraft blocks',
              'interpolation':'smoothstep', 'bones':['head','body','right_arm','left_arm','right_leg','left_leg'],
              'poses':POSES, 'aliases':aliases, 'auxiliaryClipsToReview':effects}
    (ASSETS / 'poses.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: {len(POSES)} authored motions, {len(aliases)} native body clips; {len(effects)} auxiliary/empty clips still require visual review')


if __name__ == '__main__': main()
