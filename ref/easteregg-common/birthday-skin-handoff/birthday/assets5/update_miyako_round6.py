"""Prepare only the newly generated light-lavender Miyako; preserve other rigs."""
from pathlib import Path
from PIL import Image, ImageFilter
from scipy import ndimage
import numpy as np
import json, shutil

a=Path(__file__).resolve().parent
im=Image.open(a/'miyako_atlas.png').convert('RGBA'); rgba=np.array(im)
labels,n=ndimage.label(rgba[:,:,3]>48); blobs=[]
for idx,sl in enumerate(ndimage.find_objects(labels),1):
    if sl is None or (labels[sl]==idx).sum()<1000: continue
    box=(int(sl[1].start),int(sl[0].start),int(sl[1].stop),int(sl[0].stop))
    # Generated atlas rows are approximate: a tall first-row torso can cross H/3.
    cy=(box[1]+box[3])/2
    row=int(np.argmin(np.abs(np.array([.28,.58,.85])*im.height-cy)))
    blobs.append((row,int((box[0]+box[2])/2/(im.width/3)),idx,box))
blobs.sort(); assert len(blobs)==9, len(blobs)
assert [(b[0],b[1]) for b in blobs]==[(r,c) for r in range(3) for c in range(3)]
keys=['head_open_full','head_closed_full','body','ear_spare_l','ear_spare_r','tail','arm_l','arm_r','prop']
extraction={}
for key,(_,_,idx,box) in zip(keys,blobs):
    mask=Image.fromarray(np.uint8(labels==idx)*255).filter(ImageFilter.MaxFilter(3))
    out=rgba.copy(); out[:,:,3]=np.minimum(out[:,:,3],np.array(mask))
    part=Image.fromarray(out).crop(box); part.save(a/f'miyako_{key}.png')
    extraction[key]={'box':box,'size':part.size}
size=Image.open(a/'miyako_head_open_full.png').size
for state in ['open','closed']:
    Image.open(a/f'miyako_head_{state}_full.png').resize(size,Image.Resampling.LANCZOS).save(a/f'miyako_head_{state}.png')
for side in ['l','r']:shutil.copy2(a/f'miyako_ear_spare_{side}.png',a/f'miyako_ear_{side}.png')
rig={'revision':6,'head':[31,30,178,139], 'ears':[[-16,58,54,64],[140,58,54,64]], 'earsFront':False, 'earOrigins':['80% 20%','20% 20%'],
     'layers':[['tail',163,172,54,50],['body',64,157,113,87],['prop',52,184,138,49],['arm_l',57,175,37,34],['arm_r',149,175,37,34]],'baseline':239}
rigs=json.loads((a/'rigs.json').read_text());rigs['miyako']=rig
(a/'rigs.json').write_text(json.dumps(rigs,indent=2))
(a/'miyako_extraction.json').write_text(json.dumps(extraction,indent=2))
canvas=Image.new('RGBA',(240,280))
def part(key,w,h):return Image.open(a/f'miyako_{key}.png').convert('RGBA').resize((w,h),Image.Resampling.LANCZOS)
for key,x,y,w,h in rig['layers'][:2]:canvas.alpha_composite(part(key,w,h),(x,y))
x,y,w,h=rig['head']
for key,box in zip(['ear_l','ear_r'],rig['ears']):
    ex,ey,ew,eh=box;canvas.alpha_composite(part(key,ew,eh),(x+ex,y+ey))
canvas.alpha_composite(part('head_open',w,h),(x,y))
for key,x,y,w,h in rig['layers'][2:]:canvas.alpha_composite(part(key,w,h),(x,y))
canvas.save(a/'miyako_assembled_preview.png')
print('Updated Miyako only; source alpha:',im.getchannel('A').getextrema())
print('Parts:',{k:v['size'] for k,v in extraction.items()})
