"""Blender: reconstruct only the glow occluded by the native player hand."""
import argparse
import sys
from pathlib import Path
import bpy

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--plates', type=Path, required=True)
parser.add_argument('--mattes', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
source, out = args.source.resolve(), args.out.resolve()
assert source != out and not out.is_relative_to(source)
out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT'
scene.render.film_transparent = True
scene.view_settings.view_transform = 'Standard'
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.resolution_percentage = 100
bpy.ops.object.camera_add()
scene.camera = bpy.context.object
scene.use_nodes = True
tree = scene.node_tree

def node(kind, name):
    n = tree.nodes.new(kind); n.label = name
    return n

def link(a, output, b, input):
    tree.links.new(a.outputs[output], b.inputs[input])

def image(file, name):
    n = node('CompositorNodeImage', name)
    n.image = bpy.data.images.load(str(file), check_existing=True)
    return n

def fill(input_node, socket, known, name):
    cut = node('CompositorNodeSetAlpha', name + ' missing region')
    cut.mode = 'REPLACE_ALPHA'
    link(input_node, socket, cut, 'Image'); link(known, 0, cut, 'Alpha')
    value = node('CompositorNodeInpaint', name + ' native reconstruction')
    value.inputs['Size'].default_value = 1024
    link(cut, 0, value, 'Image')
    return value

for index in range(6, 11):
    tree.nodes.clear()
    original = image(source / f'Radiance_GG_face_open{index:04}.png', 'Original eye and flash')
    w, h = original.image.size
    scene.render.resolution_x, scene.render.resolution_y = w, h
    matte = image(args.mattes / f'matte-{index}.png', 'Old claw and baked dark edges')
    matte.image.colorspace_settings.name = 'Non-Color'
    dilate = node('CompositorNodeDilateErode', 'Remove native antialiasing')
    dilate.mode = 'DISTANCE'; dilate.distance = 4
    link(matte, 0, dilate, 0)
    known = node('CompositorNodeMath', 'Unoccluded source')
    known.operation = 'SUBTRACT'; known.inputs[0].default_value = 1
    link(dilate, 0, known, 1)
    rgb = fill(original, 'Image', known, 'Premultiplied colour')
    alpha = fill(original, 'Alpha', known, 'Alpha')
    if index <= 8:
        plate = image(args.plates / f'cleanplate-{index}.png', 'Imagegen occluded glow prior')
        resize = node('CompositorNodeScale', 'Native sprite dimensions')
        resize.space = 'ABSOLUTE'
        resize.inputs['X'].default_value, resize.inputs['Y'].default_value = w, h
        link(plate, 0, resize, 'Image')
        straight = node('CompositorNodePremulKey', 'Recover clean-plate colour')
        straight.mapping = 'PREMUL_TO_STRAIGHT'; link(resize, 0, straight, 'Image')
        premul = node('CompositorNodeMixRGB', 'Match reconstructed native opacity')
        premul.blend_type = 'MULTIPLY'; premul.inputs[0].default_value = 1
        link(straight, 0, premul, 1); link(alpha, 0, premul, 2)
        weight = node('CompositorNodeMath', 'Clean-plate contribution only inside old hand')
        weight.operation = 'MULTIPLY'; weight.inputs[1].default_value = .2
        link(dilate, 0, weight, 0)
        mix = node('CompositorNodeMixRGB', 'Native boundary reconstruction with clean-plate detail')
        link(weight, 0, mix, 0); link(rgb, 0, mix, 1); link(premul, 0, mix, 2)
        rgb = mix
    rgba = node('CompositorNodeSetAlpha', 'Restore independent native transparency')
    rgba.mode = 'REPLACE_ALPHA'; link(rgb, 0, rgba, 'Image'); link(alpha, 0, rgba, 'Alpha')
    output = node('CompositorNodeComposite', 'Handless effect texture')
    link(rgba, 0, output, 'Image')
    scene.render.filepath = str(out / f'void-hand-{index:02}.png')
    bpy.ops.render.render(write_still=True)
print('HAND_EFFECTS_COMPOSITED', out)
