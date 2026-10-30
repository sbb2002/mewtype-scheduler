from pathlib import Path
from PIL import Image,ImageDraw
p=Path(__file__).resolve().parent.parent/'qa'/'shots10'
for name,period,box in [('ritsu',2600,(230,585,675,880)),('nonoka',600,(205,550,610,790))]:
 out=Image.new('RGB',(1200,850),'#eeeaf2');draw=ImageDraw.Draw(out)
 for i in range(4):
  im=Image.open(p/f'{name}_t{i}.png').convert('RGB').crop(box);im.thumbnail((590,390))
  x=(i%2)*600;y=(i//2)*425
  out.paste(im,(x+(600-im.width)//2,y+25));draw.text((x+12,y+6),f'{name} / t{i} / {i*period//4} ms',fill='#333')
 out.save(p/f'{name}_cycle.png')
