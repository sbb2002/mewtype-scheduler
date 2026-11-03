from pathlib import Path
p=Path(__file__).with_name('bdayscene-yuno.js');s=p.read_text(encoding='utf8')
s=s.replace(" const bandGradient=w.createLinearGradient(0,0,0,1);", " const bandStops=[];")
s=s.replace('bandGradient.addColorStop(f,`rgba(${col.map(Math.round)},${al})`)', 'bandStops.push([f,`rgba(${col.map(Math.round)},${al})`])')
s=s.replace('const y=395+365*u**2.5,width=7+76*u**1.5,bulge=46*Math.min(1,u*1.1);','const y=395+365*u**2.5,width=7+76*u**1.5,bulge=46*Math.min(1,u*1.1);\n  const bandGradient=w.createLinearGradient(0,0,0,width*2);for(const [stop,color] of bandStops)bandGradient.addColorStop(stop,color);')
s=s.replace('w.translate(0,y0);w.scale(1,y1-y0);','w.translate(0,y0);')
s=s.replace('(Math.max(395,y0)-y0)/(y1-y0),10,(Math.min(groundBottom,y1)-Math.max(395,y0))/(y1-y0)', 'Math.max(395,y0)-y0,10,Math.min(groundBottom,y1)-Math.max(395,y0)')
p.write_text(s,encoding='utf8',newline='\n')
