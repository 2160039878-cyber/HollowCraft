"""Blender: canonical Void Steve in the shared Godhome shots of endings D/E."""
import argparse
import json
import math
import shutil
import sys
from pathlib import Path
import bpy
from mathutils import Vector, Quaternion

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--rig', type=Path, required=True)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--variant', choices=['FinalD', 'FinalE'], required=True)
parser.add_argument('--mattes', type=Path, required=True)
parser.add_argument('--frames')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
args.rig, args.source, args.out = args.rig.resolve(), args.source.resolve(), args.out.resolve()
assert args.out != args.source and not args.out.is_relative_to(args.source)
args.out.mkdir(parents=True, exist_ok=True)
W, H, COUNT = 1920, 1080, 1508 if args.variant == 'FinalD' else 1957
frames = sorted(args.source.glob('*.png'))
assert [p.name for p in frames] == [f'{f:05}.png' for f in range(1, COUNT + 1)]
selected = sorted(set(int(f) for f in args.frames.split(','))) if args.frames else list(range(1, COUNT + 1))
assert selected and all(1 <= f <= COUNT for f in selected)
matte_info = json.loads((args.mattes / 'manifest.json').read_text())
assert matte_info['variant'] == args.variant and matte_info['count'] == COUNT
assert Path(matte_info['source']).resolve() == args.source
needed = {f for f in selected if 3 <= f <= 215 or 398 <= f <= 413 or 418 <= f <= 598}
assert needed <= set(matte_info['availableFrames']), 'Generate the selected foreground mattes first'
black_frames = set(matte_info['blackFrames'])
assets = ROOT / 'assets/cinematics/FinalD'
features = {row['frame']: row for row in json.loads((assets / 'measured-frames.json').read_text())['frames']}
motion = {row['frame']: row for row in json.loads((assets / 'plate-motion.json').read_text())['frames']}


def sample(keys, frame):
    if frame <= keys[0][0]:
        return keys[0][1]
    for (a, x), (b, y) in zip(keys, keys[1:]):
        if frame <= b:
            return x + (y - x) * (frame - a) / (b - a)
    return keys[-1][1]


assert sample([(1, 0), (3, 4)], 2) == 2
assert sample([(1, 0), (3, 4)], 0) == 0 and sample([(1, 0), (3, 4)], 4) == 4
bpy.ops.wm.open_mainfile(filepath=str(args.rig))
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 32
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'OPTIX'
prefs.get_devices()
for device in prefs.devices:
    device.use = device.type == 'OPTIX'
assert any(device.use for device in prefs.devices)
scene.cycles.device = 'GPU'
scene.cycles.use_denoising = True
scene.cycles.denoiser = 'OPTIX'
scene.render.resolution_x, scene.render.resolution_y = W, H
scene.render.resolution_percentage = 100
scene.render.fps, scene.frame_start, scene.frame_end = 30, 1, COUNT
scene.render.film_transparent = True
scene.view_settings.view_transform = 'Standard'
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
rig = bpy.data.objects['Steve']
rig.animation_data_clear()
rig['show_sword'] = 0
rig.scale = (1, 1, 1)
rig.rotation_mode = 'QUATERNION'
for bone in rig.pose.bones:
    bone.matrix_basis.identity()
    bone.rotation_mode = 'XYZ'
parts = ['head', 'body', 'right_arm', 'left_arm', 'right_leg', 'left_leg']
for obj in scene.objects:
    if obj.type == 'MESH':
        obj.hide_render = obj.name not in parts


def emission(name, colour, strength):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.node_tree.nodes.clear()
    shader = material.node_tree.nodes.new('ShaderNodeEmission')
    shader.inputs['Color'].default_value = (*colour, 1)
    shader.inputs['Strength'].default_value = strength
    output = material.node_tree.nodes.new('ShaderNodeOutputMaterial')
    material.node_tree.links.new(shader.outputs[0], output.inputs['Surface'])
    return material


void = emission('Void silhouette', (.00008, .0001, .00014), 1)
glow = emission('Void Steve square eyes', (1, 1, 1), 3)
for name in parts:
    bpy.data.objects[name].data.materials.clear()
    bpy.data.objects[name].data.materials.append(void)
eye_mesh = bpy.data.meshes.new('Canonical Steve eye rectangles')
vertices = [(x, -.227, z) for lo, hi in ((-.16875, -.05625), (.05625, .16875))
            for x, z in ((lo, 1.51875), (hi, 1.51875), (hi, 1.575), (lo, 1.575))]
eye_mesh.from_pydata(vertices, [], [(0, 1, 2, 3), (4, 5, 6, 7)])
eye_mesh.materials.append(glow)
eyes = bpy.data.objects.new('Void Steve eyes', eye_mesh)
scene.collection.objects.link(eyes)
eyes.parent = rig
eyes.vertex_groups.new(name='head').add(list(range(8)), 1, 'REPLACE')
eyes.modifiers.new('Canonical head bone', 'ARMATURE').object = rig
body_objects = [bpy.data.objects[name] for name in parts] + [eyes]

# The close camera sees only forearms; use the same canonical arm geometry.
close_arms = []
for name in ('right_arm', 'left_arm'):
    mesh = bpy.data.objects[name].data.copy()
    centre = sum((v.co for v in mesh.vertices), Vector()) / len(mesh.vertices)
    for vertex in mesh.vertices:
        vertex.co -= centre
    arm = bpy.data.objects.new('Close ' + name, mesh)
    scene.collection.objects.link(arm)
    arm.rotation_mode = 'QUATERNION'
    arm['canonical_source'] = 'Steve/' + name
    close_arms.append(arm)

camera = scene.camera
camera.data.type = 'ORTHO'
camera.data.sensor_fit = 'HORIZONTAL'
camera.location = (0, -8, 0)
camera.rotation_euler = (-camera.location).to_track_quat('-Z', 'Y').to_euler()
front = Vector((0, -1, 0))
scene.use_nodes = True
tree = scene.node_tree
tree.nodes.clear()


def node(kind, name):
    value = tree.nodes.new(kind)
    value.name = value.label = name
    return value


def link(a, output, b, socket):
    tree.links.new(a.outputs[output], b.inputs[socket])


def vec(socket, x, y):
    value = list(socket.default_value)
    value[:2] = [x, y]
    socket.default_value = value


def key(socket, value, frame):
    socket.default_value = value
    socket.keyframe_insert('default_value', frame=frame)


def image(path, name, sequence=False):
    value = node('CompositorNodeImage', name)
    value.image = bpy.data.images.load(str(path))
    if sequence:
        value.image.source = 'SEQUENCE'
        value.frame_start, value.frame_duration, value.use_auto_refresh = 1, COUNT, True
    else:
        value.image.pack()
    return value


def math_node(name, operation, a=None, b=None):
    value = node('CompositorNodeMath', name)
    value.operation = operation
    for index, source in enumerate((a, b)):
        if isinstance(source, (int, float)):
            value.inputs[index].default_value = source
        elif source is not None:
            link(source, 0, value, index)
    return value


source = image(frames[0], 'Unmodified original movie', True)
entry_plate = image(frames[396], 'Entry before the transformed protagonist arrives')
side_plate = image(frames[417], 'Unoccluded throne side view')
close_plate = image(assets / 'plate-godseeker-close.png', 'Reconstructed occluded NPC only')
cloud_plate = image(assets / 'plate-cloud-chasm.png', 'Clouds behind the original hanging Void form')
cloud_size = node('CompositorNodeScale', 'Cloud plate source dimensions')
cloud_size.space = 'ABSOLUTE'
cloud_size.inputs['X'].default_value, cloud_size.inputs['Y'].default_value = W, H
link(cloud_plate, 0, cloud_size, 'Image')
cloud_soft = node('CompositorNodeBlur', 'Match distant cloud softness')
cloud_soft.filter_type = 'GAUSS'
vec(cloud_soft.inputs['Size'], 14, 14)
link(cloud_size, 0, cloud_soft, 'Image')
size = node('CompositorNodeScale', 'Close plate source dimensions')
size.space = 'ABSOLUTE'
size.inputs['X'].default_value, size.inputs['Y'].default_value = W, H
link(close_plate, 0, size, 'Image')
side_switch = node('CompositorNodeMixRGB', 'Select entry or side repair plate')
link(entry_plate, 0, side_switch, 1)
link(side_plate, 0, side_switch, 2)
plate = node('CompositorNodeMixRGB', 'Select close-up repair plate')
link(side_switch, 0, plate, 1)
link(size, 0, plate, 2)
cloud_switch = node('CompositorNodeMixRGB', 'Select cloud-chasm repair plate')
link(plate, 0, cloud_switch, 1)
link(cloud_soft, 0, cloud_switch, 2)
plate_move = node('CompositorNodeTranslate', 'Follow original NPC and throne camera motion')
link(cloud_switch, 0, plate_move, 'Image')
source_luma = node('CompositorNodeRGBToBW', 'Original luminance')
plate_luma = node('CompositorNodeRGBToBW', 'Repair plate luminance')
link(source, 0, source_luma, 0)
link(plate_move, 0, plate_luma, 0)
denominator = math_node('Avoid unstable exposure at black NPC details', 'MAXIMUM', plate_luma, .001)
ratio = math_node('Local original exposure relative to repair plate', 'DIVIDE', source_luma, denominator)
limited_ratio = math_node('Limit reconstructed exposure to observed face highlights', 'MINIMUM', ratio, 1)
valid = math_node('Keep original black NPC details', 'GREATER_THAN', plate_luma, .003)
matte = image(args.mattes / '00001.png', 'Connected original body and eye mattes', True)
matte.image.colorspace_settings.name = 'Non-Color'
dilate = node('CompositorNodeDilateErode', 'Include blurred original edges')
dilate.mode, dilate.distance = 'DISTANCE', 22
link(matte, 0, dilate, 0)
feather = node('CompositorNodeBlur', 'Repair edge feather')
feather.filter_type = 'GAUSS'
vec(feather.inputs['Size'], 5, 5)
link(dilate, 0, feather, 'Image')
known = math_node('Only sample light outside old body', 'SUBTRACT', 1, dilate)
known = math_node('Valid unoccluded light samples', 'MULTIPLY', known, valid)
cut = node('CompositorNodeSetAlpha', 'Exclude removed figure from light samples')
link(limited_ratio, 0, cut, 'Image')
link(known, 0, cut, 'Alpha')
fill = node('CompositorNodeInpaint', 'Reconstruct local light through original form')
fill.inputs['Size'].default_value = 1500
link(cut, 0, fill, 'Image')
soft = node('CompositorNodeBlur', 'Local light smoothing')
soft.filter_type = 'GAUSS'
vec(soft.inputs['Size'], 8, 8)
link(fill, 0, soft, 'Image')
gain = node('CompositorNodeMixRGB', 'Repair follows original light and fade')
gain.blend_type = 'MULTIPLY'
gain.inputs[0].default_value = 1
link(plate_move, 0, gain, 1)
link(soft, 0, gain, 2)
tone = node('CompositorNodeMixRGB', 'Cloud chasm stays in the original shadow')
tone.blend_type = 'MULTIPLY'
tone.inputs[0].default_value = 1
link(gain, 0, tone, 1)
clean = node('CompositorNodeMixRGB', 'Replace only the old protagonist pixels')
link(feather, 0, clean, 0)
link(source, 0, clean, 1)
link(tone, 0, clean, 2)
layer = node('CompositorNodeRLayers', 'Animated canonical Void Steve')
actor = node('CompositorNodeBlur', 'Match foreground optical softness')
actor.filter_type = 'GAUSS'
vec(actor.inputs['Size'], 3, 3)
link(layer, 'Image', actor, 'Image')
glare = node('CompositorNodeGlare', 'Square eye glow')
glare.glare_type, glare.quality = 'FOG_GLOW', 'HIGH'
link(actor, 0, glare, 'Image')
over = node('CompositorNodeAlphaOver', 'Void Steve in original scene')
over.inputs[0].default_value = 1
link(clean, 0, over, 1)
link(glare, 0, over, 2)
visibility = node('CompositorNodeMixRGB', 'Only confirmed protagonist body shots')
link(source, 0, visibility, 1)
link(over, 0, visibility, 2)
output = node('CompositorNodeComposite', 'Final movie frame')
link(visibility, 0, output, 0)
report = []
# Bake every frame even for preview selections, so the saved scene has a complete timeline.
for frame in range(1, COUNT + 1):
    entry, side, close = 398 <= frame <= 413, 418 <= frame <= 498, 499 <= frame <= 598
    cloud = 3 <= frame <= 215
    active = cloud or entry or side or close
    key(side_switch.inputs[0], float(side), frame)
    key(plate.inputs[0], float(close), frame)
    key(cloud_switch.inputs[0], float(cloud), frame)
    key(visibility.inputs[0], float(active and frame not in black_frames), frame)
    shift = motion.get(frame, {'dx': 0, 'dy': 0})
    key(plate_move.inputs['X'], shift['dx'], frame)
    key(plate_move.inputs['Y'], -shift['dy'], frame)
    highlight = features.get(frame, {}).get('highlightExposure', 1)
    key(limited_ratio.inputs[1], highlight, frame)
    key(tone.inputs[2], (.55, .55, .55, 1) if cloud else (1, 1, 1, 1), frame)
    for value, amount in ((actor, 28 if cloud else 3), (feather, 48 if cloud else 5)):
        vec(value.inputs['Size'], amount, amount)
        value.inputs['Size'].keyframe_insert('default_value', frame=frame)
    if cloud:
        ppu = 650
        anchor_x, anchor_y = 900 + shift['dx'], -200 + shift['dy']
        roll = sample([(3, -5), (215, 3)], frame)
    elif entry:
        # The source holds each drawing for two frames; keep its eye reveal and wipe timing.
        pose_frame = frame - (frame % 2)
        ppu = sample([(398, 1400), (400, 1400), (402, 1850), (404, 1900), (406, 1900),
                      (408, 2000), (410, 3300), (412, 5000)], pose_frame)
        anchor_x = sample([(398, 1600), (400, 1250), (402, 1700), (404, 1630), (406, 1450),
                           (408, 1300), (410, 1190), (412, 950)], pose_frame)
        anchor_y = sample([(398, -450), (400, 231), (402, 1400), (404, 1600), (406, 1800),
                           (408, 2100), (410, 3000), (412, 4000)], pose_frame)
        roll = 150 if frame <= 401 else 180
    else:
        pose_frame = frame if frame == 418 else frame - (1 if frame % 2 == 0 else 0)
        ppu = sample([(418, 1200), (423, 1200), (431, 1500), (441, 1800)], pose_frame)
        anchor_x = sample([(418, 1650), (419, 1620), (421, 1497), (423, 1520),
                           (431, 1900), (441, 2100)], pose_frame)
        anchor_y = sample([(418, -500), (419, 25), (421, 603), (423, 1250), (431, 1450)], pose_frame)
        roll = 180
    camera.data.ortho_scale = W / (1000 if close else ppu)
    camera.data.keyframe_insert('ortho_scale', frame=frame)
    rig.rotation_quaternion = Quaternion(front, math.radians(roll))
    reach = sample([(418, 0), (455, 0), (481, -75), (498, -105)], frame) if side else 0
    left_reach = sample([(418, 0), (455, 0), (473, -35), (481, -65), (498, -70)], frame) if side else 0
    for name, angle in [('right_arm', reach), ('left_arm', left_reach)]:
        bone = rig.pose.bones[name]
        if cloud:
            angle = (1 if name == 'right_arm' else -1) * (18 + math.sin(frame / 60) * 5)
        bone.rotation_euler = (0, 0, math.radians(angle))
        bone.keyframe_insert('rotation_euler', frame=frame)
    for name, sign in (('right_leg', 1), ('left_leg', -1)):
        bone = rig.pose.bones[name]
        bone.rotation_euler = (0, 0, math.radians(4 * sign if cloud else 0))
        bone.location = (0, -.015 if cloud else 0, 0)
        bone.keyframe_insert('rotation_euler', frame=frame)
        bone.keyframe_insert('location', frame=frame)
    bpy.context.view_layer.update()
    head = rig.pose.bones['head']
    local_eye = head.matrix @ head.bone.matrix_local.inverted() @ Vector((0, -.227, 1.546875))
    rig.location = Vector(((anchor_x - W / 2) / ppu, 0, (H / 2 - anchor_y) / ppu)) - rig.rotation_quaternion @ local_eye
    rig.keyframe_insert('location', frame=frame)
    rig.keyframe_insert('rotation_quaternion', frame=frame)
    for obj in body_objects:
        obj.hide_render = not (cloud or entry or side)
        obj.keyframe_insert('hide_render', frame=frame)
    for index, arm in enumerate(close_arms):
        x = 1450 if index == 0 else sample([(499, -1100), (505, -980), (530, -450), (550, -200), (598, 0)], frame)
        y = sample([(499, 1040), (530, 1010), (550, 990), (598, 850)], frame) if index == 0 else sample([(499, 1100), (530, 850), (550, 620), (598, 300)], frame)
        angle = -75 if index == 0 else sample([(499, -60), (530, -45), (550, -35), (598, -45)], frame)
        arm.location = ((x - W / 2) / 1000, -1 - index * .1, (H / 2 - y) / 1000)
        arm.rotation_quaternion = Quaternion(front, math.radians(angle))
        arm.scale = (3, 3, 3)
        arm.hide_render = not close
        for prop in ('location', 'rotation_quaternion', 'scale', 'hide_render'):
            arm.keyframe_insert(prop, frame=frame)
    if active:
        report.append({'frame': frame, 'shot': 'cloud' if cloud else 'entry' if entry else 'side' if side else 'close',
                       'eyeAnchorPx': [anchor_x, anchor_y] if not close else None,
                       'repairOffsetPx': [shift['dx'], shift['dy']],
                       'status': 'candidate; visual and native playback acceptance pending'})
assert len(report) == 410 and [r['frame'] for r in report if r['shot'] != 'cloud'] == list(features)
scene.frame_set(selected[0])
bpy.ops.wm.save_as_mainfile(filepath=str(args.out / (args.variant + '.blend')))
(args.out / 'render-plan.json').write_text(json.dumps({
    'variant': args.variant, 'frames': COUNT, 'active': report,
    'matteManifest': str((args.mattes / 'manifest.json').resolve()),
    'limitations': ['Cloud/body replacement requires visual acceptance. Exterior liquid and radial Void effects are preserved; see outputs/acceptance/cinematic-protagonist-scope.json. Copied frames are not runtime acceptance.'],
    'audio': 'Original game AudioClip; mux_cinematic_preview.py attaches it to the watch preview without retiming.'
}, indent=2), encoding='utf-8')
for frame in selected:
    destination = args.out / f'{frame:05}.png'
    if frame in black_frames or not (3 <= frame <= 215 or 398 <= frame <= 413 or 418 <= frame <= 598):
        shutil.copy2(frames[frame - 1], destination)
        continue
    scene.frame_set(frame)
    assert bpy.data.objects['Diamond sword'].hide_render
    scene.render.filepath = str(destination)
    bpy.ops.render.render(write_still=True)
print('FINAL_DE_RENDER_COMPLETE', args.variant, len(selected), args.out)
