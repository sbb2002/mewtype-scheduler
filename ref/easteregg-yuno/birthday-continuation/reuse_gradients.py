from pathlib import Path
p=Path(__file__).with_name('bdayscene-yuno.js');s=p.read_text(encoding='utf8')
start=s.index('// 오로라의 작은 그라데이션들은')
end=s.index('function drawAurora(c,t,a,b){',start)
s=s[:start]+"const auroraGradients=new WeakMap();\nfunction skyAurora(c,t,a,b){"+s[end+len('function drawAurora(c,t,a,b){'):]
s=s.replace('auroraLayer.width=auroraLayer.height=0;','')
s=s.replace(" const fade=djEase15((t-a)/2.2)*djEase15((b-t)/2.2);if(fade<=0)return;", """ const fade=djEase15((t-a)/2.2)*djEase15((b-t)/2.2);if(fade<=0)return;
 // 정규화된 그라데이션 두 개를 좌표 변환으로 재사용한다. 색·곡선·시각은 정본 그대로다.
 if(!auroraGradients.has(c))auroraGradients.set(c,[false,true].map(middle=>{const g=c.createLinearGradient(0,0,0,1);g.addColorStop(0,'#7844ba00');g.addColorStop(.32,'#7844ba40');g.addColorStop(.7,middle?'#33edc2a0':'#50e897a0');g.addColorStop(.94,middle?'#8ae3e2':'#68ffa7');g.addColorStop(1,'#ff488d00');return g}));
 const gradients=auroraGradients.get(c);""")
s=s.replace("   const g=c.createLinearGradient(x,y-height,x,y+5);g.addColorStop(0,'#7844ba00');g.addColorStop(.32,'#7844ba40');g.addColorStop(.7,j===1?'#33edc2a0':'#50e897a0');g.addColorStop(.94,j===1?'#8ae3e2':'#68ffa7');g.addColorStop(1,'#ff488d00');c.fillStyle=g;c.fillRect(x,y-height,2,height+5);", "   c.save();c.translate(x,y-height);c.scale(1,height+5);c.fillStyle=gradients[j===1?1:0];c.fillRect(0,0,2,1);c.restore();")
needle=" // 발광 띠(Grid Current): 6.8초에 걸쳐 앞으로 다가오는 그라데이션 띠."
s=s.replace(needle,""" // 열마다 같은 색 정지점을 다시 만들지 않고 한 프레임의 띠 그라데이션을 공유한다.
 const bandGradient=w.createLinearGradient(0,0,0,1);
 for(let k=0;k<=8;k++){const f=k/8,d=2*f-1,al=(1-d*d)**2*beat*.72,col=f<.5?[120+(255-120)*f*2,68+4*f*2,186-45*f*2]:[255-117*(f-.5)*2,72+155*(f-.5)*2,141+85*(f-.5)*2];bandGradient.addColorStop(f,`rgba(${col.map(Math.round)},${al})`)}
"""+needle)
old="""   const gr=w.createLinearGradient(0,y0,0,y1);
   for(let k=0;k<=8;k++){const f=k/8,d=2*f-1,al=(1-d*d)**2*beat*.72,col=f<.5?[120+(255-120)*f*2,68+4*f*2,186-45*f*2]:[255-117*(f-.5)*2,72+155*(f-.5)*2,141+85*(f-.5)*2];gr.addColorStop(f,`rgba(${col.map(Math.round)},${al})`)}
   w.fillStyle=gr;w.fillRect(x,Math.max(395,y0),10,Math.min(groundBottom,y1)-Math.max(395,y0));"""
new="""   w.save();w.translate(0,y0);w.scale(1,y1-y0);w.fillStyle=bandGradient;
   w.fillRect(x,(Math.max(395,y0)-y0)/(y1-y0),10,(Math.min(groundBottom,y1)-Math.max(395,y0))/(y1-y0));w.restore();"""
assert old in s
s=s.replace(old,new)
p.write_text(s,encoding='utf8',newline='\n')
