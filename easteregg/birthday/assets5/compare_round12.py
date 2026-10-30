from pathlib import Path
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parent.parent;p=root/'qa'/'shots12'
reference=Image.open(root/'refs7'/'miyako_crop.png').convert('RGB').crop((90,140,695,477))
panels=[('Official reference / supplied crop',reference),('Chrome v9 / closed eyes',Image.open(p/'miyako_closed.png').convert('RGB')),('Chrome v9 / open eyes (interpretation)',Image.open(p/'miyako_open.png').convert('RGB'))]
out=Image.new('RGB',(1800,420),'#eeeaf2');draw=ImageDraw.Draw(out)
for i,(title,im) in enumerate(panels):
 im.thumbnail((580,365));x=i*600+(600-im.width)//2
 out.paste(im,(x,35));draw.text((i*600+12,10),title,fill='#34303c')
out.save(p/'reference_comparison.png')
