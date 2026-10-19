"""Trace native sprite regions for the Dream Nail actor without editing its atlas."""
import argparse
import json
import math
from collections import deque
from pathlib import Path
from PIL import Image, ImageDraw


def hull(points):
    points = sorted(set(points))
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    halves = []
    for order in (points, points[::-1]):
        part = []
        for p in order:
            while len(part) > 1 and cross(part[-2], part[-1], p) <= 0:
                part.pop()
            part.append(p)
        halves.append(part[:-1])
    return halves[0] + halves[1]


def quad(x0,x1,u0,u1,y0=0,y1=1,a0=1,a1=1):
    return [[x0,y0,a0,u0,y0],[x1,y0,a1,u1,y0],[x1,y1,a1,u1,y1],[x0,y1,a0,u0,y1]]


def body_outline(image):
    # ponytail: reviewed contours for this atlas; regenerate and review if the native artwork changes.
    w, h = image.size
    dark = {(x, y) for y in range(h) for x in range(w)
            if image.getpixel((x, y))[3] > 96 and sum(image.getpixel((x, y))[:3]) < 480}
    components = []
    while dark:
        first = dark.pop(); component = [first]; queue = deque([first])
        while queue:
            x, y = queue.popleft()
            for dx, dy in ((-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)):
                q = x+dx, y+dy
                if q in dark:
                    dark.remove(q); component.append(q); queue.append(q)
        components.append(component)
    assert components, 'No opaque body outline'
    body = max(components, key=len)
    return hull((x+dx, y+dy) for x, y in body for dx, dy in ((-2,-2),(3,-2),(3,3),(-2,3)))


def main(index_path, preview):
    index = json.loads(index_path.read_text(encoding='utf-8-sig'))
    source = index_path.parent
    preview.mkdir(parents=True, exist_ok=True)
    frames = [f for f in index['frames'] if f['libraryName'] == 'Knight Dream Custcene Anim']
    metadata = json.loads(Path(index['source']['metadataPath']).read_text(encoding='utf-8-sig'))
    definitions = {f['spriteName']: f for lib in metadata['libraries'] if lib['libraryName'] == 'Knight Dream Custcene Anim'
                   for clip in lib['clips'] for f in clip['frames']}
    sizes = {f['spriteName']: (f['width'], f['height']) for f in frames}
    def convert(points, old, new):
        a, b = definitions[old]['positions'], definitions[new]['positions']
        ow, oh = sizes[old]; nw, nh = sizes[new]
        return [((a[0]['x']+x/ow*(a[1]['x']-a[0]['x'])-b[0]['x'])/(b[1]['x']-b[0]['x'])*nw,
                 (b[2]['y']-(a[2]['y']-y/oh*(a[2]['y']-a[0]['y'])))/(b[2]['y']-b[0]['y'])*nh) for x,y in points]
    outlines = {f['spriteName']: body_outline(Image.open(source/f['outputPath']).convert('RGBA'))
                for f in frames if f['spriteName'].startswith('collect_dream_nail001') and int(f['spriteName'][-2:]) >= 12}
    # The hilt touches the original hand; its outline cannot be separated by connected components.
    nails = {'collect_dream_nail0004': [(3,92),(4,88),(12,78),(17,76),(20,79),(19,84),(11,95),(6,97)]}
    nails['collect_dream_nail0005'] = [(0,53),(3,47),(9,44),(16,46),(22,51),(22,58),(17,65),(9,66),(2,61)]
    for n in range(6,10):
        nails[f'collect_dream_nail{n:04d}'] = [(0,39),(3,33),(10,30),(17,32),(23,37),(24,45),(18,52),(10,53),(3,48)]
    sprites, cards = {}, []
    for frame in frames:
        name = frame['spriteName']
        if name in sprites: continue
        image = Image.open(source / frame['outputPath']).convert('RGBA')
        w, h = image.size
        if frame['clipName'] == 'DN Item' or name in ('dream_teleport0000', 'dream_teleport0001'):
            cut = []
        elif name == 'dream_teleport0002':
            cut = [(160,128),(216,91),(273,130),(275,230),(199,247),(159,200)]
        elif name == 'dream_teleport0003':
            cut = [(180,65),(250,60),(285,108),(278,210),(204,210),(175,135)]
        elif name in ('collect_dream_nail0010','collect_dream_nail0011'):
            cut = hull(p for ref, points in outlines.items() for p in convert(points,ref,name))
        else:
            cut = body_outline(image)
        has_effects = name.startswith('collect_dream_nail001')
        keep=[];clean_left=body_right=clean_top=None
        if has_effects:
            # The left side of the weapon is free of the Knight. Reflect that clean light
            # across the hilt, avoiding a moving silhouette-shaped hole in the glow.
            clean_left=min(min(x for x,y in cut),convert([(12,41)],'collect_dream_nail0006',name)[0][0])/w
            body_right=max(x for x,y in cut)/w
            edge=min(1,2*clean_left)
            band=convert([(12,41)],'collect_dream_nail0006',name)[0][1]/h
            top_x=[x for x,y in cut if y<=band*h]
            for a,b in zip(cut,cut[1:]+cut[:1]):
                if (a[1]<band*h)!=(b[1]<band*h):
                    top_x.append(a[0]+(b[0]-a[0])*(band*h-a[1])/(b[1]-a[1]))
            top=min(top_x)/w if top_x else 1
            clean_top=[top,band]
            # Keep the full blade above the hilt; its bright centre moves between frames.
            keep=[quad(0,clean_left,0,clean_left)]
            start=body_right if edge>body_right else max(clean_left,edge-8/w)
            end=min(edge,body_right+12/w) if edge>body_right else edge
            if start>clean_left: keep.append(quad(clean_left,start,clean_left,2*clean_left-start))
            if end>start: keep.append(quad(start,end,2*clean_left-start,2*clean_left-end,a1=0))
            if body_right<1:
                native_end=end if edge>body_right else min(1,body_right+8/w)
                if native_end>body_right: keep.append(quad(body_right,native_end,body_right,native_end,a0=0))
                if native_end<1: keep.append(quad(native_end,1,native_end,1))
            # Feather the extra native blade strip over the reflected light, without a hard cut edge.
            x1=min(clean_left+2/w,(clean_left+top)/2);x2=max(x1,top-6/w)
            xkeys=[(clean_left,0),(x1,1),(x2,1),(top,0)]
            ykeys=[(0,1),(max(0,band-6/h),1),(band,0)]
            for (xa,aa),(xb,ab) in zip(xkeys,xkeys[1:]):
                for (ya,ba),(yb,bb) in zip(ykeys,ykeys[1:]):
                    if xb<=xa or yb<=ya: continue
                    patch=quad(xa,xb,xa,xb,ya,yb)
                    for p,a in zip(patch,(aa*ba,ab*ba,ab*bb,aa*bb)):p[2]=a
                    keep.append(patch)
        nail = nails.get(name, [])
        if nail: keep.append([[x/w,y/h,1,x/w,y/h] for x,y in nail])
        hand = None
        if name in nails:
            hand = (10,94) if name.endswith('0004') else (16,64) if name.endswith('0005') else (18,51)
        elif name.startswith('collect_dream_nail') and int(name[-2:]) >= 10:
            hand = convert([(12,41)],'collect_dream_nail0006',name)[0]
        sprites[name] = {'replace': bool(cut), 'keep': keep, 'hand': [hand[0]/w,hand[1]/h] if hand else None,
                         'floor': max(y/h for x,y in cut) if cut and name.startswith('dream_teleport') else None,
                         'cleanLeft':clean_left,'bodyRight':body_right,'cleanTop':clean_top,
                         'bodyOutline': [[round(x/w,8),round(y/h,8)] for x,y in cut],
                         'sourceSize': [w,h]}
        card = Image.new('RGB', (360,310), (110,110,110))
        scale = min(330/w, 245/h)
        shown = image.resize((round(w*scale),round(h*scale)))
        ox, oy = (360-shown.width)//2, 30
        card.paste(shown,(ox,oy),shown)
        draw = ImageDraw.Draw(card)
        draw.text((8,6), name, fill='white')
        draw.text((8,285), frame['clipName'] + (' / replace body' if cut else ' / preserve'), fill='white')
        if cut: draw.line([(ox+x*scale,oy+y*scale) for x,y in cut+cut[:1]], fill=(255,60,40), width=2)
        if nail: draw.line([(ox+x*scale,oy+y*scale) for x,y in nail+nail[:1]], fill=(40,255,80), width=2)
        cards.append(card)
    for start in range(0,len(cards),12):
        page = Image.new('RGB',(1440,930),(75,75,75))
        for i,card in enumerate(cards[start:start+12]): page.paste(card,((i%4)*360,(i//4)*310))
        page.save(preview/f'body-regions-{start//12+1}.png')
    out = Path(__file__).resolve().parents[1]/'assets/steve/dream-geometry.json'
    out.write_text(json.dumps({'schema':1,'sprites':sprites},indent=2)+'\n',encoding='utf-8')
    for sprite in sprites.values():
        for polygon in sprite['keep']:
            assert all(len(p)==5 and all(math.isfinite(v) and -1e-7<=v<=1+1e-7 for v in p) for p in polygon)
            if sprite['cleanLeft'] is not None:
                assert (max(p[3] for p in polygon)<=sprite['cleanLeft']+1e-7
                        or min(p[3] for p in polygon)>=sprite['bodyRight']-1e-7
                        or (max(p[3] for p in polygon)<=sprite['cleanTop'][0]+1e-7 and max(p[4] for p in polygon)<=sprite['cleanTop'][1]+1e-7))
    print(json.dumps({'sprites':len(sprites),'replaced':sum(s['replace'] for s in sprites.values()),'preview':str(preview)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('index',type=Path); parser.add_argument('preview',type=Path)
    args = parser.parse_args(); main(args.index,args.preview)
