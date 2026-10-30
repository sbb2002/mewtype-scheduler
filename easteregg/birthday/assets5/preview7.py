from PIL import Image
import json
from pathlib import Path
p=Path('assets5');r=json.loads((p/'rigs.json').read_text());out=Image.new('RGBA',(960,280),'#eeeaf3')
for i,n in enumerate(['arale','yuno','ritsu','nonoka']):
 rig=r[n]; c=Image.new('RGBA',(240,280))
 def paste(key,b,im=c):
  src=Image.open(p/f'{n}_{key}.png').convert('RGBA').resize(tuple(b[2:]));im.alpha_composite(src,tuple(b[:2]))
 for key,*b in rig['layers']:
  if key in ['body','tail']:paste(key,b)
 x,y,w,h=rig['head'];head=Image.new('RGBA',(240,280))
 for key,b in zip(['ear_l','ear_r'],rig.get('ears',[[0,0,w,h]]*2)):paste(key,[x+b[0],y+b[1],*b[2:]],head)
 paste('head_open',[x,y,w,h],head);c.alpha_composite(head)
 for key,*b in rig['layers']:
  if key not in ['body','tail']:paste(key,b)
 out.alpha_composite(c,(i*240,0))
out.save('qa/round7-hands.png')
