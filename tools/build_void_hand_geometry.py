"""Calibrate the canonical arm and prepare native-effect reconstruction mattes."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image


def build(source, output, mattes):
    sprites = {}
    mattes.mkdir(parents=True, exist_ok=True)
    for index in range(11):
        name = f"Radiance_GG_face_open{index:04}"
        file = source / f"{name}.png"
        image = Image.open(file).convert("RGBA")
        width, height = image.size
        pixels = list(image.getdata())
        # ponytail: these mattes target the fixed native atlas; re-author on an HK asset update.
        if index >= 6:
            matte = Image.new('L', image.size)
            matte.putdata([255 if a > 0 and max(r, g, b) < 200 else 0 for r, g, b, a in pixels])
            matte.save(mattes / f'matte-{index}.png')
        else:
            assert all(a == 0 or max(r, g, b) <= 4 for r, g, b, a in pixels), "Grab contains a non-player effect"
        dark = [(i % width + .5, i // width + .5, a) for i, (r, g, b, a) in enumerate(pixels)
                if a > 128 and max(r, g, b) <= 4]
        lo, hi = min(p[0] for p in dark), max(p[0] for p in dark)
        def anchor(points):
            weight = sum(p[2] for p in points)
            return [sum(p[0] * p[2] for p in points) / weight / width,
                    sum(p[1] * p[2] for p in points) / weight / height]
        sprites[name] = dict(width=width, height=height,
            armStart=anchor([p for p in dark if p[0] <= lo + (hi - lo) * .1]),
            armEnd=anchor([p for p in dark if p[0] >= lo + (hi - lo) * .5]),
            sourceSha256=hashlib.sha256(file.read_bytes()).hexdigest())
        assert all(0 <= coordinate <= 1 for key in ('armStart', 'armEnd') for coordinate in sprites[name][key])
        assert sprites[name]['armStart'] != sprites[name]['armEnd'], "Degenerate arm"
        if index >= 6:
            sprites[name]['effect'] = f'void-hand-{index:02}.png'
        # During the crush, the end of the block fist must contact the eye rather
        # than the original palm above it; these points follow the observed eye rim.
        contact = {6: [.48, .56], 7: [.49, .50], 8: [.50, .51]}
        if index in contact:
            sprites[name]['armEnd'] = contact[index]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(source="HK 1.5.12620 / Shade Lord Anim",
        policy="Native arm anchors and canonical Steve forearm; native visible eye/flash retained, occluded glow reconstructed with Blender and three imagegen clean-plate priors.",
        sprites=sprites), separators=(",", ":")), encoding="utf-8")
    print(json.dumps(dict(sprites=len(sprites), effectMattes=5, output=str(output))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("mattes", type=Path)
    args = parser.parse_args()
    build(args.source, args.output, args.mattes)
