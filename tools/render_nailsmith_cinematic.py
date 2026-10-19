"""Blender: retarget the three Nailsmith sword-clash shots onto the canonical Steve rig."""
import argparse
import json
import math
import shutil
import sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector, Quaternion

ROOT=Path(__file__).resolve().parents[1]

parser=argparse.ArgumentParser()
parser.add_argument('--rig', required=True, type=Path)
parser.add_argument('--source', required=True, type=Path)
parser.add_argument('--tracking', required=True, type=Path)
parser.add_argument('--out', required=True, type=Path)
parser.add_argument('--frame', type=int)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
args.out.mkdir(parents=True, exist_ok=True)
frames=sorted(args.source.glob('*.png'))
tracking=json.loads(args.tracking.read_text(encoding='utf-8-sig'))
W,H,FPS=1912,1080,30
assert len(frames)==130 and len(tracking['frames'])==130 and frames[59].name=='00060.png'
observations={r['frame']:r for r in tracking['frames']}

bpy.ops.wm.open_mainfile(filepath=str(args.rig))
scene=bpy.context.scene
scene.render.engine='CYCLES'
prefs=bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type='OPTIX'; prefs.get_devices()
for device in prefs.devices: device.use=device.type=='OPTIX'
assert any(d.use for d in prefs.devices), 'OptiX GPU is required'
scene.cycles.device='GPU'; scene.cycles.samples=32; scene.cycles.use_denoising=False
scene.render.resolution_x=W; scene.render.resolution_y=H; scene.render.resolution_percentage=100
scene.render.fps=FPS; scene.frame_start=1; scene.frame_end=130
scene.render.film_transparent=True
scene.view_settings.view_transform='Standard'
scene.render.image_settings.file_format='PNG'; scene.render.image_settings.color_mode='RGB'
rig=bpy.data.objects['Steve']; rig.animation_data.action=bpy.data.actions.new('Nailsmith parries')
rig['show_sword']=1.0
placement=bpy.data.objects.new('Tracked hero head placement',None); scene.collection.objects.link(placement); rig.parent=placement
camera=scene.camera; target=Vector((0,0,1.35))
camera.location=target+Vector((3,-5,.55))
camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.type='ORTHO'; camera.data.sensor_fit='HORIZONTAL'
right=camera.rotation_euler.to_matrix()@Vector((1,0,0)); up=camera.rotation_euler.to_matrix()@Vector((0,1,0))
view=camera.rotation_euler.to_matrix()@Vector((0,0,1))
for obj in scene.objects:
    if obj.type=='LIGHT':
        obj.parent=placement; obj.data.color=(.8,.71,.95); obj.data.energy*=.8
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.06,.07,.13,1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.25

scene.use_nodes=True; tree=scene.node_tree; tree.nodes.clear()
def node(kind,name):
    item=tree.nodes.new(kind); item.name=name; item.label=name; return item
def link(a,out,b,inp): tree.links.new(a.outputs[out],b.inputs[inp])
def vec(socket,x,y):
    value=list(socket.default_value); value[:2]=[x,y]; socket.default_value=value
def key(socket,frame): socket.keyframe_insert('default_value',frame=frame)
def math_node(name,operation,a=None,b=None):
    n=node('CompositorNodeMath',name); n.operation=operation
    for i,v in enumerate((a,b)):
        if v is not None: n.inputs[i].default_value=v
    return n
def box(mask,bounds,frame):
    left,top,right_edge,bottom=bounds
    vec(mask.inputs['Position'],(left+right_edge)/2/W,1-(top+bottom)/2/H)
    vec(mask.inputs['Size'],(right_edge-left)/W,(bottom-top)/W)
    key(mask.inputs['Position'],frame); key(mask.inputs['Size'],frame)
def polygon(name,points):
    mask=bpy.data.masks.new(name)
    spline=mask.layers.new(name='Rotoscope').splines.new(); spline.points.add(len(points)-1)
    spline.use_cyclic=True
    for point,(x,y) in zip(spline.points,points):
        point.co=(x/W,.5+(H/2-y)/W)
        point.handle_left_type=point.handle_right_type='VECTOR'
    result=node('CompositorNodeMask',name); result.mask=mask
    result.size_source='FIXED'; result.size_x=W; result.size_y=H
    return result
def select_shot(name,one,two,three):
    first=node('CompositorNodeMixRGB',name+' shot 2'); link(one,0,first,1); link(two,0,first,2)
    last=node('CompositorNodeMixRGB',name+' shot 3'); link(first,0,last,1); link(three,0,last,2)
    return first,last

source=node('CompositorNodeImage','Unmodified source frames')
source.image=bpy.data.images.load(str(frames[0])); source.image.source='SEQUENCE'
source.frame_duration=130; source.frame_start=1; source.use_auto_refresh=True
blade2=polygon('Mentor blade in reverse shot',[(1290,570),(1451,763),(873,909),(914,800)])
blade3=polygon('Mentor blade in held shot',[(739,264),(1176,709),(1036,862)])
old_nail2=polygon('Player nail over reverse-shot blade',[(1012,590),(790,904),(898,905)])
old_nail2_gate=math_node('Reverse shot nail repair','MULTIPLY'); link(old_nail2,0,old_nail2_gate,0)
blade_pick=node('CompositorNodeMixRGB','Select native blade'); link(blade2,0,blade_pick,1); link(blade3,0,blade_pick,2)
foreground=math_node('Native foreground blade','MULTIPLY'); link(blade_pick,0,foreground,0)
behind=math_node('Exclude native blade from cleanup','SUBTRACT',1); link(foreground,0,behind,1)
head=node('CompositorNodeBoxMask','Original head and horns')
body=node('CompositorNodeBoxMask','Original dark cloak')
weapon=node('CompositorNodeBoxMask','Original player nail and handle')
for mask in (head,body,weapon): mask.inputs['Value'].default_value=1
head_body=math_node('Head and cloak','MAXIMUM'); link(head,0,head_body,0); link(body,0,head_body,1)
union=math_node('Complete old player matte','MAXIMUM'); link(head_body,0,union,0); link(weapon,0,union,1)
inverse=math_node('Known source background','SUBTRACT',1); link(union,0,inverse,1)
feather=node('CompositorNodeBlur','Removal matte feather'); feather.filter_type='GAUSS'
vec(feather.inputs['Size'],35,35); link(union,0,feather,'Image')
repair_mask=math_node('Feather without changing mentor blade','MULTIPLY'); link(feather,'Image',repair_mask,0); link(behind,0,repair_mask,1)
complete_repair=math_node('Include player nail in front of mentor','MAXIMUM'); link(repair_mask,0,complete_repair,0); link(old_nail2_gate,0,complete_repair,1)
clean=node('CompositorNodeMixRGB','Clean original protagonist region')
link(complete_repair,0,clean,0); link(source,'Image',clean,1)

layer=node('CompositorNodeRLayers','Canonical Steve and diamond sword')
actor_gain=node('CompositorNodeMixRGB','Match original global fade'); actor_gain.blend_type='MULTIPLY'; actor_gain.inputs[0].default_value=1
link(layer,'Image',actor_gain,1)
vignette=node('CompositorNodeEllipseMask','Original portrait framing')
vignette.inputs['Value'].default_value=1
vec(vignette.inputs['Position'],.50,.54); vec(vignette.inputs['Size'],1370/W,700/W)
vignette_soft=node('CompositorNodeBlur','Portrait vignette softness'); vignette_soft.filter_type='GAUSS'
vec(vignette_soft.inputs['Size'],150,150); link(vignette,'Mask',vignette_soft,'Image')
background=node('CompositorNodeRGB','Observed empty background colour')
background_vignette=node('CompositorNodeMixRGB','Reconstructed empty portrait'); background_vignette.blend_type='MULTIPLY'; background_vignette.inputs[0].default_value=1
link(background,0,background_vignette,1); link(vignette_soft,'Image',background_vignette,2)
plates=[]; references=[]
for frame in (24,40):
    plate=node('CompositorNodeImage','Clean plate '+str(frame))
    plate.image=bpy.data.images.load(str(ROOT/f'assets/cinematics/Nailsmith/cleanplate-{frame}.png')); plate.image.pack()
    scale=node('CompositorNodeScale','Clean plate size '+str(frame)); scale.space='ABSOLUTE'
    scale.inputs['X'].default_value=W; scale.inputs['Y'].default_value=H; link(plate,'Image',scale,'Image'); plates.append(scale)
for frame in (24,40,60):
    reference=node('CompositorNodeImage','Clear source reference '+str(frame))
    reference.image=bpy.data.images.load(str(frames[frame-1])); reference.image.pack(); references.append(reference)
plate2,plate3=select_shot('Background plate',*plates,background_vignette)
ref2,ref3=select_shot('Clear original reference',*references)
delta=node('CompositorNodeMixRGB','Original additive clash light'); delta.blend_type='SUBTRACT'; delta.inputs[0].default_value=1; delta.use_clamp=True
link(source,'Image',delta,1); link(ref3,0,delta,2)
effect_cut=node('CompositorNodeSetAlpha','Remove original player silhouette from light')
link(delta,'Image',effect_cut,'Image'); link(inverse,0,effect_cut,'Alpha')
effect_inpaint=node('CompositorNodeInpaint','Reconstruct light across replacement'); effect_inpaint.inputs['Size'].default_value=500
link(effect_cut,'Image',effect_inpaint,'Image')
effect=node('CompositorNodeBlur','Soft clash illumination'); effect.filter_type='GAUSS'
vec(effect.inputs['Size'],24,24); link(effect_inpaint,'Image',effect,'Image')
background_flash=node('CompositorNodeMixRGB','Impact light across removed player'); background_flash.blend_type='ADD'
link(plate3,0,background_flash,1); link(effect,'Image',background_flash,2); link(background_flash,'Image',clean,2)
actor_light=node('CompositorNodeMixRGB','Clash light on Steve'); actor_light.blend_type='ADD'
actor_effect=node('CompositorNodeMixRGB','Premultiply clash light by Steve alpha'); actor_effect.blend_type='MULTIPLY'; actor_effect.inputs[0].default_value=1
link(effect,'Image',actor_effect,1); link(layer,'Alpha',actor_effect,2)
link(actor_gain,'Image',actor_light,1); link(actor_effect,'Image',actor_light,2)
actor_vignette=node('CompositorNodeMixRGB','Premultiply portrait RGB'); actor_vignette.blend_type='MULTIPLY'; actor_vignette.inputs[0].default_value=1
link(actor_light,'Image',actor_vignette,1); link(vignette_soft,'Image',actor_vignette,2)
actor_alpha=math_node('Steve alpha within portrait','MULTIPLY'); link(layer,'Alpha',actor_alpha,0); link(vignette_soft,'Image',actor_alpha,1)
actor=node('CompositorNodeSetAlpha','Faded portrait edges'); actor.mode='REPLACE_ALPHA'
link(actor_vignette,'Image',actor,'Image'); link(actor_alpha,0,actor,'Alpha')
over=node('CompositorNodeAlphaOver','Animated player replacement'); over.inputs[0].default_value=1
link(clean,'Image',over,1); link(actor,'Image',over,2)
front=node('CompositorNodeMixRGB','Preserve native foreground and NPC')
link(foreground,0,front,0); link(over,'Image',front,1); link(clean,'Image',front,2)
visibility=node('CompositorNodeMixRGB','Preserve original black cuts and flashes')
link(source,'Image',visibility,1); link(front,'Image',visibility,2)
output=node('CompositorNodeComposite','Final movie frame'); link(visibility,'Image',output,'Image')
if args.frame:
    for label,upstream,socket in [('actor',layer,'Image'),('clean',clean,'Image'),('matte',repair_mask,0),('foreground',foreground,0)]:
        debug=node('CompositorNodeOutputFile',label+' inspection'); debug.base_path=str(args.out)
        debug.format.file_format='PNG'; debug.format.color_mode='RGBA'; debug.file_slots[0].path=label+'-'
        link(upstream,socket,debug,0)

def pixels(path):
    im=bpy.data.images.load(str(path),check_existing=False); im.colorspace_settings.name='Non-Color'
    assert tuple(im.size)==(W,H)
    data=np.empty(W*H*4,dtype=np.float32); im.pixels.foreach_get(data)
    rgb=data.reshape(H,W,4)[::-1,:,:3].copy(); bpy.data.images.remove(im); return rgb
def linear(value): return value/12.92 if value<=.04045 else ((value+.055)/1.055)**2.4

selected=[args.frame] if args.frame else range(1,131)
report=[]
for frame in selected:
    row=observations[frame]
    active=22<=frame<=27 or 36<=frame<=41 or 54<=frame<=98
    shot=1 if frame<28 else 2 if frame<42 else 3
    if shot==1:
        anchor=(548,720); ppu=410; yaw=100; roll=-8
        head_box=[315,537,723,866]; body_box=[370,774,845,1010]; nail_box=[589,483,817,942]
        edge=((875,450),(1070,1000)); arm=-115+min(5,max(0,frame-22))*2
    elif shot==2:
        anchor=(739,716); ppu=450; yaw=155; roll=0
        head_box=[581,421,919,924]; body_box=[450,735,858,977]; nail_box=[765,560,1045,936]
        edge=((975,700),(1450,440)); arm=-53+min(4,max(0,frame-36))*1.5
    else:
        anchor=(642,562); ppu=450; yaw=100; roll=8
        head_box=[451,301,879,740]; body_box=[465,641,895,946]; nail_box=[770,368,942,851]
        edge=((741,265),(1038,861)); arm=-85+min(4,max(0,frame-54))*3
    fade=1.0 if frame<82 else float(pixels(frames[frame-1])[350:700,490:840].max()) if frame<=98 else 0.0
    fade=linear(fade)
    camera.data.ortho_scale=W/ppu; camera.data.keyframe_insert('ortho_scale',frame=frame)
    values={'head.rx':-22,'head.ry':0,'right_arm.rx':arm,'right_arm.ry':-15,'right_arm.rz':-8,
            'left_arm.rx':-20,'left_arm.rz':8,'right_leg.rx':-8,'left_leg.rx':9}
    if shot==3: values.update({'right_arm.ry':15,'right_arm.rz':-2})
    if shot==2: values.update({'right_arm.ry':-43,'right_arm.rz':-36})
    for name in ('head','body','right_arm','left_arm','right_leg','left_leg'):
        bone=rig.pose.bones[name]; bone.rotation_mode='XYZ'
        bone.rotation_euler=[math.radians(values.get(name+'.r'+axis,0)) for axis in 'xyz']
        bone.keyframe_insert('rotation_euler',frame=frame,group=name)
    rig.location=(0,0,0); rig.scale=(1,1,1); rig.rotation_mode='QUATERNION'
    rig.rotation_quaternion=Quaternion(view,math.radians(roll))@Quaternion((0,0,1),math.radians(yaw))
    rig.keyframe_insert('rotation_quaternion',frame=frame); rig.keyframe_insert('location',frame=frame)
    rig.keyframe_insert('["show_sword"]',frame=frame)
    bpy.context.view_layer.update()
    head_bone=rig.pose.bones['head']
    local_head=head_bone.matrix@head_bone.bone.matrix_local.inverted()@Vector((0,0,1.575))
    target_pixel=target+right*((anchor[0]-W/2)/ppu)+up*((H/2-anchor[1])/ppu)
    placement.location=target_pixel-rig.matrix_local@local_head
    placement.keyframe_insert('location',frame=frame)
    for mask,bounds in ((head,head_box),(body,body_box),(weapon,nail_box)): box(mask,bounds,frame)
    blade_pick.inputs[0].default_value=1 if shot==3 else 0; key(blade_pick.inputs[0],frame)
    foreground.inputs[1].default_value=0 if shot==1 else 1; key(foreground.inputs[1],frame)
    old_nail2_gate.inputs[1].default_value=1 if shot==2 else 0; key(old_nail2_gate.inputs[1],frame)
    for first,last in ((plate2,plate3),(ref2,ref3)):
        first.inputs[0].default_value=1 if shot==2 else 0; last.inputs[0].default_value=1 if shot==3 else 0
        key(first.inputs[0],frame); key(last.inputs[0],frame)
    flash={22:.8,23:.4,24:.12,36:1,37:.8,38:.35,39:.1,54:1,55:.8,56:.4,57:.1}.get(frame,0)
    for effect_gain in (background_flash,actor_light):
        effect_gain.inputs[0].default_value=1 if flash else 0; key(effect_gain.inputs[0],frame)
    bg={1:(12,17,32),2:(4,3,8),3:(8,8,18)}[shot]
    background.outputs[0].default_value=(*(linear(c/255)*fade for c in bg),1); key(background.outputs[0],frame)
    lighting=fade*(1+flash*.75)
    actor_gain.inputs[2].default_value=(lighting,lighting,lighting,1); key(actor_gain.inputs[2],frame)
    visibility.inputs[0].default_value=1 if active else 0; key(visibility.inputs[0],frame)
    report.append({'frame':frame,'active':active,'shot':shot,'headAnchor':anchor,'pixelsPerUnit':ppu,
        'oldHeadMatte':head_box,'oldBodyMatte':body_box,'oldNailMatte':nail_box,'foregroundEdge':edge,'fadeLinear':fade})

scene.frame_set(next(iter(selected))); bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(args.out/'Nailsmith.blend'))
(args.out/'render-plan.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
for frame in selected:
    destination=args.out/f'{frame:05}.png'
    if not args.frame and not report[frame-1]['active']:
        shutil.copy2(frames[frame-1],destination)
    else:
        scene.frame_set(frame); scene.render.filepath=str(destination)
        bpy.ops.render.render(write_still=True)
print('NAILSMITH_RENDER_COMPLETE',len(list(selected)),args.out)
