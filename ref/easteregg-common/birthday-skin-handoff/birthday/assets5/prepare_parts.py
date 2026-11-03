"""Crop/mask generated raster pixels only; no illustration is redrawn here."""
from PIL import Image, ImageDraw, ImageFilter
from pathlib import Path
import json, shutil
import numpy as np

assets = Path(__file__).resolve().parent
rigs = json.loads((assets / 'rigs.json').read_text())
miyako_round6 = rigs.get('miyako') if rigs.get('miyako', {}).get('revision') == 6 else None

def copy(name, source, dest):
    shutil.copy2(assets / f'{name}_{source}.png', assets / f'{name}_{dest}.png')

def heads(name):
    a = Image.open(assets / f'{name}_head_open_full.png').convert('RGBA')
    for state in ['open', 'closed']:
        im = Image.open(assets / f'{name}_head_{state}_full.png').convert('RGBA').resize(a.size, Image.Resampling.LANCZOS)
        im.save(assets / f'{name}_head_{state}.png')
    return a

def split_head_ears(name, left, right):
    a = heads(name)
    masks = []
    for key, points in [('ear_l', left), ('ear_r', right)]:
        mask = Image.new('L', a.size)
        ImageDraw.Draw(mask).polygon(points, fill=255)
        masks.append(mask)
        out = np.array(a)
        out[:, :, 3] = np.minimum(out[:, :, 3], np.array(mask.filter(ImageFilter.MaxFilter(3))))
        Image.fromarray(out).save(assets / f'{name}_{key}.png')
    # Five-pixel painted overlap covers seams during small joint rotations.
    keep = Image.fromarray(np.uint8(255 - np.maximum(np.array(masks[0]), np.array(masks[1])))).filter(ImageFilter.MaxFilter(11))
    for state in ['open', 'closed']:
        out = np.array(Image.open(assets / f'{name}_head_{state}.png'))
        out[:, :, 3] = np.minimum(out[:, :, 3], np.array(keep))
        Image.fromarray(out).save(assets / f'{name}_head_{state}.png')

split_head_ears('arale', [(0,0),(145,0),(145,86),(112,102),(83,124),(57,146),(28,171),(0,180)], [(195,0),(341,0),(341,180),(309,155),(276,130),(249,113),(224,99),(195,86)])
split_head_ears('yuno', [(0,0),(110,0),(110,68),(84,91),(65,120),(40,157),(0,175)], [(277,0),(380,0),(380,175),(346,150),(322,118),(300,90),(277,68)])
if not miyako_round6:
    split_head_ears('miyako', [(0,140),(48,145),(64,165),(58,199),(68,234),(104,270),(68,311),(0,311)], [(374,140),(326,145),(310,165),(316,199),(306,234),(270,270),(306,311),(374,311)])
else:
    heads('miyako')
    copy('miyako', 'ear_spare_l', 'ear_l'); copy('miyako', 'ear_spare_r', 'ear_r')
for name in ['ritsu', 'nonoka', 'maru', 'duck']:
    heads(name)
for name in ['ritsu', 'nonoka', 'maru']:
    copy(name, 'ear_spare_l', 'ear_l')
    copy(name, 'ear_spare_r', 'ear_r')
# Remove tails that the generator also attached to a torso, retaining the separate tail artwork.
for name, width in [('ritsu', 275), ('miyako', 290), ('nonoka', 270)]:
    if name == 'miyako' and miyako_round6: continue
    p = assets / f'{name}_body.png'
    im = Image.open(p)
    im.crop((0, 0, width, im.height)).save(p)
# A duck has wings instead of ears; its feet were generated in the third row.
copy('duck', 'arm_l', 'foot_l'); copy('duck', 'arm_r', 'foot_r')
copy('duck', 'ear_spare_l', 'arm_l'); copy('duck', 'ear_spare_r', 'arm_r')
copy('yuno', 'prop', 'headset')

rigs['arale']['baseline'] = 225
rigs.update({
 'yuno': {'head':[32,10,175,156], 'earsFront':True, 'headExtras':[['headset',142,97,42,40]], 'layers':[['tail',157,159,82,70],['body',59,154,126,80],['arm_l',55,178,48,48],['arm_r',155,178,47,49]], 'baseline':229},
 'ritsu': {'head':[32,35,175,140], 'ears':[[8,-8,45,42],[121,-8,45,42]], 'earOrigins':['50% 95%','50% 95%'], 'layers':[['tail',161,191,36,35],['body',64,165,112,78],['prop',67,156,91,84],['arm_l',81,186,37,32],['arm_r',125,151,40,35]], 'baseline':238},
 'miyako': {'head':[27,26,184,153], 'earsFront':True, 'earOrigins':['16% 52%','84% 52%'], 'layers':[['tail',164,163,62,66],['body',62,158,118,80],['prop',53,188,138,43],['arm_l',57,176,35,37],['arm_r',149,176,35,37]], 'baseline':233},
 'nonoka': {'head':[33,62,176,130], 'ears':[[9,-63,55,88],[113,-63,55,88]], 'earOrigins':['50% 95%','50% 95%'], 'layers':[['tail',165,211,34,33],['body',64,181,112,74],['prop',66,170,98,83],['arm_l',80,200,36,38],['arm_r',132,167,39,41]], 'baseline':250},
 'maru': {'head':[31,10,178,160], 'ears':[[-15,44,60,111],[138,38,63,117]], 'earOrigins':['50% 10%','50% 10%'], 'earsFront':True, 'layers':[['tail',159,170,61,60],['body',63,161,116,87],['arm_l',42,179,48,47],['arm_r',150,179,48,47]], 'baseline':243},
 'duck': {'head':[35,31,171,163], 'ears':[], 'layers':[['tail',166,174,45,45],['body',66,153,109,76],['foot_l',76,217,31,23],['foot_r',128,217,31,25],['arm_l',64,172,40,46],['arm_r',143,172,40,46]], 'baseline':237},
})
if miyako_round6: rigs['miyako'] = miyako_round6
(assets / 'rigs.json').write_text(json.dumps(rigs, indent=2))

def resized(name,key,w,h):
    return Image.open(assets / f'{name}_{key}.png').convert('RGBA').resize((w,h),Image.Resampling.LANCZOS)

for name,rig in rigs.items():
    canvas=Image.new('RGBA',(240,280))
    behind=[p for p in rig['layers'] if p[0] in ['tail','body','foot_l','foot_r']]
    front=[p for p in rig['layers'] if p not in behind]
    for key,x,y,w,h in behind: canvas.alpha_composite(resized(name,key,w,h),(x,y))
    x,y,w,h=rig['head']; head=Image.new('RGBA',(300,300))
    ears=rig.get('ears',[[0,0,w,h],[0,0,w,h]])
    def ear_layer():
        for key,box in zip(['ear_l','ear_r'],ears):
            ex,ey,ew,eh=box
            head.alpha_composite(resized(name,key,ew,eh),(ex+50,ey+90))
    if not rig.get('earsFront',True if name=='arale' else False): ear_layer()
    head.alpha_composite(resized(name,'head_open',w,h),(50,90))
    if rig.get('earsFront',True if name=='arale' else False): ear_layer()
    for key,ex,ey,ew,eh in rig.get('headExtras',[]):head.alpha_composite(resized(name,key,ew,eh),(ex+50,ey+90))
    canvas.alpha_composite(head,(x-50,y-90))
    for key,x,y,w,h in front: canvas.alpha_composite(resized(name,key,w,h),(x,y))
    canvas.save(assets / f'{name}_assembled_preview.png')
print('Prepared seven cutout puppets, assemblies and rig metadata')
