"""Blender replacement of Intro's five protagonist shots, using the shared Steve rig."""
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
parser.add_argument('--frames', help='Comma-separated preview frames; omit for the whole film')
parser.add_argument('--render-range', type=int, nargs=2, metavar=('FIRST', 'LAST'),
                    help='Author the complete scene, but render only this repaired range')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
args.rig, args.source, args.out = args.rig.resolve(), args.source.resolve(), args.out.resolve()
args.out.mkdir(parents=True, exist_ok=True)
W, H, FPS, COUNT = 1920, 1080, 25, 953
frames = sorted(args.source.glob('*.png'))
assert [p.name for p in frames] == [f'{f:05}.png' for f in range(1, COUNT + 1)]
assets = ROOT / 'assets/cinematics/Intro'
tracking = json.loads((assets / 'tracking-observed.json').read_text(encoding='utf-8-sig'))
wide_boxes = {r['frame']: r['head_bbox_xyxy'] for r in tracking['keyframes'] if r['scene_id'] == 'cavern_wide'}
final_boxes = {r['frame']: r['head_bbox_xyxy'] for r in tracking['keyframes']
               if r['scene_id'] == 'final_ledge' and r['head_bbox_xyxy'] and r['frame'] <= 930}
measured = {r['frame']: r for r in json.loads((assets / 'head-bright-bounds-measured.json').read_text())['frames']}
registration = json.loads((assets / 'camera-offsets-observed.json').read_text())['sequences']
foot_offsets = {r['frame']: (r['dx'], r['dy']) for r in registration['lower_body']['offsets']}
final_offsets = {r['frame']: (r['dx'], r['dy']) for r in registration['final_ledge']['offsets']}
assert len(foot_offsets) == 125 and len(final_offsets) == 120
assert registration['lower_body']['reference_frame'] == 580 and registration['final_ledge']['reference_frame'] == 880


def interpolate(values, frame):
    before = max((f for f in values if f <= frame), default=min(values))
    after = min((f for f in values if f >= frame), default=max(values))
    a, b = values[before], values[after]
    t = (frame - before) / (after - before) if before != after else 0
    if isinstance(a, (list, tuple)):
        return [x * (1 - t) + y * t for x, y in zip(a, b)]
    return a * (1 - t) + b * t


assert interpolate({1: [0, 2], 3: [2, 4]}, 2) == [1, 3]
assert interpolate({1: 4, 3: 8}, 0) == 4
bpy.ops.wm.open_mainfile(filepath=str(args.rig))
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
preferences = bpy.context.preferences.addons['cycles'].preferences
preferences.compute_device_type = 'OPTIX'
preferences.get_devices()
for device in preferences.devices:
    device.use = device.type == 'OPTIX'
assert any(device.use for device in preferences.devices)
scene.cycles.device = 'GPU'
scene.cycles.samples = 24
scene.cycles.use_denoising = True
scene.cycles.denoiser = 'OPTIX'
scene.render.resolution_x = W
scene.render.resolution_y = H
scene.render.resolution_percentage = 100
scene.render.fps = FPS
scene.frame_start, scene.frame_end = 1, COUNT
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
scene.view_settings.view_transform = 'Standard'
rig = bpy.data.objects['Steve']
rig.animation_data.action = bpy.data.actions.new('Intro walk, approach, closeups and departure')
rig['show_sword'] = 0.0
rig.rotation_mode = 'QUATERNION'
rig.scale = (1, 1, 1)
rig.keyframe_insert('["show_sword"]', frame=1)

# The original carries its weapon on its back in these shots. Reuse the same item mesh.
sword = bpy.data.objects['Diamond sword']
carried = sword.copy()
carried.data = sword.data.copy()
carried.animation_data_clear()
carried.name = 'Diamond sword carried on back'
scene.collection.objects.link(carried)
carried.hide_render = carried.hide_viewport = False
carried.vertex_groups.clear()
carried.vertex_groups.new(name='body').add(list(range(len(carried.data.vertices))), 1, 'REPLACE')
source_grip = Vector((-.337500065, -.104435608, .744220555))
source_tip = Vector((-.337500095, -.845247507, .613595366))
target_grip = Vector((-.23, .25, 1.43))
target_tip = Vector((.24, .25, .80))
rotation = (source_tip - source_grip).rotation_difference(target_tip - target_grip)
item_scale = (target_tip - target_grip).length / (source_tip - source_grip).length
for vertex in carried.data.vertices:
    vertex.co = target_grip + rotation @ ((vertex.co - source_grip) * item_scale)

camera = scene.camera
camera.data.type = 'ORTHO'
camera.data.sensor_fit = 'HORIZONTAL'
target = Vector((0, 0, .9))
lights = [(obj, obj.location.copy()) for obj in scene.objects if obj.type == 'LIGHT']
for obj, _ in lights:
    obj.data.energy *= .5
    obj.data.color = (.60, .72, 1.0)
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (.035, .055, .13, 1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = .28

scene.use_nodes = True
tree = scene.node_tree
tree.nodes.clear()


def node(kind, name):
    result = tree.nodes.new(kind)
    result.name = result.label = name
    return result


def link(a, output, b, slot):
    tree.links.new(a.outputs[output], b.inputs[slot])


def vec(socket, x, y):
    value = list(socket.default_value)
    value[:2] = [x, y]
    socket.default_value = value


def key(socket, frame):
    socket.keyframe_insert('default_value', frame=frame)


def value_node(name, operation, a=None, b=None):
    result = node('CompositorNodeMath', name)
    result.operation = operation
    for index, value in enumerate((a, b)):
        if value is not None:
            result.inputs[index].default_value = value
    return result


def image_node(path, name):
    result = node('CompositorNodeImage', name)
    result.image = bpy.data.images.load(str(path))
    result.image.pack()
    return result


def box_node(name, box):
    result = node('CompositorNodeBoxMask', name)
    set_box(result, box)
    return result


def set_box(mask, box):
    left, top, right, bottom = box
    vec(mask.inputs['Position'], (left + right) / (2 * W), 1 - (top + bottom) / (2 * H))
    vec(mask.inputs['Size'], (right - left) / W, (bottom - top) / W)


def soften(mask, radius, name):
    result = node('CompositorNodeBlur', name)
    result.filter_type = 'GAUSS'
    vec(result.inputs['Size'], radius, radius)
    link(mask, 0, result, 'Image')
    return result


def polygon_node(name, points):
    mask = bpy.data.masks.new(name)
    spline = mask.layers.new(name='Rotoscope').splines.new()
    spline.points.add(len(points) - 1)
    spline.use_cyclic = True
    for point, (x, y) in zip(spline.points, points):
        point.co = (x / W, .5 + (H / 2 - y) / W)
        point.handle_left_type = point.handle_right_type = 'VECTOR'
    result = node('CompositorNodeMask', name)
    result.mask = mask
    result.size_source = 'FIXED'
    result.size_x, result.size_y = W, H
    return result


source = node('CompositorNodeImage', 'Unmodified source frames')
source.image = bpy.data.images.load(str(frames[0]))
source.image.source = 'SEQUENCE'
source.frame_duration = COUNT
source.frame_start = 1
source.use_auto_refresh = True
wide_mask = box_node('Distant original protagonist', [1450, 540, 1540, 650])
wide_alpha = value_node('Keep pixels outside distant figure', 'SUBTRACT', 1)
link(wide_mask, 0, wide_alpha, 1)
wide_hole = node('CompositorNodeSetAlpha', 'Distant figure removed')
link(source, 0, wide_hole, 'Image')
link(wide_alpha, 0, wide_hole, 'Alpha')
wide_fill = node('CompositorNodeInpaint', 'Rebuild small moving background')
wide_fill.inputs['Size'].default_value = 100
link(wide_hole, 0, wide_fill, 'Image')
wide_clean = node('CompositorNodeMixRGB', 'Distant cleanup feather')
link(soften(wide_mask, 3, 'Distant edge'), 0, wide_clean, 0)
link(source, 0, wide_clean, 1)
link(wide_fill, 0, wide_clean, 2)

foot_plate = image_node(frames[579], 'Empty ledge before entry')
foot_transform = node('CompositorNodeTranslate', 'Approach camera registration')
link(foot_plate, 0, foot_transform, 'Image')
foot_mask = box_node('Original approach cloak and feet', [-80, -80, 1480, 970])
foot_clean = node('CompositorNodeMixRGB', 'Approach temporal background repair')
link(soften(foot_mask, 16, 'Approach edge'), 0, foot_clean, 0)
link(source, 0, foot_clean, 1)
link(foot_transform, 0, foot_clean, 2)

cleanups = {'wide': wide_clean, 'feet': foot_clean}
for label, points in (
    ('front', [(-40, -40), (1300, -40), (1300, 400), (1250, 680), (1150, 800),
               (940, 850), (1010, 1120), (-40, 1120)]),
    ('rear', [(-40, -40), (1690, -40), (1660, 130), (1755, 170), (1755, 350),
              (1500, 640), (1370, 790), (1430, 1120), (-40, 1120)]),
):
    plate = image_node(assets / f'cleanplate-{label}.png', label + ' clean background')
    scale = node('CompositorNodeScale', label + ' plate dimensions')
    scale.space = 'ABSOLUTE'
    scale.inputs['X'].default_value, scale.inputs['Y'].default_value = W, H
    link(plate, 0, scale, 'Image')
    matte = polygon_node(label + ' original body and weapon matte', points)
    clean = node('CompositorNodeMixRGB', label + ' local cleanup')
    link(soften(matte, 12, label + ' feather'), 0, clean, 0)
    link(source, 0, clean, 1)
    link(scale, 0, clean, 2)
    cleanups[label] = clean

final_plate = image_node(frames[932], 'Empty final ledge after departure')
final_transform = node('CompositorNodeTranslate', 'Final camera registration')
link(final_plate, 0, final_transform, 'Image')
final_mask = box_node('Original final figure and jump envelope', [315, 285, 835, 1025])
fog_difference = node('CompositorNodeMixRGB', 'Current over temporal atmosphere')
fog_difference.blend_type = 'DIVIDE'
fog_difference.use_clamp = True
fog_difference.inputs[0].default_value = 1
link(source, 0, fog_difference, 1)
link(final_transform, 0, fog_difference, 2)
fog_known = value_node('Atmosphere samples outside old figure', 'SUBTRACT', 1)
link(final_mask, 0, fog_known, 1)
fog_cut = node('CompositorNodeSetAlpha', 'Exclude original figure from atmosphere')
link(fog_difference, 0, fog_cut, 'Image')
link(fog_known, 0, fog_cut, 'Alpha')
fog_fill = node('CompositorNodeInpaint', 'Reconstruct current fog across removed figure')
fog_fill.inputs['Size'].default_value = 650
link(fog_cut, 0, fog_fill, 'Image')
fog_plate = node('CompositorNodeMixRGB', 'Temporal plate with current atmosphere')
fog_plate.blend_type = 'MULTIPLY'
fog_plate.inputs[0].default_value = 1
fog_plate.use_clamp = True
link(final_transform, 0, fog_plate, 1)
link(soften(fog_fill, 15, 'Smooth local atmosphere correction'), 0, fog_plate, 2)
final_clean = node('CompositorNodeMixRGB', 'Final temporal background repair')
link(soften(final_mask, 12, 'Final edge'), 0, final_clean, 0)
link(source, 0, final_clean, 1)
link(fog_plate, 0, final_clean, 2)
cleanups['final'] = final_clean

last = source
selectors = {}
for label, clean in cleanups.items():
    choose = node('CompositorNodeMixRGB', label + ' shot selection')
    link(last, 0, choose, 1)
    link(clean, 0, choose, 2)
    selectors[label] = choose.inputs[0]
    last = choose
actor = node('CompositorNodeRLayers', 'Canonical Steve performance')
shadow = node('CompositorNodeEllipseMask', 'Foot contact shadow')
shadow_soft = soften(shadow, 18, 'Soft contact shadow')
shadow_strength = value_node('Contact shadow opacity', 'MULTIPLY', None, 0)
link(shadow_soft, 0, shadow_strength, 0)
shadow_mix = node('CompositorNodeMixRGB', 'Contact shadow on original ground')
link(shadow_strength, 0, shadow_mix, 0)
link(last, 0, shadow_mix, 1)
shadow_mix.inputs[2].default_value = (0, 0, 0, 1)
grade = node('CompositorNodeMixRGB', 'Actor atmospheric tint')
grade.blend_type = 'MULTIPLY'
grade.inputs[0].default_value = 1
link(actor, 'Image', grade, 1)
fade_rgb = node('CompositorNodeMixRGB', 'Distant emergence through original fog')
fade_rgb.blend_type = 'MULTIPLY'
fade_rgb.inputs[0].default_value = 1
link(grade, 0, fade_rgb, 1)
fade_alpha = value_node('Distant alpha follows fog', 'MULTIPLY', None, 1)
link(actor, 'Alpha', fade_alpha, 0)
faded_actor = node('CompositorNodeSetAlpha', 'Premultiplied atmosphere and alpha')
link(fade_rgb, 0, faded_actor, 'Image')
link(fade_alpha, 0, faded_actor, 'Alpha')
over = node('CompositorNodeAlphaOver', 'Steve in original environment')
over.inputs[0].default_value = 1
link(shadow_mix, 0, over, 1)
link(faded_actor, 0, over, 2)
ledge = polygon_node('Foreground ledge at source frame 933',
                     [(-80, 934), (80, 930), (170, 944), (250, 954), (310, 966),
                      (380, 972), (450, 984), (520, 990), (605, 1004), (705, 1014),
                      (800, 1025), (900, 1040), (980, 1060), (1020, 1160), (-80, 1160)])
ledge_transform = node('CompositorNodeTranslate', 'Foreground camera registration')
link(soften(ledge, 2, 'Foreground soft edge'), 0, ledge_transform, 'Image')
ledge_weight = value_node('Final shot foreground gate', 'MULTIPLY', None, 0)
border = box_node('Solid terrain at the raster bottom edge', [-80, 1076, 2000, 1160])
ledge_complete = value_node('Foreground including raster border', 'MAXIMUM')
# An untransformed first input fixes the compositor domain at the full raster size.
link(border, 0, ledge_complete, 0)
link(ledge_transform, 0, ledge_complete, 1)
link(ledge_complete, 0, ledge_weight, 0)
occlude = node('CompositorNodeMixRGB', 'Original ledge occludes departure')
link(ledge_weight, 0, occlude, 0)
link(over, 0, occlude, 1)
link(final_clean, 0, occlude, 2)
visibility = node('CompositorNodeMixRGB', 'Retain all original shots without protagonist')
link(source, 0, visibility, 1)
link(occlude, 0, visibility, 2)
output = node('CompositorNodeComposite', 'Final movie frame')
link(visibility, 0, output, 0)


def pose_and_camera(frame, view, ppu, anchor, part, values):
    camera.location = target + Vector(view)
    camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.ortho_scale = W / ppu
    right = camera.rotation_euler.to_matrix() @ Vector((1, 0, 0))
    up = camera.rotation_euler.to_matrix() @ Vector((0, 1, 0))
    rig.rotation_quaternion = Quaternion((0, 0, 1), math.radians(values.get('yaw', 0)))
    rig.location = (0, 0, 0)
    for name in ('head', 'body', 'right_arm', 'left_arm', 'right_leg', 'left_leg'):
        bone = rig.pose.bones[name]
        bone.rotation_mode = 'XYZ'
        bone.rotation_euler = [math.radians(values.get(name + '.r' + axis, 0)) for axis in 'xyz']
        bone.keyframe_insert('rotation_euler', frame=frame, group=name)
    bpy.context.view_layer.update()
    if part == 'head':
        bone = rig.pose.bones['head']
        point = bone.matrix @ bone.bone.matrix_local.inverted() @ Vector((0, 0, 1.575))
        point = rig.rotation_quaternion @ point
    else:
        # Keep the lowest projected sole on the observed ground during the approach.
        soles = []
        for name in ('right_leg', 'left_leg'):
            bone = rig.pose.bones[name]
            matrix = bone.matrix @ bone.bone.matrix_local.inverted()
            soles.extend(rig.rotation_quaternion @ (matrix @ vertex.co)
                         for vertex in bpy.data.objects[name].data.vertices)
        point = up * min(vertex.dot(up) for vertex in soles)
    rig.location = target + right * ((anchor[0] - W / 2) / ppu) + up * ((H / 2 - anchor[1]) / ppu) - point
    rig.keyframe_insert('location', frame=frame)
    rig.keyframe_insert('rotation_quaternion', frame=frame)
    camera.keyframe_insert('location', frame=frame)
    camera.keyframe_insert('rotation_euler', frame=frame)
    camera.data.keyframe_insert('ortho_scale', frame=frame)
    for light, offset in lights:
        light.location = rig.location + offset
        light.rotation_euler = (rig.location + Vector((0, 0, 1)) - light.location).to_track_quat('-Z', 'Y').to_euler()
        light.keyframe_insert('location', frame=frame)
        light.keyframe_insert('rotation_euler', frame=frame)


def shot_at(frame):
    if 164 <= frame <= 432:
        return 'wide'
    if 588 <= frame <= 672:
        return 'feet'
    if 673 <= frame <= 759:
        return 'front'
    if 760 <= frame <= 819:
        return 'rear'
    if 820 <= frame <= 931:
        return 'final'
    return None


selected = [int(value) for value in args.frames.split(',')] if args.frames else list(range(1, COUNT + 1))
assert selected and all(1 <= frame <= COUNT for frame in selected)
assert not (args.frames and args.render_range)
if args.render_range:
    assert 1 <= args.render_range[0] <= args.render_range[1] <= COUNT
render_frames = list(range(args.render_range[0], args.render_range[1] + 1)) if args.render_range else selected
report = []
for frame in selected:
    shot = shot_at(frame)
    for label, selector in selectors.items():
        selector.default_value = float(label == shot)
        key(selector, frame)
    visibility.inputs[0].default_value = float(shot is not None)
    key(visibility.inputs[0], frame)
    ledge_weight.inputs[1].default_value = float(shot == 'final')
    key(ledge_weight.inputs[1], frame)
    tint = {'wide': (.70, .80, 1), 'feet': (.25, .30, .45), 'front': (.85, .90, 1),
            'rear': (.5, .6, .8), 'final': (.5, .65, .85)}.get(shot, (1, 1, 1))
    grade.inputs[2].default_value = (*tint, 1)
    key(grade.inputs[2], frame)
    fade = max(0, min(1, (measured[frame]['peakL8'] - 70) / 140)) if shot == 'wide' else 1
    fade_rgb.inputs[2].default_value = (fade, fade, fade, 1)
    fade_alpha.inputs[1].default_value = fade
    key(fade_rgb.inputs[2], frame)
    key(fade_alpha.inputs[1], frame)
    shadow_strength.inputs[1].default_value = .35 if shot == 'feet' or (shot == 'final' and frame <= 920) else 0
    key(shadow_strength.inputs[1], frame)
    values = {'right_arm.rz': 3, 'left_arm.rz': -3}
    anchor = None
    if shot == 'wide':
        box = measured[frame]['brightBounds'] if measured[frame]['selectedPixels'] >= 20 else interpolate(wide_boxes, frame)
        set_box(wide_mask, [box[0] - 8, box[1] - 8, box[2] + 8, box[3] + 25])
        key(wide_mask.inputs['Position'], frame)
        key(wide_mask.inputs['Size'], frame)
        anchor = ((box[0] + box[2]) / 2, box[1] + 63)
        walk = math.sin((frame - 164) * math.tau / 34) * 18
        values.update({'right_leg.rx': walk, 'left_leg.rx': -walk, 'right_arm.rx': -walk * .65,
                       'left_arm.rx': walk * .65, 'head.rx': -3})
        pose_and_camera(frame, (1, -6, .8), 34, anchor, 'feet', values)
    elif shot == 'feet':
        progress = max(0, min(1, (frame - 588) / 44))
        travel = 1 - (1 - progress) ** 2
        walk = math.sin((frame - 588) * math.tau / 32) * 32 * (1 - max(0, (progress - .65) / .35))
        values.update({'right_leg.rx': walk, 'left_leg.rx': -walk,
                       'right_leg.rz': 6, 'left_leg.rz': -6,
                       'right_arm.rx': -walk * .5, 'left_arm.rx': walk * .5})
        dx, dy = foot_offsets[frame]
        anchor = (-450 + travel * 1120 + dx, 912 + dy)
        pose_and_camera(frame, (3, 5, .35), 1500, anchor, 'feet', values)
        foot_transform.inputs['X'].default_value = dx
        foot_transform.inputs['Y'].default_value = -dy
        key(foot_transform.inputs['X'], frame)
        key(foot_transform.inputs['Y'], frame)
    elif shot == 'front':
        anchor = (650, 300 + math.sin((frame - 673) * math.tau / 140) * 3)
        values['head.ry'] = 2 + math.sin((frame - 673) * math.tau / 180) * 1.5
        pose_and_camera(frame, (1.5, -6, .25), 2400, anchor, 'head', values)
    elif shot == 'rear':
        anchor = (730, -320 + math.sin((frame - 760) * math.tau / 140) * 3)
        values['head.rx'] = 4
        pose_and_camera(frame, (1.5, 6, -.2), 2900, anchor, 'head', values)
    elif shot == 'final':
        box = measured[frame]['brightBounds'] or interpolate(final_boxes, frame)
        anchor, part = ((box[0] + box[2]) / 2, box[1] + 72), 'head'
        if frame <= 916:
            values['head.ry'] = math.sin((frame - 820) * math.tau / 170) * 2
        elif frame <= 920:
            crouch = max(0, min(1, (box[1] - measured[916]['brightBounds'][1]) / 133))
            values.update({'right_leg.rx': crouch * 83, 'left_leg.rx': -crouch * 83,
                           'body.rx': crouch * 25, 'head.rx': crouch * 10,
                           'right_arm.rx': -crouch * 40, 'left_arm.rx': -crouch * 40})
        else:
            if frame == 931:
                anchor = (730, 1170)
            values.update({'right_leg.rx': 18, 'left_leg.rx': -22, 'right_arm.rx': -28,
                           'left_arm.rx': -18, 'head.rx': 12})
        pose_and_camera(frame, (1.2, 6, 1.1), 300, anchor, part, values)
        offset_x = final_offsets[frame][0] - final_offsets[933][0]
        offset_y = final_offsets[frame][1] - final_offsets[933][1]
        for transform in (final_transform, ledge_transform):
            transform.inputs['X'].default_value = offset_x
            transform.inputs['Y'].default_value = -offset_y
            key(transform.inputs['X'], frame)
            key(transform.inputs['Y'], frame)
    if anchor is not None:
        shadow_y = 986 + final_offsets[frame][1] if shot == 'final' else anchor[1]
        vec(shadow.inputs['Position'], anchor[0] / W, 1 - shadow_y / H)
        vec(shadow.inputs['Size'], (850 if shot == 'feet' else 180) / W, (32 if shot == 'feet' else 16) / W)
        key(shadow.inputs['Position'], frame)
        key(shadow.inputs['Size'], frame)
    report.append({'frame': frame, 'shot': shot, 'anchorPx': anchor,
                   'observations': 'Source tracking keyframes; intervening pose/position values are authored interpolation',
                   'cameraRegistration': 'Measured stationary environmental feature translation; see camera-offsets-observed.json uncertainty'})

for action in bpy.data.actions:
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for point in curve.keyframe_points:
                        point.interpolation = 'LINEAR'
scene.frame_set(selected[0])
bpy.ops.wm.save_as_mainfile(filepath=str(args.out / 'Intro.blend'))
(args.out / 'render-plan.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
for frame in render_frames:
    destination = args.out / f'{frame:05}.png'
    if not shot_at(frame):
        shutil.copy2(frames[frame - 1], destination)
        continue
    scene.frame_set(frame)
    scene.render.filepath = str(destination)
    bpy.ops.render.render(write_still=True)
print('INTRO_RENDER_COMPLETE', len(render_frames), args.out)
