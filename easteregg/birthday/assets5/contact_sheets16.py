from pathlib import Path
from PIL import Image,ImageDraw
import json

root=Path(__file__).resolve().parent.parent;p=root/'qa'/'shots16'
report=json.loads((root/'assets5'/'validation_v13.json').read_text(encoding='utf-8'))
sheet=Image.new('RGB',(2000,920),'#eeeaf2');hands=Image.new('RGB',(2200,440),'#eeeaf2')
for i,q in enumerate(report['frames']):
 im=Image.open(p/f'yuno_t{i}.png').convert('RGB')
 small=im.copy();small.thumbnail((390,410));x=(i%5)*400;y=(i//5)*460
 sheet.paste(small,(x+(400-small.width)//2,y+25));draw=ImageDraw.Draw(sheet)
 draw.text((x+8,y+7),f'{q["seconds"]*1000:g} ms / beat {q["beat"]} / {q["mode"]}',fill='#34303c')
 draw.text((x+8,y+438),f'L {q["left"]:+.1f} deg / record {q["leftRecord"]:+.1f} deg',fill='#34303c')
 close=im.crop((35,560,895,810));close.thumbnail((430,165));hx=(i%5)*440;hy=(i//5)*220
 hands.paste(close,(hx+(440-close.width)//2,hy+25));hd=ImageDraw.Draw(hands)
 hd.text((hx+8,hy+7),f'{q["seconds"]*1000:g} ms / {q["mode"]}',fill='#34303c')
 hd.text((hx+8,hy+195),f'L {q["left"]:+.1f} / R {q["right"]:+.1f} deg',fill='#34303c')
sheet.save(p/'bar_contact_sheet.png');hands.save(p/'hands_contact_sheet.png')
