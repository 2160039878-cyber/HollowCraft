"""Blender: retarget the sealed-vessel ending to the shared Steve rig."""
import argparse
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path
import bpy
from mathutils import Vector, Matrix, Quaternion

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--rig',type=Path,required=True)
parser.add_argument('--source',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--frames',help='Comma-separated preview frames')
parser.add_argument('--variant',choices=('FinalA','FinalB'),default='FinalA')
parser.add_argument('--reuse-close',type=Path,help='Accepted FinalA rendered directory for pixel-identical FinalB close frames')
parser.add_argument('--reuse-outside-wide','--reuse-previous',dest='reuse_outside_wide',type=Path,help='Previous render of the same ending; rebuild the wide shot unless --rerender-range is given')
parser.add_argument('--rerender-range',type=int,nargs=2,help='With --reuse-previous, rebuild only this changed interval')
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
args.rig,args.source,args.out=args.rig.resolve(),args.source.resolve(),args.out.resolve()
args.out.mkdir(parents=True,exist_ok=True)
is_b=args.variant=='FinalB'
W,H,FPS,COUNT=1920,1080,30,1144 if is_b else 969
assets=ROOT/'assets/cinematics/FinalA'
frames=sorted(args.source.glob('*.png'))
assert [p.name for p in frames]==[f'{f:05}.png' for f in range(1,COUNT+1)]
features=json.loads((ROOT/'assets/cinematics'/args.variant/'measured-frames.json').read_text())['frames']
assert len(features)==COUNT
wide_eyes=json.loads((ROOT/'assets/cinematics'/args.variant/'wide-eye-tracking.json').read_text())['frames']
assert set(map(int,wide_eyes))=={row['frame'] for row in features if row['shot']=='wide'}
reused={}
assert not args.rerender_range or args.reuse_outside_wide
if args.reuse_outside_wide:
    wide_start,wide_end=(229,427) if is_b else (87,319)
    if args.rerender_range:
        assert 1<=args.rerender_range[0]<=args.rerender_range[1]<=COUNT
        wide_start,wide_end=args.rerender_range
    for frame in range(1,COUNT+1):
        if not wide_start<=frame<=wide_end:
            candidate=args.reuse_outside_wide/f'{frame:05}.png';assert candidate.is_file();reused[frame]=candidate
if args.reuse_close:
    assert is_b
    for pair in json.loads((ROOT/'assets/cinematics/FinalB/identical-close-frames.json').read_text()):
        frame=pair['frame'];candidate=args.reuse_close/f"{pair['sourceFrameA']:05}.png"
        assert candidate.is_file()
        assert hashlib.file_digest(frames[frame-1].open('rb'),'sha256').hexdigest()==pair['sourceBSha256']
        reused[frame]=candidate

def sample(values,frame):
    before=max((f for f in values if f<=frame),default=min(values))
    after=min((f for f in values if f>=frame),default=max(values))
    t=(frame-before)/(after-before) if before!=after else 0
    a,b=values[before],values[after]
    return [x*(1-t)+y*t for x,y in zip(a,b)] if isinstance(a,(list,tuple)) else a*(1-t)+b*t

assert sample({1:[0,2],3:[2,4]},2)==[1,3]
bpy.ops.wm.open_mainfile(filepath=str(args.rig))
scene=bpy.context.scene
scene.render.engine='CYCLES'
prefs=bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type='OPTIX';prefs.get_devices()
for device in prefs.devices:device.use=device.type=='OPTIX'
assert any(device.use for device in prefs.devices)
scene.cycles.device='GPU';scene.cycles.samples=32
scene.cycles.use_denoising=True;scene.cycles.denoiser='OPTIX'
scene.render.resolution_x=W;scene.render.resolution_y=H;scene.render.resolution_percentage=100
scene.render.fps=FPS;scene.frame_start=1;scene.frame_end=COUNT
scene.render.film_transparent=True;scene.view_settings.view_transform='Standard'
scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
rig=bpy.data.objects['Steve'];rig.animation_data.action=bpy.data.actions.new('Sealed vessel performance')
rig['show_sword']=0.0;rig.keyframe_insert('["show_sword"]',frame=1)
rig.rotation_mode='QUATERNION';rig.rotation_quaternion=Quaternion();rig.scale=(1,1,1)
camera=scene.camera;camera.data.type='ORTHO';camera.data.sensor_fit='HORIZONTAL'
target=Vector((0,0,.9))
lights=[(obj,obj.location.copy()) for obj in scene.objects if obj.type=='LIGHT']
for light,_ in lights:
    light.data.energy*=.3;light.data.color=(.72,.73,.77)
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.035,.035,.04,1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.25
footage=bpy.data.images.load(str(frames[0]));footage.source='SEQUENCE'

eyes=[]
for side,x0,x1 in [('left',-.16875,-.05625),('right',.05625,.16875)]:
    mesh=bpy.data.meshes.new(side+' infection plane')
    mesh.from_pydata([(x0,-.226,1.51875),(x1,-.226,1.51875),(x1,-.226,1.575),(x0,-.226,1.575)],[],[(0,1,2,3)])
    mesh.uv_layers.new(name='Eye source window')
    for loop,uv in zip(mesh.uv_layers.active.data,[(0,0),(1,0),(1,1),(0,1)]):loop.uv=uv
    obj=bpy.data.objects.new(side+' infected eye',mesh);scene.collection.objects.link(obj);obj.parent=rig
    obj.vertex_groups.new(name='head').add(list(range(4)),1,'REPLACE')
    obj.modifiers.new('Head motion','ARMATURE').object=rig
    material=bpy.data.materials.new(side+' original infection fire');material.use_nodes=True
    mesh.materials.append(material);tree=material.node_tree;tree.nodes.clear()
    def shader_node(kind):return tree.nodes.new(kind)
    uv=shader_node('ShaderNodeTexCoord')
    scale=shader_node('ShaderNodeVectorMath');scale.operation='MULTIPLY'
    offset=shader_node('ShaderNodeVectorMath');offset.operation='ADD'
    tex=shader_node('ShaderNodeTexImage');tex.image=footage;tex.interpolation='Linear'
    tex.image_user.frame_start=1;tex.image_user.frame_duration=COUNT;tex.image_user.use_auto_refresh=True
    tree.links.new(uv.outputs['UV'],scale.inputs[0]);tree.links.new(scale.outputs[0],offset.inputs[0]);tree.links.new(offset.outputs[0],tex.inputs['Vector'])
    rgb=shader_node('ShaderNodeSeparateColor');rgb.mode='RGB';tree.links.new(tex.outputs['Color'],rgb.inputs[0])
    orange=shader_node('ShaderNodeMath');orange.operation='SUBTRACT'
    tree.links.new(rgb.outputs[0],orange.inputs[0]);tree.links.new(rgb.outputs[1],orange.inputs[1])
    warm=shader_node('ShaderNodeMath');warm.operation='SUBTRACT';warm.inputs[1].default_value=.05
    tree.links.new(orange.outputs[0],warm.inputs[0])
    gain=shader_node('ShaderNodeMath');gain.operation='MULTIPLY';gain.inputs[1].default_value=6;gain.use_clamp=True
    tree.links.new(warm.outputs[0],gain.inputs[0])
    blue_difference=shader_node('ShaderNodeMath');blue_difference.operation='SUBTRACT'
    tree.links.new(rgb.outputs[0],blue_difference.inputs[0]);tree.links.new(rgb.outputs[2],blue_difference.inputs[1])
    saturation=shader_node('ShaderNodeMath');saturation.operation='SUBTRACT';saturation.inputs[1].default_value=.35
    tree.links.new(blue_difference.outputs[0],saturation.inputs[0])
    saturation_gain=shader_node('ShaderNodeMath');saturation_gain.operation='MULTIPLY';saturation_gain.inputs[1].default_value=4;saturation_gain.use_clamp=True
    tree.links.new(saturation.outputs[0],saturation_gain.inputs[0])
    fire_key=shader_node('ShaderNodeMath');fire_key.operation='MINIMUM'
    tree.links.new(gain.outputs[0],fire_key.inputs[0]);tree.links.new(saturation_gain.outputs[0],fire_key.inputs[1])
    colour=shader_node('ShaderNodeMixRGB');colour.blend_type='MULTIPLY';colour.inputs[0].default_value=1
    tree.links.new(tex.outputs[0],colour.inputs[1]);tree.links.new(fire_key.outputs[0],colour.inputs[2])
    emission=shader_node('ShaderNodeEmission');emission.inputs['Strength'].default_value=2
    tree.links.new(colour.outputs[0],emission.inputs['Color'])
    transparent=shader_node('ShaderNodeBsdfTransparent')
    mix=shader_node('ShaderNodeMixShader');tree.links.new(transparent.outputs[0],mix.inputs[1]);tree.links.new(emission.outputs[0],mix.inputs[2])
    output=shader_node('ShaderNodeOutputMaterial');tree.links.new(mix.outputs[0],output.inputs['Surface'])
    eyes.append((scale.inputs[1],offset.inputs[1],mix.inputs[0],saturation.inputs[1],tex.image_user))

def chain_mesh():
    points=[];vertices=[];faces=[];tube=.006;radius=.020;straight=.0215
    for half in range(2):
        for i in range(17):
            angle=half*math.pi+i*math.pi/16
            centre=Vector((radius*math.cos(angle),radius*math.sin(angle)+(straight if half==0 else -straight),0))
            normal=Vector((math.cos(angle),math.sin(angle),0))
            points.append((centre,normal))
    for centre,normal in points:
        for j in range(8):
            angle=j*math.tau/8
            vertices.append(centre+normal*(tube*math.cos(angle))+Vector((0,0,tube*math.sin(angle))))
    for i in range(len(points)):
        for j in range(8):faces.append((i*8+j,i*8+(j+1)%8,((i+1)%len(points))*8+(j+1)%8,((i+1)%len(points))*8+j))
    mesh=bpy.data.meshes.new('Sealing chain link');mesh.from_pydata(vertices,[],faces);mesh.update()
    for polygon in mesh.polygons:polygon.use_smooth=True
    return mesh

link_mesh=chain_mesh()
metal=bpy.data.materials.new('Dark sealing metal');metal.use_nodes=True
metal_shader=metal.node_tree.nodes['Principled BSDF']
metal_shader.inputs['Base Color'].default_value=(.19,.21,.23,1)
metal_shader.inputs['Metallic'].default_value=.7;metal_shader.inputs['Roughness'].default_value=.32
metal_shader.inputs['Emission Color'].default_value=(1,1,1,1)
fresnel=metal.node_tree.nodes.new('ShaderNodeFresnel');fresnel.inputs['IOR'].default_value=1.45
edge=metal.node_tree.nodes.new('ShaderNodeMath');edge.operation='POWER';edge.inputs[1].default_value=2
metal.node_tree.links.new(fresnel.outputs[0],edge.inputs[0])
travel_glow=metal.node_tree.nodes.new('ShaderNodeMath');travel_glow.name='Travelling rim glow';travel_glow.operation='MULTIPLY'
metal.node_tree.links.new(edge.outputs[0],travel_glow.inputs[0]);metal.node_tree.links.new(travel_glow.outputs[0],metal_shader.inputs['Emission Strength'])
link_mesh.materials.append(metal)
chains=[]
for side in range(2):
    objects=[]
    for index in range(44):
        obj=bpy.data.objects.new(f'Sealing chain {side} link {index:02}',link_mesh);scene.collection.objects.link(obj)
        obj.rotation_mode='QUATERNION';obj.material_slots[0].link='OBJECT';obj.material_slots[0].material=metal.copy()
        strength=obj.material_slots[0].material.node_tree.nodes['Travelling rim glow'].inputs[1]
        objects.append((obj,strength))
    chains.append(objects)

scene.use_nodes=True;tree=scene.node_tree;tree.nodes.clear()
def node(kind,name):
    result=tree.nodes.new(kind);result.name=result.label=name;return result
def link(a,output,b,slot):tree.links.new(a.outputs[output],b.inputs[slot])
def vec(socket,x,y):
    value=list(socket.default_value);value[:2]=[x,y];socket.default_value=value
def key(socket,frame):socket.keyframe_insert('default_value',frame=frame)
def math_node(name,operation,a=None,b=None):
    result=node('CompositorNodeMath',name);result.operation=operation
    for i,value in enumerate((a,b)):
        if value is not None:result.inputs[i].default_value=value
    return result
def set_box(mask,box):
    left,top,right,bottom=box
    vec(mask.inputs['Position'],(left+right)/(2*W),1-(top+bottom)/(2*H))
    vec(mask.inputs['Size'],(right-left)/W,(bottom-top)/W)
def box(name,bounds):
    result=node('CompositorNodeBoxMask',name);set_box(result,bounds);return result
def blur(image,size,name):
    result=node('CompositorNodeBlur',name);result.filter_type='GAUSS';vec(result.inputs['Size'],size,size);link(image,0,result,'Image');return result
def image(path,name):
    result=node('CompositorNodeImage',name);result.image=bpy.data.images.load(str(path));result.image.pack();return result
def polygon(name,points):
    mask=bpy.data.masks.new(name);spline=mask.layers.new(name='Rotoscope').splines.new();spline.points.add(len(points)-1);spline.use_cyclic=True
    for point,(x,y) in zip(spline.points,points):
        point.co=(x/W,.5+(H/2-y)/W);point.handle_left_type=point.handle_right_type='VECTOR'
    result=node('CompositorNodeMask',name);result.mask=mask;result.size_source='FIXED';result.size_x=W;result.size_y=H;return result
def corridor(name,start,end,width):
    a,b=Vector(start),Vector(end);direction=(b-a).normalized();normal=Vector((-direction.y,direction.x))*width/2
    return polygon(name,[a+normal,b+normal,b-normal,a-normal])

source=node('CompositorNodeImage','Unmodified source frames');source.image=footage
source.frame_duration=COUNT;source.frame_start=1;source.use_auto_refresh=True
small_mask=box('Original distant figure and reflection',[900,500,1030,630])
outside=math_node('Pixels outside distant figure','SUBTRACT',1);link(small_mask,0,outside,1)
cut=node('CompositorNodeSetAlpha','Remove distant original');link(source,0,cut,'Image');link(outside,0,cut,'Alpha')
fill=node('CompositorNodeInpaint','Rebuild floor behind overhead figure');fill.inputs['Size'].default_value=72;link(cut,0,fill,'Image')
wide_plate=image(assets/'plate-wide.png','Empty chamber floor')
wide_size=node('CompositorNodeScale','Wide plate dimensions');wide_size.space='ABSOLUTE';wide_size.inputs['X'].default_value=W;wide_size.inputs['Y'].default_value=H;link(wide_plate,0,wide_size,'Image')
wide_zoom=node('CompositorNodeScale','Variant wide camera distance');wide_zoom.space='RELATIVE'
wide_zoom.inputs['X'].default_value=wide_zoom.inputs['Y'].default_value=.95 if is_b else 1;link(wide_size,0,wide_zoom,'Image')
wide_move=node('CompositorNodeTranslate','Wide floor camera motion');link(wide_zoom,0,wide_move,'Image')
floor_region=box('Floor plate below contact line only',[0,832,W,H])
floor_enable=math_node('Wide floor plate gate','MULTIPLY',None,0);link(floor_region,0,floor_enable,0)
small_fill=node('CompositorNodeMixRGB','Keep native chamber haze above the floor');link(floor_enable,0,small_fill,0);link(fill,0,small_fill,1);link(wide_move,0,small_fill,2)
small_feather=blur(small_mask,3,'Distant feather')
small_clean=node('CompositorNodeMixRGB','Distant cleanup edge');link(small_feather,0,small_clean,0);link(source,0,small_clean,1);link(small_fill,0,small_clean,2)

old_actor=box('Original close figure',[650,380,1280,1160])
holes=old_actor
chain_removal=[]
for i,(start,end,width) in enumerate([((-500,-500),(1450,1500),220),((2320,0),(750,1160),260),((-400,-300),(950,1500),350),((2300,0),(950,1520),350)]):
    ribbon=corridor('Original foreground chain region '+str(i),start,end,width)
    gate=math_node('Original chain removal timing '+str(i),'MULTIPLY',None,0);link(ribbon,0,gate,0);chain_removal.append(gate.inputs[1])
    union=math_node('Character and chain removal '+str(i),'MAXIMUM');link(holes,0,union,0);link(gate,0,union,1);holes=union
known=math_node('Exposure samples outside removed areas','SUBTRACT',1);link(holes,0,known,1)
close_cut=node('CompositorNodeSetAlpha','Remove old close actor and chains');link(source,0,close_cut,'Image');link(known,0,close_cut,'Alpha')
close_fill=node('CompositorNodeInpaint','Continue current moving chamber light');close_fill.inputs['Size'].default_value=1600;link(close_cut,0,close_fill,'Image')
close_clean=node('CompositorNodeMixRGB','Close-shot reconstruction');link(blur(holes,8,'Close cleanup feather'),0,close_clean,0);link(source,0,close_clean,1);link(close_fill,0,close_clean,2)
background=node('CompositorNodeMixRGB','Close or distant shot');link(small_clean,0,background,1);link(close_clean,0,background,2)

layer=node('CompositorNodeRLayers','Steve and sealing chains')
clamp=node('CompositorNodeMixRGB','Film-range character colour');clamp.blend_type='MULTIPLY';clamp.use_clamp=True;clamp.inputs[0].default_value=1;clamp.inputs[2].default_value=(1,1,1,1);link(layer,'Image',clamp,1)
fade_rgb=node('CompositorNodeMixRGB','Character exposure and fade');fade_rgb.blend_type='MULTIPLY';fade_rgb.inputs[0].default_value=1;link(clamp,0,fade_rgb,1)
fade_alpha=math_node('Character fade alpha','MULTIPLY',None,1);link(layer,'Alpha',fade_alpha,0)
actor=node('CompositorNodeSetAlpha','Premultiplied character fade');link(fade_rgb,0,actor,'Image');link(fade_alpha,0,actor,'Alpha')
reflection_flip=node('CompositorNodeFlip','Reflected sealed vessel');reflection_flip.axis='Y';link(actor,0,reflection_flip,'Image')
reflection_scale=node('CompositorNodeScale','Floor reflection compression');reflection_scale.space='RELATIVE';reflection_scale.inputs['X'].default_value=1;reflection_scale.inputs['Y'].default_value=.6;link(reflection_flip,0,reflection_scale,'Image')
reflection_move=node('CompositorNodeTranslate','Reflection floor position');link(reflection_scale,0,reflection_move,'Image')
reflection=node('CompositorNodeAlphaOver','Dim floor reflection');reflection.inputs[0].default_value=0;link(background,0,reflection,1);link(blur(reflection_move,3,'Reflection softness'),0,reflection,2)
over=node('CompositorNodeAlphaOver','Retargeted protagonist');over.inputs[0].default_value=1;link(reflection,0,over,1);link(actor,0,over,2)
glow=node('CompositorNodeGlare','Eye infection and chain bloom');glow.glare_type='FOG_GLOW';glow.quality='HIGH';glow.inputs['Threshold'].default_value=1.1;glow.inputs['Size'].default_value=.3;link(layer,'Image',glow,'Image')
# Blender 4.5 Image includes the source; only Glare can be added to an existing composite.
glow_clamp=node('CompositorNodeMixRGB','Film-range bloom');glow_clamp.blend_type='MULTIPLY';glow_clamp.use_clamp=True;glow_clamp.inputs[0].default_value=1;glow_clamp.inputs[2].default_value=(1,1,1,1);link(glow,'Glare',glow_clamp,1)
glow_fade=node('CompositorNodeMixRGB','Bloom fade');glow_fade.blend_type='MULTIPLY';glow_fade.inputs[0].default_value=1;link(glow_clamp,0,glow_fade,1)
add_glow=node('CompositorNodeMixRGB','Emissive light over original environment');add_glow.blend_type='ADD';add_glow.inputs[0].default_value=1;link(over,0,add_glow,1);link(glow_fade,0,add_glow,2)
visibility=node('CompositorNodeMixRGB','Keep original non-player shots');link(source,0,visibility,1);link(add_glow,0,visibility,2)
output=node('CompositorNodeComposite','Final movie frame');link(visibility,0,output,0)

# The transient white sealing glyph is scenery, not a second character.
source_rgb=node('CompositorNodeSeparateColor','Original light colour');source_rgb.mode='RGB';link(source,0,source_rgb,0)
# Independent effects artwork avoids recovering the old face from its changing illumination.
glyph_layers=[]
for name in ('base','complete'):
    artwork=image(assets/('sealing-ornament-'+name+'.png'),'Reconstructed sealing ornament '+name)
    size=node('CompositorNodeScale','Sealing artwork dimensions '+name);size.space='ABSOLUTE';size.inputs['X'].default_value=W;size.inputs['Y'].default_value=H;link(artwork,0,size,'Image');glyph_layers.append(size)
glyph_design=node('CompositorNodeMixRGB','Inner sealing strokes arrive');link(glyph_layers[0],0,glyph_design,1);link(glyph_layers[1],0,glyph_design,2)
glyph_hole=node('CompositorNodeEllipseMask','Sealing strokes advance from the perimeter');vec(glyph_hole.inputs['Position'],.5,.5)
glyph_reveal=math_node('Revealed sealing strokes','SUBTRACT',1);link(blur(glyph_hole,16,'Soft sealing reveal'),0,glyph_reveal,1)
glyph_gain=node('CompositorNodeMixRGB','Progressive sealing ornament');glyph_gain.blend_type='MULTIPLY';glyph_gain.inputs[0].default_value=1;link(glyph_design,0,glyph_gain,1);link(glyph_reveal,0,glyph_gain,2)
glyph_softness=blur(glyph_gain,1.5,'Sealing light dispersal')
glyph_gate=node('CompositorNodeMixRGB','Sealing glyph timing');glyph_gate.blend_type='MULTIPLY';glyph_gate.inputs[0].default_value=1;link(glyph_softness,0,glyph_gate,1)
glyph_add=node('CompositorNodeMixRGB','Sealing light over retargeted face');glyph_add.blend_type='SCREEN';glyph_add.inputs[0].default_value=1
link(add_glow,0,glyph_add,1);link(glyph_gate,0,glyph_add,2);link(glyph_add,0,visibility,2)

# Keep the original luminous chain tips during the two incoming sweeps.
tip_reference=image(frames[427 if is_b else 319],'Before incoming sealing chains')
tip_difference=node('CompositorNodeMixRGB','Transient chain light');tip_difference.blend_type='SUBTRACT';tip_difference.inputs[0].default_value=1;tip_difference.use_clamp=True;link(source,0,tip_difference,1);link(tip_reference,0,tip_difference,2)
tip_rgb=node('CompositorNodeSeparateColor','Neutral incoming light');tip_rgb.mode='RGB';link(tip_difference,0,tip_rgb,0)
tip_level=math_node('Reject background compression differences','SUBTRACT',None,.025);tip_level.use_clamp=True;link(tip_rgb,2,tip_level,0)
tip_reference_rgb=node('CompositorNodeSeparateColor','Original mask exclusion');tip_reference_rgb.mode='RGB';link(tip_reference,0,tip_reference_rgb,0)
tip_old_mask=math_node('Original pale mask','GREATER_THAN',None,.18);link(tip_reference_rgb,2,tip_old_mask,0)
tip_mask_margin=math_node('Cover original outline motion','GREATER_THAN',None,.01);link(blur(tip_old_mask,12,'Original outline margin'),0,tip_mask_margin,0)
tip_outside=math_node('Never restore the original mask','SUBTRACT',1);link(tip_mask_margin,0,tip_outside,1)
tip_brightness=math_node('Suppress dark cloak pixels','SUBTRACT',None,.18);link(source_rgb,2,tip_brightness,0)
tip_soft=math_node('Soft incoming light edge','MULTIPLY',None,4);tip_soft.use_clamp=True;link(tip_brightness,0,tip_soft,0)
tip_safe=math_node('Only light outside the original mask','MULTIPLY');link(tip_outside,0,tip_safe,0);link(tip_soft,0,tip_safe,1)
tip_light=math_node('Tracked tip emission','MULTIPLY');link(tip_level,0,tip_light,0);link(tip_safe,0,tip_light,1)
tip_region=box('Tracked chain tip region',[0,0,1,1])
tip_colour=math_node('Original chain tip light','MULTIPLY');link(tip_light,0,tip_colour,0);link(tip_region,0,tip_colour,1)
tip_gate=node('CompositorNodeMixRGB','Incoming chain tip timing');tip_gate.blend_type='MULTIPLY';tip_gate.inputs[0].default_value=1;link(tip_colour,0,tip_gate,1)
tip_add=node('CompositorNodeMixRGB','Incoming tips over Steve');tip_add.blend_type='ADD';tip_add.inputs[0].default_value=1;link(glyph_add,0,tip_add,1);link(tip_gate,0,tip_add,2)
tip_behind=node('CompositorNodeMixRGB','Second chain passes behind Steve before wrapping');tip_behind.blend_type='MULTIPLY';tip_behind.inputs[0].default_value=1;link(tip_colour,0,tip_behind,1)
tip_backdrop=node('CompositorNodeMixRGB','Native tip occluded by new body');tip_backdrop.blend_type='ADD';tip_backdrop.inputs[0].default_value=1;link(reflection,0,tip_backdrop,1);link(tip_behind,0,tip_backdrop,2);link(tip_backdrop,0,over,1)

# Recover only chromatic emission. Neutral mask/cloak pixels cannot become a second body.
fire=node('CompositorNodeMixRGB','Original orange emission above neutral background');fire.blend_type='SUBTRACT';fire.inputs[0].default_value=1;fire.use_clamp=True
link(source,0,fire,1);link(source_rgb,2,fire,2)
warm=math_node('Warm emission difference','SUBTRACT');link(source_rgb,0,warm,0);link(source_rgb,1,warm,1)
warm_gain=math_node('Warm emission key','MULTIPLY',None,20);warm_gain.use_clamp=True;link(warm,0,warm_gain,0)
fire_region=box('Original eye beams above the floor',[900,700,1030,840])
fire_key=math_node('Original eye beam region','MULTIPLY');link(warm_gain,0,fire_key,0);link(fire_region,0,fire_key,1)
fire_colour=node('CompositorNodeMixRGB','Recovered eye beam colour');fire_colour.blend_type='MULTIPLY';fire_colour.inputs[0].default_value=1;link(fire,0,fire_colour,1);link(fire_key,0,fire_colour,2)
# Orange rays also darken the underlying blue channel. Rebuild their actual footprint,
# rather than subtracting colour (dark ghosts) or clearing the entire bounding rectangle (lost fog).
ray_pixels=math_node('Original ray footprint','GREATER_THAN',None,.06);link(fire_key,0,ray_pixels,0)
ray_holes=math_node('Wide ray removal timing','MULTIPLY',None,0);link(ray_pixels,0,ray_holes,0)
distant_holes=math_node('Original distant body and ray pixels','MAXIMUM');link(small_mask,0,distant_holes,0);link(ray_holes,0,distant_holes,1)
link(distant_holes,0,outside,1);link(distant_holes,0,small_feather,'Image')
fire_scale=node('CompositorNodeScale','Steve eye spacing');fire_scale.space='RELATIVE';fire_scale.inputs['Y'].default_value=1;link(fire_colour,0,fire_scale,'Image')
fire_move=node('CompositorNodeTranslate','Steve eye beam origin');link(fire_scale,0,fire_move,'Image')
fire_flip=node('CompositorNodeFlip','Reflected eye beams');fire_flip.axis='Y';link(fire_move,0,fire_flip,'Image')
fire_ref_scale=node('CompositorNodeScale','Eye beam reflection compression');fire_ref_scale.space='RELATIVE';fire_ref_scale.inputs['X'].default_value=1;fire_ref_scale.inputs['Y'].default_value=.6;link(fire_flip,0,fire_ref_scale,'Image')
fire_ref_move=node('CompositorNodeTranslate','Eye beam reflection contact line');link(fire_ref_scale,0,fire_ref_move,'Image')
fire_ref_gain=node('CompositorNodeMixRGB','Dim reflected eye beams');fire_ref_gain.blend_type='MULTIPLY';fire_ref_gain.inputs[0].default_value=1;fire_ref_gain.inputs[2].default_value=(.14,.14,.14,1);link(fire_ref_move,0,fire_ref_gain,1)
fire_both=node('CompositorNodeMixRGB','Eye beams and their reflection');fire_both.blend_type='ADD';fire_both.inputs[0].default_value=1;link(fire_move,0,fire_both,1);link(fire_ref_gain,0,fire_both,2)
fire_gate=node('CompositorNodeMixRGB','Wide-shot eye beam timing');fire_gate.blend_type='MULTIPLY';fire_gate.inputs[0].default_value=1;link(fire_both,0,fire_gate,1)
fire_add=node('CompositorNodeMixRGB','Infection light attached to Steve');fire_add.blend_type='ADD';fire_add.inputs[0].default_value=1;link(tip_add,0,fire_add,1);link(fire_gate,0,fire_add,2);link(fire_add,0,visibility,2)

def projected_points(name,right,up):
    bone=rig.pose.bones[name];matrix=bone.matrix@bone.bone.matrix_local.inverted()
    return [rig.rotation_quaternion@(matrix@v.co) for v in bpy.data.objects[name].data.vertices]

def pose_actor(frame,view,ppu,anchor,mode,values):
    camera.location=target+Vector(view)
    camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.ortho_scale=W/ppu
    right=camera.rotation_euler.to_matrix()@Vector((1,0,0))
    up=camera.rotation_euler.to_matrix()@Vector((0,1,0))
    front=camera.rotation_euler.to_matrix()@Vector((0,0,1))
    rig.location=(0,0,0);rig.rotation_quaternion=Quaternion(front,math.radians(values.get('roll',0)))
    for name in ('head','body','right_arm','left_arm','right_leg','left_leg'):
        bone=rig.pose.bones[name];bone.rotation_mode='XYZ'
        bone.rotation_euler=[math.radians(values.get(name+'.r'+axis,0)) for axis in 'xyz']
        bone.keyframe_insert('rotation_euler',frame=frame,group=name)
    bpy.context.view_layer.update()
    head=rig.pose.bones['head']
    head_center=rig.rotation_quaternion@(head.matrix@head.bone.matrix_local.inverted()@Vector((0,0,1.575)))
    if mode=='chin':
        vertical=min(p.dot(up) for p in projected_points('head',right,up))
    elif mode=='ground':
        vertical=min(p.dot(up) for name in ('right_leg','left_leg') for p in projected_points(name,right,up))
    else:vertical=head_center.dot(up)
    rig.location=target+right*((anchor[0]-W/2)/ppu-head_center.dot(right))+up*((H/2-anchor[1])/ppu-vertical)
    rig.keyframe_insert('location',frame=frame);rig.keyframe_insert('rotation_quaternion',frame=frame)
    camera.keyframe_insert('location',frame=frame);camera.keyframe_insert('rotation_euler',frame=frame);camera.data.keyframe_insert('ortho_scale',frame=frame)
    for light,offset in lights:
        light.location=rig.location+offset
        light.rotation_euler=(rig.location+Vector((0,0,1))-light.location).to_track_quat('-Z','Y').to_euler()
        light.keyframe_insert('location',frame=frame);light.keyframe_insert('rotation_euler',frame=frame)
    return right,up,front

def place_chains(frame,story,close,ppu,right,up,front):
    phase=max(0,min(1,(story-407)/5))
    endpoints=[((-500,-500),(1450,1500),(-400,-300),(950,1500)),
               ((2320,0),(750,1160),(2300,0),(950,1520))]
    for side,objects in enumerate(chains):
        a0,b0,a1,b1=endpoints[side]
        a=Vector(a0).lerp(Vector(a1),phase);b=Vector(b0).lerp(Vector(b1),phase)
        tangent=(b-a).normalized()
        direction=(right*tangent.x-up*tangent.y).normalized()
        normal=direction.cross(front).normalized()
        orient=Matrix(((normal.x,direction.x,front.x),(normal.y,direction.y,front.y),(normal.z,direction.z,front.z))).to_quaternion()
        sweep=sample({324:0,325:.3,326:.3,327:.6,328:.8,329:1} if side==0 else {350:0,351:.25,352:.25,353:.85,354:1},story)
        for index,(obj,strength) in enumerate(objects):
            scale=1.7*(1-phase)+.95*phase
            obj.scale=(scale,scale,scale);obj.keyframe_insert('scale',frame=frame)
            distance=(index-4)*.075*ppu*scale
            obj.hide_render=not close or sweep==0 or (sweep<1 and distance>sweep*(b-a).length-160)
            obj.keyframe_insert('hide_render',frame=frame)
            if not close:continue
            pixel=a+tangent*distance
            depth=-.55 if side==1 and story<354 else .55+.025*side
            obj.location=target+right*((pixel.x-W/2)/ppu)+up*((H/2-pixel.y)/ppu)+front*depth
            obj.rotation_quaternion=orient@Quaternion((0,1,0),math.radians((index%2)*90-35))
            obj.keyframe_insert('location',frame=frame);obj.keyframe_insert('rotation_quaternion',frame=frame)
            travel=max(0,min(1,distance/(b-a).length))
            wave=(story-(389 if side==0 else 403))/(43 if side==0 else 29)
            amount=max(0,min(1,(wave-travel)*8))
            strength.default_value=amount*5
            key(strength,frame)

def set_eye_window(frame,index,rectangle,alpha,threshold=.35,source_frame=None):
    left,top,right,bottom=rectangle
    scale,offset,visibility,cutoff,image_user=eyes[index]
    scale.default_value=((right-left)/W,(bottom-top)/H,0)
    offset.default_value=(left/W,1-bottom/H,0)
    visibility.default_value=alpha
    cutoff.default_value=threshold
    image_user.frame_offset=(source_frame or frame)-frame
    image_user.keyframe_insert('frame_offset',frame=frame)
    for socket in (scale,offset,visibility,cutoff):key(socket,frame)

selected=[int(f) for f in args.frames.split(',')] if args.frames else list(range(1,COUNT+1))
assert selected and all(1<=frame<=COUNT for frame in selected)
report=[]
for frame in selected:
    feature=features[frame-1];shot=feature['shot'];fade=feature['fade'];story=feature.get('poseFrame',frame)
    active=shot is not None and fade>1e-6;close=shot=='close'
    visibility.inputs[0].default_value=float(active);key(visibility.inputs[0],frame)
    background.inputs[0].default_value=float(close);key(background.inputs[0],frame)
    floor_enable.inputs[1].default_value=float(shot=='wide');key(floor_enable.inputs[1],frame)
    ray_holes.inputs[1].default_value=float(shot=='wide');key(ray_holes.inputs[1],frame)
    vec(small_feather.inputs['Size'],8 if shot=='wide' else 3,8 if shot=='wide' else 3);key(small_feather.inputs['Size'],frame)
    fire_gate.inputs[2].default_value=(1,1,1,1) if shot=='wide' else (0,0,0,1);key(fire_gate.inputs[2],frame)
    for i,socket in enumerate(chain_removal):
        socket.default_value=float(close and story>=(325 if i%2==0 else 351) and (story<=412 if i<2 else story>=407));key(socket,frame)
    fade_rgb.inputs[2].default_value=(fade*.75,fade*.75,fade*.78,1);key(fade_rgb.inputs[2],frame)
    # The film fades to black; reducing opacity would expose the chamber through Steve.
    fade_alpha.inputs[1].default_value=1;key(fade_alpha.inputs[1],frame)
    glow_fade.inputs[2].default_value=(fade,fade,fade,1);key(glow_fade.inputs[2],frame)
    glyph_opacity=sample({435:0,437:1,452:1,453:.8,454:.4,455:.12,456:0},story) if close else 0
    glyph_gate.inputs[2].default_value=(glyph_opacity,glyph_opacity,glyph_opacity,1);key(glyph_gate.inputs[2],frame)
    radius=sample({435:1400,437:1100,440:650,442:520,445:270,448:0},story)
    # Ellipse mask dimensions are both expressed relative to the image width.
    vec(glyph_hole.inputs['Size'],2*radius/W,2*radius/W);key(glyph_hole.inputs['Size'],frame)
    glyph_design.inputs[0].default_value=sample({445:0,448:1},story);key(glyph_design.inputs[0],frame)
    softness=sample({451:1.5,453:5,455:10,456:12},story)
    vec(glyph_softness.inputs['Size'],softness,softness);key(glyph_softness.inputs['Size'],frame)
    tip_gate.inputs[2].default_value=(1,1,1,1) if close and 325<=story<=329 else (0,0,0,1);key(tip_gate.inputs[2],frame)
    tip_behind.inputs[2].default_value=(1,1,1,1) if close and 351<=story<=353 else (0,0,0,1);key(tip_behind.inputs[2],frame)
    tip_box=sample({325:[0,0,360,380],326:[0,0,360,380],327:[440,440,820,850],328:[700,700,1100,1110],329:[960,950,1310,1250],
                    351:[1500,50,1920,600],352:[1500,50,1920,600],353:[980,400,1620,1130]},story)
    set_box(tip_region,tip_box);key(tip_region.inputs['Position'],frame);key(tip_region.inputs['Size'],frame)
    reflection.inputs[0].default_value=.14 if shot=='wide' else 0;key(reflection.inputs[0],frame)
    values={'right_arm.rx':-35,'left_arm.rx':-35,'right_arm.rz':-4,'left_arm.rz':4,
            'right_leg.rz':3,'left_leg.rz':-3}
    ppu=36;anchor=(960,845);view=(0,-6,.8);mode='ground'
    if shot=='overhead':
        box_value=feature['headBrightBounds'];anchor=((box_value[0]+box_value[2])/2,(box_value[1]+box_value[3])/2+8)
        ppu=75;view=(3,-5,18);mode='head'
        values.update({'head.rx':35,'body.rx':25,'right_leg.rx':20,'left_leg.rx':-20})
        set_box(small_mask,[910,510,1008,605])
    elif shot=='wide':
        head=feature['headBrightBounds'];ground=sample({87:845,260:835,319:835},story)-(16 if is_b else 0);anchor=((head[0]+head[2])/2,ground)
        ppu=32 if is_b else 36
        # Source rise occurs at A155..163 / B277..285; the longer shot holds must not stretch the motion.
        crouch=sample({154:1,155:.77,157:.54,159:.19,161:.04,163:0},frame-(122 if is_b else 0))
        view=(6*crouch,-6+5*crouch,.8)
        look_up=max(0,min(1,(story-250)/5))
        values.update({'head.rx':(20+30*crouch)*(1-look_up)-35*look_up,
                       'body.rx':30*crouch,'right_leg.rx':65*crouch,'left_leg.rx':-65*crouch})
        # Bright head bounds omit the dark cloak and horns, including while the head turns.
        margin=28
        set_box(small_mask,[head[0]-margin,head[1]-8,head[2]+margin,915])
        warm_bounds=wide_eyes[str(frame)]['warmBounds']
        set_box(fire_region,[warm_bounds[0],warm_bounds[1],warm_bounds[2],ground-2] if warm_bounds else [0,0,1,1])
        key(fire_region.inputs['Position'],frame);key(fire_region.inputs['Size'],frame)
        set_box(floor_region,[0,ground-3,W,H]);key(floor_region.inputs['Position'],frame);key(floor_region.inputs['Size'],frame)
        wide_move.inputs['Y'].default_value=(H/2+(835-H/2)*(.95 if is_b else 1))-ground;key(wide_move.inputs['Y'],frame)
        reflection_move.inputs['Y'].default_value=-(1.6*anchor[1]-.8*H);key(reflection_move.inputs['Y'],frame)
        fire_ref_move.inputs['Y'].default_value=reflection_move.inputs['Y'].default_value;key(fire_ref_move.inputs['Y'],frame)
    elif close:
        ppu=sample({320:800,406:800,407:1000,408:2200,412:3300,622:3300},story)
        sway=sample({320:0,328:0,329:40,330:25,335:0,353:0,354:-40,355:-25,360:0},story)
        roll=sample({320:0,328:0,329:-9,330:-6,335:0,353:0,354:9,355:6,360:0},story)
        anchor=(960+sway,sample({320:850,407:850,408:950,412:950,622:950},story));mode='chin'
        values['roll']=roll
        values['head.rx']=sample({320:-35,370:-35,374:20,407:20,412:45,622:45},story)
        set_box(old_actor,sample({320:[650,380,1280,1160],370:[650,380,1280,1160],371:[600,190,1320,1160],
                                  406:[600,190,1320,1160],407:[600,100,1320,1160],408:[280,-80,1660,1160],412:[140,-80,1790,1160],622:[140,-80,1790,1160]},story))
        key(old_actor.inputs['Position'],frame);key(old_actor.inputs['Size'],frame)
    key(small_mask.inputs['Position'],frame);key(small_mask.inputs['Size'],frame)
    right,up,front=pose_actor(frame,view,ppu,anchor,mode,values)
    if shot=='wide':
        bone=rig.pose.bones['head'];matrix=bone.matrix@bone.bone.matrix_local.inverted()
        projected=[]
        for x in (-.1125,.1125):
            point=rig.location+rig.rotation_quaternion@(matrix@Vector((x,-.226,1.546875)))-target
            projected.append((W/2+point.dot(right)*ppu,H/2-point.dot(up)*ppu))
        centres=wide_eyes[str(frame)]['centres'];old_x=sum(p[0] for p in centres)/2;old_y=sum(p[1] for p in centres)/2
        new_x=sum(p[0] for p in projected)/2;new_y=sum(p[1] for p in projected)/2
        spacing=max(.25,min(2,abs(projected[1][0]-projected[0][0])/max(4,abs(centres[1][0]-centres[0][0]))))
        for socket,value in ((fire_scale.inputs['X'],spacing),(fire_move.inputs['X'],new_x-(W/2+(old_x-W/2)*spacing)),(fire_move.inputs['Y'],old_y-new_y)):
            socket.default_value=value;key(socket,frame)
    place_chains(frame,story,close,ppu,right,up,front)
    if close:
        left=sample({320:[810,495,895,575],370:[810,495,895,575],374:[810,675,890,780],406:[810,675,890,780],
                     407:[775,665,890,790],408:[740,630,875,785],409:[685,580,835,770],410:[620,520,795,740],
                     411:[535,450,755,715],412:[475,400,740,710],622:[475,400,740,710]},story)
        right_eye=sample({320:[1035,495,1120,575],370:[1035,495,1120,575],374:[1030,675,1115,780],406:[1030,675,1115,780],
                          407:[1020,665,1135,790],408:[1045,630,1180,785],409:[1085,580,1235,770],410:[1125,520,1300,740],
                          411:[1165,450,1385,715],412:[1200,400,1470,710],622:[1200,400,1470,710]},story)
        left=[left[0]+sway,left[1]+roll*2.5,left[2]+sway,left[3]+roll*2.5]
        right_eye=[right_eye[0]+sway,right_eye[1]-roll*2.5,right_eye[2]+sway,right_eye[3]-roll*2.5]
        infected=1
    elif shot=='wide':
        left,right_eye=wide_eyes[str(frame)]['windows'];infected=1
    else:left,right_eye,infected=[940,520,960,545],[960,520,980,545],0
    # Use nearby clean flame motion while the source eyes are covered by the white seal.
    eye_frame=frame+40 if close and 436<=story<=456 else frame
    set_eye_window(frame,0,left,infected,.05 if shot=='wide' else .35,eye_frame);set_eye_window(frame,1,right_eye,infected,.05 if shot=='wide' else .35,eye_frame)
    report.append({'frame':frame,'shot':shot,'poseFrame':story,'fade':fade,'pixelsPerUnit':ppu,'anchorPx':anchor,
                   'reusedRenderedFrame':str(reused[frame]) if frame in reused else None,
                   'anchorMode':mode,'headPitch':values.get('head.rx',0),'originalEyeWindows':[left,right_eye],
                   'eyeSourceFrame':eye_frame,'sealOpacity':glyph_opacity,
                   'sealTreatment':'Independent reconstructed artwork; perimeter reveal, inner-stroke transition and blur/fade on original timeline',
                   'chainTreatment':'3D links enter at native frames325/351, original luminous tips retained through tracked mattes; Steve reacts to chain pulls',
                   'status':'render candidate, visual and runtime acceptance required'})

for action in bpy.data.actions:
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for point in curve.keyframe_points:point.interpolation='LINEAR'
scene.frame_set(selected[0])
bpy.ops.wm.save_as_mainfile(filepath=str(args.out/(args.variant+'.blend')))
(args.out/'render-plan.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
for frame in selected:
    destination=args.out/f'{frame:05}.png'
    if frame in reused:
        shutil.copy2(reused[frame],destination);continue
    if features[frame-1]['shot'] is None or features[frame-1]['fade']<=1e-6:
        shutil.copy2(frames[frame-1],destination);continue
    scene.frame_set(frame);scene.render.filepath=str(destination);bpy.ops.render.render(write_still=True)
print('ENDING_RENDER_COMPLETE',args.variant,len(selected),'reused',len(reused),args.out)
