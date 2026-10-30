from pathlib import Path
from PIL import Image,ImageDraw,ImageChops
import json
p=Path('assets5');r=json.loads((p/'rigs.json').read_text())
for n in ['miyako','maru']:
 im=Image.open(p/f'{n}_generated7.png').convert('RGBA');box=im.getchannel('A').point(lambda a:255 if a>32 else 0).getbbox()
 im.crop(box).save(p/f'{n}_sprite7.png')
 if n=='miyako':
  masks=[]
  for key,points in [('wing7_l',[(274,808),(303,775),(363,745),(431,737),(422,803),(410,848),(377,880),(335,866),(302,851)]),('wing7_r',[(821,750),(875,744),(940,779),(979,814),(954,848),(906,884),(846,872),(822,825)])]:
   mask=Image.new('L',im.size);ImageDraw.Draw(mask).polygon(points,fill=255)
   part=im.copy();part.putalpha(ImageChops.multiply(im.getchannel('A'),mask));part.crop(box).save(p/f'{n}_{key}.png');masks.append(mask)
  main=im.copy();main.putalpha(ImageChops.subtract(im.getchannel('A'),ImageChops.lighter(*masks)));main.crop(box).save(p/f'{n}_sprite7.png')
  # Paw patches overlap their original contact shadows, preserving keyboard continuity.
  for key,b in [('paw7_l',(409,800,561,922)),('paw7_r',(651,800,830,923))]:
   part=Image.new('RGBA',im.size);part.paste(im.crop(b),b[:2]);part.crop(box).save(p/f'{n}_{key}.png')
  r[n]['layers']=[['wing7_l',9,14,222,230],['wing7_r',9,14,222,230],['sprite7',9,14,222,230],['paw7_l',9,14,222,230],['paw7_r',9,14,222,230]]
for n in ['miyako','maru']:
 im=Image.open(p/f'{n}_sprite7.png');w=222 if n=='miyako' else 214;h=round(w*im.height/im.width)
 for layer in r[n]['layers']:layer[1:]=[(240-w)//2,243-h,w,h]
(p/'rigs.json').write_text(json.dumps(r,indent=2))
