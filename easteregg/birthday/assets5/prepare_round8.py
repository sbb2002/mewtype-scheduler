"""Extract generated complete arms; similarity-map shoulder/paw landmarks to rig contacts."""
from pathlib import Path
from PIL import Image
import json, numpy as np

p=Path(__file__).resolve().parent
r=json.loads((p/'rigs_v4_preserved.json').read_text())
# source normalized shoulder/paw, target shoulder/paw in the 240x280 rig.
spec={
 'ritsu': [((.25,.14),(.84,.87),(82,172),(103,201)), ((.79,.14),(.15,.52),(157,174),(126,184))],
 'nonoka': [((.26,.16),(.85,.88),(80,187),(102,219)), ((.78,.17),(.15,.68),(158,189),(130,198))],
 'yuno': [((.82,.12),(.28,.88),(86,164),(61,202)), ((.27,.12),(.48,.9),(153,164),(123,202))]
}
for n,arms in spec.items():
 im=Image.open(p/f'{n}_arms8_generated.png').convert('RGBA')
 r[n]['layers']=[v for v in r[n]['layers'] if not v[0].startswith('arm')]
 r[n]['shoulders']={}
 for i,(a,b,A,B) in enumerate(arms):
  if n in ['ritsu','nonoka']:
   center=np.array([120,200 if n=='ritsu' else 214]);angle=np.deg2rad(22)
   rotation=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
   B=tuple(center+rotation@(np.array(B)-center))
  half=im.crop((i*im.width//2,0,(i+1)*im.width//2,im.height))
  bbox=half.getchannel('A').point(lambda v:255 if v>32 else 0).getbbox()
  part=half.crop(bbox)
  a=np.array(a)*part.size;b=np.array(b)*part.size;A=np.array(A);B=np.array(B)
  v=b-a;w=B-A;u=(w[0]*v[0]+w[1]*v[1])/np.dot(v,v);z=(w[1]*v[0]-w[0]*v[1])/np.dot(v,v)
  matrix=np.array([[u,-z],[z,u]]);offset=A-matrix@a;inv=np.linalg.inv(matrix);off=-inv@offset
  # Four-times supersampling keeps the generated thin outlines crisp.
  out=part.transform((960,1120),Image.Transform.AFFINE,tuple(np.column_stack((inv/4,off)).ravel()),Image.Resampling.BICUBIC)
  box=out.getchannel('A').point(lambda v:255 if v>16 else 0).getbbox()
  x0,y0,x1,y1=[v/4 for v in box];x=int(x0);y=int(y0);width=int(np.ceil(x1))-x;height=int(np.ceil(y1))-y
  out=out.crop((x*4,y*4,(x+width)*4,(y+height)*4))
  key='arm8_'+('l' if i==0 else 'r');out.save(p/f'{n}_{key}.png')
  r[n]['layers'].append([key,x,y,width,height]);r[n]['shoulders'][key]=[int(A[0])-x,int(A[1])-y]
# The generated integrated paws already connect to the torso; remove duplicate patch overlays.
r['miyako']['layers']=[v for v in r['miyako']['layers'] if not v[0].startswith('paw7')]
(p/'rigs.json').write_text(json.dumps(r,indent=2))
(p/'round8_contacts.json').write_text(json.dumps(spec,indent=2))
