from pathlib import Path
from PIL import Image,ImageDraw
import json
p=Path(__file__).resolve().parent.parent/'qa'/'shots18'
r=json.loads((p.parent.parent/'assets5'/'validation_v15.json').read_text(encoding='utf-8'))
sheet=Image.new('RGB',(1600,1840),'#eeeaf2')
for i,q in enumerate(r['frames']):
 im=Image.open(p/f'yuno_t{i}.png').convert('RGB');im.thumbnail((390,410))
 x=i%4*400;y=i//4*460;sheet.paste(im,(x+(400-im.width)//2,y+25))
 d=ImageDraw.Draw(sheet);d.text((x+6,y+5),f'{q["seconds"]:.3f}s / beat {q["beat"]}',fill='#34303c')
 d.text((x+6,y+438),f'L {q["left"]:+.1f} / R {q["right"]:+.1f} / headY {q["headY"]:.2f}',fill='#34303c')
sheet.save(p/'two_bar_sheet.png')
