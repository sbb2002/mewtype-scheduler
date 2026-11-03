from pathlib import Path
p=Path(__file__).with_name('bdayscene-yuno.js');s=p.read_text(encoding='utf8')
s=s.replace("cv.width=1200;cv.height=h;const ctx=cv.getContext('2d');ctx.beginPath();ctx.rect(0,395,1200,h-395);ctx.clip()", "cv.width=1200;cv.height=h")
p.write_text(s,encoding='utf8',newline='\n')
