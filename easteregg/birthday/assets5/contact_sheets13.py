from pathlib import Path
from PIL import Image,ImageDraw
p=Path(__file__).resolve().parent.parent/'qa'/'shots13'
out=Image.new('RGB',(800,850),'#eeeaf2');draw=ImageDraw.Draw(out)
for i in range(4):
 im=Image.open(p/f'mallard_t{i}.png').convert('RGB');im.thumbnail((390,390))
 x=(i%2)*400;y=(i//2)*425
 out.paste(im,(x+(400-im.width)//2,y+25));draw.text((x+10,y+7),f't{i} / {i*2250} ms',fill='#333')
out.save(p/'mallard_cycle.png')
