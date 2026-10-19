"""Blender: replace the tracked StagTunnelRun passenger using the shared Steve rig."""
import argparse
import json
import math
import sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector, Quaternion

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from steve_motion import evaluate

parser=argparse.ArgumentParser()
parser.add_argument('--rig',required=True,type=Path)
parser.add_argument('--source',required=True,type=Path)
parser.add_argument('--tracking',type=Path)
parser.add_argument('--out',required=True,type=Path)
parser.add_argument('--frame',type=int)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
args.out.mkdir(parents=True,exist_ok=True)
W,H,FPS=1920,1080,30
frames=sorted(args.source.glob('*.png'))
assert len(frames)==115 and frames[15].name=='00016.png'
if args.tracking:
    observed=json.loads(args.tracking.read_text(encoding='utf-8-sig'))['frames']
    known={row['frame']:row['head_bbox'] for row in observed if row['head_bbox'] is not None}
    assert len(observed)==115 and len(known)>60
else:
    assert args.frame==16, 'Full animation requires reviewed tracking'
    known={16:[818,345,881,429]}

def box_at(frame):
    if frame in known: return np.array(known[frame],dtype=float)
    before=max((i for i in known if i<frame),default=min(known))
    after=min((i for i in known if i>frame),default=max(known))
    if before==after: return np.array(known[before],dtype=float)
    t=(frame-before)/(after-before)
    return np.array(known[before])*(1-t)+np.array(known[after])*t

bpy.ops.wm.open_mainfile(filepath=str(args.rig))
scene=bpy.context.scene
scene.render.engine='CYCLES'
prefs=bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type='OPTIX'; prefs.get_devices()
for device in prefs.devices: device.use=device.type=='OPTIX'
assert any(d.use for d in prefs.devices), 'An OptiX device is required for this production render'
scene.cycles.device='GPU'; scene.cycles.samples=24
scene.cycles.use_denoising=False
scene.render.resolution_x=W; scene.render.resolution_y=H; scene.render.resolution_percentage=100
scene.render.fps=FPS; scene.frame_start=1; scene.frame_end=116
scene.render.film_transparent=True
scene.view_settings.view_transform='Standard'
scene.render.image_settings.file_format='PNG'; scene.render.image_settings.color_mode='RGB'
rig=bpy.data.objects['Steve']
rig.animation_data.action=bpy.data.actions.new('Stag rider')
rig['show_sword']=0.0
placement=bpy.data.objects.new('Tracked seat placement',None)
scene.collection.objects.link(placement); rig.parent=placement
camera=scene.camera
target=Vector((0,0,.9))
camera.location=target+Vector((3,-5,1.7))
camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.type='ORTHO'; camera.data.sensor_fit='HORIZONTAL'; camera.data.ortho_scale=W/90
camera.data.lens=50
right=camera.rotation_euler.to_matrix()@Vector((1,0,0))
up=camera.rotation_euler.to_matrix()@Vector((0,1,0))
pixels_per_unit=W/camera.data.ortho_scale
for obj in scene.objects:
    if obj.type=='LIGHT':
        obj.parent=placement
        obj.data.color=(.48,.64,1)
        obj.data.energy*=.55
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.06,.10,.20,1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.35
motion=json.loads((ROOT/'assets/steve/poses.json').read_text())['poses']['sit']

scene.use_nodes=True
tree=scene.node_tree; tree.nodes.clear()
def node(kind,name):
    item=tree.nodes.new(kind); item.name=name; item.label=name; return item
def link(a,out,b,inp): tree.links.new(a.outputs[out],b.inputs[inp])
def vec(socket,x,y):
    value=list(socket.default_value); value[0]=x; value[1]=y; socket.default_value=value
def key(socket,frame): socket.keyframe_insert('default_value',frame=frame)

source=node('CompositorNodeImage','Unmodified source frames')
source.image=bpy.data.images.load(str(frames[0])); source.image.source='SEQUENCE'
source.frame_duration=115; source.frame_start=1; source.use_auto_refresh=True
plate=node('CompositorNodeImage','Passenger removed by imagegen')
plate.image=bpy.data.images.load(str(ROOT/'assets/cinematics/StagTunnelRun/cleanplate.png'))
plate.image.pack()
scale=node('CompositorNodeScale','Clean plate canvas')
scale.space='ABSOLUTE'; scale.inputs['X'].default_value=W; scale.inputs['Y'].default_value=H
link(plate,'Image',scale,'Image')
transform=node('CompositorNodeTransform','Track clean plate with passenger')
link(scale,'Image',transform,'Image')
gain=node('CompositorNodeMixRGB','Match moving cave illumination')
gain.blend_type='MULTIPLY'; gain.inputs[0].default_value=1
link(transform,'Image',gain,1)
above_chair=node('CompositorNodeBoxMask','Moving background above chair')
above_chair.inputs['Value'].default_value=1
above_feather=node('CompositorNodeBlur','Blend cave into reconstructed chair'); above_feather.filter_type='GAUSS'
vec(above_feather.inputs['Size'],3,3); link(above_chair,'Mask',above_feather,'Image')
plate_background=node('CompositorNodeMixRGB','Reconstruct moving background and chair')
link(above_feather,'Image',plate_background,0); link(gain,'Image',plate_background,1)
head=node('CompositorNodeEllipseMask','Knight head and horns matte')
body=node('CompositorNodeEllipseMask','Knight cloak matte')
for mask in (head,body): mask.inputs['Value'].default_value=1
union=node('CompositorNodeMath','Passenger matte union'); union.operation='MAXIMUM'
link(head,'Mask',union,0); link(body,'Mask',union,1)
inverse=node('CompositorNodeMath','Known background'); inverse.operation='SUBTRACT'; inverse.inputs[0].default_value=1
link(union,0,inverse,1)
cutout=node('CompositorNodeSetAlpha','Remove original passenger before inpainting')
link(source,'Image',cutout,'Image'); link(inverse,0,cutout,'Alpha')
inpaint=node('CompositorNodeInpaint','Native Blender background reconstruction'); inpaint.inputs['Size'].default_value=110
link(cutout,'Image',inpaint,'Image'); link(inpaint,'Image',plate_background,2)
feather=node('CompositorNodeBlur','Matte edge feather'); feather.filter_type='GAUSS'
vec(feather.inputs['Size'],2,2); link(union,0,feather,'Image')
clean=node('CompositorNodeMixRGB','Only replace passenger pixels')
link(feather,'Image',clean,0); link(source,'Image',clean,1); link(plate_background,'Image',clean,2)
layer=node('CompositorNodeRLayers','Animated 3D Steve')
actor_gain=node('CompositorNodeMixRGB','Moving light on Steve'); actor_gain.blend_type='MULTIPLY'; actor_gain.inputs[0].default_value=1
link(layer,'Image',actor_gain,1)
over=node('CompositorNodeAlphaOver','Seat Steve in the scene'); over.inputs[0].default_value=1
link(clean,'Image',over,1); link(actor_gain,'Image',over,2)
chair=node('CompositorNodeEllipseMask','Original chair in front of rider')
chair.inputs['Value'].default_value=1
pillar=node('CompositorNodeBoxMask','Passing black foreground pillar')
luminance=node('CompositorNodeRGBToBW','Original foreground luminance'); link(source,'Image',luminance,0)
darkness=node('CompositorNodeMath','Soft foreground key'); darkness.operation='SUBTRACT'; darkness.inputs[0].default_value=.018
link(luminance,0,darkness,1)
key_range=node('CompositorNodeMath','Foreground feather'); key_range.operation='DIVIDE'; key_range.inputs[1].default_value=.012; key_range.use_clamp=True
link(darkness,0,key_range,0)
pillar_detail=node('CompositorNodeMath','Original pillar contour'); pillar_detail.operation='MULTIPLY'
link(pillar,'Mask',pillar_detail,0); link(key_range,0,pillar_detail,1)
occlusion=node('CompositorNodeMath','Foreground occlusion'); occlusion.operation='MAXIMUM'
link(chair,'Mask',occlusion,0); link(pillar_detail,0,occlusion,1)
final=node('CompositorNodeMixRGB','Preserve original foreground')
link(occlusion,0,final,0); link(over,'Image',final,1); link(source,'Image',final,2)
visibility=node('CompositorNodeMixRGB','Preserve entry and fade without a visible rider')
link(source,'Image',visibility,1); link(final,'Image',visibility,2)
output=node('CompositorNodeComposite','Final frame'); link(visibility,'Image',output,'Image')
if args.frame:
    for label,upstream,socket in [('actor',layer,'Image'),('matte',feather,'Image'),('foreground',occlusion,0),('clean',clean,'Image')]:
        debug=node('CompositorNodeOutputFile',label+' inspection')
        debug.base_path=str(args.out); debug.format.file_format='PNG'; debug.format.color_mode='RGBA'
        debug.file_slots[0].path=label+'-'; link(upstream,socket,debug,0)

def read_pixels(path):
    image=bpy.data.images.load(str(path),check_existing=False)
    image.colorspace_settings.name='Non-Color'
    assert tuple(image.size)==(W,H)
    pixels=np.empty(W*H*4,dtype=np.float32); image.pixels.foreach_get(pixels)
    rgb=pixels.reshape(H,W,4)[::-1,:,:3].copy()
    bpy.data.images.remove(image)
    return rgb

def background_color(rgb,box):
    left,top,right,bottom=map(int,box)
    samples=[]
    for x in (left-45,right+15):
        patch=rgb[max(0,top-18):max(1,top+18),max(0,x):min(W,x+24)].reshape(-1,3)
        valid=patch[(patch.max(axis=1)>.025)&(patch.max(axis=1)<.9)]
        if len(valid): samples.append(valid)
    return np.median(np.concatenate(samples),axis=0) if samples else np.zeros(3)

def linear(rgb): return np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)

reference_box=box_at(16); ref_cx=(reference_box[0]+reference_box[2])/2; ref_cy=(reference_box[1]+reference_box[3])/2
reference_color=linear(background_color(read_pixels(frames[15]),reference_box))
report=[]
selected=[args.frame] if args.frame else list(range(1,117))
for frame in selected:
    source_frame=min(frame,115)
    box=box_at(source_frame); left,top,right_edge,bottom=box
    cx,cy=(left+right_edge)/2,(top+bottom)/2
    rgb=read_pixels(frames[source_frame-1])
    split=bottom-3
    vec(above_chair.inputs['Position'],.5,1-split/H/2); vec(above_chair.inputs['Size'],1,split/W)
    key(above_chair.inputs['Position'],frame); key(above_chair.inputs['Size'],frame)
    color_gain=np.clip(linear(background_color(rgb,box))/np.maximum(.001,reference_color),0,4)
    phase=((frame-1)/FPS) % 1
    values={k:evaluate(curve,phase) for k,curve in motion['tracks'].items()}
    values.update({'right_arm.rx':-8,'left_arm.rx':-8,'right_arm.rz':3,'left_arm.rz':-3,
                   'right_leg.rx':-65,'left_leg.rx':-70,'right_leg.rz':-8,'left_leg.rz':8,
                   'head.rx':6+2*math.sin(phase*math.tau),'head.ry':3*math.sin(phase*math.tau)})
    for name in ('head','body','right_arm','left_arm','right_leg','left_leg'):
        bone=rig.pose.bones[name]; bone.rotation_mode='XYZ'
        bone.rotation_euler=[math.radians(values.get(name+'.r'+axis,0)) for axis in 'xyz']
        bone.keyframe_insert('rotation_euler',frame=frame,group=name)
    rig.rotation_mode='QUATERNION'; rig.rotation_quaternion=Quaternion((0,0,1),math.pi/2)
    rig.location=(0,0,-.4); rig.scale=(1,1,1)
    rig.keyframe_insert('rotation_quaternion',frame=frame); rig.keyframe_insert('location',frame=frame)
    rig.keyframe_insert('["show_sword"]',frame=frame)
    seat_y=bottom+36
    target_pixel=target+right*((cx-W/2)/pixels_per_unit)+up*((H/2-seat_y)/pixels_per_unit)
    bpy.context.view_layer.update()
    pelvis=rig.matrix_local@Vector((0,0,.675))
    placement.location=target_pixel-pelvis
    placement.keyframe_insert('location',frame=frame)
    transform.inputs['X'].default_value=cx-ref_cx; transform.inputs['Y'].default_value=ref_cy-cy
    key(transform.inputs['X'],frame); key(transform.inputs['Y'],frame)
    gain.inputs[2].default_value=(*color_gain,1); key(gain.inputs[2],frame)
    actor_gain.inputs[2].default_value=(*np.sqrt(color_gain),1); key(actor_gain.inputs[2],frame)
    # Blender mask sizes use canvas width on both axes; positions use each axis.
    vec(head.inputs['Position'],cx/W,1-cy/H); vec(head.inputs['Size'],(right_edge-left+20)/W,(bottom-top+18)/W)
    vec(body.inputs['Position'],(cx-3)/W,1-(bottom+10)/H); vec(body.inputs['Size'],46/W,34/W)
    for mask in (head,body): key(mask.inputs['Position'],frame); key(mask.inputs['Size'],frame)
    vec(chair.inputs['Position'],(cx-4)/W,1-(bottom+36)/H); vec(chair.inputs['Size'],94/W,38/W)
    key(chair.inputs['Position'],frame); key(chair.inputs['Size'],frame)
    visibility.inputs[0].default_value=0 if source_frame<10 or source_frame>=112 else 1
    key(visibility.inputs[0],frame)
    x0,x1=max(0,int(cx-100)),min(W,int(cx+100))
    rows=[max(0,int(top-30)),int(cy),min(H-1,int(bottom+110))]
    dark=np.max(rgb[rows,x0:x1],axis=(0,2))<.02
    runs=[]; start=None
    for i,masked in enumerate([*dark,False]):
        if masked and start is None: start=i
        if not masked and start is not None:
            if i-start>=3: runs.append((x0+start,x0+i))
            start=None
    span=max(runs,key=lambda v:v[1]-v[0]) if runs else None
    pillar.inputs['Value'].default_value=1 if span else 0
    if span:
        a,b=span; vec(pillar.inputs['Position'],(a+b)/2/W,.5); vec(pillar.inputs['Size'],(b-a+62)/W,H/W)
    key(pillar.inputs['Value'],frame); key(pillar.inputs['Position'],frame); key(pillar.inputs['Size'],frame)
    report.append({'frame':frame,'sourceFrame':source_frame,'headBox':box.tolist(),'seat':[cx,seat_y],
                   'backgroundGain':color_gain.tolist(),'foregroundPillar':span,'observed':source_frame in known})

for action in bpy.data.actions:
    if action.name not in ('Stag rider',) and not action.name.startswith(('NodeTree','Tracked seat')): continue
    for layer_data in action.layers:
        for strip in layer_data.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for point in curve.keyframe_points: point.interpolation='LINEAR'
scene.frame_set(selected[0]); bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(args.out/'StagTunnelRun.blend'))
(args.out/'render-plan.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
for frame in selected:
    scene.frame_set(frame)
    source.frame_offset=0 if frame<=115 else -1
    scene.render.filepath=str(args.out/f'{frame:05}.png')
    bpy.ops.render.render(write_still=True)
print('STAG_RENDER_COMPLETE',len(selected),args.out)
