"""Composite generated rounded paws only; retain original sleeve pixels and rig bounds."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageChops
import json,numpy as np

p=Path(__file__).resolve().parent
atlas=Image.open(p/'yuno_paws9_generated.png').convert('RGBA')
spec=[('l',[(0,150),(35,150),(50,153),(64,159),(77,168),(86,180),(90,192),(172,193),(172,212),(0,212)],(2,155,88,207)),
      ('r',[(0,133),(28,131),(44,137),(58,154),(63,176),(61,208),(0,208)],(1,137,62,204))]
report={}
for i,(side,points,box) in enumerate(spec):
 original=Image.open(p/f'yuno_arm8_{side}.png').convert('RGBA')
 part=atlas.crop((atlas.width*i//2,0,atlas.width*(i+1)//2,atlas.height))
 part=part.crop(part.getchannel('A').point(lambda a:255 if a>32 else 0).getbbox())
 part.save(p/f'yuno_paw9_{side}.png')
 mask=Image.new('L',original.size);ImageDraw.Draw(mask).polygon(points,fill=255)
 arr=np.array(original);m=np.array(mask)
 cuff=(arr[:,:,3]>128)&(arr[:,:,0]>140)&(arr[:,:,1]<90)&(arr[:,:,2]>60)
 m[cuff]=0;mask=Image.fromarray(m)
 sleeve=original.copy();sleeve.putalpha(ImageChops.subtract(original.getchannel('A'),mask))
 new=Image.new('RGBA',original.size)
 x,y,x1,y1=box;new.alpha_composite(part.resize((x1-x,y1-y),Image.Resampling.LANCZOS),(x,y))
 new.alpha_composite(sleeve)
 result=np.array(new);result[m==0]=arr[m==0];new=Image.fromarray(result)
 new.save(p/f'yuno_arm8_{side}_round9.png')
 changed=np.any(np.array(new)!=arr,axis=2)
 report[side]={'sameSize':new.size==original.size,'changedBounds':Image.fromarray(changed.astype('uint8')*255).getbbox(),'outsidePawMaskUnchanged':bool(np.all(result[m==0]==arr[m==0])),'redCuffUnchanged':bool(np.all(result[cuff]==arr[cuff]))}
(p/'round9_pixel_scope.json').write_text(json.dumps(report,indent=2))
