"""Replace only distal paws using generated pixels; retain proximal arms and shoulder anchors."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops
import numpy as np,json
from scipy.ndimage import map_coordinates

p=Path(__file__).resolve().parent
r=json.loads((p/'rigs_v6_preserved.json').read_text())
# Viewer-left is the anatomical right/strumming arm. Coordinates are in the rig.
spec={
 'ritsu': [([(96,82),(144,82),(144,128),(91,128),(89,103)],(106,196),(15,12)),
           ([(0,45),(36,45),(51,62),(54,94),(42,112),(0,112)],(139,186),(13,15))],
 'nonoka': [([(103,103),(148,103),(148,140),(102,140),(98,122)],(104,212),(15,12)),
            ([(0,55),(28,55),(40,69),(43,95),(34,112),(0,112)],(141,202),(12,13))]
}
report={};contacts={}
old_centers={'ritsu':[(100,191),(131,189)],'nonoka':[(99,211),(133,204)]}
for n,arms in spec.items():
 atlas=Image.open(p/f'{n}_paws10_generated.png').convert('RGBA');contacts[n]={}
 for i,(points,contact,sz) in enumerate(arms):
  key='arm8_'+('l' if i==0 else 'r');layer=next(v for v in r[n]['layers'] if v[0]==key)
  _,x,y,w,h=layer;source=Image.open(p/f'{n}_{key}.png').convert('RGBA')
  mask=Image.new('L',source.size);ImageDraw.Draw(mask).polygon(points,fill=255)
  rest=source.copy();rest.putalpha(ImageChops.subtract(source.getchannel('A'),mask))
  part=atlas.crop((i*atlas.width//2,0,(i+1)*atlas.width//2,atlas.height))
  part=part.crop(part.getchannel('A').point(lambda a:255 if a>32 else 0).getbbox())
  part.save(p/(f'{n}_paw10_'+('l' if i==0 else 'r')+'.png'))
  shoulder=np.array(r[n]['shoulders'][key])+[x,y]
  # Move the distal forearm continuously with its new paw. The shoulder and upper
  # 35% of the arm remain at their exact original pixels; no new arm is drawn.
  old=np.array(old_centers[n][i],dtype=float);delta=np.array(contact)-old;axis=old-shoulder
  if i==1:delta[:]=0  # The rounded fretting paw overlaps the unchanged existing wrist.
  yy,xx=np.mgrid[:1120,:960].astype('float32');sx=xx.copy();sy=yy.copy()
  def weight(px,py):
   t=((px/4-shoulder[0])*axis[0]+(py/4-shoulder[1])*axis[1])/np.dot(axis,axis)
   a=np.clip((t-.35)/.65,0,1)
   return a*a*(3-2*a)
  for _ in range(8):
   q=weight(sx,sy);sx=xx-4*delta[0]*q;sy=yy-4*delta[1]*q
  full=Image.new('RGBA',(960,1120));full.alpha_composite(rest,(x*4,y*4))
  original_full=np.array(full);warped=np.empty_like(original_full)
  for channel in range(4):warped[:,:,channel]=map_coordinates(original_full[:,:,channel],[sy,sx],order=1,mode='constant',cval=0)
  proximal=weight(xx,yy)==0;warped[proximal]=original_full[proximal]
  canvas=Image.new('RGBA',(960,1120));pw,ph=sz;cx,cy=contact
  canvas.alpha_composite(Image.fromarray(warped))
  canvas.alpha_composite(part.resize((pw*4,ph*4),Image.Resampling.LANCZOS),(round((cx-pw/2)*4),round((cy-ph/2)*4)))
  box=canvas.getchannel('A').point(lambda a:255 if a>16 else 0).getbbox()
  nx,ny=box[0]//4,box[1]//4;nw=(box[2]+3)//4-nx;nh=(box[3]+3)//4-ny
  canvas.crop((nx*4,ny*4,(nx+nw)*4,(ny+nh)*4)).save(p/f'{n}_{key}_round10.png')
  layer[1:]=[nx,ny,nw,nh];r[n]['shoulders'][key]=[int(shoulder[0])-nx,int(shoulder[1])-ny]
  contacts[n][key]={'shoulder':shoulder.tolist(),'center':list(contact),'size':list(sz)}
  report[n+'/'+key]={'proximalArmPixelsUnchanged':bool(np.all(warped[proximal]==original_full[proximal])),'distalShift':delta.tolist(),'shoulder':shoulder.tolist(),'oldBox':[x,y,w,h],'newBox':layer[1:]}
(p/'rigs_v7.json').write_text(json.dumps(r,indent=2))
(p/'round10_contacts.json').write_text(json.dumps(contacts,indent=2))
(p/'round10_pixel_scope.json').write_text(json.dumps(report,indent=2))
