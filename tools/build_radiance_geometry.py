"""Measure the native protagonist's anchors; no native atlas pixels are modified."""
import argparse
import json
import math
import statistics
from pathlib import Path
from PIL import Image, ImageDraw


def centre(points):
    return [sum(p[i] for p in points)/len(points) for i in (0,1)]


def beam(points,w,h):
    outside=[p for p in points if p[1]<h*.22 or p[1]>h*.78]
    assert len(outside)>5,'Missing native split streak'
    cx,cy=centre(outside)
    xx=sum((x-cx)**2 for x,y in outside); yy=sum((y-cy)**2 for x,y in outside)
    xy=sum((x-cx)*(y-cy) for x,y in outside)
    angle=.5*math.atan2(2*xy,xx-yy);dx,dy=math.cos(angle),math.sin(angle)
    projections=sorted((x-cx)*dx+(y-cy)*dy for x,y in outside)
    ends=[projections[len(projections)//100],projections[-1-len(projections)//100]]
    return [[(cx+t*dx)/w,(cy+t*dy)/h] for t in ends]


def main(index_path,preview):
    index=json.loads(index_path.read_text(encoding='utf-8-sig'));source=index_path.parent.resolve()
    metadata=json.loads(Path(index['source']['metadataPath']).read_text(encoding='utf-8-sig'))
    library=next(l for l in metadata['libraries'] if l['libraryName']=='Radiance Anim')
    definitions={f['spriteId']:f for c in library['clips'] for f in c['frames']}
    clips={c['name']:{'fps':c['fps'],'frames':[f['spriteId'] for f in c['frames']]} for c in library['clips']}
    assert len(clips)==12 and sum(len(c['frames']) for c in clips.values())==64
    samples={f['spriteId']:f for f in index['frames'] if f['libraryName']=='Radiance Anim'}
    images={}
    for key,f in samples.items():
        path=(source/f['outputPath']).resolve();assert source in path.parents and path.suffix=='.png'
        images[key]=Image.open(path).convert('RGBA')
    def local(key,p):
        q=definitions[key]['positions'];w,h=images[key].size
        return [q[0]['x']+p[0]/w*(q[1]['x']-q[0]['x']),q[2]['y']-p[1]/h*(q[2]['y']-q[0]['y'])]
    def pixel(key,p):
        q=definitions[key]['positions'];w,h=images[key].size
        return [(p[0]-q[0]['x'])/(q[1]['x']-q[0]['x'])*w,(q[2]['y']-p[1])/(q[2]['y']-q[0]['y'])*h]
    bright={};opaque={}
    for key,image in images.items():
        w,h=image.size
        opaque[key]=[(x,y) for y in range(h) for x in range(w) if image.getpixel((x,y))[3]>160]
        bright[key]=[(x,y) for x,y in opaque[key] if min(image.getpixel((x,y))[:3])>230]
    spans=[]
    for key in clips['Knight Idle']['frames']:
        xs=[p[0] for p in bright[key]];q=definitions[key]['positions'];w,h=images[key].size
        spans.append((max(xs)-min(xs)+1)/w*(q[1]['x']-q[0]['x']))
    scale=statistics.median(spans)/((6*1.8/32)*math.cos(math.radians(20))*math.cos(math.radians(25)))
    void_anchor=local(163,centre(bright[163]))
    # The shell's eyes merge into its painted shadow. These three anchors were checked on a pixel grid.
    skin_reference=[34,56]
    skin_anchor=local(283,skin_reference)
    streak_ids={279,274,281,277,269,276}
    streak_style={279:[.14,.95,0],274:[.12,.65,1],281:[.10,.4,1],
                  277:[.07,.10,.25],269:[.09,.4,.3],276:[.16,.3,0]}
    sprites={};cards=[];preview.mkdir(parents=True,exist_ok=True)
    for key,image in images.items():
        name=definitions[key]['spriteName'];w,h=image.size;points=opaque[key];assert points
        kind='skin' if name.startswith('hollow_knight_break') else 'void'
        if name.startswith('player_knight_appear') and int(name[-3:])<=6:kind='ball'
        eyes=kind=='void' and bool(bright[key])
        if kind=='ball':anchor=centre(points)
        elif kind=='void':anchor=centre(bright[key]) if eyes else pixel(key,void_anchor)
        else:anchor={273:[50,62],284:[48.5,51.5]}.get(key)
        if anchor is None:anchor=pixel(key,skin_anchor)
        hand=None
        if name.startswith('player_knight_slashes'):
            right=max(x for x,y in points);tip=centre([p for p in points if p[0]>=right-3])
            if local(key,tip)[0]-local(key,anchor)[0]>.8:hand=[tip[0]/w,tip[1]/h]
        streak=[(x,y) for y in range(h) for x in range(w) if image.getpixel((x,y))[3]>12] if key in streak_ids else []
        line=beam(streak,w,h) if streak else None
        q=definitions[key]['positions']
        ball_scale=(max(y for x,y in points)-min(y for x,y in points)+1)/h*(q[2]['y']-q[0]['y'])/(8*1.8/32)
        sprites[str(key)]={'name':name,'kind':kind,'anchor':[anchor[0]/w,anchor[1]/h],
                           'scale':ball_scale if kind=='ball' else scale if kind=='void' else 1/1.404878,
                           'eyes':eyes,'hand':hand,'beam':line,'beamStyle':streak_style.get(key)}
        card=Image.new('RGB',(320,310),(110,110,110));s=min(290/w,250/h)
        shown=image.resize((round(w*s),round(h*s)));ox,oy=(320-shown.width)//2,30
        card.paste(shown,(ox,oy),shown);d=ImageDraw.Draw(card)
        d.text((8,5),f'{key}: {name}',fill='white');d.text((8,287),kind,fill='white')
        ax,ay=ox+anchor[0]*s,oy+anchor[1]*s;d.ellipse((ax-4,ay-4,ax+4,ay+4),outline='yellow',width=2)
        if hand:d.line([(ax,ay),(ox+hand[0]*w*s,oy+hand[1]*h*s)],fill=(70,255,70),width=2)
        if line:d.line([(ox+x*w*s,oy+y*h*s) for x,y in line],fill=(255,70,70),width=2)
        cards.append(card)
    for start in range(0,len(cards),12):
        page=Image.new('RGB',(1280,930),(70,70,70))
        for n,card in enumerate(cards[start:start+12]):page.paste(card,((n%4)*320,(n//4)*310))
        page.save(preview/f'anchors-{start//12+1}.png')
    data={'schema':1,'collection':'Radiance Cln','clips':clips,'sprites':sprites,'voidScale':scale}
    out=Path(__file__).resolve().parents[1]/'assets/steve/radiance-geometry.json'
    out.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    assert len(sprites)==53 and all(math.isfinite(v) for s in sprites.values() for v in [s['scale'],*s['anchor']])
    assert 0<scale<4 and len(streak_ids)==6
    print(json.dumps({'sprites':len(sprites),'frames':64,'voidScale':scale,'skinAnchorLocal':skin_anchor,'preview':str(preview)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('index',type=Path);parser.add_argument('preview',type=Path)
    args=parser.parse_args();main(args.index,args.preview)
