from pathlib import Path
p=Path(__file__).with_name('bdayscene-yuno.js');s=p.read_text(encoding='utf8')
s=s.replace("getContext('2d',{willReadFrequently:true})","getContext('2d')")
s=s.replace("cv.width=1200;cv.height=h}return cv", "cv.width=1200;cv.height=h;const ctx=cv.getContext('2d');ctx.beginPath();ctx.rect(0,395,1200,h-395);ctx.clip()}return cv")
p.write_text(s,encoding='utf8',newline='\n')
