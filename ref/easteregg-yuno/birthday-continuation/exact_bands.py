from pathlib import Path
p=Path(__file__).with_name('bdayscene-yuno.js');s=p.read_text(encoding='utf8')
s=s.replace('  const bandGradient=w.createLinearGradient(0,y-width,0,y+width);for(const [stop,color] of bandStops)bandGradient.addColorStop(stop,color);\n','')
s=s.replace('   w.save();w.translate(0,yc-y);w.fillStyle=bandGradient;\n   w.fillRect(x,Math.max(395,y0)-(yc-y),10,Math.min(groundBottom,y1)-Math.max(395,y0));w.restore();', '   const bandGradient=w.createLinearGradient(0,y0,0,y1);for(const [stop,color] of bandStops)bandGradient.addColorStop(stop,color);\n   w.fillStyle=bandGradient;w.fillRect(x,Math.max(395,y0),10,Math.min(groundBottom,y1)-Math.max(395,y0));')
p.write_text(s,encoding='utf8',newline='\n')
