"""Extract large alpha-connected components from generated 3x3 atlases."""
from pathlib import Path
from PIL import Image, ImageFilter
from scipy import ndimage
import numpy as np
import json

assets=Path(__file__).resolve().parent
keys=['head_open_full','head_closed_full','body','ear_spare_l','ear_spare_r','tail','arm_l','arm_r','prop']
for name in ['yuno','ritsu','miyako','nonoka','maru','duck']:
    im=Image.open(assets / f'{name}_atlas.png').convert('RGBA')
    arr=np.array(im); labels,n=ndimage.label(arr[:,:,3]>48); blobs=[]
    for idx,sl in enumerate(ndimage.find_objects(labels),1):
        if sl is None: continue
        size=int((labels[sl]==idx).sum())
        if size<1000: continue
        box=(int(sl[1].start),int(sl[0].start),int(sl[1].stop),int(sl[0].stop))
        cy=(box[1]+box[3])/2
        row=int(np.argmin(np.abs(np.array([.28,.58,.85])*im.height-cy))) if name=='miyako' else int(cy/(im.height/3))
        blobs.append((row,int((box[0]+box[2])/2/(im.width/3)),idx,box))
    blobs.sort(); assert len(blobs)==9,(name,len(blobs))
    manifest={}
    for key,(_,_,idx,box) in zip(keys,blobs):
        mask=Image.fromarray(np.uint8(labels==idx)*255).filter(ImageFilter.MaxFilter(3))
        out=arr.copy(); out[:,:,3]=np.minimum(arr[:,:,3],np.array(mask))
        part=Image.fromarray(out).crop(box); part.save(assets / f'{name}_{key}.png')
        manifest[key]={'box':box,'size':part.size}
    (assets / f'{name}_extraction.json').write_text(json.dumps(manifest,indent=2))
print('Extracted generated alpha components, retaining original RGBA pixels')
