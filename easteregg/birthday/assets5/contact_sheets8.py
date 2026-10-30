from pathlib import Path
from PIL import Image,ImageDraw
p=Path('qa/shots8')
for name in ['arale','yuno','ritsu','nonoka','miyako','maru','duck']:
 sheet=Image.new('RGB',(1600,480),'#ebe7ee')
 for i in range(4):
  im=Image.open(p/f'{name}_t{i}.png').convert('RGB');im.thumbnail((400,450));sheet.paste(im,(400*i+(400-im.width)//2,25));ImageDraw.Draw(sheet).text((400*i+10,7),f'{name} / t{i}',fill='#333333')
 sheet.save(p/f'{name}_cycle.jpg',quality=94)
