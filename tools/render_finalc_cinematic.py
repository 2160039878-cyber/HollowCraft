"""Blender: replace the Knight's broken shell with fragments of the canonical Steve head."""
import argparse
import json
import math
import shutil
import sys
from pathlib import Path
import bpy
import bmesh
from mathutils import Vector, Quaternion

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--rig',type=Path,required=True)
parser.add_argument('--source',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--frames')
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
args.rig,args.source,args.out=args.rig.resolve(),args.source.resolve(),args.out.resolve()
args.out.mkdir(parents=True,exist_ok=True)
assets=ROOT/'assets/cinematics/FinalC'
W,H,COUNT=1920,1080,2532
frames=sorted(args.source.glob('*.png'))
assert [p.name for p in frames]==[f'{f:05}.png' for f in range(1,COUNT+1)]
features={row['frame']:row for row in json.loads((assets/'measured-frames.json').read_text())['frames']}
motion=json.loads((assets/'camera-motion.json').read_text())['background_motion']['keyframes']
def camera_motion(frame):
    before=max((row for row in motion if row['frame']<=frame),key=lambda row:row['frame'],default=motion[0])
    after=min((row for row in motion if row['frame']>=frame),key=lambda row:row['frame'],default=motion[-1])
    t=(frame-before['frame'])/(after['frame']-before['frame']) if before!=after else 0
    return [before[key]*(1-t)+after[key]*t for key in ('scale','dx_px','dy_px')]
assert camera_motion(1336)==[1,0,0] and camera_motion(1499)==[1.048,2,-6]
bpy.ops.wm.open_mainfile(filepath=str(args.rig))
scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.samples=32
prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
for device in prefs.devices:device.use=device.type=='OPTIX'
assert any(device.use for device in prefs.devices)
scene.cycles.device='GPU';scene.cycles.use_denoising=True;scene.cycles.denoiser='OPTIX'
scene.render.resolution_x=W;scene.render.resolution_y=H;scene.render.resolution_percentage=100
scene.render.fps=30;scene.frame_start=1;scene.frame_end=COUNT
scene.render.film_transparent=True;scene.view_settings.view_transform='Standard'
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
for obj in list(scene.objects):
    if obj.type in ('MESH','ARMATURE'):obj.hide_render=True
# The preview idle action keys equipment visibility; detach it before hiding the original rig.
bpy.data.objects['Steve'].animation_data_clear()
bpy.data.objects['Steve']['show_sword']=0

# Keep the original head UVs. The open, hollow cut is a shell, not a fleshy cross-section.
interior=bpy.data.materials.new('Dark hollow shell');interior.use_nodes=True
shader=interior.node_tree.nodes['Principled BSDF'];shader.inputs['Base Color'].default_value=(.012,.016,.025,1)
shader.inputs['Roughness'].default_value=1
fragments=[]
for side in (-1,1):
    mesh=bpy.data.objects['head'].data.copy()
    bm=bmesh.new();bm.from_mesh(mesh)
    for vertex in bm.verts:vertex.co.z-=1.575
    bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),dist=.000001,
        plane_co=Vector((0,0,0)),plane_no=Vector((1,0,0)),clear_inner=side>0,clear_outer=side<0)
    assert len(bm.faces)>=5 and all(vertex.co.x*side>=-1e-5 for vertex in bm.verts)
    bm.to_mesh(mesh);bm.free();mesh.update()
    obj=bpy.data.objects.new('Steve shell '+('left' if side<0 else 'right'),mesh);scene.collection.objects.link(obj)
    mesh.materials.append(interior)
    solid=obj.modifiers.new('Hollow shell thickness','SOLIDIFY');solid.thickness=.012;solid.offset=-1
    solid.material_offset=1;solid.material_offset_rim=1
    obj.rotation_mode='QUATERNION';fragments.append(obj)

camera=scene.camera;camera.data.type='ORTHO';camera.data.sensor_fit='HORIZONTAL'
camera.location=(0,-6,2);camera.rotation_euler=(-camera.location).to_track_quat('-Z','Y').to_euler()
ppu=900;camera.data.ortho_scale=W/ppu
right=camera.rotation_euler.to_matrix()@Vector((1,0,0))
up=camera.rotation_euler.to_matrix()@Vector((0,1,0))
front=camera.rotation_euler.to_matrix()@Vector((0,0,1))
for obj,centre,bottom,angle,yaw in zip(fragments,(565,1130),(790,760),(-63,13),(-18,20)):
    obj.rotation_quaternion=Quaternion(front,math.radians(angle))@Quaternion((0,0,1),math.radians(yaw))
    points=[obj.rotation_quaternion@v.co for v in obj.data.vertices]
    z=-min(p.z for p in points)+.012
    x=(centre-W/2)/ppu-(min(p.dot(right) for p in points)+max(p.dot(right) for p in points))/2
    y=((H/2-bottom)/ppu-min(p.dot(up) for p in points)-z*up.z)/up.y
    obj.location=(x,y,z)
    obj['canonical_source']='Steve/head with original skin UVs; bisected at local x=0'
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,0))
floor=bpy.context.object;floor.name='Original paving shadow receiver';floor.is_shadow_catcher=True
for obj in scene.objects:
    if obj.type=='LIGHT':obj.data.energy*=.32;obj.data.color=(.45,.53,.8)
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.035,.045,.09,1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.3

scene.use_nodes=True;tree=scene.node_tree;tree.nodes.clear()
def node(kind,name):
    value=tree.nodes.new(kind);value.name=value.label=name;return value
def link(a,output,b,socket):tree.links.new(a.outputs[output],b.inputs[socket])
def vec(socket,x,y):
    value=list(socket.default_value);value[:2]=[x,y];socket.default_value=value
def image(path,name,sequence=False):
    value=node('CompositorNodeImage',name);value.image=bpy.data.images.load(str(path))
    if sequence:
        value.image.source='SEQUENCE';value.frame_start=1;value.frame_duration=COUNT;value.use_auto_refresh=True
    else:value.image.pack()
    return value
def box(name,bounds):
    left,top,right,bottom=bounds
    value=node('CompositorNodeBoxMask',name)
    vec(value.inputs['Position'],(left+right)/(2*W),1-(top+bottom)/(2*H))
    vec(value.inputs['Size'],(right-left)/W,(bottom-top)/W);return value
def multiply(name,a,b):
    value=node('CompositorNodeMixRGB',name);value.blend_type='MULTIPLY';value.inputs[0].default_value=1
    link(a,0,value,1)
    if isinstance(b,tuple):value.inputs[2].default_value=b
    else:link(b,0,value,2)
    return value
transforms=[]
def follow_camera(value,name):
    scale=node('CompositorNodeScale',name+' zoom');scale.space='RELATIVE';link(value,0,scale,'Image')
    shift=node('CompositorNodeTranslate',name+' translation');link(scale,0,shift,'Image')
    transforms.append((scale,shift));return shift
source=image(frames[0],'Unmodified source frames',True)
plate=image(assets/'plate-floor.png','Reconstructed empty paving')
size=node('CompositorNodeScale','Plate dimensions');size.space='ABSOLUTE';size.inputs['X'].default_value=W;size.inputs['Y'].default_value=H;link(plate,0,size,'Image')
plate_fade=multiply('Paving exposure and fade',follow_camera(size,'Paving camera motion'),(1,1,1,1))
left_mask=box('Original left shell',[245,370,880,835])
right_mask=box('Original right shell',[870,165,1410,815])
mask=node('CompositorNodeMath','Both original fragments');mask.operation='MAXIMUM';link(left_mask,0,mask,0);link(right_mask,0,mask,1)
feather=node('CompositorNodeBlur','Repair feather');feather.filter_type='GAUSS';vec(feather.inputs['Size'],12,12);link(follow_camera(mask,'Removal camera motion'),0,feather,'Image')
clean=node('CompositorNodeMixRGB','Remove original mask fragments');link(feather,0,clean,0);link(source,0,clean,1);link(plate_fade,0,clean,2)
layer=node('CompositorNodeRLayers','Canonical Steve shell fragments')
actor_fade=multiply('Shell exposure and fade',layer,(1,1,1,1))
alpha=node('CompositorNodeSetAlpha','Preserve opaque shell during fade');link(actor_fade,0,alpha,'Image');link(layer,'Alpha',alpha,'Alpha')
over=node('CompositorNodeAlphaOver','Fractured Steve on original floor');over.inputs[0].default_value=1;link(clean,0,over,1);link(follow_camera(alpha,'Shell camera motion'),0,over,2)
visibility=node('CompositorNodeMixRGB','Only replace the protagonist shell shot');link(source,0,visibility,1);link(over,0,visibility,2)
output=node('CompositorNodeComposite','Final film frame');link(visibility,0,output,0)

selected=[int(value) for value in args.frames.split(',')] if args.frames else list(range(1,COUNT+1))
assert selected and all(1<=frame<=COUNT for frame in selected)
report=[]
for frame in selected:
    feature=features.get(frame);active=feature is not None and feature['fade']>0
    fade=feature['fade'] if active else 1
    zoom,dx,dy=camera_motion(frame)
    for scale,shift in transforms:
        for socket,value in ((scale.inputs['X'],zoom),(scale.inputs['Y'],zoom),(shift.inputs['X'],dx),(shift.inputs['Y'],-dy)):
            socket.default_value=value;socket.keyframe_insert('default_value',frame=frame)
    visibility.inputs[0].default_value=float(active);visibility.inputs[0].keyframe_insert('default_value',frame=frame)
    for value in (actor_fade,plate_fade):
        value.inputs[2].default_value=(fade,fade,fade,1);value.inputs[2].keyframe_insert('default_value',frame=frame)
    report.append({'frame':frame,'replaceShell':active,'fade':fade,'cameraTransform':[zoom,dx,dy],
                   'status':'candidate; visual and native playback acceptance pending'})
scene.frame_set(selected[0])
bpy.ops.wm.save_as_mainfile(filepath=str(args.out/'FinalC.blend'))
(args.out/'render-plan.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
for frame in selected:
    destination=args.out/f'{frame:05}.png';feature=features.get(frame)
    if feature is None or feature['fade']<=0:shutil.copy2(frames[frame-1],destination);continue
    scene.frame_set(frame)
    assert bpy.data.objects['Diamond sword'].hide_render
    scene.render.filepath=str(destination);bpy.ops.render.render(write_still=True)
print('FINAL_C_RENDER_COMPLETE',len(selected),args.out)
