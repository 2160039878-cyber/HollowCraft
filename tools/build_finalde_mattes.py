"""Build connected foreground mattes using installed NumPy/Pillow; source frames are read-only."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
W, H = 1920, 1080


def thick_core(mask, radius=15):
    width = radius * 2 + 1
    integral = np.pad(mask.astype(np.int32), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    sums = integral[width:, width:] - integral[:-width, width:] - integral[width:, :-width] + integral[:-width, :-width]
    result = np.zeros_like(mask)
    result[radius:-radius, radius:-radius] = sums == width * width
    return result


def connected_to_seed(mask, seed):
    """Eight-connected scanline runs, with no maximum distance from a limb core."""
    parents, seeded, runs, previous = [], [], [], []

    def find(label):
        while parents[label] != label:
            parents[label] = parents[parents[label]]
            label = parents[label]
        return label

    for y, row in enumerate(mask):
        edges = np.flatnonzero(np.diff(np.pad(row.astype(np.int8), (1, 1))))
        current, cursor = [], 0
        for left, right in edges.reshape(-1, 2):
            left, right = int(left), int(right)
            label = len(parents)
            parents.append(label)
            seeded.append(bool(seed[y, left:right].any()))
            while cursor < len(previous) and previous[cursor][1] < left:
                cursor += 1
            index = cursor
            while index < len(previous) and previous[index][0] <= right:
                a, b = find(label), find(previous[index][2])
                if a != b:
                    parents[b] = a
                    seeded[a] |= seeded[b]
                index += 1
            current.append((left, right, label))
            runs.append((y, left, right, label))
        previous = current
    result = np.zeros_like(mask)
    for y, left, right, label in runs:
        if seeded[find(label)]:
            result[y, left:right] = True
    return result


def self_check():
    mask = np.zeros((100, 2000), dtype=bool)
    mask[15:65, 10:60] = True
    mask[40, 60:1900] = True
    mask[80:82, 1800:1802] = True
    result = connected_to_seed(mask, thick_core(mask))
    assert result[40, 1899] and result.sum() == 50 * 50 + 1840
    assert not result[80, 1800]
    diagonal = np.eye(4, dtype=bool)
    seed = np.zeros_like(diagonal)
    seed[0, 0] = True
    assert np.array_equal(connected_to_seed(diagonal, seed), diagonal)
    assert not connected_to_seed(mask, np.zeros_like(mask)).any()


def luminance(image):
    rgb = np.asarray(image.convert('RGB'), dtype=np.float32) / 255
    linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    return linear @ np.array([.2126, .7152, .0722], dtype=np.float32)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--variant', choices=['FinalD', 'FinalE'], required=True)
    parser.add_argument('--frames')
    args = parser.parse_args()
    self_check()
    args.source, args.out = args.source.resolve(), args.out.resolve()
    assert args.source != args.out and not args.out.is_relative_to(args.source)
    assert not args.out.exists(), 'Use a new output directory for changed matte logic'
    args.out.mkdir(parents=True)
    count = 1508 if args.variant == 'FinalD' else 1957
    assets = ROOT / 'assets/cinematics/FinalD'
    features = {r['frame']: r for r in json.loads((assets / 'measured-frames.json').read_text())['frames']}
    motion = {r['frame']: r for r in json.loads((assets / 'plate-motion.json').read_text())['frames']}
    active = list(range(3, 216)) + list(range(398, 414)) + list(range(418, 599))
    selected = sorted(set(int(f) for f in args.frames.split(','))) if args.frames else active
    assert selected and set(selected) <= set(active)
    with Image.open(args.source / '00397.png') as im:
        entry_plate = im.convert('RGB')
    with Image.open(args.source / '00418.png') as im:
        side_plate = im.convert('RGB')
    with Image.open(assets / 'plate-godseeker-close.png') as im:
        close_plate = im.convert('RGB').resize((W, H), Image.Resampling.BILINEAR)
    with Image.open(assets / 'plate-cloud-chasm.png') as im:
        cloud_plate = im.convert('RGB').resize((W, H), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(7))
    blank = Image.new('L', (W, H))
    blank_path = args.out / '00001.png'
    blank.save(blank_path)
    blank_bytes = blank_path.read_bytes()
    for frame in range(2, count + 1):
        (args.out / f'{frame:05}.png').write_bytes(blank_bytes)
    records, black = [], []
    for frame in selected:
        cloud, entry, close = frame <= 215, 398 <= frame <= 413, frame >= 499
        reference = cloud_plate if cloud else entry_plate if entry else close_plate if close else side_plate
        shift = motion.get(frame, {'dx': 0, 'dy': 0})
        translated = Image.new('RGB', (W, H))
        translated.paste(reference, (shift['dx'], shift['dy']))
        plate = luminance(translated)
        with Image.open(args.source / f'{frame:05}.png') as im:
            assert im.size == (W, H)
            source = luminance(im)
        if source.max() == 0:
            black.append(frame)
        highlight = features.get(frame, {}).get('highlightExposure', 1)
        dark = source / np.maximum(plate, .001) < (.6 if cloud else .035) * highlight
        valid = plate > .003
        left = 430 + shift['dx'] if cloud else 1350 if entry and frame <= 399 else 1100 if entry and frame <= 401 else 0 if entry or close else 450
        right = 1300 + shift['dx'] if cloud else W
        dark[:, :left] = False
        dark[:, right:] = False
        matte = connected_to_seed(dark, thick_core(dark & valid)) & valid
        eye = features.get(frame, {}).get('whiteEyeBounds')
        if eye:
            matte[max(0, eye[1] - 80):min(H, eye[3] + 80), max(0, eye[0] - 80):min(W, eye[2] + 80)] = True
        Image.fromarray(matte.astype(np.uint8) * 255).save(args.out / f'{frame:05}.png')
        records.append({'frame': frame, 'pixels': int(matte.sum())})
    manifest = {'variant': args.variant, 'source': str(args.source), 'count': count,
                'availableFrames': selected, 'blackFrames': black, 'frames': records,
                'method': 'Eight-connected components selected by a 31px solid core; no finite propagation limit. Rec709 linear luminance, tracked repair plate, original eye bounds.',
                'scriptSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'selfCheckPassed': True}
    (args.out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('FINAL_DE_MATTES_COMPLETE', args.variant, len(selected), args.out)


if __name__ == '__main__':
    main()
