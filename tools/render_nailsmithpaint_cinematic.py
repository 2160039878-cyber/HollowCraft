"""Blender: put the canonical Steve figure into the original painted canvas shot."""
import argparse
import json
import math
import shutil
import sys
from pathlib import Path
import bpy
from mathutils import Vector, Quaternion

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--rig',required=True,type=Path)
parser.add_argument('--source',required=True,type=Path)
parser.add_argument('--out',required=True,type=Path)
parser.add_argument('--frame',type=int)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
args.out.mkdir(parents=True,exist_ok=True)
W,H,FPS=1920,1080,30
frames=sorted(args.source.glob('*.png'))
assert [p.name for p in frames]==[f'{n:05}.png' for n in range(1,317)]
tracking=json.loads((ROOT/'assets/cinematics/NailsmithPaint/tracking.json').read_text(encoding='utf-8-sig'))
assert len(tracking['frames'])==316 and tracking['metadata']['fps']==FPS

bpy.ops.wm.open_mainfile(filepath=str(args.rig))
scene=bpy.context.scene;scene.render.engine='CYCLES'
prefs=bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type='OPTIX';prefs.get_devices()
for d in prefs.devices:d.use=d.type=='OPTIX'
assert any(d.use for d in prefs.devices)
scene.cycles.device='GPU';scene.cycles.samples=32;scene.cycles.use_denoising=False
scene.render.resolution_x=W;scene.render.resolution_y=H;scene.render.resolution_percentage=100
scene.render.fps=FPS;scene.frame_start=1;scene.frame_end=316
scene.render.film_transparent=True;scene.view_settings.view_transform='Standard'
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
rig=bpy.data.objects['Steve'];rig.animation_data.action=bpy.data.actions.new('Painted great slash')
rig['show_sword']=1.0
camera=scene.camera;target=Vector((0,0,.9));camera.location=target+Vector((3,-5,1.1))
camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.type='ORTHO';camera.data.sensor_fit='HORIZONTAL';camera.data.ortho_scale=W/150
right=camera.rotation_euler.to_matrix()@Vector((1,0,0));up=camera.rotation_euler.to_matrix()@Vector((0,1,0))
view=camera.rotation_euler.to_matrix()@Vector((0,0,1))
values={'head.rx':-15,'head.ry':25,'right_arm.rx':-65,'right_arm.rz':-12,'left_arm.rx':-55,'left_arm.rz':15,
        'right_leg.rx':35,'left_leg.rx':-40,'right_leg.rz':-8,'left_leg.rz':8}
for name in ('head','body','right_arm','left_arm','right_leg','left_leg'):
    bone=rig.pose.bones[name];bone.rotation_mode='XYZ'
    bone.rotation_euler=[math.radians(values.get(name+'.r'+axis,0)) for axis in 'xyz']
    bone.keyframe_insert('rotation_euler',frame=1,group=name)
rig.location=(0,0,0);rig.scale=(1,1,1);rig.rotation_mode='QUATERNION'
rig.rotation_quaternion=Quaternion(view,math.radians(-65))@Quaternion((0,0,1),math.pi/2)
bpy.context.view_layer.update()
head_bone=rig.pose.bones['head']
local_head=head_bone.matrix@head_bone.bone.matrix_local.inverted()@Vector((0,0,1.575))
anchor=(1020,522)
target_head=target+right*((anchor[0]-W/2)/150)+up*((H/2-anchor[1])/150)
rig.location=target_head-rig.rotation_quaternion@local_head
rig.keyframe_insert('location',frame=1);rig.keyframe_insert('rotation_quaternion',frame=1);rig.keyframe_insert('["show_sword"]',frame=1)
for obj in scene.objects:
    if obj.type=='LIGHT':
        obj.location+=rig.location;obj.data.energy*=.7;obj.data.color=(1,.83,.82)
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.12,.13,.22,1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.5

for material in set(m for o in scene.objects if o.type=='MESH' for m in o.data.materials):
    tree=material.node_tree;shader=tree.nodes.get('Principled BSDF')
    texture=next(n for n in tree.nodes if n.type=='TEX_IMAGE')
    noise=tree.nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=90;noise.inputs['Detail'].default_value=2
    ramp=tree.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color=(.72,.72,.72,1);ramp.color_ramp.elements[1].color=(1,1,1,1)
    pigment=tree.nodes.new('ShaderNodeMixRGB');pigment.blend_type='MULTIPLY';pigment.inputs[0].default_value=1
    tree.links.new(noise.outputs['Fac'],ramp.inputs[0]);tree.links.new(texture.outputs['Color'],pigment.inputs[1])
    tree.links.new(ramp.outputs[0],pigment.inputs[2]);tree.links.new(pigment.outputs[0],shader.inputs['Base Color'])
    shader.inputs['Roughness'].default_value=1

scene.use_nodes=True;tree=scene.node_tree;tree.nodes.clear()
def node(kind,name):
    n=tree.nodes.new(kind);n.name=name;n.label=name;return n
def link(a,out,b,inp):tree.links.new(a.outputs[out],b.inputs[inp])
def vec(socket,x,y):
    v=list(socket.default_value);v[:2]=[x,y];socket.default_value=v
def key(socket,frame):socket.keyframe_insert('default_value',frame=frame)
def math_node(name,operation,a=None,b=None):
    n=node('CompositorNodeMath',name);n.operation=operation
    for i,v in enumerate((a,b)):
        if v is not None:n.inputs[i].default_value=v
    return n

source=node('CompositorNodeImage','Unmodified source frames')
source.image=bpy.data.images.load(str(frames[0]));source.image.source='SEQUENCE'
source.frame_duration=316;source.frame_start=1;source.use_auto_refresh=True
plate=node('CompositorNodeImage','Painted Knight removed')
plate.image=bpy.data.images.load(str(ROOT/'assets/cinematics/NailsmithPaint/cleanplate.png'));plate.image.pack()
scale=node('CompositorNodeScale','Clean canvas dimensions');scale.space='ABSOLUTE'
scale.inputs['X'].default_value=W;scale.inputs['Y'].default_value=H;link(plate,0,scale,'Image')
plate_gain=node('CompositorNodeMixRGB','Original canvas light and fade');plate_gain.blend_type='MULTIPLY';plate_gain.inputs[0].default_value=1
link(scale,0,plate_gain,1)
points=[(789,566),(811,535),(832,500),(856,496),(814,460),(810,393),(935,401),(980,423),
        (980,387),(999,342),(1035,338),(1040,352),(1085,352),(1092,411),(1076,467),
        (1097,496),(1110,545),(1098,589),(1073,622),(1024,640),(991,650),(983,675),
        (941,695),(905,686),(873,669),(841,647),(831,625),(810,609)]
mask=bpy.data.masks.new('Painted protagonist silhouette')
spline=mask.layers.new(name='Rotoscope').splines.new();spline.points.add(len(points)-1);spline.use_cyclic=True
for point,(x,y) in zip(spline.points,points):
    point.co=(x/W,.5+(H/2-y)/W);point.handle_left_type=point.handle_right_type='VECTOR'
matte=node('CompositorNodeMask','Old painted figure matte');matte.mask=mask;matte.size_source='FIXED';matte.size_x=W;matte.size_y=H
feather=node('CompositorNodeBlur','Painted edge feather');feather.filter_type='GAUSS';vec(feather.inputs['Size'],5,5);link(matte,0,feather,'Image')
clean=node('CompositorNodeMixRGB','Repair only original painted figure')
link(feather,0,clean,0);link(source,0,clean,1);link(plate_gain,0,clean,2)
layer=node('CompositorNodeRLayers','Canonical Steve painted pose')
paint=node('CompositorNodeKuwahara','Pigment edge treatment');paint.variation='CLASSIC';paint.inputs['Size'].default_value=2
link(layer,'Image',paint,'Image')
actor_gain=node('CompositorNodeMixRGB','Painted Steve illumination');actor_gain.blend_type='MULTIPLY';actor_gain.inputs[0].default_value=1
link(paint,0,actor_gain,1)
over=node('CompositorNodeAlphaOver','Steve painted into the canvas');over.inputs[0].default_value=1
link(clean,0,over,1);link(actor_gain,0,over,2)
reference=node('CompositorNodeImage','Original bright painting reference');reference.image=bpy.data.images.load(str(frames[239]));reference.image.pack()
exposure=node('CompositorNodeMixRGB','Original local canvas exposure');exposure.blend_type='DIVIDE';exposure.inputs[0].default_value=1;exposure.use_clamp=True
link(source,0,exposure,1);link(reference,0,exposure,2)
known=math_node('Exposure samples outside old figure','SUBTRACT',1);link(matte,0,known,1)
exposure_cut=node('CompositorNodeSetAlpha','Exclude old white figure from exposure')
link(exposure,0,exposure_cut,'Image');link(known,0,exposure_cut,'Alpha')
exposure_fill=node('CompositorNodeInpaint','Reconstruct exposure across painted figure');exposure_fill.inputs['Size'].default_value=450
link(exposure_cut,0,exposure_fill,'Image')
exposure_soft=node('CompositorNodeBlur','Smooth compression noise in exposure');exposure_soft.filter_type='GAUSS';vec(exposure_soft.inputs['Size'],6,6)
link(exposure_fill,0,exposure_soft,'Image');link(exposure_soft,0,plate_gain,2);link(exposure_soft,0,actor_gain,2)
luma=node('CompositorNodeRGBToBW','Decorative paint brightness');link(reference,0,luma,0)
bright=math_node('Crescent and paint flecks','SUBTRACT',None,.1);link(luma,0,bright,0)
soft=math_node('Decorative pigment alpha','DIVIDE',None,.2);soft.use_clamp=True;link(bright,0,soft,0)
outside=math_node('Preserve decorative paint only','SUBTRACT',1);link(matte,0,outside,1)
decor=math_node('Original brushstroke foreground','MULTIPLY');link(soft,0,decor,0);link(outside,0,decor,1)
foreground=node('CompositorNodeMixRGB','Retain original decorative stroke layering')
link(decor,0,foreground,0);link(over,0,foreground,1);link(source,0,foreground,2)
visibility=node('CompositorNodeMixRGB','Keep original drawing sequence and black cuts')
link(source,0,visibility,1);link(foreground,0,visibility,2)
output=node('CompositorNodeComposite','Final movie frame');link(visibility,0,output,0)
if args.frame:
    for label,upstream,socket in [('actor',paint,0),('clean',clean,0),('matte',feather,0),('foreground',decor,0)]:
        debug=node('CompositorNodeOutputFile',label+' inspection');debug.base_path=str(args.out)
        debug.format.file_format='PNG';debug.format.color_mode='RGBA';debug.file_slots[0].path=label+'-';link(upstream,socket,debug,0)

selected=[args.frame] if args.frame else list(range(1,317));report=[]
for frame in selected:
    active=190<=frame<=303
    visibility.inputs[0].default_value=1 if active else 0;key(visibility.inputs[0],frame)
    report.append({'frame':frame,'replacePainting':active,'lighting':'Original/reference RGB ratio, inpainted through old-figure mask','pose':'painted great slash',
                   'headAnchorPx':anchor,'canvasGeometry':'Original source canvas; no inferred off-screen corners'})
scene.frame_set(next(iter(selected)));bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(args.out/'NailsmithPaint.blend'))
(args.out/'render-plan.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
for frame in selected:
    destination=args.out/f'{frame:05}.png'
    if not args.frame and not report[frame-1]['replacePainting']:shutil.copy2(frames[frame-1],destination)
    else:
        scene.frame_set(frame);scene.render.filepath=str(destination);bpy.ops.render.render(write_still=True)
print('NAILSMITHPAINT_RENDER_COMPLETE',len(selected),args.out)
