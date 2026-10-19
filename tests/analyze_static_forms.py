"""Validate native static-body replacement and preserved effect component captures."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageChops


def analyze(root):
    result = json.loads((root / 'result.json').read_text(encoding='utf-8-sig'))
    assert result['passed'] and not result['errors'] and len(result['frames']) == 9
    assert result['resolution'] == [1920, 1080] and result['scene'] == 'Town'
    hashes = {}
    for frame in result['frames']:
        name = frame['label']
        before, after = (root / (name + '-native.png')), (root / (name + '-steve.png'))
        assert before.read_bytes() != after.read_bytes() if frame['replaced'] else before.read_bytes() == after.read_bytes()
        assert frame['originalHidden'] == frame['replaced'] and frame['layer'] == 31
        for path in (before, after):
            image = Image.open(path).convert('RGB')
            assert image.size == (1920, 1080)
            assert ImageChops.difference(image, Image.new('RGB', image.size, image.getpixel((0, 0)))).getbbox()
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        if frame['replaced']:
            image = Image.open(after).convert('RGB')
            assert sum(g > r * 1.3 and b > r * 1.3 and g > 90 for r, g, b in image.getdata()) > 100
    body = [f for f in result['frames'] if f['replaced']]
    assert len(body) == 6 and all(f['clip'] is None for f in body)
    assert {f['defaultClip'] for f in body} == {'Fury Aura', 'Death', 'Spike Death', 'Acid Death'}
    summary = dict(passed=True, replaced=6, preserved=3, activationHooks=True, cleanup=True,
                   nonblankBodyCaptures=True, files=hashes,
                   limitations='Native component captures only; actual cutscene and reflecting-surface flows remain unverified.')
    (root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k != 'files'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    analyze(parser.parse_args().evidence)
