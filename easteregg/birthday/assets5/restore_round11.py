"""Restore the operator-specified original cutouts verbatim; change rig transforms only."""
from pathlib import Path
import copy,hashlib,json,math,shutil

p=Path(__file__).resolve().parent;root=p.parent
source=Path('C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/devpapers/ref/birthday-easteregg-handoff/birthday/assets5')
prior=json.loads((p/'rigs_v7.json').read_text())
original=json.loads((source/'rigs.json').read_text())
preserved=p/'round11_preserved.json'
if not preserved.exists():
 files=[f'birthday_bg_v{i}.html' for i in range(2,8)]+['assets5/rigs.json','assets5/rigs_v7.json','assets5/round7.css','assets5/round8.css']
 preserved.write_text(json.dumps({f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in files},indent=2))
r=copy.deepcopy(prior);proof={};contacts={}
# Local shoulder / local paw center are fractions of the untouched original image.
spec={
 'ritsu': [('arm_l',(106,196),(32,28),(.78,.14),(.25,.74),-90),('arm_r',(131,188.5),(32,28),(.16,.14),(.76,.73),110)],
 'nonoka': [('arm_l',(104,212),(36,36),(.68,.12),(.29,.72),-75),('arm_r',(137,206.5),(32,34),(.34,.12),(.72,.74),110)]
}
for name,arms in spec.items():
 r[name]=copy.deepcopy(original[name]);r[name]['shoulders']={};contacts[name]={}
 for key,center,size,a,b,angle in arms:
  for ext in ['png','webp']:
   filename=f'{name}_{key}.{ext}';dest=p/filename;backup=p/f'{name}_{key}_pre_r11.{ext}'
   if dest.exists() and not backup.exists():shutil.copy2(dest,backup)
   shutil.copy2(source/filename,dest)
   assert dest.read_bytes()==(source/filename).read_bytes()
   proof[filename]=hashlib.sha256(dest.read_bytes()).hexdigest()
  w,h=size;pivot=[a[0]*w,a[1]*h];delta=[(b[0]-a[0])*w,(b[1]-a[1])*h]
  theta=math.radians(angle);v=[math.cos(theta)*delta[0]-math.sin(theta)*delta[1],math.sin(theta)*delta[0]+math.cos(theta)*delta[1]]
  shoulder=[center[i]-v[i] for i in range(2)]
  layer=next(layer for layer in r[name]['layers'] if layer[0]==key)
  layer[1:]=[round(shoulder[0]-pivot[0],4),round(shoulder[1]-pivot[1],4),w,h]
  r[name]['shoulders'][key]=pivot
  contacts[name][key]={'center':list(center),'shoulder':shoulder,'size':list(size),'restRotation':angle}
 # Original body/tail then guitar, with both untouched gripping cutouts in front.
 assert [v[0] for v in r[name]['layers']][-3:]==['prop','arm_l','arm_r']
(p/'rigs_v8.json').write_text(json.dumps(r,indent=2))
(p/'round11_contacts.json').write_text(json.dumps(contacts,indent=2))
(p/'round11_original_hashes.json').write_text(json.dumps({'source':str(source),'files':proof,'originalRigs':{n:original[n] for n in spec}},indent=2))
