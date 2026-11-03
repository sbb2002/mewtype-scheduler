from pathlib import Path
p=Path(__file__).with_name('bdayscene-yuno.js');s=p.read_text(encoding='utf8')
s=s.replace('function skyAurora(c,t,a,b){', '''// 오로라의 작은 그라데이션들은 CPU 레이어에서 모아 한 번만 업로드한다.
const auroraLayer=document.createElement('canvas');
function skyAurora(c,t,a,b){
 const m=c.getTransform(),w=c.canvas.width,h=Math.min(c.canvas.height,Math.max(1,Math.ceil(240*m.d+m.f)));
 if(auroraLayer.width!==w||auroraLayer.height!==h){auroraLayer.width=w;auroraLayer.height=h}
 const ac=auroraLayer.getContext('2d',{willReadFrequently:true});ac.setTransform(1,0,0,1,0,0);ac.clearRect(0,0,w,h);ac.setTransform(m);
 drawAurora(ac,t,a,b);c.save();c.setTransform(1,0,0,1,0,0);c.drawImage(auroraLayer,0,0);c.restore();
}
function drawAurora(c,t,a,b){''')
s=s.replace('canvas.remove();spotLayer.width', 'canvas.remove();auroraLayer.width=auroraLayer.height=0;spotLayer.width')
p.write_text(s,encoding='utf8',newline='\n')
