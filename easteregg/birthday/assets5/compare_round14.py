from pathlib import Path
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parent.parent;p=root/'qa'/'shots14'
ref=Image.open(root/'assets5'/'maru_dot_ref.png').convert('RGBA').crop((0,16,200,191))
ref=ref.resize((600,525),Image.Resampling.NEAREST)
paper=Image.new('RGBA',ref.size,'#eeeaf2');paper.alpha_composite(ref)
panels=[('Provided dot / design authority',paper.convert('RGB')),('Chrome v11 / open eyes',Image.open(p/'maru_t0.png').convert('RGB')),('Chrome v11 / smiling closed eyes',Image.open(p/'maru_closed.png').convert('RGB'))]
out=Image.new('RGB',(1920,620),'#eeeaf2');draw=ImageDraw.Draw(out)
for i,(title,im) in enumerate(panels):
 im.thumbnail((610,565));out.paste(im,(640*i+(640-im.width)//2,35));draw.text((640*i+12,10),title,fill='#34303c')
out.save(p/'reference_comparison.png')
cycle=Image.new('RGB',(1000,1000),'#eeeaf2');draw=ImageDraw.Draw(cycle)
for i in range(4):
 im=Image.open(p/f'maru_t{i}.png').convert('RGB');im.thumbnail((490,460))
 x=(i%2)*500;y=(i//2)*500;cycle.paste(im,(x+(500-im.width)//2,y+25));draw.text((x+12,y+7),f't{i} / {i*1750} ms',fill='#34303c')
cycle.save(p/'maru_cycle.png')
