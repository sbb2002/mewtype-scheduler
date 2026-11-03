from pathlib import Path
p=Path(__file__).with_name('bdayscene-yuno.js');s=p.read_text(encoding='utf8')
s=s.replace('w.createLinearGradient(0,0,0,width*2)','w.createLinearGradient(0,y-width,0,y+width)')
s=s.replace('w.translate(0,y0);w.fillStyle=bandGradient;', 'w.translate(0,yc-y);w.fillStyle=bandGradient;')
s=s.replace('w.fillRect(x,Math.max(395,y0)-y0,10,','w.fillRect(x,Math.max(395,y0)-(yc-y),10,')
p.write_text(s,encoding='utf8',newline='\n')
