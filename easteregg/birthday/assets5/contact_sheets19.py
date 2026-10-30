from pathlib import Path
from PIL import Image,ImageDraw
import json
p=Path(__file__).resolve().parent.parent/'qa'/'shots19'
sheet=Image.new('RGB',(1800,1080),'#181327');d=ImageDraw.Draw(sheet)
for i in range(12):
 im=Image.open(p/f'eq_t{i}.png').convert('RGB');im.thumbnail((890,140))
 x=i%2*900;y=i//2*180
 sheet.paste(im,(x,y+25));d.text((x+8,y+5),f'{.108+i*.2:.3f}s',fill='white')
sheet.save(p/'spectrum_sheet.png')
