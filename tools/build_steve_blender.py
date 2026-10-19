"""Run with Blender --background --python this_file -- OUTPUT_DIRECTORY."""
import json
import math
import sys
from pathlib import Path
import bpy
from mathutils import Vector, Quaternion, Matrix

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets' / 'steve'
OUT = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
MODEL = json.loads((ASSETS / 'model.json').read_text(encoding='utf-8-sig'))
MOTIONS = json.loads((ASSETS / 'poses.json').read_text(encoding='utf-8'))
UNIT = 1.8 / 32


def point(v):
    return Vector((v[0] * UNIT, v[2] * UNIT, (24-v[1]) * UNIT))


def sample(curve, t):
    if t <= curve[0][0]: return curve[0][1]
    for (a,v0),(b,v1) in zip(curve,curve[1:]):
        if t <= b:
            u = (t-a)/(b-a)
            return v0+(v1-v0)*u*u*(3-2*u)
    return curve[-1][1]


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 32
scene.render.resolution_x = 768
scene.render.resolution_y = 768
scene.render.resolution_percentage = 100
scene.render.fps = 60
scene.view_settings.view_transform = 'Standard'
scene.render.film_transparent = True

image = bpy.data.images.load(str(ASSETS / 'steve.png'), check_existing=True)
image.pack()
material = bpy.data.materials.new('Steve • original Minecraft skin')
material.use_nodes = True
nodes = material.node_tree.nodes
shader = nodes.get('Principled BSDF')
shader.inputs['Roughness'].default_value = .9
texture = nodes.new('ShaderNodeTexImage')
texture.image = image
texture.interpolation = 'Closest'
material.node_tree.links.new(texture.outputs['Color'], shader.inputs['Base Color'])
material.node_tree.links.new(texture.outputs['Alpha'], shader.inputs['Alpha'])

armature = bpy.data.armatures.new('Steve skeleton')
rig = bpy.data.objects.new('Steve', armature)
scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
rig.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
root = armature.edit_bones.new('root')
root.head, root.tail = (0,0,0), (0,0,.2)
parts = {p['name']:p for p in MODEL['parts']}
for name in MOTIONS['bones']:
    p = parts[name]
    bone = armature.edit_bones.new(name)
    bone.head = point(p['pivot'])
    bone.tail = bone.head + Vector((0,0,-.3))
    bone.align_roll(Vector((0,1,0)))
    bone.parent = root
bpy.ops.object.mode_set(mode='OBJECT')
rig.show_in_front = True
rig['void_mode']=rig['head_only']=rig['void_eyes']=0.0

def rig_driver(target,prop,expression,variables):
    driver=target.driver_add(prop).driver
    for name,path in variables.items():
        variable=driver.variables.new();variable.name=name
        variable.targets[0].id=rig;variable.targets[0].data_path=f'["{path}"]'
    driver.expression=expression

void_mix=nodes.new('ShaderNodeMixRGB');void_mix.blend_type='MIX'
void_mix.inputs[2].default_value=(0,0,0,1)
material.node_tree.links.new(texture.outputs['Color'],void_mix.inputs[1])
material.node_tree.links.new(void_mix.outputs[0],shader.inputs['Base Color'])
rig_driver(void_mix.inputs[0],'default_value','v',{'v':'void_mode'})

faces = [(5,4,0,1),(2,3,7,6),(0,4,7,3),(1,0,3,2),(5,1,2,6),(4,5,6,7)]
for part in MODEL['parts']:
    name, cube = part['name'], part['cube']
    owner = name if name in MOTIONS['bones'] else part['parent']
    pivot = parts[owner]['pivot']
    origin = cube['origin']
    size = cube['size']
    d = cube.get('deformation', 0)
    x0,y0,z0 = [origin[i]-d for i in range(3)]
    x1,y1,z1 = [origin[i]+size[i]+d for i in range(3)]
    if cube.get('mirror'): x0,x1 = x1,x0
    vertices = [(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
                (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
    vertices = [point([v[i]+pivot[i] for i in range(3)]) for v in vertices]
    polygons = [list(reversed(face)) if cube.get('mirror') else list(face) for face in faces]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], polygons)
    mesh.update()
    u,v = cube['uv']
    w,h,depth = size
    u0,u1,u2,u3,u4,u5 = u,u+depth,u+depth+w,u+depth+w+w,u+depth+w+depth,u+depth+w+depth+w
    v0,v1,v2 = v,v+depth,v+depth+h
    rects = [(u1,v0,u2,v1),(u2,v1,u3,v0),(u0,v1,u1,v2),(u1,v1,u2,v2),(u2,v1,u4,v2),(u4,v1,u5,v2)]
    uv = mesh.uv_layers.new(name='Minecraft UV')
    for polygon, (a,b,c,e) in zip(mesh.polygons,rects):
        coords = [(c,b),(a,b),(a,e),(c,e)]
        if cube.get('mirror'): coords.reverse()
        for loop, (tu,tv) in zip(polygon.loop_indices,coords): uv.data[loop].uv = (tu/64,1-tv/64)
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    obj.parent = rig
    obj.data.materials.append(material)
    group = obj.vertex_groups.new(name=owner)
    group.add(list(range(8)),1,'REPLACE')
    modifier = obj.modifiers.new('Steve skeleton','ARMATURE')
    modifier.object = rig
    hidden=[]
    if owner!='head':hidden.append('h > .5')
    if name not in MOTIONS['bones']:hidden.append('v > .5')
    if hidden:
        for prop in ('hide_render','hide_viewport'):
            rig_driver(obj,prop,' or '.join(hidden),{'h':'head_only','v':'void_mode'})

eye_material=bpy.data.materials.new('Void eyes');eye_material.use_nodes=True
eye_material.node_tree.nodes.clear()
emission=eye_material.node_tree.nodes.new('ShaderNodeEmission');emission.inputs['Color'].default_value=(1,1,1,1)
output=eye_material.node_tree.nodes.new('ShaderNodeOutputMaterial')
eye_material.node_tree.links.new(emission.outputs[0],output.inputs['Surface'])
for x in (-3,1):
    mesh=bpy.data.meshes.new('Void eye')
    mesh.from_pydata([point([px,py,-4.04]) for px,py in ((x,-4),(x+2,-4),(x+2,-3),(x,-3))],[],[(3,2,1,0)])
    mesh.update();eye=bpy.data.objects.new('Void eye',mesh);scene.collection.objects.link(eye);eye.parent=rig
    mesh.materials.append(eye_material);eye.vertex_groups.new(name='head').add(list(range(4)),1,'REPLACE')
    eye.modifiers.new('Steve skeleton','ARMATURE').object=rig
    for prop in ('hide_render','hide_viewport'):
        rig_driver(eye,prop,'v < .5 or e < .5',{'v':'void_mode','e':'void_eyes'})

# ItemInHandLayer and ItemTransform: bind the actual generated item to the right hand.
sword_image = bpy.data.images.load(str(ASSETS / 'diamond_sword.png'), check_existing=True)
sword_image.pack()
sword_material = material.copy()
sword_material.name = 'Diamond sword'
next(node for node in sword_material.node_tree.nodes if node.type == 'TEX_IMAGE').image = sword_image
display = json.loads((ASSETS/'handheld.json').read_text())['display']['thirdperson_righthand']
rot = lambda axis,degrees: Matrix.Rotation(math.radians(degrees),4,axis)
item_transform = rot('X',-90) @ rot('Y',180) @ Matrix.Translation(Vector((1,2,-10))+Vector(display['translation']))
item_transform = item_transform @ rot('X',display['rotation'][0]) @ rot('Y',display['rotation'][1]) @ rot('Z',display['rotation'][2])
item_transform = item_transform @ Matrix.Diagonal((*display['scale'],1)) @ Matrix.Translation((-8,-8,-8))
occupied = {(x,y) for y in range(16) for x in range(16) if sword_image.pixels[(y*16+x)*4+3]>.5}
sword_vertices, sword_faces, sword_uv = [], [], []
for x,y in sorted(occupied):
    vertices=[(x,y,7.5),(x+1,y,7.5),(x+1,y+1,7.5),(x,y+1,7.5),
              (x,y,8.5),(x+1,y,8.5),(x+1,y+1,8.5),(x,y+1,8.5)]
    neighbors=[(x,y-1),(x,y+1),(x-1,y),None,(x+1,y),None]
    for face,neighbor in zip(faces,neighbors):
        if neighbor in occupied: continue
        start=len(sword_vertices)
        sword_vertices.extend(point(item_transform @ Vector(vertices[i])+Vector(parts['right_arm']['pivot'])) for i in face)
        sword_faces.append(tuple(range(start,start+4)))
        sword_uv.extend([((x+.5)/16,(y+.5)/16)]*4)
sword_mesh = bpy.data.meshes.new('Diamond sword pixels')
sword_mesh.from_pydata(sword_vertices,[],sword_faces)
sword_mesh.update()
uv = sword_mesh.uv_layers.new(name='Minecraft item UV')
for loop,coordinate in zip(uv.data,sword_uv): loop.uv=coordinate
sword = bpy.data.objects.new('Diamond sword',sword_mesh)
scene.collection.objects.link(sword)
sword.parent=rig
sword.data.materials.append(sword_material)
sword.vertex_groups.new(name='right_arm').add(list(range(len(sword_vertices))),1,'REPLACE')
sword.modifiers.new('Right hand','ARMATURE').object=rig
rig['show_sword']=1.0
for prop in ('hide_render','hide_viewport'):
    driver=sword.driver_add(prop).driver
    variable=driver.variables.new(); variable.name='show'
    variable.targets[0].id=rig; variable.targets[0].data_path='["show_sword"]'
    driver.expression='show < 0.5'

for name, motion in MOTIONS['poses'].items():
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    rig.animation_data_create()
    rig.animation_data.action = action
    frames = max(2, round(motion['duration']*60))
    for frame in range(frames+1):
        t = frame/frames
        values = {key:sample(curve,t) for key,curve in motion['tracks'].items()}
        rig['show_sword']=0.0 if motion['hideHeld'] else 1.0
        rig.keyframe_insert('["show_sword"]',frame=frame+1,group='Equipment')
        rig['void_mode']=float(bool(motion.get('voidEyes') or motion.get('headOnly')))
        rig['head_only']=float(bool(motion.get('headOnly')))
        rig['void_eyes']=float(bool(motion.get('voidEyes')))
        for prop in ('void_mode','head_only','void_eyes'):
            rig.keyframe_insert(f'["{prop}"]',frame=frame+1,group='Appearance')
        for bone_name in MOTIONS['bones']:
            bone = rig.pose.bones[bone_name]
            bone.rotation_mode = 'XYZ'
            bone.rotation_euler = [math.radians(values.get(bone_name+'.r'+axis,0)) for axis in 'xyz']
            bone.keyframe_insert('rotation_euler',frame=frame+1,group=bone_name)
        yaw=values.get('root.yaw',0)*(-1 if motion.get('nativeFacingRight') else 1)+values.get('root.yawSide',0)
        rotation = Quaternion((0,1,0),-math.radians(values.get('root.roll',0))) @ Quaternion((0,0,1),math.radians(yaw)) @ Quaternion((0,0,1),math.pi/2)
        scale_y = values.get('root.sy',1)
        rig.location = Vector((0,0,values.get('root.dy',0)+.9)) - rotation @ Vector((0,0,.9*scale_y))
        rig.rotation_mode = 'QUATERNION'
        rig.rotation_quaternion = rotation
        rig.scale = (1,1,scale_y)
        rig.keyframe_insert('location',frame=frame+1,group='root')
        rig.keyframe_insert('rotation_quaternion',frame=frame+1,group='root')
        rig.keyframe_insert('scale',frame=frame+1,group='root')
    # Curves are sampled from the same smoothstep evaluator; linear interpolation preserves those samples.
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for key in curve.keyframe_points: key.interpolation='LINEAR'

rig.animation_data.action = bpy.data.actions['idle']
scene.frame_set(1)

camera_data = bpy.data.cameras.new('Preview camera')
camera = bpy.data.objects.new('Preview camera', camera_data)
scene.collection.objects.link(camera)
camera.location = (3,-5,2.6)
camera.rotation_euler = (Vector((0,0,.92))-camera.location).to_track_quat('-Z','Y').to_euler()
camera_data.type = 'ORTHO'
camera_data.ortho_scale = 2.5
scene.camera = camera
world = bpy.data.worlds.new('Studio')
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (.16,.2,.28,1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = .5
scene.world = world
for name, location, energy, color in [('Key',(2,-4,4),450,(1,.9,.8)),('Fill',(-3,-1,2),180,(.6,.8,1)),('Rim',(1,3,3),400,(.4,.7,1))]:
    data = bpy.data.lights.new(name,'AREA')
    data.energy, data.color, data.shape, data.size = energy,color,'DISK',3
    light = bpy.data.objects.new(name,data)
    scene.collection.objects.link(light)
    light.location = location
    light.rotation_euler = (Vector((0,0,1))-light.location).to_track_quat('-Z','Y').to_euler()

core = [obj for obj in scene.objects if obj.type=='MESH' and obj.name in MOTIONS['bones']]
heights = [vertex.co.z for obj in core for vertex in obj.data.vertices]
assert len(core)==6 and abs(min(heights))<1e-6 and abs(max(heights)-1.8)<1e-6
assert len(bpy.data.actions)==len(MOTIONS['poses'])
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'steve.blend'))
scene.render.filepath = str(OUT/'steve-preview.png')
bpy.ops.render.render(write_still=True)
if 'radiance_idle' in MOTIONS['poses']:
    for name,label in (('radiance_idle','void'),('radiance_ball','core')):
        rig.animation_data.action=bpy.data.actions[name];scene.frame_set(1)
        scene.render.filepath=str(OUT/f'steve-{label}-preview.png');bpy.ops.render.render(write_still=True)
(OUT/'build-report.json').write_text(json.dumps({'height':1.8,'meshes':len([obj for obj in scene.objects if obj.type=='MESH']),'bones':len(armature.bones),
    'actions':list(MOTIONS['poses']),'nativeClipAliases':len(MOTIONS['aliases']),
    'status':'generated; poses and movie shots still require visual and runtime acceptance'},indent=2),encoding='utf-8')
print('STEVE_RIG_OK',OUT)
